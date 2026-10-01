"""
打法16 形态+量能+MACD 三重确认 — backtest vs the existing playbook stable.

Entry (all three pillars on the signal bar):
  1. 形态: W双底颈线突破 OR fresh 20d-high platform breakout
  2. 量能: volume >= 1.5x 20d avg AND OBV above its 20d MA
  3. MACD: golden alignment (MACD > signal) with expanding histogram
Exit: MACD dead cross, or heavy-volume close below MA20, or stop
  (signal-bar low - 0.5*ATR; W-bottom uses trough2).
打法16b 双重确认: same pattern trigger + (volume OR MACD) confirmation.

Windows: 2024 / 2025 / 2026 YTD / 3年累计(2024-01-01→today), all playbooks
from backtest_playbooks_2026 re-run alongside for a same-data comparison.
Signals research only — not financial advice, no live orders.
"""

import json
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from backtest_playbooks_2026 import (  # noqa: E402
    PLAYBOOKS, add_indicators, bench_returns, download_all, get_universe,
    rotation_backtest, run_trades, summarize,
)

HERE = Path(__file__).parent
TODAY = datetime.now().strftime("%Y-%m-%d")

WINDOWS = [
    ("2024",       "2024-01-01", "2025-01-01"),
    ("2025",       "2025-01-01", "2026-01-01"),
    ("2026 YTD",   "2026-01-01", None),
    ("3年累计",     "2024-01-01", None),
]


def add_pb16_indicators(df):
    df["hist"] = df["macd"] - df["macds"]
    step = np.sign(df["Close"].diff()).fillna(0) * df["Volume"]
    df["obv"] = step.cumsum()
    df["obv20"] = df["obv"].rolling(20).mean()
    return df


def _w_bottom(df, i):
    c = df["Close"]
    seg2 = c.iloc[i - 15:i - 2]
    if len(seg2) < 5:
        return None
    j2 = i - 15 + int(np.argmin(seg2.values))
    seg1 = c.iloc[i - 60:j2 - 7]
    if len(seg1) < 10:
        return None
    j1 = i - 60 + int(np.argmin(seg1.values))
    t1, t2 = float(c.iloc[j1]), float(c.iloc[j2])
    neck = float(c.iloc[j1:j2 + 1].max())
    if (t2 >= t1 * 0.97 and neck > t2 * 1.03
            and c.iloc[i] > neck and c.iloc[i - 1] <= neck):
        return {"stop": t2, "pat": "W双底"}
    return None


def _plat_break(df, i):
    if (not np.isnan(df["hi20"].iloc[i])
            and df["Close"].iloc[i] > df["hi20"].iloc[i]
            and df["Close"].iloc[i - 1] <= df["hi20"].iloc[i - 1]):
        return {"stop": float(df["Low"].iloc[i] - 0.5 * df["atr"].iloc[i]),
                "pat": "平台突破"}
    return None


def _vol_ok(df, i):
    return (df["Volume"].iloc[i] >= 1.5 * df["vol20"].iloc[i]
            and df["obv"].iloc[i] > df["obv20"].iloc[i])


def _macd_ok(df, i):
    return (df["macd"].iloc[i] > df["macds"].iloc[i]
            and df["hist"].iloc[i] > df["hist"].iloc[i - 1])


def pb16_entry(df, i):
    if not (_vol_ok(df, i) and _macd_ok(df, i)):
        return None
    return _w_bottom(df, i) or _plat_break(df, i)


def pb16b_entry(df, i):
    if not (_vol_ok(df, i) or _macd_ok(df, i)):
        return None
    return _w_bottom(df, i) or _plat_break(df, i)


def pb16_exit(df, i, pos):
    c = df["Close"].iloc[i]
    dead = (df["macd"].iloc[i] < df["macds"].iloc[i]
            and df["macd"].iloc[i - 1] >= df["macds"].iloc[i - 1])
    heavy_break = (c < df["ma20"].iloc[i]
                   and df["Volume"].iloc[i] >= 1.2 * df["vol20"].iloc[i])
    return dead or heavy_break or c < pos["stop"]


NEW_PLAYBOOKS = {
    "打法16 三重确认(形+量+MACD)": (pb16_entry, pb16_exit),
    "打法16b 双重确认(形+量或MACD)": (pb16b_entry, pb16_exit),
}


def main():
    tickers, _ = get_universe()
    print(f"universe: {len(tickers)} tickers")
    data = download_all(tickers)
    print(f"data ok: {len(data)} tickers")
    for t in data:
        data[t] = add_pb16_indicators(add_indicators(data[t]))

    all_pb = {**NEW_PLAYBOOKS, **PLAYBOOKS}
    out = {"asof": TODAY, "universe_size": len(data), "windows": {}}
    md = [f"# 打法16 三重确认 回测对比 2024 / 2025 / 2026 YTD / 3年累计 (as of {TODAY})",
          f"universe: {len(data)} tickers · entries at signal-bar close · no costs/slippage",
          "· 打法16: W双底/平台突破 + 放量1.5x&OBV在均线上 + MACD金叉红柱扩张; "
          "离场=MACD死叉/放量破MA20/止损", ""]

    for label, start, end in WINDOWS:
        results = {}
        for name, (efn, xfn) in all_pb.items():
            trades = []
            for t, df in data.items():
                for tr in run_trades(df, efn, xfn, name, start, end):
                    tr["ticker"] = t
                    trades.append(tr)
            results[name] = summarize(trades)
            if name in NEW_PLAYBOOKS:
                results[name + "__trades"] = trades
            n = results[name]["n_trades"] if results[name] else 0
            print(f"  [{label}] {name}: {n} trades")
        rot = rotation_backtest(data, start, end)
        bench = bench_returns(data, start, end)
        out["windows"][label] = {
            "results": {k: v for k, v in results.items() if not k.endswith("__trades")},
            "pb16_trades": results.get("打法16 三重确认(形+量+MACD)__trades", []),
            "pb16b_trades": results.get("打法16b 双重确认(形+量或MACD)__trades", []),
            "rotation_打法3": {"ret": rot["ytd_return"]} if rot else None,
            "benchmarks": bench,
        }

        md += [f"## {label} ({start} → {end or TODAY})", "",
               "| 打法 | 交易数 | 胜率 | 平均单笔 | 中位数 | 盈亏比PF | 平均持仓天 | 每票复利均值 |",
               "|---|---|---|---|---|---|---|---|"]
        for name in all_pb:
            s = results[name]
            if not s:
                md.append(f"| {name} | 0 | — | — | — | — | — | — |")
                continue
            md.append(f"| {name} | {s['n_trades']} | {s['win_rate']:.0%} | {s['avg_ret']:+.2%} | "
                      f"{s['median_ret']:+.2%} | {s['profit_factor']:.2f} | {s['avg_days']:.0f} | "
                      f"{s['avg_ticker_ytd']:+.2%} |")
        if rot:
            md.append(f"\n**打法3 强弱轮动 (top-10动量, 20日调仓)**: **{rot['ytd_return']:+.2%}**")
        md.append("\n基准: " + " · ".join(f"{b} {r:+.2%}" for b, r in bench.items()))
        md.append("")
        print(f"[{label}] done")

    (HERE / f"backtest_pb16_{TODAY}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (HERE / f"backtest_pb16_{TODAY}.md").write_text("\n".join(md), encoding="utf-8")
    print("saved md+json")


if __name__ == "__main__":
    main()
