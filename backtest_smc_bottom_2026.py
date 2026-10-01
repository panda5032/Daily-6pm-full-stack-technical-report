# -*- coding: utf-8 -*-
"""
机构买区(.786–.826 fib) + Smart Money Concepts 抄底: 准不准? 能不能当辅助信号?  (2026-09-19)

A. 事件研究 — 大升浪(>=30%) 后首次回撤触及各 fib 位 (.5/.618/.786/.886): 之后 20/60/120 日收益,
   "底守住率"(120日内收盘不破升浪起点 L), 触及后继续下探的最大跌幅. 检验 .786 是否比别的位特殊.
   对照: 同期同池任意一天的 20/60/120 日收益.
B. 辅助测试 — 打法7/14/15 的信号按"是否在机构买区内"分组 (近10根最低价 <= .786 线 且 收盘 > L).
C. SMC 机械代理:
   SWEEP  流动性猎杀: 最低价刺破前20日低点后收回其上 (stop-hunt reclaim)
   CHOCH  结构转换:   近10根内出现 SWEEP, 今日收盘突破 sweep 前最近一个 lower-high(近10根最高收盘)
   FVG    多头失衡缺口回补: 3根内 low[i-?]>high 留缺口, 回踩缺口上沿收阳
   OB     多头订单块: 前20日内"启动大阳前最后一根阴线"区间被回踩并收在其上
   单独当入场 (离场同打法7: 到MA20 / 破信号低点 / 15根) + 当打法7/14 的过滤器.
窗口 2022-01-01→今 (含灾难年); entries at signal close, no costs.
"""
import json, warnings
from datetime import datetime
from pathlib import Path
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import backtest_playbooks_2026 as bp
from backtest_playbooks_2026 import (add_indicators, download_all, get_universe, run_trades, summarize,
                                     pb7_entry, pb7_exit, cd1_entry, cd1_exit, cd6_entry, cd6_exit)
bp.DATA_START = "2020-01-01"
HERE = Path(__file__).parent
TODAY = datetime.now().strftime("%Y-%m-%d")
START = "2022-01-01"
LEVELS = [0.5, 0.618, 0.786, 0.886]


def add_swing(df):
    h, l = df["High"].values, df["Low"].values
    n = len(df)
    L, H = np.full(n, np.nan), np.full(n, np.nan)
    for i in range(252, n):
        seg = h[i - 252:i + 1]
        k = int(np.argmax(seg)); hi_i = i - 252 + k
        lo_start = max(0, hi_i - 252)
        if hi_i - lo_start < 20:
            continue
        lo = l[lo_start:hi_i + 1].min()
        if seg[k] / lo - 1 >= 0.30:
            L[i], H[i] = lo, seg[k]
    df["sw_lo"], df["sw_hi"] = L, H
    df["z786"] = df["sw_hi"] - 0.786 * (df["sw_hi"] - df["sw_lo"])
    df["lo20p"] = df["Low"].rolling(20).min().shift(1)
    return df


def in_zone(df, i):
    z = df["z786"].iloc[i]
    return (not np.isnan(z)) and df["Low"].iloc[i - 9:i + 1].min() <= z and df["Close"].iloc[i] > df["sw_lo"].iloc[i]


# ───────── A. fib-level event study ─────────
def fib_events(data):
    rows, base = [], []
    for t, df in data.items():
        c, l = df["Close"].values, df["Low"].values
        idx = df.index
        s_i = int(np.searchsorted(idx, pd.Timestamp(START)))
        for i in range(max(s_i, 260), len(df) - 1, 5):          # unconditional baseline (every 5th bar)
            base.append([c[min(i + k, len(c) - 1)] / c[i] - 1 if i + k < len(c) else np.nan for k in (20, 60, 120)])
        for lv in LEVELS:
            last_key = None
            for i in range(max(s_i, 260), len(df)):
                Lo, Hi = df["sw_lo"].iloc[i], df["sw_hi"].iloc[i]
                if np.isnan(Lo):
                    continue
                line = Hi - lv * (Hi - Lo)
                key = (round(Lo, 4), round(Hi, 4))
                if l[i] <= line < l[i - 1] and key != last_key and c[i] > Lo:   # first touch of this swing's level
                    last_key = key
                    fwd = {k: (c[i + k] / c[i] - 1 if i + k < len(c) else np.nan) for k in (20, 60, 120)}
                    w = c[i + 1:i + 121]
                    rows.append({"lv": lv, "t": t, **{f"f{k}": v for k, v in fwd.items()},
                                 "held": float(w.min() > Lo) if len(w) >= 60 else np.nan,
                                 "mae": float(l[i + 1:i + 121].min() / c[i] - 1) if len(w) >= 20 else np.nan})
    return pd.DataFrame(rows), np.array(base, dtype=float)


# ───────── C. SMC proxies ─────────
def sweep(df, i):
    p = df["lo20p"].iloc[i]
    return (not np.isnan(p)) and df["Low"].iloc[i] < p and df["Close"].iloc[i] > p and df["Close"].iloc[i] > df["Open"].iloc[i]

def smc_sweep_entry(df, i):
    return {"stop": float(df["Low"].iloc[i])} if sweep(df, i) else None

def smc_choch_entry(df, i):
    js = [j for j in range(i - 10, i) if sweep(df, j)]
    if not js:
        return None
    j = js[-1]
    lh = df["Close"].iloc[j - 10:j].max()                      # last lower-high proxy before the sweep
    if df["Close"].iloc[i] > lh and df["Close"].iloc[i - 1] <= lh:
        return {"stop": float(df["Low"].iloc[j])}
    return None

def smc_fvg_entry(df, i):
    # bullish FVG formed at bar k (low[k] > high[k-2]) within last 10 bars; today dips into gap and closes up above it
    for k in range(i - 10, i - 1):
        top, bot = df["Low"].iloc[k], df["High"].iloc[k - 2]
        if top > bot * 1.002 and df["Low"].iloc[k + 1:i].min() > top:       # untouched until today
            if df["Low"].iloc[i] <= top and df["Close"].iloc[i] > top and df["Close"].iloc[i] > df["Open"].iloc[i]:
                return {"stop": float(min(bot, df["Low"].iloc[i]))}
    return None

def smc_ob_entry(df, i):
    # bullish order block: last down candle before an impulse up-bar (body > 1.5 ATR) in prior 20 bars; first retest
    for k in range(i - 20, i - 2):
        o, c = df["Open"].iloc[k + 1], df["Close"].iloc[k + 1]
        if c - o > 1.5 * df["atr"].iloc[k + 1] and df["Close"].iloc[k] < df["Open"].iloc[k]:
            ob_hi, ob_lo = df["High"].iloc[k], df["Low"].iloc[k]
            if df["Low"].iloc[k + 2:i].min() > ob_hi and df["Low"].iloc[i] <= ob_hi and df["Close"].iloc[i] > ob_hi:
                return {"stop": float(ob_lo)}
    return None


def filt(entry, cond):
    return lambda df, i: (entry(df, i) if cond(df, i) else None)

def recent_sweep(df, i):
    return any(sweep(df, j) for j in range(i - 5, i + 1))


def stats(data, en, ex, name):
    trades = []
    for t, df in data.items():
        tr = run_trades(df, en, ex, name, start=START)
        for x in tr:
            x["ticker"] = t
        trades += tr
    s = summarize(trades)
    if not s:
        return f"| {name} | 0 | — | — | — | — | — |", None
    yr = {}
    for x in trades:
        yr.setdefault(x["entry_date"][:4], []).append(x["ret"])
    yrs = " · ".join(f"{y}:{np.mean(v):+.1%}" for y, v in sorted(yr.items()))
    return (f"| {name} | {s['n_trades']} | {s['win_rate']:.0%} | {s['avg_ret']:+.2%} | {s['median_ret']:+.2%} | "
            f"{s['profit_factor']:.2f} | {yrs} |"), s


def main():
    tickers, _ = get_universe()
    data = download_all(tickers)
    for t in list(data):
        data[t] = add_swing(add_indicators(data[t]))
    md = [f"# 机构买区 + SMC 抄底检验 ({START} → {TODAY}, {len(data)} tickers)", ""]

    ev, base = fib_events(data)
    md += ["## A. 大升浪(≥30%)后首次触及各 fib 回撤位 — 之后表现", "",
           "| 回撤位 | 事件数 | 20日均值/胜率 | 60日均值/胜率 | 120日均值/胜率 | 120日守住升浪起点 | 触及后平均再跌(MAE) |", "|---|---|---|---|---|---|---|"]
    for lv in LEVELS:
        e = ev[ev.lv == lv]
        cell = lambda k: f"{e[k].mean():+.1%} / {(e[k] > 0).mean():.0%}"
        md.append(f"| {lv} | {len(e)} | {cell('f20')} | {cell('f60')} | {cell('f120')} | {e.held.mean():.0%} | {e.mae.mean():+.1%} |")
    bm = np.nanmean(base, axis=0); bw = np.nanmean(base > 0, axis=0)
    md += [f"| 对照: 任意一天 | {len(base)} | {bm[0]:+.1%} / {bw[0]:.0%} | {bm[1]:+.1%} / {bw[1]:.0%} | {bm[2]:+.1%} / {bw[2]:.0%} | — | — |", ""]

    hdr = ["| 策略 | 交易 | 胜率 | 单笔均值 | 中位数 | PF | 逐年单笔均值 |", "|---|---|---|---|---|---|---|"]
    md += ["## B. 机构买区当辅助: 打法7/14/15 信号按是否在买区内分组", ""] + hdr
    for nm, en, ex in (("打法7 恐慌反转", pb7_entry, pb7_exit), ("打法14 MACD底背离", cd1_entry, cd1_exit), ("打法15 金针", cd6_entry, cd6_exit)):
        md.append(stats(data, en, ex, nm + " (全部)")[0])
        md.append(stats(data, filt(en, in_zone), ex, nm + " · 买区内")[0])
        md.append(stats(data, filt(en, lambda d, i: not in_zone(d, i)), ex, nm + " · 买区外")[0])
    md += ["", "## C. SMC 机械代理 — 单独入场 (离场同打法7: MA20/破信号低/15根)", ""] + hdr
    for nm, en in (("SMC 流动性猎杀 SWEEP", smc_sweep_entry), ("SMC SWEEP→CHoCH 结构转换", smc_choch_entry),
                   ("SMC 多头FVG回补", smc_fvg_entry), ("SMC 多头订单块OB回踩", smc_ob_entry)):
        md.append(stats(data, en, pb7_exit, nm)[0])
    md += ["", "## C2. SMC 当过滤器: 打法7/14 + 近5根出现 SWEEP", ""] + hdr
    for nm, en, ex in (("打法7", pb7_entry, pb7_exit), ("打法14", cd1_entry, cd1_exit)):
        md.append(stats(data, filt(en, recent_sweep), ex, nm + " + SWEEP")[0])
        md.append(stats(data, filt(en, lambda d, i: not recent_sweep(d, i)), ex, nm + " 无SWEEP")[0])
    out = "\n".join(md)
    (HERE / f"backtest_smc_bottom_{TODAY}.md").write_text(out, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
