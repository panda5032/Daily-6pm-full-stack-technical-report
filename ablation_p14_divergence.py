"""
打法14 MACD底背离 消融实验 — 原版 vs 叠加确认信号
(2024 / 2025 / 2026YTD, 复用 backtest_playbooks_2026 的宇宙/指标/交易引擎)

变体:
  V0 原版基线      背离 + MACD<0 + 金叉触发 (cd1 原样)
  V1 +放量反转     触发日成交量 ≥1.2×20日均量
  V2 +RSI同步背离  第二低点 RSI 高于第一低点 (双指标背离)
  V3 +RSI超卖      第二低点 RSI <35 (只抄深跌)
  V4 +MA200趋势闸  入场时 收盘>MA200 或 MA200 20日走升 (只在长期趋势内抄回调)
  V5 +反转K确认    触发日收盘 > 昨日最高 (价格确认)
  A  组合 V2+V5    双指标背离 + 反转K
  B  组合 V4+V2    趋势闸 + 双指标背离
  X1 原版入场+宽离场  死叉离场 → 收盘<MA20×0.99, 60根时间止损 (让利润奔跑)
  AX 组合A入场+宽离场

Signals research only — not financial advice, no live orders.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from backtest_playbooks_2026 import (
    HERE, TODAY, WINDOWS, get_universe, download_all, add_indicators,
    run_trades, summarize)


# ────────────────────── entry factory ──────────────────────
def find_divergence(df, i):
    """cd1 的背离检测: 返回 (j, pj) 低点索引, 无背离返回 None."""
    c = df["Close"]
    seg = c.iloc[i - 8:i + 1]
    j = i - 8 + int(np.argmin(seg.values))
    prev = c.iloc[i - 60:j - 5]
    if len(prev) < 10:
        return None
    pj = i - 60 + int(np.argmin(prev.values))
    if (c.iloc[j] < c.iloc[pj]
            and df["macd"].iloc[j] > df["macd"].iloc[pj]
            and df["macd"].iloc[j] < 0):
        return j, pj
    return None


def make_entry(vol_gate=False, rsi_div=False, oversold=False,
               trend_gate=False, price_confirm=False):
    def entry(df, i):
        if not (df["macd"].iloc[i] > df["macds"].iloc[i]
                and df["macd"].iloc[i - 1] <= df["macds"].iloc[i - 1]):
            return None
        hit = find_divergence(df, i)
        if hit is None:
            return None
        j, pj = hit
        if vol_gate and not df["Volume"].iloc[i] >= 1.2 * df["vol20"].iloc[i]:
            return None
        if rsi_div and not df["rsi"].iloc[j] > df["rsi"].iloc[pj]:
            return None
        if oversold and not df["rsi"].iloc[j] < 35:
            return None
        if trend_gate:
            c, ma200 = df["Close"].iloc[i], df["ma200"].iloc[i]
            if np.isnan(ma200) or not (c > ma200 or ma200 > df["ma200"].iloc[i - 20]):
                return None
        if price_confirm and not df["Close"].iloc[i] > df["High"].iloc[i - 1]:
            return None
        return {"stop": float(df["Low"].iloc[i - 10:i + 1].min()
                              - 0.5 * df["atr"].iloc[i])}
    return entry


# ────────────────────── exits ──────────────────────
def exit_deadcross(df, i, pos):          # cd1 原版
    dead = (df["macd"].iloc[i] < df["macds"].iloc[i]
            and df["macd"].iloc[i - 1] >= df["macds"].iloc[i - 1])
    return dead or df["Close"].iloc[i] < pos["stop"] or i - pos["entry_i"] >= 40


def exit_ma20(df, i, pos):               # 宽离场
    c = df["Close"].iloc[i]
    return (c < pos["stop"] or c < df["ma20"].iloc[i] * 0.99
            or i - pos["entry_i"] >= 60)


VARIANTS = {
    "V0 原版基线":            (make_entry(), exit_deadcross),
    "V1 +放量反转":           (make_entry(vol_gate=True), exit_deadcross),
    "V2 +RSI同步背离":        (make_entry(rsi_div=True), exit_deadcross),
    "V3 +RSI超卖<35":         (make_entry(oversold=True), exit_deadcross),
    "V4 +MA200趋势闸":        (make_entry(trend_gate=True), exit_deadcross),
    "V5 +反转K确认":          (make_entry(price_confirm=True), exit_deadcross),
    "A  V2+V5双确认":         (make_entry(rsi_div=True, price_confirm=True), exit_deadcross),
    "B  V4+V2趋势+双背离":    (make_entry(trend_gate=True, rsi_div=True), exit_deadcross),
    "X1 原版入场+MA20宽离场": (make_entry(), exit_ma20),
    "AX A入场+MA20宽离场":    (make_entry(rsi_div=True, price_confirm=True), exit_ma20),
}


def main():
    tickers, _ = get_universe()
    print(f"universe: {len(tickers)} tickers")
    data = download_all(tickers)
    print(f"data ok: {len(data)} tickers")
    for t in data:
        data[t] = add_indicators(data[t])

    out = {"asof": TODAY, "universe_size": len(data), "windows": {}}
    md = [f"# 打法14 底背离消融实验 (as of {TODAY})",
          f"universe: {len(data)} tickers · 复用 backtest_playbooks_2026 引擎 · 无成本/滑点", ""]

    agg = {name: [] for name in VARIANTS}
    for label, start, end in WINDOWS:
        md += [f"## {label}", "",
               "| 变体 | 交易数 | 胜率 | 平均单笔 | 中位数 | PF | 持仓天 | 每票复利均值 |",
               "|---|---|---|---|---|---|---|---|"]
        wres = {}
        for name, (efn, xfn) in VARIANTS.items():
            trades = []
            for t, df in data.items():
                for tr in run_trades(df, efn, xfn, name, start, end):
                    tr["ticker"] = t
                    trades.append(tr)
            s = summarize(trades)
            wres[name] = s
            if not s:
                md.append(f"| {name} | 0 | — | — | — | — | — | — |")
                agg[name].append(None)
                continue
            agg[name].append(s)
            md.append(f"| {name} | {s['n_trades']} | {s['win_rate']:.0%} | {s['avg_ret']:+.2%} | "
                      f"{s['median_ret']:+.2%} | {s['profit_factor']:.2f} | {s['avg_days']:.0f} | "
                      f"{s['avg_ticker_ytd']:+.2%} |")
        md.append("")
        out["windows"][label] = {n: s for n, s in wres.items()}

    md += ["## 三年汇总 (各窗口简单平均)", "",
           "| 变体 | 年均交易数 | 均胜率 | 均单笔 | 均PF | 均每票复利 |",
           "|---|---|---|---|---|---|"]
    for name, rows in agg.items():
        rows = [r for r in rows if r]
        if not rows:
            continue
        md.append(f"| {name} | {np.mean([r['n_trades'] for r in rows]):.0f} "
                  f"| {np.mean([r['win_rate'] for r in rows]):.0%} "
                  f"| {np.mean([r['avg_ret'] for r in rows]):+.2%} "
                  f"| {np.mean([min(r['profit_factor'], 99) for r in rows]):.2f} "
                  f"| {np.mean([r['avg_ticker_ytd'] for r in rows]):+.2%} |")

    (HERE / f"ablation_p14_{TODAY}.md").write_text("\n".join(md), encoding="utf-8")
    (HERE / f"ablation_p14_{TODAY}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"saved ablation_p14_{TODAY}.md")


if __name__ == "__main__":
    main()
