"""
Peter DiCarlo (@pdicarlotrader) framework vs 我的打法 — YTD + trailing 3-year.

DiCarlo 公开框架 (X/Threads 帖子重建, 非其付费课程原版参数):
  BX Trender  = B-Xtrender (Bharat Jhunjhunwala, IFTA; TradingView @Puppytherapy):
                short = RSI(EMA5 - EMA20, 15) - 50   (柱: >0 绿 / <0 红)
                long  = RSI(EMA20, 15) - 50
  Smart Money / Institutional Buy Zone = 上一段大升浪 L→H 的 .786–.826 回撤带 ("80% discount")
  Institutional Sell Zone (对称)        = 下跌段 H→L2 的 .786–.826 反弹带 (头顶供给区)
  离场: ATR / trailing stop / BX 由绿翻红

Variants:
  DC1 周线BX翻绿→翻红            纯周线趋势跟随
  DC2 两步法 周BX绿+日BX翻绿     日BX翻红离场
  DC3 机构买区+日BX翻绿          离场: 3×ATR 吊灯止损 / 周BX(转绿后)翻红
  DC4 机构买区+日BX翻绿          离场: 到机构卖区 / 2.5×ATR 硬止损
Portfolio metric: 等权"每票一个袖子" (有信号持仓, 无信号现金) → 总收益/CAGR/MaxDD/Sharpe/仓位占用.
Entries at signal-bar close, no costs — same convention as backtest_playbooks_2026.py.
"""
import json, warnings
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")
import backtest_playbooks_2026 as bp
bp.DATA_START = "2022-01-01"          # 3y window + weekly-BX warmup
from backtest_playbooks_2026 import (add_indicators, download_all, get_universe, run_trades,
                                     summarize, rotation_backtest, PLAYBOOKS)
from backtest_pb16_2026 import add_pb16_indicators
from backtest_pb16_gate_2026 import i_entry as pb16_entry
from backtest_pb16_pure_2026 import chart_exit as pb16_exit

HERE = Path(__file__).parent
TODAY = datetime.now().strftime("%Y-%m-%d")
END = pd.Timestamp(TODAY)
WINDOWS = [("2026 YTD", "2026-01-01"), ("3年 (trailing)", str((END - pd.DateOffset(years=3)).date()))]


# ────────────────────────── BX Trender ──────────────────────────
def _rsi_wilder(s, n):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def bx_short(c):
    return _rsi_wilder(c.ewm(span=5, adjust=False).mean() - c.ewm(span=20, adjust=False).mean(), 15) - 50


def add_dicarlo(df):
    c = df["Close"]
    df["bx_d"] = bx_short(c)
    # weekly BX — value of a week becomes known on that week's last trading bar (no lookahead)
    wk = df.index.to_period("W-FRI")
    last_bar = pd.Series(df.index, index=df.index).groupby(wk).max()
    wc = c.groupby(wk).last()
    wbx = bx_short(wc)
    wbx.index = last_bar.values
    df["bx_w"] = wbx.reindex(df.index).ffill()
    wprev = wbx.shift(1); wprev.index = wbx.index
    df["bx_w_prev"] = wprev.reindex(df.index).ffill()
    df["wk_end"] = df.index.isin(last_bar.values)
    # institutional buy zone: major upswing L→H inside trailing 252 bars
    h, l = df["High"].values, df["Low"].values
    n = len(df)
    zt, zb, sw_lo, sw_hi = (np.full(n, np.nan) for _ in range(4))
    for i in range(252, n):
        seg_h = h[i - 252:i + 1]
        k = int(np.argmax(seg_h)); H = seg_h[k]; hi_i = i - 252 + k
        lo_start = max(0, hi_i - 252)
        if hi_i - lo_start < 20:
            continue
        L = l[lo_start:hi_i + 1].min()
        if H / L - 1 < 0.30:               # need a real upswing
            continue
        zt[i], zb[i] = H - 0.786 * (H - L), H - 0.826 * (H - L)
        sw_lo[i], sw_hi[i] = L, H
    df["zone_top"], df["zone_bot"], df["sw_lo"], df["sw_hi"] = zt, zb, sw_lo, sw_hi
    return df


def _flip_up(s, i):   return s.iloc[i] > 0 and s.iloc[i - 1] <= 0
def _flip_dn(s, i):   return s.iloc[i] < 0 and s.iloc[i - 1] >= 0


def dc1_entry(df, i):
    if df["wk_end"].iloc[i] and df["bx_w"].iloc[i] > 0 and df["bx_w_prev"].iloc[i] <= 0:
        return {}
def dc1_exit(df, i, pos):
    return bool(df["wk_end"].iloc[i] and df["bx_w"].iloc[i] < 0)

def dc2_entry(df, i):
    if df["bx_w"].iloc[i] > 0 and _flip_up(df["bx_d"], i):
        return {}
def dc2_exit(df, i, pos):
    return _flip_dn(df["bx_d"], i) or df["bx_w"].iloc[i] < 0

def _zone_entry(df, i):
    if not _flip_up(df["bx_d"], i):
        return None
    zt = df["zone_top"].iloc[i]
    if np.isnan(zt):
        return None
    lo10 = df["Low"].iloc[i - 9:i + 1].min()
    c = df["Close"].iloc[i]
    # touched the .786 line within 10 bars, swing low intact, not already far above the zone
    if lo10 <= zt and c > df["sw_lo"].iloc[i] and c <= zt * 1.10:
        return {"atr0": float(df["atr"].iloc[i]), "H": float(df["sw_hi"].iloc[i]),
                "hi_close": float(c), "w_green": False}
    return None

def dc3_exit(df, i, pos):
    c = df["Close"].iloc[i]
    pos["hi_close"] = max(pos["hi_close"], c)
    if df["bx_w"].iloc[i] > 0:
        pos["w_green"] = True
    if c < pos["hi_close"] - 3 * df["atr"].iloc[i]:
        return True
    return bool(pos["w_green"] and df["wk_end"].iloc[i] and df["bx_w"].iloc[i] < 0)

def dc4_exit(df, i, pos):
    c = df["Close"].iloc[i]
    if c < pos["entry"] - 2.5 * pos["atr0"]:
        return True
    L2 = df["Low"].iloc[max(pos["entry_i"] - 10, 0):pos["entry_i"] + 1].min()
    return c >= L2 + 0.786 * (pos["H"] - L2)       # institutional sell zone reached

DICARLO = {
    "DC1 周线BX翻绿→翻红":          (dc1_entry, dc1_exit),
    "DC2 两步法 周BX绿+日BX翻绿":    (dc2_entry, dc2_exit),
    "DC3 机构买区+BX, ATR吊灯/周BX离场": (_zone_entry, dc3_exit),
    "DC4 机构买区+BX, 到机构卖区离场":   (_zone_entry, dc4_exit),
}
MINE = {k: PLAYBOOKS[k] for k in ["打法1 回踩企稳", "打法2 缩量平台突破", "打法7 下轨恐慌反转", "打法8 带行持有"]}
MINE["打法13 MA50/200金叉"] = PLAYBOOKS["基线 MA50/200金叉"]
MINE["打法14 MACD底背离"] = PLAYBOOKS["抄底1 MACD底背离"]
MINE["打法15 金针探底"] = PLAYBOOKS["抄底6 金针探底"]
MINE["打法16 纯图突破(双闸)"] = (pb16_entry, pb16_exit)


# ────────────────────────── sleeve portfolio ──────────────────────────
def sleeve_curve(data, trades_by_tk, start):
    """Equal-weight sleeves: each ticker's sleeve is long while a trade is open, else cash."""
    cal = pd.DatetimeIndex(sorted(set().union(*[d.index[d.index >= pd.Timestamp(start)] for d in data.values()])))
    cal = cal[cal.dayofweek < 5]
    rets, expo = [], []
    for t, df in data.items():
        c = df["Close"]
        pos = pd.Series(0.0, index=c.index)
        for tr in trades_by_tk.get(t, []):
            e = pd.Timestamp(tr["entry_date"])
            x = c.index[-1] if tr["exit_date"].startswith(("OPEN", "EOW")) else pd.Timestamp(tr["exit_date"])
            pos[(pos.index > e) & (pos.index <= x)] = 1.0
        r = (c.pct_change() * pos)
        r = r[r.index >= pd.Timestamp(start)]
        # crypto weekend P&L folds into Monday so the weekday calendar keeps it
        r = (1 + r).groupby(np.searchsorted(cal, r.index).clip(max=len(cal) - 1)).prod() - 1
        r.index = cal[r.index]
        rets.append(r.reindex(cal).fillna(0)); expo.append(pos.reindex(cal).fillna(0))
    port = pd.concat(rets, axis=1).mean(axis=1)
    eq = (1 + port).cumprod()
    yrs = max((cal[-1] - cal[0]).days / 365.25, 1e-9)
    return {"total": float(eq.iloc[-1] - 1), "cagr": float(eq.iloc[-1] ** (1 / yrs) - 1),
            "maxdd": float((eq / eq.cummax() - 1).min()),
            "sharpe": float(port.mean() / port.std() * np.sqrt(252)) if port.std() > 0 else 0.0,
            "exposure": float(pd.concat(expo, axis=1).mean().mean())}


def buy_hold(series, start):
    c = series[series.index >= pd.Timestamp(start)].dropna()
    eq = c / c.iloc[0]
    yrs = (c.index[-1] - c.index[0]).days / 365.25
    r = c.pct_change().dropna()
    return {"total": float(eq.iloc[-1] - 1), "cagr": float(eq.iloc[-1] ** (1 / yrs) - 1),
            "maxdd": float((eq / eq.cummax() - 1).min()),
            "sharpe": float(r.mean() / r.std() * np.sqrt(252)), "exposure": 1.0}


def main():
    import yfinance as yf
    tickers, _ = get_universe()
    data = download_all(tickers)
    for t in list(data):
        data[t] = add_dicarlo(add_pb16_indicators(add_indicators(data[t])))
    print(f"universe {len(data)} tickers, data from {bp.DATA_START}")
    bench_px = {}
    for b in ["SPY", "QQQ"]:
        d = yf.download(b, start=bp.DATA_START, auto_adjust=True, progress=False)
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = d.columns.get_level_values(0)
        bench_px[b] = d["Close"].dropna()

    out, md = {}, [f"# DiCarlo 框架 vs 我的打法 — YTD / 3年 (as of {TODAY})",
                   f"universe {len(data)} tickers · 信号bar收盘成交 · 无成本滑点 · 组合=等权每票袖子(无信号持现金)", ""]
    for label, start in WINDOWS:
        rows = {}
        for group, books in (("DiCarlo", DICARLO), ("我的", MINE)):
            for name, (en, ex) in books.items():
                trades, by_tk = [], {}
                for t, df in data.items():
                    tr = run_trades(df, en, ex, name, start=start)
                    for x in tr:
                        x["ticker"] = t
                    trades += tr; by_tk[t] = tr
                s = summarize(trades)
                if not s:
                    continue
                rows[name] = {"group": group, **{k: s[k] for k in ("n_trades", "win_rate", "avg_ret", "profit_factor", "avg_days")},
                              **sleeve_curve(data, by_tk, start)}
        rot = rotation_backtest(data, start=start)
        eqs = np.array([1.0] + [x[1] for x in rot["legs"]])
        yrs = (END - pd.Timestamp(start)).days / 365.25
        rows["打法3 强弱轮动 top-10"] = {"group": "我的", "n_trades": len(rot["legs"]), "win_rate": float(np.mean(np.diff(eqs) > 0)),
                                   "avg_ret": float(np.mean(eqs[1:] / eqs[:-1] - 1)), "profit_factor": float("nan"), "avg_days": 20,
                                   "total": float(eqs[-1] - 1), "cagr": float(eqs[-1] ** (1 / yrs) - 1),
                                   "maxdd": float((eqs / np.maximum.accumulate(eqs) - 1).min()), "sharpe": float("nan"), "exposure": 1.0}
        for b in ("SPY", "QQQ"):
            rows[f"基准 {b} 买入持有"] = {"group": "基准", **buy_hold(bench_px[b], start)}
        ew = [buy_hold(d["Close"], start) for d in data.values() if (d.index >= pd.Timestamp(start)).sum() > 10]
        rows["基准 池内等权买入持有"] = {"group": "基准", "total": float(np.mean([e["total"] for e in ew])), "exposure": 1.0}
        out[label] = rows
        md += [f"## {label} ({start} → {TODAY})", "",
               "| 组 | 策略 | 组合总收益 | 年化 | MaxDD | Sharpe | 仓位占用 | 交易数 | 胜率 | 单笔均值 | PF | 持仓天 |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        f = lambda v, p="{:+.1%}": "—" if v is None or (isinstance(v, float) and np.isnan(v)) else p.format(v)
        for name, r in sorted(rows.items(), key=lambda kv: -kv[1]["total"]):
            md.append(f"| {r['group']} | {name} | **{f(r['total'])}** | {f(r.get('cagr'))} | {f(r.get('maxdd'))} | {f(r.get('sharpe'), '{:.2f}')} | "
                      f"{f(r.get('exposure'), '{:.0%}')} | {r.get('n_trades', '—')} | {f(r.get('win_rate'), '{:.0%}')} | {f(r.get('avg_ret'), '{:+.2%}')} | "
                      f"{f(r.get('profit_factor'), '{:.2f}')} | {f(r.get('avg_days'), '{:.0f}')} |")
        md.append("")
    (HERE / f"backtest_dicarlo_{TODAY}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (HERE / f"backtest_dicarlo_{TODAY}.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
