"""
Bollinger Band-Top Detection Strategy — AI_Portfolios.xlsx
==========================================================
Detects stocks approaching / tagging the UPPER Bollinger Band (20, 2σ)
and classifies whether the tag is likely to be a BAND-WALK continuation
or a TOP (reject / fade), emitting explicit SELL signals.

Rules encoded (the "band-top playbook"):

  R1  BAND REGIME      — expanding bands on approach → walk-likely;
                         flat/contracting bands → tag acts as ceiling
  R2  VOLUME TRUTH     — approach on RVOL ≥ 1.1 = real demand;
                         RVOL < 0.8 = exhaustion, tag-and-fade risk
  R3  FAKE BREAKOUT    — close above upper band (%B > 1) on RVOL < 0.9
                         → classic fake-out signature → SELL/TRIM
  R4  RSI GATE         — RSI ≥ 78 at the band → tag likely stalls;
                         bearish RSI divergence (price HH, RSI LH) = top tell
  R5  MACD HISTOGRAM   — fading histogram into the band = decelerating
                         push exactly at resistance
  R6  BANDWIDTH EXTREME— bandwidth percentile ≥ 97 (vs 1y) = late-in-move;
                         extremes precede contraction
  R7  MIDLINE EXIT     — a band-walker's first close below MA20 midline
                         is THE exit signal (not the tag itself) → SELL
  R8  SQUEEZE IGNITION — tag out of a squeeze (bandwidth ≤ p15) with
                         volume = ignition, NOT a top (bullish exception)
  R9  ABOUT-TO-HIT     — distance to upper band ≤ 1 ATR = one ordinary
                         up-day tags it; classify expected outcome now

Verdicts per stock:
  SELL / TRIM        — top-risk score ≥ 5 (fake breakout, midline break,
                       divergence stacks)
  SELL-PARTIAL / TIGHTEN — score 3-4.5: take partials, stop → MA10
  DON'T ADD          — approaching the band but reject-likely
  HOLD-RIDE          — healthy band-walk: hold until midline break
  IGNITION-WATCH     — squeeze pre-tag: next tag is a BUY trigger
  APPROACHING-WALK   — ≤1 ATR from band, walk-likely (constructive)
  NEUTRAL            — not near the upper band, no band-top signal

Output: bollinger_top_YYYY-MM-DD.md + console summary.
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
from intraday_volume import rvol_now, low_volume_threshold, note as _iv_note


# ────────────────────────── Per-ticker analysis ───────────────────────
def analyze(tkr: str, sector: str, df: pd.DataFrame) -> dict:
    close, high, low, vol = df['Close'], df['High'], df['Low'], df['Volume']

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

    last = float(close.iloc[-1])
    up_l, mid_l, atr_l = float(upper.iloc[-1]), float(mid.iloc[-1]), float(atr.iloc[-1])
    pctb_l = float(pctb.iloc[-1])
    bw_l = float(bw.iloc[-1])
    rsi_l = float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50.0
    # 盘中部分bar的量不能直接比全日均量 — 归一化后再判(见 intraday_volume.py)
    _rv, rvol_est = rvol_now(vol, ticker=tkr, index=df.index)
    rvol = _rv if _rv is not None else 1.0
    rvol_unusable = _rv is None

    bw_hist = bw.dropna()
    bw_pctile = float((bw_hist < bw_l).mean() * 100) if len(bw_hist) > 60 else 50.0
    bw_slope = float(bw.iloc[-1] - bw.iloc[-6]) if len(bw) > 6 else 0.0  # 5-day change
    expanding = bw_slope > 0
    squeeze = bw_pctile <= 15.0

    dist_atr = (up_l - last) / atr_l if atr_l > 0 else 99.0

    # band-walk: closes with %B >= 0.8 in the last 10 bars
    walk_recent = int((pctb.iloc[-10:] >= 0.8).sum())
    walk_prior = int((pctb.iloc[-11:-1] >= 0.8).sum())   # excluding today
    was_walking = walk_prior >= 4

    # MACD histogram fading: positive but shrinking 3 bars in a row
    h = hist.iloc[-4:].values
    hist_fading = bool(len(h) == 4 and h[-1] > 0 and h[-1] < h[-2] < h[-3])
    hist_rising = bool(len(h) == 4 and h[-1] > h[-2] > h[-3])

    # bearish RSI divergence: price higher-high vs RSI lower-high (30-bar window)
    divergence = False
    if len(close) > 35:
        win_c, win_r = close.iloc[-30:], rsi.iloc[-30:]
        recent_hi = win_c.iloc[-7:].max()
        prior_hi = win_c.iloc[:-7].max()
        if recent_hi >= prior_hi * 0.999:                # made/matched a high
            r_recent = win_r.iloc[-7:][win_c.iloc[-7:].idxmax():].max()
            r_prior = float(win_r.iloc[:-7].loc[win_c.iloc[:-7].idxmax()])
            if not np.isnan(r_recent) and not np.isnan(r_prior) and r_recent < r_prior - 3:
                divergence = True

    midline_break = was_walking and last < mid_l
    # R3 只在量能可信时开: 盘中估算收紧到 0.72, 外推不可用则整条规则关闭
    fake_breakout = (not rvol_unusable) and pctb_l > 1.0 and \
        rvol < low_volume_threshold(0.9, rvol_est)
    at_band = pctb_l >= 0.95
    exhaustion_tag = at_band and (rsi_l >= 78 or hist_fading or divergence)
    bw_extreme = bw_pctile >= 97.0

    # top-risk score (0-10+)
    score = 0.0
    reasons = []
    if fake_breakout:
        score += 3.0; reasons.append(f'R3 假突破: 收在上轨外(%B {pctb_l:.2f})但 RVOL {rvol:.2f}{_iv_note(rvol_est)} 缩量')
    if midline_break:
        score += 3.0; reasons.append(f'R7 中轨破位: 带行进行中首次收破 MA20 ${mid_l:.2f} — 离场信号')
    if exhaustion_tag:
        score += 2.5; reasons.append(f'R4/R5 衰竭触带: %B {pctb_l:.2f} + ' +
                                     ('RSI ' + str(round(rsi_l)) if rsi_l >= 78 else '') +
                                     (' 柱状图衰减' if hist_fading else '') +
                                     (' RSI顶背离' if divergence else ''))
    if divergence and not exhaustion_tag:
        score += 2.0; reasons.append('R4 RSI 顶背离 (价新高/RSI 未确认)')
    if bw_extreme and (hist_fading or rsi_l >= 75):
        score += 1.5; reasons.append(f'R6 带宽极值 p{bw_pctile:.0f} + 动能衰减 — 行情后段')
    if at_band and (not rvol_unusable) and rvol < low_volume_threshold(0.8, rvol_est) \
            and not fake_breakout:
        score += 1.0; reasons.append(f'R2 贴带缩量 RVOL {rvol:.2f}{_iv_note(rvol_est)}')
    if hist_fading and at_band and not exhaustion_tag:
        score += 1.0; reasons.append('R5 MACD 柱状图连续衰减')

    # verdict
    trend_up = last > mid_l
    if score >= 5.0:
        verdict = 'SELL / TRIM'
    elif score >= 3.0:
        verdict = 'SELL-PARTIAL / TIGHTEN'
    elif squeeze and 0.5 <= pctb_l <= 1.05 and trend_up:
        verdict = 'IGNITION-WATCH'          # R8: tag out of squeeze = buy trigger, not top
    elif at_band or (0 < dist_atr <= 1.0 and trend_up):
        walk_likely = expanding and rvol >= 1.1 and not hist_fading and rsi_l < 78
        # 量能不可用时不得单凭它判 reject — 交给趋势/RSI 决定
        reject_likely = (not expanding) or rsi_l >= 75 or \
            ((not rvol_unusable) and rvol < low_volume_threshold(0.8, rvol_est))
        _vol_ok = rvol_unusable or rvol >= low_volume_threshold(0.7, rvol_est)
        if pctb_l >= 0.8 and expanding and rsi_l < 78 and not divergence and _vol_ok:
            verdict = 'HOLD-RIDE'           # healthy band walk
        elif walk_likely:
            verdict = 'APPROACHING-WALK'
        elif reject_likely:
            verdict = "DON'T ADD"
        else:
            verdict = 'APPROACHING-NEUTRAL'
    else:
        verdict = 'NEUTRAL'

    return dict(
        ticker=tkr, sector=sector, last=round(last, 2),
        pctb=round(pctb_l, 2), bw=round(bw_l, 1), bw_pctile=round(bw_pctile, 0),
        expanding=expanding, squeeze=squeeze,
        dist_atr=round(dist_atr, 2), rvol=round(rvol, 2), rvol_est=rvol_est,
        rvol_unusable=rvol_unusable, rsi=round(rsi_l, 0),
        hist_fading=hist_fading, hist_rising=hist_rising, divergence=divergence,
        walk_recent=walk_recent, was_walking=was_walking,
        midline_break=midline_break, fake_breakout=fake_breakout,
        exhaustion_tag=exhaustion_tag, bw_extreme=bw_extreme,
        upper=round(up_l, 2), mid=round(mid_l, 2), ma10=round(float(ma10.iloc[-1]), 2),
        score=round(score, 1), verdict=verdict, reasons=reasons,
    )


# ────────────────────────────────── Main ──────────────────────────────
def main():
    stamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    print('=' * 70)
    print(f'  Bollinger Band-Top Detection — AI Portfolio    {stamp}')
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

    sells = sorted([r for r in results if r['verdict'] == 'SELL / TRIM'], key=lambda r: -r['score'])
    partials = sorted([r for r in results if r['verdict'] == 'SELL-PARTIAL / TIGHTEN'], key=lambda r: -r['score'])
    dontadd = sorted([r for r in results if r['verdict'] == "DON'T ADD"], key=lambda r: -r['pctb'])
    riders = sorted([r for r in results if r['verdict'] == 'HOLD-RIDE'], key=lambda r: -r['pctb'])
    approaching = sorted([r for r in results if r['verdict'].startswith('APPROACHING')], key=lambda r: r['dist_atr'])
    ignition = sorted([r for r in results if r['verdict'] == 'IGNITION-WATCH'], key=lambda r: r['bw'])

    print(f"\n  🔴 SELL/TRIM: {len(sells)} | 🟠 SELL-PARTIAL: {len(partials)} | "
          f"⛔ DON'T ADD: {len(dontadd)} | 🟢 HOLD-RIDE: {len(riders)} | "
          f"👀 APPROACHING: {len(approaching)} | 🎯 IGNITION: {len(ignition)}")
    for r in sells:
        print(f"    🔴 {r['ticker']:8} ${r['last']:<9} score {r['score']:>4} — {'; '.join(r['reasons'])}")
    for r in partials:
        print(f"    🟠 {r['ticker']:8} ${r['last']:<9} score {r['score']:>4} — {'; '.join(r['reasons'])}")

    # ── markdown report ──
    md = [f'# Bollinger Band-Top Detection — {stamp}', '',
          f'**{len(results)} tickers** | 🔴 SELL/TRIM {len(sells)} · 🟠 SELL-PARTIAL {len(partials)} · '
          f"⛔ DON'T ADD {len(dontadd)} · 🟢 HOLD-RIDE {len(riders)} · "
          f'👀 APPROACHING {len(approaching)} · 🎯 IGNITION-WATCH {len(ignition)}', '']
    if failed:
        md.append('> 数据缺失: ' + ', '.join(t for t, _ in failed) + '\n')

    def table(rows, title, note=''):
        if not rows:
            return
        md.append(f'## {title}')
        if note:
            md.append(f'_{note}_\n')
        md.append('| Ticker | Sector | Price | %B | BW(pctile) | dist(ATR) | RVOL | RSI | Walk10 | Score | Signals |')
        md.append('|---|---|---|---|---|---|---|---|---|---|---|')
        for r in rows:
            sig = '; '.join(r['reasons']) if r['reasons'] else '—'
            md.append(f"| {r['ticker']} | {r['sector']} | ${r['last']} | {r['pctb']} | "
                      f"{r['bw']}% (p{r['bw_pctile']:.0f}) | {r['dist_atr']} | {r['rvol']} | "
                      f"{r['rsi']:.0f} | {r['walk_recent']}/10 | {r['score']} | {sig} |")
        md.append('')

    table(sells, '🔴 SELL / TRIM — 顶部信号成立',
          '假突破 / 中轨破位 / 衰竭触带叠加。持仓者按信号离场或减仓；MA10 见 report 内 ma10 值。')
    table(partials, '🟠 SELL-PARTIAL / TIGHTEN — 减仓并收紧止损至 MA10',
          '衰竭迹象但趋势未破：兑现部分利润，止损上移 MA10，中轨破位则全退。')
    table(dontadd, "⛔ DON'T ADD — 贴近上轨但拒绝概率大", '带收缩/缩量/RSI 过热的接近触带——不开新仓。')
    table(approaching, '👀 APPROACHING — 距上轨 ≤1 ATR', 'walk-likely 的接近属建设性；一根普通阳线即触带。')
    table(riders, '🟢 HOLD-RIDE — 健康带行', '触带非卖出信号；离场信号 = 首次收破中轨 MA20。')
    table(ignition, '🎯 IGNITION-WATCH — 挤压预触带', 'R8：放量突破上轨 = 点火买入触发，非顶部。')

    others = sorted([r for r in results if r['verdict'] in ('NEUTRAL', 'APPROACHING-NEUTRAL')],
                    key=lambda r: (r['sector'], r['ticker']))
    md.append('## 其余标的 (NEUTRAL)')
    md.append('| Ticker | Sector | Price | %B | dist(ATR) | RSI | Verdict |')
    md.append('|---|---|---|---|---|---|---|')
    for r in others:
        md.append(f"| {r['ticker']} | {r['sector']} | ${r['last']} | {r['pctb']} | "
                  f"{r['dist_atr']} | {r['rsi']:.0f} | {r['verdict']} |")
    md += ['', '## 规则速查',
           '- R1 带扩张→带行；带收缩→上轨是天花板',
           '- R2 RVOL≥1.1 真需求；<0.8 衰竭',
           '- R3 %B>1 + RVOL<0.9 = 假突破 → SELL',
           '- R4 RSI≥78 触带必滞；顶背离 = 最强反转信号',
           '- R5 柱状图衰减进带 = 推力减速',
           '- R6 带宽 p≥97 = 行情后段',
           '- R7 带行者的离场信号是收破 MA20 中轨，不是触带本身',
           '- R8 挤压后放量触带 = 点火(买入)，非顶部',
           '- R9 距上轨 ≤1 ATR = 一根普通阳线即触带',
           '', '> Algorithmic technical analysis only — not financial advice.']

    out = HERE / f'bollinger_top_{TODAY}.md'
    out.write_text('\n'.join(md), encoding='utf-8')
    print(f'\n  Report saved: {out.name}')
    print('DONE')


if __name__ == '__main__':
    main()
