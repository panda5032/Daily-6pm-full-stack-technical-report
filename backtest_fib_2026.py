# -*- coding: utf-8 -*-
"""
Fibonacci 回撤打法回测 2026-08-28 (口径同 backtest_playbooks_2026)
波段定义: 近90根内 hi=最高高点, lo=hi之前的最低低点, 涨幅>=15%
入场: 价格回撤进指定 fib 档 (±1.5% 容差) 且当日反包 (收>昨高), 收盘价成交
  F382 回撤38.2% / F500 50% / F618 61.8% / FZONE 38.2-61.8 任意档
离场两种:
  T版: 目标=前波段高点, 止损=78.6%位下方, 25根时间止损  (fib 教科书版)
  M版: 跟踪 MA20 — 首次收破 MA20 离场, 止损同上          (吃右尾版)
附 MA200 质量闸变体 (FZONE_G)。
"""
import json, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")

from backtest_playbooks_2026 import (get_universe, download_all, add_indicators,
                                     run_trades, summarize, WINDOWS)

LOOKBACK = 90
MIN_SWING = 0.15
TOL = 0.015

def prep(df):
    df = add_indicators(df)
    return df

def swing(df, i):
    """return (lo, hi) of the most recent upswing ending in lookback, else None"""
    h = df["High"].iloc[i - LOOKBACK:i + 1]
    hi_pos = int(np.argmax(h.values))
    hi = float(h.iloc[hi_pos])
    if hi_pos < 10:  # swing high too old is fine, too близко к началу окна нет lo
        return None
    l = df["Low"].iloc[i - LOOKBACK:i - LOOKBACK + hi_pos + 1]
    lo = float(l.min())
    if lo <= 0 or hi / lo - 1 < MIN_SWING:
        return None
    # price must currently be below the swing high (pulling back), above the lo
    c = float(df["Close"].iloc[i])
    if c >= hi or c <= lo:
        return None
    return lo, hi

def fib_entry_factory(levels):
    def entry(df, i):
        s = swing(df, i)
        if s is None: return None
        lo, hi = s
        rng = hi - lo
        c = float(df["Close"].iloc[i])
        in_zone = False
        for lv in levels:
            px = hi - rng * lv
            if abs(c / px - 1) <= TOL:
                in_zone = True
        if isinstance(levels, tuple) and len(levels) == 2 and not in_zone:
            z_hi = hi - rng * levels[0]; z_lo = hi - rng * levels[1]
            in_zone = z_lo <= c <= z_hi
        if not in_zone: return None
        if df["Close"].iloc[i] <= df["High"].iloc[i - 1]:  # need reversal bar
            return None
        stop = hi - rng * 0.786
        return {"stop": float(stop), "target": float(hi)}
    return entry

def exit_T(df, i, pos):
    c = float(df["Close"].iloc[i])
    return (c >= pos["target"] or c < pos["stop"] or i - pos["entry_i"] >= 25)

def exit_M(df, i, pos):
    c = float(df["Close"].iloc[i])
    return (c < pos["stop"] or c < df["ma20"].iloc[i] * 0.995 and i - pos["entry_i"] >= 2)

def gate200(entry_fn):
    def g(df, i):
        if df["Close"].iloc[i] <= df["ma200"].iloc[i]: return None
        return entry_fn(df, i)
    return g

def main():
    tickers, _ = get_universe()
    data = download_all(tickers)
    print(f"universe {len(tickers)} | data ok {len(data)}")
    data = {t: prep(df) for t, df in data.items()}

    ez = fib_entry_factory((0.382, 0.618))
    variants = [
        ("F382_T",  fib_entry_factory([0.382]), exit_T),
        ("F500_T",  fib_entry_factory([0.5]),   exit_T),
        ("F618_T",  fib_entry_factory([0.618]), exit_T),
        ("FZONE_T", ez, exit_T),
        ("FZONE_M", ez, exit_M),
        ("FZONE_G_T", gate200(ez), exit_T),
        ("FZONE_G_M", gate200(ez), exit_M),
    ]
    out = {}
    for label, start, end in WINDOWS:
        out[label] = {}
        print(f"\n== {label} ==")
        for name, efn, xfn in variants:
            trades = []
            for t, df in data.items():
                for tr in run_trades(df, efn, xfn, name, start=start, end=end):
                    tr["ticker"] = t; trades.append(tr)
            s = summarize(trades)
            out[label][name] = s
            if s:
                print(f"{name:10s} n={s['n_trades']:4d} win={s['win_rate']:.0%} avg={s['avg_ret']:+.2%} "
                      f"PF={s['profit_factor']:.2f} 每票复利={s['avg_ticker_ytd']:+.2%} days={s['avg_days']:.1f}")
            else:
                print(f"{name:10s} 无交易")
    json.dump(out, open("backtest_fib_2026-08-28.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=str)
    print("\nsaved backtest_fib_2026-08-28.json")

if __name__ == "__main__":
    main()
