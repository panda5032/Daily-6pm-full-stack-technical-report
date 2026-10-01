# -*- coding: utf-8 -*-
"""
金叉确认天数实证 2026-08-28: 打法13 入场时点消融
对全池 2024-01 起的所有 MA50/200 金叉:
  - whipsaw 率: 金叉后 10/20/40 交易日内重新死叉的比例
  - 入场延迟 L∈{0,1,3,5,10}: 金叉后第 L 天收盘进, 死叉收盘出 (打法13 原始出场)
    比较 avg/每票复利/PF/胜率; L 天内已重新死叉的信号 = 跳过(这就是'确认'滤掉的部分)
"""
import json, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
from backtest_playbooks_2026 import get_universe, download_all, summarize

def main():
    tickers, _ = get_universe()
    data = download_all(tickers)
    print(f"universe {len(tickers)} | data ok {len(data)}")

    events = []  # (ticker, cross_idx, df)
    for t, df in data.items():
        c = df["Close"]
        ma50 = c.rolling(50).mean(); ma200 = c.rolling(200).mean()
        df = df.assign(ma50=ma50, ma200=ma200)
        gold = (ma50 > ma200)
        prev = gold.shift(1).fillna(False).astype(bool)
        cross = gold & (~prev)
        idxs = [i for i, x in enumerate(cross.values) if x and df.index[i] >= pd.Timestamp("2024-01-01")]
        for i in idxs:
            events.append((t, i, df))
    print(f"golden crosses since 2024: {len(events)}")

    # whipsaw rate
    for H in (10, 20, 40):
        n, whip = 0, 0
        for t, i, df in events:
            if i + H >= len(df): continue
            n += 1
            seg = df.iloc[i+1:i+1+H]
            if (seg["ma50"] < seg["ma200"]).any(): whip += 1
        print(f"whipsaw(重新死叉) within {H}d: {whip}/{n} = {whip/n:.0%}")

    # entry-lag ablation
    print(f"\n{'lag':>4} {'n':>5} {'skipped':>7} {'win':>5} {'avg':>8} {'PF':>6} {'每票复利':>9} {'avg_days':>8}")
    for L in (0, 1, 3, 5, 10):
        trades = []
        for t, i, df in events:
            j = i + L
            if j >= len(df) - 1: continue
            seg = df.iloc[i+1:j+1]
            if L > 0 and (seg["ma50"] < seg["ma200"]).any():
                continue  # already whipsawed before confirmation day -> signal filtered
            entry = float(df["Close"].iloc[j])
            # exit at death cross after j, else mark to end
            dead = None
            g = (df["ma50"] > df["ma200"]).values
            for k in range(j+1, len(df)):
                if not g[k]: dead = k; break
            k = dead if dead is not None else len(df) - 1
            trades.append({"ticker": t, "ret": float(df["Close"].iloc[k]/entry - 1),
                           "days": k - j, "exit_date": "X", "strategy": f"L{L}"})
        s = summarize(trades)
        skipped = len(events) - len(trades)
        if s:
            print(f"{L:>4} {s['n_trades']:>5} {skipped:>7} {s['win_rate']:>5.0%} {s['avg_ret']:>+8.2%} "
                  f"{s['profit_factor']:>6.2f} {s['avg_ticker_ytd']:>+9.2%} {s['avg_days']:>8.1f}")

if __name__ == "__main__":
    main()
