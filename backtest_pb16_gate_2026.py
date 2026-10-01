"""
蓄势闸 / 趋势闸 on top of 打法16d 纯图 (pattern entry + chart-only exit).
  16g 蓄势闸:   BW <= 120d 20th pct within last 5 bars (same squeeze as 打法2)
  16h MA50趋势闸: close > MA50
  16i 双闸:     squeeze + MA50
Old rows read from today's backtest_pb16_pure_<date>.json.
"""
import json, warnings
from datetime import datetime
from pathlib import Path
warnings.filterwarnings("ignore")
from backtest_playbooks_2026 import add_indicators, download_all, get_universe, run_trades, summarize
from backtest_pb16_2026 import add_pb16_indicators, _w_bottom, _plat_break, WINDOWS
from backtest_pb16_pure_2026 import pure_entry, chart_exit

HERE = Path(__file__).parent
TODAY = datetime.now().strftime("%Y-%m-%d")

def _sq(df, i):  return bool((df["bw"].iloc[i-5:i+1] <= df["bw_q20"].iloc[i-5:i+1]).any())
def _ma50(df, i): return df["Close"].iloc[i] > df["ma50"].iloc[i]
def g_entry(df, i): return pure_entry(df, i) if _sq(df, i) else None
def h_entry(df, i): return pure_entry(df, i) if _ma50(df, i) else None
def i_entry(df, i): return pure_entry(df, i) if (_sq(df, i) and _ma50(df, i)) else None

VARIANTS = {"打法16g 蓄势闸+纯图": (g_entry, chart_exit),
            "打法16h MA50闸+纯图": (h_entry, chart_exit),
            "打法16i 蓄势+MA50双闸+纯图": (i_entry, chart_exit)}
KEEP = ["打法16d 纯形态+纯图离场", "打法16 三重确认(形+量+MACD)", "打法1 回踩企稳", "打法2 缩量平台突破", "打法8 带行持有"]

def main():
    tickers, _ = get_universe()
    data = download_all(tickers)
    for t in data: data[t] = add_pb16_indicators(add_indicators(data[t]))
    print(f"data ok: {len(data)}")
    prev = json.loads((HERE / f"backtest_pb16_pure_{TODAY}.json").read_text(encoding="utf-8"))
    out = {"asof": TODAY, "windows": {}}
    md = [f"# 蓄势闸/趋势闸 × 纯图打法16 回测 (as of {TODAY})", f"universe: {len(data)} · entries at signal close · no costs", ""]
    for label, start, end in WINDOWS:
        res = {}
        for name, (efn, xfn) in VARIANTS.items():
            trades = []
            for t, df in data.items():
                for tr in run_trades(df, efn, xfn, name, start, end):
                    tr["ticker"] = t; trades.append(tr)
            res[name] = summarize(trades); print(f"  [{label}] {name}: {len(trades)}")
        for k in KEEP: res[k] = prev["windows"][label]["results"].get(k)
        out["windows"][label] = {"results": res}
        md += [f"## {label} ({start} → {end or TODAY})", "",
               "| 打法 | 交易数 | 胜率 | 平均单笔 | 中位数 | PF | 持仓天 | 每票复利均值 |", "|---|---|---|---|---|---|---|---|"]
        for name, s in res.items():
            if not s: md.append(f"| {name} | 0 | — | — | — | — | — | — |"); continue
            md.append(f"| {name} | {s['n_trades']} | {s['win_rate']:.0%} | {s['avg_ret']:+.2%} | {s['median_ret']:+.2%} | "
                      f"{s['profit_factor']:.2f} | {s['avg_days']:.0f} | {s['avg_ticker_ytd']:+.2%} |")
        md.append("")
    (HERE / f"backtest_pb16_gate_{TODAY}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (HERE / f"backtest_pb16_gate_{TODAY}.md").write_text("\n".join(md), encoding="utf-8")
    print("saved")
if __name__ == "__main__": main()
