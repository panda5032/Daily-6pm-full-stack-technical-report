"""Follow-up: (1) DC1 周线BX vs 打法13 金叉 逐年; (2) 周线BX>0 当作闸门叠加到 打法1/8/16."""
import json, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import backtest_dicarlo_2026 as dc
from backtest_playbooks_2026 import run_trades, summarize

def gated(entry):
    return lambda df, i: entry(df, i) if df["bx_w"].iloc[i] > 0 else None

def run(data, en, ex, name, start, end=None):
    trades, by = [], {}
    for t, df in data.items():
        tr = run_trades(df, en, ex, name, start=start, end=end)
        for x in tr: x["ticker"] = t
        trades += tr; by[t] = tr
    s = summarize(trades)
    d2 = data if end is None else {t: d[d.index < pd.Timestamp(end)] for t, d in data.items()}
    c = dc.sleeve_curve(d2, by, start)
    return f"| {name} | {c['total']:+.1%} | {c['maxdd']:+.1%} | {c['sharpe']:.2f} | {c['exposure']:.0%} | {s['n_trades']} | {s['win_rate']:.0%} | {s['avg_ret']:+.2%} | {s['profit_factor']:.2f} |"

def main():
    tickers, _ = dc.get_universe()
    data = dc.download_all(tickers)
    for t in list(data):
        data[t] = dc.add_dicarlo(dc.add_pb16_indicators(dc.add_indicators(data[t])))
    hdr = "| 策略 | 组合收益 | MaxDD | Sharpe | 仓位 | 交易 | 胜率 | 单笔 | PF |\n|---|---|---|---|---|---|---|---|---|"
    md = ["# 周线BX: 逐年稳健性 + 闸门叠加", ""]
    for lab, s, e in [("2024", "2024-01-01", "2025-01-01"), ("2025", "2025-01-01", "2026-01-01"), ("2026 YTD", "2026-01-01", None)]:
        md += [f"## {lab}", hdr]
        md.append(run(data, *dc.DICARLO["DC1 周线BX翻绿→翻红"], "DC1 周线BX", s, e))
        md.append(run(data, *dc.MINE["打法13 MA50/200金叉"], "打法13 金叉", s, e))
        for k in ["打法1 回踩企稳", "打法8 带行持有", "打法16 纯图突破(双闸)", "打法2 缩量平台突破"]:
            en, ex = dc.MINE[k]
            md.append(run(data, en, ex, k, s, e))
            md.append(run(data, gated(en), ex, k + " +周BX闸", s, e))
        md.append("")
    out = "\n".join(md)
    (dc.HERE / f"backtest_dicarlo_gate_{dc.TODAY}.md").write_text(out, encoding="utf-8")
    print(out)

if __name__ == "__main__":
    main()
