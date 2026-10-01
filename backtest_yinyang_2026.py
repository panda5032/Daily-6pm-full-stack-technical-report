# -*- coding: utf-8 -*-
"""
Backtest: 用户阴阳量价规则 (2026-08-28)
  BUY  低位阳后缩量阴: 大跌背景 + 近3日像样阳线 + 当日缩量小阴 -> 买入收盘
  SELL 高位大阴后缩量阳: 大涨背景 + 近3日放量大阴 + 当日缩量阳 -> 做空收盘 (另附前瞻收益诊断)
口径与 backtest_playbooks_2026.py 一致: 收盘成交/无费用/单票满仓, 2024/2025/2026YTD 三窗口.
"""
import json, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")

from backtest_playbooks_2026 import (get_universe, download_all, add_indicators,
                                     run_trades, summarize, WINDOWS)

def prep(df):
    df = add_indicators(df)
    c, o, h, l, v = df["Close"], df["Open"], df["High"], df["Low"], df["Volume"]
    rng = (h - l).replace(0, np.nan)
    df["body"] = (c - o).abs() / rng
    df["up"] = c >= o
    df["chg"] = c.pct_change() * 100
    df["rvol"] = v / df["vol20"].shift(1)
    df["ret5"] = c.pct_change(5)
    return df

# ---- BUY leg ----
def buy_entry(df, i):
    if not ((df["ret20"].iloc[i] <= -0.10 or df["ret5"].iloc[i] <= -0.07)
            and df["Close"].iloc[i] < df["ma20"].iloc[i]):
        return None
    if df["up"].iloc[i] or df["rvol"].iloc[i] >= 0.85: return None
    if df["body"].iloc[i] > 0.6 or abs(df["chg"].iloc[i]) > 3.5: return None
    ok = False
    for j in (i-3, i-2, i-1):
        if df["up"].iloc[j] and (df["chg"].iloc[j] >= 1.5 or df["body"].iloc[j] >= 0.5):
            ok = True
    if not ok: return None
    return {"stop": float(df["Low"].iloc[i-5:i+1].min())}

def buy_exit(df, i, pos):
    c = df["Close"].iloc[i]
    return (c >= df["ma20"].iloc[i] or c < pos["stop"] or i - pos["entry_i"] >= 15)

# ---- SELL leg (short) ----
def sell_entry(df, i):
    if not ((df["ret20"].iloc[i] >= 0.12 or df["ret5"].iloc[i] >= 0.08)
            and df["Close"].iloc[i] > df["ma20"].iloc[i]):
        return None
    if (not df["up"].iloc[i]) or df["rvol"].iloc[i] >= 0.95: return None
    ok = False
    for j in (i-3, i-2, i-1):
        if ((not df["up"].iloc[j]) and df["body"].iloc[j] >= 0.55 and df["rvol"].iloc[j] >= 1.0
                and (df["chg"].iloc[j] <= -2.5 or (df["High"].iloc[j]-df["Low"].iloc[j]) >= 1.2*df["atr"].iloc[j])):
            ok = True
    if not ok: return None
    return {"stop": float(df["High"].iloc[i-5:i+1].max() + 0.5*df["atr"].iloc[i])}

def sell_exit(df, i, pos):
    c = df["Close"].iloc[i]
    return (c <= df["ma20"].iloc[i] or c > pos["stop"] or i - pos["entry_i"] >= 15)

def main():
    tickers, _ = get_universe()
    data = download_all(tickers)
    print(f"universe {len(tickers)} | data ok {len(data)}")
    data = {t: prep(df) for t, df in data.items()}

    out = {}
    for label, start, end in WINDOWS:
        # BUY leg
        bt = []
        for t, df in data.items():
            for tr in run_trades(df, buy_entry, buy_exit, "BUY", start=start, end=end):
                tr["ticker"] = t; bt.append(tr)
        # SELL leg (short: invert ret)
        st = []
        fwd = {5: [], 10: [], 20: []}
        for t, df in data.items():
            for tr in run_trades(df, sell_entry, sell_exit, "SELL", start=start, end=end):
                tr["ticker"] = t; tr["ret"] = -tr["ret"]; st.append(tr)
            # forward-return diagnostics on raw sell signals
            idx = df.index
            s_i = int(np.searchsorted(idx, pd.Timestamp(start)))
            e_i = len(df) if end is None else int(np.searchsorted(idx, pd.Timestamp(end)))
            for i in range(max(s_i, 210), e_i):
                if sell_entry(df, i) is not None:
                    for k in (5, 10, 20):
                        if i + k < len(df):
                            fwd[k].append(float(df["Close"].iloc[i+k]/df["Close"].iloc[i]-1))
        days = None
        out[label] = {"BUY": summarize(bt), "SELL_short": summarize(st),
                      "SELL_fwd": {k: (float(np.mean(v)), float(np.median(v)), len(v)) for k, v in fwd.items() if v}}
        b, s = out[label]["BUY"], out[label]["SELL_short"]
        print(f"\n== {label} ==")
        if b: print(f"BUY  n={b['n_trades']} win={b['win_rate']:.0%} avg={b['avg_ret']:+.2%} PF={b['profit_factor']:.2f} 每票复利={b['avg_ticker_ytd']:+.2%} avg_days={b['avg_days']:.1f}")
        else: print("BUY  无交易")
        if s: print(f"SELL(做空) n={s['n_trades']} win={s['win_rate']:.0%} avg={s['avg_ret']:+.2%} PF={s['profit_factor']:.2f} 每票复利={s['avg_ticker_ytd']:+.2%}")
        else: print("SELL 无交易")
        for k, (m, md, n) in out[label]["SELL_fwd"].items():
            print(f"  SELL信号后{k}日 标的自身收益: mean {m:+.2%} / median {md:+.2%} (n={n})")

    json.dump(out, open("backtest_yinyang_2026-08-28.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=str)
    print("\nsaved backtest_yinyang_2026-08-28.json")

if __name__ == "__main__":
    main()
