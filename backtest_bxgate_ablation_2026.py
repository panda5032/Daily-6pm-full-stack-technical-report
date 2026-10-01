# -*- coding: utf-8 -*-
"""
打法13 长线趋势闸消融 (2026-09-19): MA50/200 金叉 vs 周线/月线 BX Trender.
状态型闸门: 闸开=满仓持有, 闸关=空仓; 信号收盘确认, 次日起计权重; 逐日复利.
  G13      MA50 > MA200                (现行打法13)
  GW       周线 BX > 0                 (周最后一根bar更新)
  GM       月线 BX > 0                 (月最后一根bar更新)
  G13&W    两闸同开才持有 (周BX当金叉的提前离场/延后进场)
  G13|W    任一闸开即持有 (周BX当金叉的提前进场)
  GW&M     周+月 BX 同绿
  BH       买入持有
窗口: 2022(灾难年) / 2023 / 2024 / 2025 / 2026 YTD / 全程. 两个池: 全池, 长线池(今日 LT>=75, 有事后偏差).
成本敏感性: 每次开/关闸 10bp.
"""
import json, warnings
from datetime import datetime
from pathlib import Path
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import backtest_playbooks_2026 as bp
from backtest_playbooks_2026 import get_universe, download_all
from backtest_dicarlo_2026 import bx_short
bp.DATA_START = "2020-01-01"   # after the dicarlo import (it sets its own start)

HERE = Path(__file__).parent
TODAY = datetime.now().strftime("%Y-%m-%d")
WINDOWS = [("2022", "2022-01-01", "2023-01-01"), ("2023", "2023-01-01", "2024-01-01"),
           ("2024", "2024-01-01", "2025-01-01"), ("2025", "2025-01-01", "2026-01-01"),
           ("2026 YTD", "2026-01-01", None), ("全程 2022→今", "2022-01-01", None)]
COST = 0.001


def _htf_bx(c, freq):
    per = c.index.to_period(freq)
    last_bar = pd.Series(c.index, index=c.index).groupby(per).max()
    bx = bx_short(c.groupby(per).last())
    bx.index = last_bar.values
    return bx.reindex(c.index).ffill()


def gates(df):
    c = df["Close"]
    g13 = (c.rolling(50).mean() > c.rolling(200).mean())
    gw = _htf_bx(c, "W-FRI") > 0
    gm = _htf_bx(c, "M") > 0
    valid = c.rolling(200).mean().notna()
    g = {"G13 金叉": g13, "GW 周BX": gw, "GM 月BX": gm, "G13&W": g13 & gw, "G13|W": g13 | gw,
         "GW&M": gw & gm, "BH 买入持有": pd.Series(True, index=c.index)}
    return {k: (v & valid).astype(float) for k, v in g.items()}


def evaluate(data, tickers, start, end):
    cal = pd.bdate_range(start, end or TODAY)
    res = {}
    names = None
    per_gate = {}
    for t in tickers:
        df = data[t]
        c = df["Close"]
        r = c.pct_change()
        for k, g in gates(df).items():
            w = g.shift(1).fillna(0)
            sw = g.diff().abs().fillna(0)
            net = w * r - sw.shift(1).fillna(0) * COST
            gross = w * r
            m = (c.index >= pd.Timestamp(start)) & ((c.index < pd.Timestamp(end)) if end else True)
            if m.sum() < 20 or w[m].isna().all():
                continue
            # fold weekend (crypto) into next business day
            def fold(s):
                s = s[m]
                pos = np.searchsorted(cal, s.index).clip(max=len(cal) - 1)
                out = (1 + s).groupby(pos).prod() - 1
                out.index = cal[out.index]
                return out.reindex(cal).fillna(0)
            eq_t = (1 + gross[m]).cumprod()
            per_gate.setdefault(k, []).append({
                "gross": fold(gross), "net": fold(net), "expo": float(w[m].mean()),
                "switch_py": float(sw[m].sum() / max(m.sum() / 252, 1e-9)),
                "tk_ret": float(eq_t.iloc[-1] - 1), "tk_dd": float((eq_t / eq_t.cummax() - 1).min())})
    for k, lst in per_gate.items():
        port = pd.concat([x["gross"] for x in lst], axis=1).mean(axis=1)
        portn = pd.concat([x["net"] for x in lst], axis=1).mean(axis=1)
        eq, eqn = (1 + port).cumprod(), (1 + portn).cumprod()
        res[k] = {"total": float(eq.iloc[-1] - 1), "net": float(eqn.iloc[-1] - 1),
                  "maxdd": float((eq / eq.cummax() - 1).min()),
                  "sharpe": float(port.mean() / port.std() * np.sqrt(252)) if port.std() > 0 else 0.0,
                  "expo": float(np.mean([x["expo"] for x in lst])),
                  "switch_py": float(np.mean([x["switch_py"] for x in lst])),
                  "tk_median": float(np.median([x["tk_ret"] for x in lst])),
                  "tk_dd_avg": float(np.mean([x["tk_dd"] for x in lst])), "n": len(lst)}
    return res


def main():
    tickers, _ = get_universe()
    data = download_all(tickers)
    print(f"{len(data)} tickers from {bp.DATA_START}")
    lt = json.loads(max(HERE.glob("long_term_strategy_*.json")).read_text(encoding="utf-8"))
    pool = [t for t in data if (lt.get(t, {}).get("score") or 0) >= 75]
    out, md = {}, [f"# 打法13 趋势闸消融: 金叉 vs 周/月线 BX (as of {TODAY})",
                   f"全池 {len(data)} 只 · 长线池(今日LT>=75) {len(pool)} 只 · 状态型闸门满仓/空仓 · 净值列含每次开关闸 10bp", ""]
    for uni_name, uni in (("全池", list(data)), ("长线池 LT>=75", pool)):
        for lab, s, e in WINDOWS:
            r = evaluate(data, uni, s, e)
            out[f"{uni_name}|{lab}"] = r
            md += [f"## {uni_name} · {lab} (n={next(iter(r.values()))['n']})", "",
                   "| 闸门 | 组合收益 | 扣成本 | MaxDD | Sharpe | 持仓占比 | 开关次数/票/年 | 单票中位收益 | 单票平均MaxDD |", "|---|---|---|---|---|---|---|---|---|"]
            for k, v in r.items():
                md.append(f"| {k} | **{v['total']:+.1%}** | {v['net']:+.1%} | {v['maxdd']:+.1%} | {v['sharpe']:.2f} | {v['expo']:.0%} | "
                          f"{v['switch_py']:.1f} | {v['tk_median']:+.1%} | {v['tk_dd_avg']:+.1%} |")
            md.append("")
    # today's gate snapshot
    snap = []
    for t, df in data.items():
        g = gates(df)
        snap.append({"t": t, "g13": bool(g["G13 金叉"].iloc[-1]), "gw": bool(g["GW 周BX"].iloc[-1]),
                     "gm": bool(g["GM 月BX"].iloc[-1]), "lt": lt.get(t, {}).get("score")})
    sd = pd.DataFrame(snap)
    md += ["## 今日闸门快照", "",
           f"- 金叉开 {int(sd.g13.sum())} / 周BX绿 {int(sd.gw.sum())} / 月BX绿 {int(sd.gm.sum())} (共 {len(sd)})",
           f"- 金叉开但周BX红 (金叉内提前预警): {', '.join(sd[sd.g13 & ~sd.gw].t)}",
           f"- 死叉但周BX绿 (周BX提前放行): {', '.join(sd[~sd.g13 & sd.gw].t)}",
           f"- 长线池内 周BX红: {', '.join(sd[(sd["lt"].fillna(0) >= 75) & ~sd.gw].t)}",
           f"- 长线池内 周BX绿: {', '.join(sd[(sd["lt"].fillna(0) >= 75) & sd.gw].t)}", ""]
    (HERE / f"backtest_bxgate_ablation_{TODAY}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    (HERE / f"backtest_bxgate_ablation_{TODAY}.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
