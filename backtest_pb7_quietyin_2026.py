# -*- coding: utf-8 -*-
"""
Combo backtest 2026-08-28: 打法7洗仓背景 × 用户缩量阴入场
  A pb7原版: 恐慌(收<下轨 & RSI<32, 近5日) + 反包阳(收>昨高) 入场
  B 7+缩量阴: 恐慌(近8日) -> 其后出现过阳线 -> 当日缩量小阴 入场
  C = B + MA200质量闸 (收盘价在MA200上方)
  D = B 但入场后等次日确认? (不做, 保持三版)
退出统一 pb7: 到达MA20 / 破序列低点 / 15根时间止损。口径同 backtest_playbooks_2026。
"""
import json, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")

from backtest_playbooks_2026 import (get_universe, download_all, add_indicators,
                                     run_trades, summarize, WINDOWS,
                                     pb7_entry, pb7_exit)

def prep(df):
    df = add_indicators(df)
    c, o, h, l, v = df["Close"], df["Open"], df["High"], df["Low"], df["Volume"]
    rng = (h - l).replace(0, np.nan)
    df["body"] = (c - o).abs() / rng
    df["up"] = c >= o
    df["chg"] = c.pct_change() * 100
    df["rvol"] = v / df["vol20"].shift(1)
    return df

def combo_entry(df, i):
    # 当日 = 缩量小阴
    if df["up"].iloc[i] or df["rvol"].iloc[i] >= 0.85: return None
    if df["body"].iloc[i] > 0.6 or abs(df["chg"].iloc[i]) > 3.5: return None
    # 近8日内有打法7级恐慌bar
    cap = None
    for j in range(i-8, i):
        if df["Close"].iloc[j] < df["bb_lo"].iloc[j] and df["rsi"].iloc[j] < 32:
            cap = j
    if cap is None: return None
    # 恐慌之后出现过像样阳线
    ok = any(df["up"].iloc[j] and (df["chg"].iloc[j] >= 1.5 or df["body"].iloc[j] >= 0.5)
             for j in range(cap+1, i))
    if not ok: return None
    return {"stop": float(df["Low"].iloc[i-8:i+1].min())}

def combo_exit(df, i, pos):
    c = df["Close"].iloc[i]
    return (c >= df["ma20"].iloc[i] or c < pos["stop"] or i - pos["entry_i"] >= 15)

def gated_entry(df, i):
    if df["Close"].iloc[i] <= df["ma200"].iloc[i]: return None
    return combo_entry(df, i)

def main():
    tickers, _ = get_universe()
    data = download_all(tickers)
    print(f"universe {len(tickers)} | data ok {len(data)}")
    data = {t: prep(df) for t, df in data.items()}

    variants = [("A_pb7原版", pb7_entry, pb7_exit),
                ("B_7+缩量阴", combo_entry, combo_exit),
                ("C_B+MA200闸", gated_entry, combo_exit)]
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
                print(f"{name:12s} n={s['n_trades']:4d} win={s['win_rate']:.0%} avg={s['avg_ret']:+.2%} "
                      f"PF={s['profit_factor']:.2f} 每票复利={s['avg_ticker_ytd']:+.2%} days={s['avg_days']:.1f}")
            else:
                print(f"{name:12s} 无交易")
    json.dump(out, open("backtest_pb7_quietyin_2026-08-28.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=str)
    print("\nsaved backtest_pb7_quietyin_2026-08-28.json")

if __name__ == "__main__":
    main()
