# -*- coding: utf-8 -*-
"""
全打法组合研究 2026-08-30
8 条袖: PB1回踩企稳 PB2平台突破 PB7恐慌反转 PB8带行 PB13金叉 PB14底背离(cd1) PB15金针(cd6) PB16p W双底(cd3)
每袖 = 逐日收益流(袖内活跃仓等权, 无仓=现金0)。
组合测试: 单袖 / 全等权 / 趋势篮 / 抄底篮 / QQQ-MA50状态切换 / 3000组Dirichlet随机权重搜索。
指标: 2024-2026总复利, 分年, maxDD, 收益/回撤比, 平均敞口。
"""
import json, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import yfinance as yf
from backtest_playbooks_2026 import (get_universe, download_all, add_indicators,
                                     pb1_entry, pb1_exit, pb2_entry, pb2_exit,
                                     pb7_entry, pb7_exit, pb8_entry, pb8_exit,
                                     cd1_entry, cd1_exit, cd3_entry, cd3_exit,
                                     cd6_entry, cd6_exit)

START = pd.Timestamp("2024-01-01")

def daily_mask(df, entry_fn, exit_fn):
    """active-position mask per run_trades semantics: enter close of bar i -> active i+1..exit bar."""
    n = len(df); mask = np.zeros(n, dtype=bool); pos = None
    for i in range(210, n):
        if pos is None:
            e = entry_fn(df, i)
            if e is not None:
                pos = {"entry_i": i, "entry": float(df["Close"].iloc[i]), **e}
        else:
            mask[i] = True
            if exit_fn(df, i, pos):
                pos = None
    return mask

def pb13_mask(df):
    c = df["Close"]; g = (c.rolling(50).mean() > c.rolling(200).mean()).values
    m = np.zeros(len(df), dtype=bool); m[1:] = g[:-1]  # hold while golden (enter close of cross day)
    m[:211] = False
    return m

SLEEVES = [("PB1", pb1_entry, pb1_exit), ("PB2", pb2_entry, pb2_exit),
           ("PB7", pb7_entry, pb7_exit), ("PB8", pb8_entry, pb8_exit),
           ("PB14", cd1_entry, cd1_exit), ("PB15", cd6_entry, cd6_exit),
           ("PB16p", cd3_entry, cd3_exit)]

def main():
    tickers, _ = get_universe()
    data = download_all(tickers)
    print(f"data ok {len(data)}")
    # master calendar from QQQ
    qqq = yf.download("QQQ", start="2023-06-01", interval="1d", auto_adjust=True, progress=False)
    if isinstance(qqq.columns, pd.MultiIndex): qqq.columns = qqq.columns.get_level_values(0)
    cal = qqq.index[qqq.index >= START]
    regime_trend = (qqq["Close"] > qqq["Close"].rolling(50).mean()).reindex(cal).fillna(True).values

    names = [s[0] for s in SLEEVES] + ["PB13"]
    # build sleeve daily returns aligned to cal
    sums = {nm: np.zeros(len(cal)) for nm in names}
    cnts = {nm: np.zeros(len(cal)) for nm in names}
    for t, df in data.items():
        df = add_indicators(df)
        ret = df["Close"].pct_change().values
        pos_idx = df.index.get_indexer(cal)  # -1 where missing
        masks = {nm: daily_mask(df, e, x) for nm, e, x in SLEEVES}
        masks["PB13"] = pb13_mask(df)
        for nm, m in masks.items():
            for k, j in enumerate(pos_idx):
                if j > 0 and m[j] and not np.isnan(ret[j]):
                    sums[nm][k] += ret[j]; cnts[nm][k] += 1
    sleeve_ret = {nm: np.where(cnts[nm] > 0, sums[nm] / np.maximum(cnts[nm], 1), 0.0) for nm in names}
    exposure = {nm: float((cnts[nm] > 0).mean()) for nm in names}

    def stats(r):
        eq = np.cumprod(1 + r)
        mdd = float(np.min(eq / np.maximum.accumulate(eq)) - 1)
        yrs = {}
        years = pd.Series(cal.year)
        for y in (2024, 2025, 2026):
            sel = (years == y).values
            yrs[y] = float(np.prod(1 + r[sel]) - 1)
        tot = float(eq[-1] - 1)
        return tot, yrs, mdd, (tot / abs(mdd) if mdd < 0 else float("inf"))

    print(f"\n{'combo':28s} {'total':>8} {'2024':>8} {'2025':>8} {'2026':>8} {'maxDD':>7} {'ret/DD':>7}")
    def show(name, r):
        tot, yrs, mdd, rdd = stats(r)
        print(f"{name:28s} {tot:>+8.1%} {yrs[2024]:>+8.1%} {yrs[2025]:>+8.1%} {yrs[2026]:>+8.1%} {mdd:>7.1%} {rdd:>7.2f}")
        return tot, mdd, rdd

    R = np.vstack([sleeve_ret[nm] for nm in names])  # sleeves x days
    for nm in names:
        show(f"单袖 {nm} (敞口{exposure[nm]:.0%})", sleeve_ret[nm])

    ew = R.mean(axis=0); show("全等权(8袖)", ew)
    trend_i = [names.index(x) for x in ("PB1", "PB2", "PB8", "PB13", "PB16p")]
    bottom_i = [names.index(x) for x in ("PB7", "PB14", "PB15")]
    tr = R[trend_i].mean(axis=0); bo = R[bottom_i].mean(axis=0)
    show("趋势篮(1/2/8/13/16p)", tr)
    show("抄底篮(7/14/15)", bo)
    sw = np.where(regime_trend, tr, bo); show("状态切换(QQQ>MA50→趋势)", sw)
    sw2 = np.where(regime_trend, 0.8 * tr + 0.2 * bo, 0.2 * tr + 0.8 * bo)
    show("软切换(80/20)", sw2)

    # random weight search
    rng = np.random.default_rng(42)
    best_tot, best_rdd = [], []
    for _ in range(3000):
        w = rng.dirichlet(np.ones(len(names)) * 0.5)
        r = w @ R
        tot, yrs, mdd, rdd = stats(r)
        best_tot.append((tot, rdd, w)); best_rdd.append((rdd, tot, w))
    best_tot.sort(key=lambda x: -x[0]); best_rdd.sort(key=lambda x: -x[0])
    print("\n随机搜索 top3 (按总复利):")
    for tot, rdd, w in best_tot[:3]:
        ws = " ".join(f"{nm}:{v:.0%}" for nm, v in zip(names, w) if v >= 0.05)
        print(f"  total {tot:+.1%} ret/DD {rdd:.2f} | {ws}")
    print("随机搜索 top3 (按收益/回撤):")
    for rdd, tot, w in best_rdd[:3]:
        ws = " ".join(f"{nm}:{v:.0%}" for nm, v in zip(names, w) if v >= 0.05)
        print(f"  ret/DD {rdd:.2f} total {tot:+.1%} | {ws}")

    json.dump({nm: list(map(float, sleeve_ret[nm])) for nm in names},
              open("combo_sleeves_2026-08-30.json", "w"), indent=0)
    print("\nsaved combo_sleeves_2026-08-30.json")

if __name__ == "__main__":
    main()
