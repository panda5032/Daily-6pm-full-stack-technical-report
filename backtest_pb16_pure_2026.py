"""
纯形态 variants of 打法16 — how much do volume + MACD confirmations add?
  16c 纯形态(同离场): pattern-only entry, 打法16 exit (MACD死叉/放量破MA20/stop)
  16d 纯形态+纯图离场: pattern-only entry, chart-only exit (close<MA20 / stop)
  16e 只W双底 / 16f 只平台突破: single-pattern, chart-only exit
Old playbooks are read from today's backtest_pb16_<date>.json (same data day).
"""
import json, warnings
from datetime import datetime
from pathlib import Path
import numpy as np
warnings.filterwarnings("ignore")
from backtest_playbooks_2026 import add_indicators, download_all, get_universe, run_trades, summarize
from backtest_pb16_2026 import add_pb16_indicators, _w_bottom, _plat_break, pb16_exit, WINDOWS

HERE = Path(__file__).parent
TODAY = datetime.now().strftime("%Y-%m-%d")

def pure_entry(df, i):   return _w_bottom(df, i) or _plat_break(df, i)
def w_entry(df, i):      return _w_bottom(df, i)
def plat_entry(df, i):   return _plat_break(df, i)
def chart_exit(df, i, pos):
    c = df["Close"].iloc[i]
    return c < df["ma20"].iloc[i] or c < pos["stop"]

VARIANTS = {
    "打法16c 纯形态(同16离场)":      (pure_entry, pb16_exit),
    "打法16d 纯形态+纯图离场":      (pure_entry, chart_exit),
    "打法16e 只W双底(纯图)":        (w_entry, chart_exit),
    "打法16f 只平台突破(纯图)":      (plat_entry, chart_exit),
}
KEEP = ["打法16 三重确认(形+量+MACD)", "打法16b 双重确认(形+量或MACD)",
        "打法1 回踩企稳", "打法2 缩量平台突破", "打法8 带行持有", "抄底3 W双底", "基线 MACD金叉"]

def main():
    tickers, _ = get_universe()
    data = download_all(tickers)
    for t in data:
        data[t] = add_pb16_indicators(add_indicators(data[t]))
    print(f"data ok: {len(data)}")
    prev = json.loads((HERE / f"backtest_pb16_{TODAY}.json").read_text(encoding="utf-8"))
    out = {"asof": TODAY, "windows": {}}
    md = [f"# 纯形态打法回测 (as of {TODAY}) — 只看图 vs 加量能/MACD确认",
          f"universe: {len(data)} · entries at signal close · no costs", ""]
    for label, start, end in WINDOWS:
        res = {}
        for name, (efn, xfn) in VARIANTS.items():
            trades = []
            for t, df in data.items():
                for tr in run_trades(df, efn, xfn, name, start, end):
                    tr["ticker"] = t; trades.append(tr)
            res[name] = summarize(trades)
            print(f"  [{label}] {name}: {len(trades)}")
        old = prev["windows"][label]["results"]
        for k in KEEP:
            res[k] = old.get(k)
        out["windows"][label] = {"results": res, "benchmarks": prev["windows"][label]["benchmarks"]}
        md += [f"## {label} ({start} → {end or TODAY})", "",
               "| 打法 | 交易数 | 胜率 | 平均单笔 | 中位数 | PF | 持仓天 | 每票复利均值 |", "|---|---|---|---|---|---|---|---|"]
        for name, s in res.items():
            if not s:
                md.append(f"| {name} | 0 | — | — | — | — | — | — |"); continue
            md.append(f"| {name} | {s['n_trades']} | {s['win_rate']:.0%} | {s['avg_ret']:+.2%} | {s['median_ret']:+.2%} | "
                      f"{s['profit_factor']:.2f} | {s['avg_days']:.0f} | {s['avg_ticker_ytd']:+.2%} |")
        md.append("\n基准: " + " · ".join(f"{b} {r:+.2%}" for b, r in prev["windows"][label]["benchmarks"].items()) + "\n")
    (HERE / f"backtest_pb16_pure_{TODAY}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (HERE / f"backtest_pb16_pure_{TODAY}.md").write_text("\n".join(md), encoding="utf-8")
    print("saved")

if __name__ == "__main__":
    main()
