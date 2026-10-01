# -*- coding: utf-8 -*-
"""
机构卖区 (institutional sell zone) 能不能辅助见顶?  (2026-09-19)
卖区 = 前一段大跌 H→L (跌幅>=30%) 的 .786–.826 反弹带 (头顶供给区), 与买区对称.

A. 事件研究: 大跌后首次反弹触及 .5/.618/.786/.886 — 之后 20/60/120 日收益/下跌率,
   120日内未收复前高 H 的比例("被压回率"), 触及后平均还能再涨多少(MFE). 对照: 任意一天.
B. 见顶信号 × 卖区: 逃顶五式 + 打法8离场触发(放量收破MA20) 按是否在卖区内分组, 看之后 20 日.
C. 趋势打法 (1/8/16) 叠加:
   C1 到卖区止盈: 持仓中首次触及 .786 线即离场
   C2 卖区+见顶信号才离场
   C3 卖区禁买闸: 价格处于卖区下沿~前高之间 (.786~1.0) 不开新仓 (类似 M顶闸)
窗口 2022-01-01→今; entries at signal close, no costs.
"""
import warnings
from datetime import datetime
from pathlib import Path
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import backtest_playbooks_2026 as bp
from backtest_playbooks_2026 import (add_indicators, download_all, get_universe, run_trades, summarize,
                                     pb1_entry, pb1_exit, pb8_entry, pb8_exit, TOPSIGS)
from backtest_pb16_2026 import add_pb16_indicators
from backtest_pb16_gate_2026 import i_entry as pb16_entry
from backtest_pb16_pure_2026 import chart_exit as pb16_exit
bp.DATA_START = "2020-01-01"
HERE = Path(__file__).parent
TODAY = datetime.now().strftime("%Y-%m-%d")
START = "2022-01-01"
LEVELS = [0.5, 0.618, 0.786, 0.886]


def add_downswing(df):
    h, l = df["High"].values, df["Low"].values
    n = len(df)
    dl, dh = np.full(n, np.nan), np.full(n, np.nan)
    for i in range(252, n):
        seg = l[i - 252:i + 1]
        k = i - 252 + int(np.argmin(seg))
        hs = max(0, k - 252)
        if k - hs < 20:
            continue
        H = h[hs:k + 1].max()
        if (H - l[k]) / H >= 0.30:
            dl[i], dh[i] = l[k], H
    df["dn_lo"], df["dn_hi"] = dl, dh
    df["s786"] = df["dn_lo"] + 0.786 * (df["dn_hi"] - df["dn_lo"])
    return df


def in_sell_zone(df, i):
    z = df["s786"].iloc[i]
    return (not np.isnan(z)) and df["High"].iloc[i - 9:i + 1].max() >= z and df["Close"].iloc[i] < df["dn_hi"].iloc[i]


def under_supply(df, i):          # price sitting between the .786 line and the prior high
    z = df["s786"].iloc[i]
    return (not np.isnan(z)) and z <= df["Close"].iloc[i] < df["dn_hi"].iloc[i]


def fwd(c, i, ks=(20, 60, 120)):
    return {k: (c[i + k] / c[i] - 1 if i + k < len(c) else np.nan) for k in ks}


def level_events(data):
    rows, base = [], []
    for t, df in data.items():
        c, h = df["Close"].values, df["High"].values
        s_i = max(int(np.searchsorted(df.index, pd.Timestamp(START))), 260)
        for i in range(s_i, len(df) - 1, 5):
            base.append(list(fwd(c, i).values()))
        for lv in LEVELS:
            last = None
            for i in range(s_i, len(df)):
                Lo, Hi = df["dn_lo"].iloc[i], df["dn_hi"].iloc[i]
                if np.isnan(Lo):
                    continue
                line = Lo + lv * (Hi - Lo)
                key = (round(Lo, 4), round(Hi, 4))
                if h[i] >= line > h[i - 1] and key != last and c[i] < Hi:
                    last = key
                    w = c[i + 1:i + 121]
                    rows.append({"lv": lv, **{f"f{k}": v for k, v in fwd(c, i).items()},
                                 "capped": float(w.max() < Hi) if len(w) >= 60 else np.nan,
                                 "mfe": float(h[i + 1:i + 121].max() / c[i] - 1) if len(w) >= 20 else np.nan})
    return pd.DataFrame(rows), np.array(base, dtype=float)


def signal_split(data):
    sigs = dict(TOPSIGS)
    sigs["打法8离场触发(放量破MA20)"] = lambda df, i: (df["Close"].iloc[i] < df["ma20"].iloc[i] <= df["Close"].iloc[i - 1]
                                                   and df["Volume"].iloc[i] >= 1.2 * df["vol20"].iloc[i])
    out = {}
    for t, df in data.items():
        c = df["Close"].values
        s_i = max(int(np.searchsorted(df.index, pd.Timestamp(START))), 260)
        for i in range(s_i, len(df) - 20):
            z = in_sell_zone(df, i)
            for nm, sg in sigs.items():
                try:
                    hit = sg(df, i)
                except Exception:
                    hit = False
                if hit:
                    out.setdefault((nm, z), []).append(c[i + 20] / c[i] - 1)
            out.setdefault(("任意一天", z), []).append(c[i + 20] / c[i] - 1)
    return out


def stats(data, en, ex, name):
    trades = []
    for t, df in data.items():
        tr = run_trades(df, en, ex, name, start=START)
        for x in tr:
            x["ticker"] = t
        trades += tr
    s = summarize(trades)
    if not s:
        return f"| {name} | 0 | — | — | — | — | — |"
    yr = {}
    for x in trades:
        yr.setdefault(x["entry_date"][:4], []).append(x["ret"])
    yrs = " · ".join(f"{y}:{np.mean(v):+.1%}" for y, v in sorted(yr.items()))
    tk = s["avg_ticker_ytd"]
    return (f"| {name} | {s['n_trades']} | {s['win_rate']:.0%} | {s['avg_ret']:+.2%} | {s['profit_factor']:.2f} | "
            f"{tk:+.1%} | {yrs} |")


def any_top(df, i):
    for sg in TOPSIGS.values():
        try:
            if sg(df, i):
                return True
        except Exception:
            pass
    return False


def main():
    tickers, _ = get_universe()
    data = download_all(tickers)
    for t in list(data):
        data[t] = add_downswing(add_pb16_indicators(add_indicators(data[t])))
    md = [f"# 机构卖区见顶检验 ({START} → {TODAY}, {len(data)} tickers)", ""]

    ev, base = level_events(data)
    md += ["## A. 大跌(≥30%)后首次反弹触及各回撤位 — 之后表现", "",
           "| 反弹位 | 事件数 | 20日均值/下跌率 | 60日均值/下跌率 | 120日均值/下跌率 | 120日未收复前高 | 触及后平均还能涨(MFE) |", "|---|---|---|---|---|---|---|"]
    for lv in LEVELS:
        e = ev[ev.lv == lv]
        cell = lambda k: f"{e[k].mean():+.1%} / {(e[k] < 0).mean():.0%}"
        md.append(f"| {lv} | {len(e)} | {cell('f20')} | {cell('f60')} | {cell('f120')} | {e.capped.mean():.0%} | {e.mfe.mean():+.1%} |")
    bm = np.nanmean(base, axis=0); bd = np.nanmean(base < 0, axis=0)
    md += [f"| 对照: 任意一天 | {len(base)} | {bm[0]:+.1%} / {bd[0]:.0%} | {bm[1]:+.1%} / {bd[1]:.0%} | {bm[2]:+.1%} / {bd[2]:.0%} | — | — |", ""]

    sp = signal_split(data)
    md += ["## B. 见顶信号 × 卖区 — 信号后 20 日", "", "| 信号 | 卖区内 n | 区内 均值/下跌率 | 卖区外 n | 区外 均值/下跌率 |", "|---|---|---|---|---|"]
    for nm in sorted({k[0] for k in sp}):
        a, b = np.array(sp.get((nm, True), [])), np.array(sp.get((nm, False), []))
        f = lambda v: f"{v.mean():+.1%} / {(v < 0).mean():.0%}" if len(v) else "—"
        md.append(f"| {nm} | {len(a)} | {f(a)} | {len(b)} | {f(b)} |")
    md.append("")

    hdr = ["| 策略 | 交易 | 胜率 | 单笔均值 | PF | 每票复利均值 | 逐年单笔均值 |", "|---|---|---|---|---|---|---|"]
    md += ["## C. 趋势打法叠加卖区规则", ""] + hdr
    for nm, en, ex in (("打法8 带行持有", pb8_entry, pb8_exit), ("打法1 回踩企稳", pb1_entry, pb1_exit), ("打法16 纯图双闸", pb16_entry, pb16_exit)):
        md.append(stats(data, en, ex, nm + " (基线)"))
        md.append(stats(data, en, lambda d, i, p, ex=ex: ex(d, i, p) or (in_sell_zone(d, i) and not in_sell_zone(d, p["entry_i"])), nm + " +C1 到卖区止盈"))
        md.append(stats(data, en, lambda d, i, p, ex=ex: ex(d, i, p) or (in_sell_zone(d, i) and any_top(d, i)), nm + " +C2 卖区且见顶信号离场"))
        md.append(stats(data, lambda d, i, en=en: None if under_supply(d, i) else en(d, i), ex, nm + " +C3 卖区禁买闸"))
        md.append(stats(data, lambda d, i, en=en: en(d, i) if under_supply(d, i) else None, ex, nm + " · 只看卖区内开的仓"))
    out = "\n".join(md)
    (HERE / f"backtest_sellzone_top_{TODAY}.md").write_text(out, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
