"""
Bollinger Band-Bottom Detection Strategy — AI_Portfolios.xlsx
=============================================================
Mirror of bollinger_top_strategy.py for the LOWER band: detects stocks
approaching / tagging the lower Bollinger Band (20, 2σ) and classifies
whether the tag is a WALK-DOWN continuation (avoid) or a BOTTOM
(buy signal), emitting explicit BUY / BOTTOM-WATCH verdicts.

Key asymmetry vs the top playbook: "oversold can stay oversold" — in a
downtrend a lower-band tag is NOT a buy; bottoms need one extra
confirmation step (reversal bar, W-bottom, or midline reclaim).

Rules encoded (the "band-bottom playbook"):

  B1  BAND REGIME      — expanding bands on the decline → walk-down
                         likely (don't catch the knife); flat/contracting
                         bands → lower band acts as a floor
  B2  CAPITULATION     — flush into/through the band on RVOL ≥ 1.5 is a
                         washout ingredient; low-volume drift (RVOL<0.8)
                         at the band = numb decline, no bottom
  B3  REVERSAL BAR     — hammer (lower wick ≥ 2× body, close upper half)
                         or bullish engulfing at/below the band, with
                         volume → the confirmation capitulation needs
  B4  RSI GATE         — RSI ≤ 30 at the band = stretched (bounce at
                         least); bullish divergence (price LL, RSI HL)
                         = strongest bottom tell — but only trust it if
                         OBV is not still bleeding out
  B5  MACD HISTOGRAM   — negative histogram shrinking 3 bars = seller
                         exhaustion; still expanding = don't touch
  B6  BEAR SQUEEZE     — squeeze (bw ≤ p15) near the lower band usually
                         resolves DOWN → warning, never a buy
  B7  MIDLINE RECLAIM  — a lower-band walker's first close back above
                         MA20 is THE recovery/buy signal (not the tag);
                         MA10 reclaim = early notice
  B8  W-BOTTOM         — second low ≈/below first low (10–40 bars apart)
                         but with clearly higher %B (second low doesn't
                         reach the band) = quantified seller exhaustion;
                         Bollinger's classic W-type buy structure
  B9  ABOUT-TO-HIT     — distance to lower band ≤ 1 ATR = one ordinary
                         down-day tags it; classify expected outcome now
  B10 TREND FILTER     — above MA200 with flat bands → band tag may be
                         bought as mean-reversion; below MA200 → only a
                         midline reclaim counts, no exceptions

Verdicts per stock:
  BUY / ACCUMULATE     — bottom score ≥ 5 (capitulation+reversal,
                         confirmed W-bottom, or midline reclaim stacks)
  BOTTOM-WATCH         — ingredients present (divergence, RSI≤30,
                         histogram shrinking) but no confirmation yet
  MEAN-REVERT BUY      — above MA200, flat bands, deep %B, RSI ≤ 32
  WALK-DOWN / AVOID    — expanding bands / numb drift at the band
  BEAR-SQUEEZE WARNING — squeeze coiling at the lower band (downside)
  NEUTRAL              — not near the lower band, no signal

Output: bollinger_bottom_YYYY-MM-DD.md + console summary.
Disclaimer: algorithmic technical analysis only — not financial advice.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
import warnings

warnings.filterwarnings('ignore')

HERE = Path(__file__).parent
TODAY = datetime.now().strftime('%Y-%m-%d')

# single source of truth for the universe + indicator helpers
# (this import also rewraps sys.stdout as UTF-8 — do not wrap it again here)
from technical_macd_volume_strategy import load_portfolio, _rsi, _macd
from intraday_volume import rvol_now, low_volume_threshold, session_fraction, note as _iv_note


# ────────────────────────── Per-ticker analysis ───────────────────────
def analyze(tkr: str, sector: str, df: pd.DataFrame) -> dict:
    o, close, high, low, vol = df['Open'], df['Close'], df['High'], df['Low'], df['Volume']

    mid = close.rolling(20).mean()
    sd = close.rolling(20).std()
    upper, lower = mid + 2 * sd, mid - 2 * sd
    pctb = (close - lower) / (upper - lower)
    bw = (upper - lower) / mid * 100.0

    tr = pd.concat([high - low, (high - close.shift()).abs(),
                    (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()

    rsi = _rsi(close)
    _, _, hist = _macd(close)
    ma10 = close.rolling(10).mean()
    ma200 = close.rolling(200).mean()
    obv = (np.sign(close.diff()).fillna(0) * vol).cumsum()

    last = float(close.iloc[-1])
    low_l, mid_l, atr_l = float(lower.iloc[-1]), float(mid.iloc[-1]), float(atr.iloc[-1])
    pctb_l = float(pctb.iloc[-1])
    bw_l = float(bw.iloc[-1])
    rsi_l = float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50.0
    # 盘中部分bar的量不能直接比全日均量 — 归一化后再判(见 intraday_volume.py)
    _rv, rvol_est = rvol_now(vol, ticker=tkr, index=df.index)
    rvol = _rv if _rv is not None else 1.0
    rvol_unusable = _rv is None
    ma200_l = float(ma200.iloc[-1]) if not np.isnan(ma200.iloc[-1]) else None
    above_ma200 = ma200_l is not None and last > ma200_l

    bw_hist = bw.dropna()
    bw_pctile = float((bw_hist < bw_l).mean() * 100) if len(bw_hist) > 60 else 50.0
    bw_slope = float(bw.iloc[-1] - bw.iloc[-6]) if len(bw) > 6 else 0.0
    expanding = bw_slope > 0
    squeeze = bw_pctile <= 15.0

    dist_atr = (last - low_l) / atr_l if atr_l > 0 else 99.0     # ATRs ABOVE lower band

    # lower-band walk: closes with %B <= 0.2 in the last 10 bars
    walk_recent = int((pctb.iloc[-10:] <= 0.2).sum())
    walk_prior = int((pctb.iloc[-11:-1] <= 0.2).sum())
    was_walking = walk_prior >= 4

    # B5: negative histogram shrinking 3 bars (seller exhaustion)
    h = hist.iloc[-4:].values
    hist_shrinking = bool(len(h) == 4 and h[-1] < 0 and abs(h[-1]) < abs(h[-2]) < abs(h[-3]))
    hist_expanding_neg = bool(len(h) == 4 and h[-1] < 0 and abs(h[-1]) > abs(h[-2]) > abs(h[-3]))

    # B4: bullish RSI divergence — price lower-low vs RSI higher-low (30-bar window)
    divergence = False
    if len(close) > 35:
        win_c, win_r = close.iloc[-30:], rsi.iloc[-30:]
        recent_lo = win_c.iloc[-7:].min()
        prior_lo = win_c.iloc[:-7].min()
        if recent_lo <= prior_lo * 1.001:                # made/matched a low
            r_recent = win_r.iloc[-7:].loc[win_c.iloc[-7:].idxmin():].min()
            r_prior = float(win_r.iloc[:-7].loc[win_c.iloc[:-7].idxmin()])
            if not np.isnan(r_recent) and not np.isnan(r_prior) and r_recent > r_prior + 3:
                divergence = True
    obv_rising = bool(obv.iloc[-5:].mean() > obv.iloc[-20:].mean())   # money-flow backing

    # B2: capitulation flush in the last 3 bars (big down bar into the band zone)
    capitulation = False
    for i in (-3, -2, -1):
        try:
            bar_rvol = float(vol.iloc[i] / vol.rolling(20).mean().iloc[i])
            if i == -1 and rvol_est:      # 今日未完成bar — 用归一化值
                bar_rvol = rvol
            bar_ret = float(close.iloc[i] / close.iloc[i - 1] - 1)
            if bar_rvol >= 1.5 and bar_ret <= -0.03 and float(pctb.iloc[i]) <= 0.15:
                capitulation = True
        except Exception:
            pass

    # B3: reversal bar today at/near the band (hammer or bullish engulfing)
    body = abs(float(close.iloc[-1] - o.iloc[-1]))
    lower_wick = float(min(close.iloc[-1], o.iloc[-1]) - low.iloc[-1])
    rng = float(high.iloc[-1] - low.iloc[-1])
    hammer = (rng > 0 and body > 0 and lower_wick >= 2 * body
              and close.iloc[-1] >= low.iloc[-1] + 0.5 * rng)
    engulf = (len(close) > 2 and close.iloc[-1] > o.iloc[-1]
              and o.iloc[-2] > close.iloc[-2]
              and close.iloc[-1] > o.iloc[-2] and o.iloc[-1] < close.iloc[-2])
    # 量能不可用(开盘初期)时不因量否决反转线 — 形态本身仍然成立
    reversal_bar = bool((hammer or engulf) and pctb_l <= 0.25
                        and (rvol_unusable or rvol >= 1.0))

    # B8: W-bottom — two lows 10-40 bars apart, 2nd low ≈/below 1st, 2nd %B clearly higher
    w_bottom = False
    if len(close) > 45:
        seg1 = close.iloc[-45:-10]
        i1 = seg1.idxmin()
        lo1 = float(seg1.min())
        seg2 = close.iloc[-10:]
        i2 = seg2.idxmin()
        lo2 = float(seg2.min())
        if lo2 <= lo1 * 1.02:                            # 2nd low near/below 1st
            b1, b2 = float(pctb.loc[i1]), float(pctb.loc[i2])
            if not np.isnan(b1) and not np.isnan(b2) and b2 >= b1 + 0.15 and b1 <= 0.15:
                w_bottom = True

    # B7: midline reclaim after a lower-band walk
    midline_reclaim = was_walking and last > mid_l
    ma10_reclaim = was_walking and last > float(ma10.iloc[-1]) and last <= mid_l

    at_band = pctb_l <= 0.1
    near_band = pctb_l <= 0.25 or (0 < dist_atr <= 1.0)
    bear_squeeze = squeeze and pctb_l <= 0.35

    # bottom score (0-10+)
    score = 0.0
    reasons = []
    if capitulation and reversal_bar:
        score += 3.0; reasons.append(f'B2+B3 恐慌洗仓(RVOL≥1.5砸带) + 反转线({"锤子" if hammer else "阳吞没"})')
    elif capitulation:
        score += 1.5; reasons.append('B2 恐慌放量砸带 — 洗仓原料, 等反转线')
    elif reversal_bar:
        score += 1.5; reasons.append(f'B3 带区反转线({"锤子" if hammer else "阳吞没"}) RVOL {rvol:.2f}{_iv_note(rvol_est)}')
    if w_bottom:
        score += 2.5; reasons.append('B8 W底: 二次探底未触带(%B 显著抬升) — 卖压衰竭')
    if divergence:
        pts = 2.0 + (1.0 if obv_rising else 0.0)
        score += pts
        reasons.append('B4 RSI 底背离' + (' + OBV 资金回流确认' if obv_rising else ' (OBV 未确认, 打折)'))
    if midline_reclaim:
        score += 3.0; reasons.append(f'B7 中轨收复: 贴下轨带行后收回 MA20 ${mid_l:.2f} — 右侧回归信号')
    elif ma10_reclaim:
        score += 1.0; reasons.append('B7 早期: 收复 MA10, 中轨确认待收')
    if rsi_l <= 28 and near_band:
        score += 1.0; reasons.append(f'B4 RSI {rsi_l:.0f} 深度超卖')
    if hist_shrinking and near_band:
        score += 1.0; reasons.append('B5 负柱连续收窄 — 卖方力竭')
    # penalties
    if bear_squeeze:
        score -= 2.0; reasons.append(f'B6 空头挤压(bw p{bw_pctile:.0f}) — 变盘偏下, 非买点')
    if expanding and pctb_l <= 0.25 and not (capitulation or reversal_bar):
        score -= 1.5; reasons.append('B1 带扩张下行 — 向下带行制度, 别接刀')
    if at_band and (not rvol_unusable) and rvol < low_volume_threshold(0.8, rvol_est) \
            and not reversal_bar:
        score -= 1.0
        reasons.append(f'B2 贴带阴跌无恐慌(RVOL {rvol:.2f}{_iv_note(rvol_est)}) — 麻木下跌无底')
    if hist_expanding_neg and near_band:
        score -= 1.0; reasons.append('B5 负柱仍在放大 — 卖压未竭')

    # verdict
    if score >= 5.0:
        verdict = 'BUY / ACCUMULATE'
    elif midline_reclaim and score >= 3.0:
        verdict = 'BUY / ACCUMULATE'
    elif above_ma200 and not expanding and pctb_l <= 0.05 and rsi_l <= 32 and not bear_squeeze:
        verdict = 'MEAN-REVERT BUY'         # B10: uptrend context band tag
        reasons.append('B10 MA200 上方 + 带未扩张 + 深触带 — 均值回归买点')
    elif score >= 2.5:
        verdict = 'BOTTOM-WATCH'
    elif bear_squeeze:
        verdict = 'BEAR-SQUEEZE WARNING'
    elif near_band and (expanding or hist_expanding_neg or
                        ((not rvol_unusable) and at_band
                         and rvol < low_volume_threshold(0.8, rvol_est))):
        verdict = 'WALK-DOWN / AVOID'
    elif near_band:
        verdict = 'BOTTOM-WATCH' if reasons else 'NEUTRAL'
    else:
        verdict = 'NEUTRAL'

    return dict(
        ticker=tkr, sector=sector, last=round(last, 2),
        pctb=round(pctb_l, 2), bw=round(bw_l, 1), bw_pctile=round(bw_pctile, 0),
        expanding=expanding, squeeze=squeeze, bear_squeeze=bear_squeeze,
        dist_atr=round(dist_atr, 2), rvol=round(rvol, 2), rvol_est=rvol_est,
        rvol_unusable=rvol_unusable, rsi=round(rsi_l, 0),
        hist_shrinking=hist_shrinking, divergence=divergence, obv_rising=obv_rising,
        capitulation=capitulation, reversal_bar=reversal_bar, w_bottom=w_bottom,
        walk_recent=walk_recent, was_walking=was_walking,
        midline_reclaim=midline_reclaim, above_ma200=above_ma200,
        lower=round(low_l, 2), mid=round(mid_l, 2), ma10=round(float(ma10.iloc[-1]), 2),
        score=round(score, 1), verdict=verdict, reasons=reasons,
    )


# ────────────────────────────────── Main ──────────────────────────────
def main():
    stamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    print('=' * 70)
    print(f'  Bollinger Band-Bottom Detection — AI Portfolio    {stamp}')
    print('=' * 70)

    sectors = load_portfolio()
    tick2sec = {t: s for s, ts in sectors.items() for t in ts}
    tickers = list(tick2sec)
    print(f'Loaded {len(tickers)} tickers across {len(sectors)} sectors')

    raw = yf.download(tickers, period='1y', interval='1d', auto_adjust=True,
                      group_by='ticker', progress=False, threads=True)
    results, failed = [], []
    for i, tkr in enumerate(tickers, 1):
        try:
            df = raw[tkr].dropna(subset=['Close']).copy()
            if len(df) < 60:
                raise ValueError(f'only {len(df)} bars')
            results.append(analyze(tkr, tick2sec[tkr], df))
        except Exception as e:
            failed.append((tkr, str(e)))
        if i % 40 == 0:
            print(f'  {i}/{len(tickers)} complete')
    print(f'  {len(results)} analyzed, {len(failed)} failed')
    if failed:
        print('  FAILED:', ', '.join(t for t, _ in failed))

    buys = sorted([r for r in results if r['verdict'] == 'BUY / ACCUMULATE'], key=lambda r: -r['score'])
    mrev = sorted([r for r in results if r['verdict'] == 'MEAN-REVERT BUY'], key=lambda r: r['pctb'])
    watch = sorted([r for r in results if r['verdict'] == 'BOTTOM-WATCH'], key=lambda r: -r['score'])
    walk = sorted([r for r in results if r['verdict'] == 'WALK-DOWN / AVOID'], key=lambda r: r['pctb'])
    sqz = sorted([r for r in results if r['verdict'] == 'BEAR-SQUEEZE WARNING'], key=lambda r: r['bw'])

    print(f"\n  🟢 BUY/ACCUMULATE: {len(buys)} | 💚 MEAN-REVERT BUY: {len(mrev)} | "
          f"👀 BOTTOM-WATCH: {len(watch)} | 🔻 WALK-DOWN/AVOID: {len(walk)} | "
          f"⚠️ BEAR-SQUEEZE: {len(sqz)}")
    for r in buys:
        print(f"    🟢 {r['ticker']:8} ${r['last']:<9} score {r['score']:>4} — {'; '.join(r['reasons'])}")
    for r in mrev:
        print(f"    💚 {r['ticker']:8} ${r['last']:<9} %B {r['pctb']} RSI {r['rsi']:.0f} — 均值回归买点(MA200上方)")
    for r in watch:
        print(f"    👀 {r['ticker']:8} ${r['last']:<9} score {r['score']:>4} — {'; '.join(r['reasons'])}")

    # ── markdown report ──
    md = [f'# Bollinger Band-Bottom Detection — {stamp}', '',
          f'**{len(results)} tickers** | 🟢 BUY/ACCUMULATE {len(buys)} · 💚 MEAN-REVERT {len(mrev)} · '
          f'👀 BOTTOM-WATCH {len(watch)} · 🔻 WALK-DOWN {len(walk)} · ⚠️ BEAR-SQUEEZE {len(sqz)}', '']
    if failed:
        md.append('> 数据缺失: ' + ', '.join(t for t, _ in failed) + '\n')

    def table(rows, title, note=''):
        if not rows:
            return
        md.append(f'## {title}')
        if note:
            md.append(f'_{note}_\n')
        md.append('| Ticker | Sector | Price | %B | dist(ATR) | RVOL | RSI | Walk10 | MA200↑ | Score | Signals |')
        md.append('|---|---|---|---|---|---|---|---|---|---|---|')
        for r in rows:
            sig = '; '.join(r['reasons']) if r['reasons'] else '—'
            md.append(f"| {r['ticker']} | {r['sector']} | ${r['last']} | {r['pctb']} | {r['dist_atr']} | "
                      f"{r['rvol']} | {r['rsi']:.0f} | {r['walk_recent']}/10 | {'Y' if r['above_ma200'] else 'N'} | "
                      f"{r['score']} | {sig} |")
        md.append('')

    table(buys, '🟢 BUY / ACCUMULATE — 底部信号成立',
          '洗仓+反转线 / W底 / 中轨收复叠加。入场参考: 反转线高点上方; 止损: 信号低点下方。')
    table(mrev, '💚 MEAN-REVERT BUY — 均值回归买点 (B10)',
          'MA200 上方 + 带未扩张 + 深触带 + RSI≤32。等反转线更稳; 止损: 下轨外 1 ATR。')
    table(watch, '👀 BOTTOM-WATCH — 底部原料就位, 等确认',
          '背离/超卖/负柱收窄已现, 但缺洗仓反转或中轨收复。确认前不入场。')
    table(sqz, '⚠️ BEAR-SQUEEZE WARNING — 空头挤压, 变盘偏下', 'B6: 贴下轨的窄带不是买点, 谨防向下变盘。')
    table(walk, '🔻 WALK-DOWN / AVOID — 向下带行, 别接刀',
          'B1 带扩张下行或麻木阴跌; 只有收复 MA20 中轨才重新考虑 (B7)。')

    others = sorted([r for r in results if r['verdict'] == 'NEUTRAL'],
                    key=lambda r: (r['sector'], r['ticker']))
    md.append('## 其余标的 (NEUTRAL)')
    md.append('| Ticker | Sector | Price | %B | dist(ATR) | RSI |')
    md.append('|---|---|---|---|---|---|')
    for r in others:
        md.append(f"| {r['ticker']} | {r['sector']} | ${r['last']} | {r['pctb']} | {r['dist_atr']} | {r['rsi']:.0f} |")
    md += ['', '## 规则速查 (底部与顶部不对称: 超卖可以更超卖, 底部多一道确认)',
           '- B1 带扩张下行→向下带行别接; 带收平→下轨才是地板',
           '- B2 RVOL≥1.5 恐慌砸带 = 洗仓原料; RVOL<0.8 阴跌 = 麻木无底',
           '- B3 带区锤子线/阳吞没 + 量 = 洗仓的确认件',
           '- B4 RSI≤30 触带至少反弹; 底背离最强, 但需 OBV 回流佐证',
           '- B5 负柱收窄 = 卖方力竭; 负柱放大 = 别碰',
           '- B6 贴下轨的挤压偏向下变盘 → 警告非买点',
           '- B7 贴下轨带行者的买入信号是首次收回 MA20, 不是触带',
           '- B8 W底: 二次探底 %B 显著抬升 = 卖压衰竭 (Bollinger 经典)',
           '- B9 距下轨 ≤1 ATR = 一根普通阴线即触带',
           '- B10 MA200 上方+带未扩张才可直接均值回归买; MA200 下方只认中轨收复',
           '', '> Algorithmic technical analysis only — not financial advice.']

    out = HERE / f'bollinger_bottom_{TODAY}.md'
    out.write_text('\n'.join(md), encoding='utf-8')
    print(f'\n  Report saved: {out.name}')
    print('DONE')


if __name__ == '__main__':
    main()
