"""
TSLA single-name backtest — fills the ⑤ 回测与验证 table of the Tesla trading-system design.

Rules (mechanical versions, same definitions as backtest_playbooks_2026 / backtest_pb16_2026,
re-parameterised where the design says TSLA differs):
  打法1 回踩企稳 · 打法2/16 突破(纯图) · 打法7 恐慌反转 · 打法15 金针探底
  打法6 财报/交付 PEAD · 打法8 带行+MA20离场 · 打法13 金叉闸(长线)
  情绪极值修正器 / 鲸鱼流修正器 — no historical data → 数据缺失 rows.

Window: entries 2021-10-01 → today (main), plus per-year splits as the walk-forward
validation slices; 打法13 additionally run on 2012→ for more cross samples.
Execution: signal at close, filled next open, 0.1% slippage each side. No costs beyond that.
Output: backtest_tsla_<date>.md / .json. Signals research only — not financial advice.
"""
import json
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")
from backtest_playbooks_2026 import add_indicators, pb1_entry, pb1_exit, pb7_entry, pb8_entry  # noqa: E402
from backtest_pb16_2026 import add_pb16_indicators, _w_bottom, _plat_break  # noqa: E402

HERE = Path(__file__).parent
TODAY = datetime.now().strftime("%Y-%m-%d")
TICKER = "TSLA"
SLIP = 0.001
MAIN = ("主回测 2021-10→今", "2021-10-01", None)
SLICES = [("2022", "2022-01-01", "2023-01-01"), ("2023", "2023-01-01", "2024-01-01"),
          ("2024", "2024-01-01", "2025-01-01"), ("2025", "2025-01-01", "2026-01-01"),
          ("2026 YTD", "2026-01-01", None)]


# ────────────────────────── data ──────────────────────────
def load():
    t = yf.Ticker(TICKER)
    df = t.history(start="2010-06-29", interval="1d", auto_adjust=True)
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"]).copy()
    df.index = df.index.tz_localize(None)
    df = add_pb16_indicators(add_indicators(df))
    df["ma5"] = df["Close"].rolling(5).mean()
    df["ma10"] = df["Close"].rolling(10).mean()
    df["bw_q15"] = df["bw"].rolling(126).quantile(0.15)
    try:
        ed = t.get_earnings_dates(limit=60)
        earn = sorted({pd.Timestamp(x).tz_localize(None).normalize() for x in ed.index})
    except Exception:
        earn = []
    return df, earn


def delivery_days(idx):
    """TSLA posts quarterly deliveries on the 2nd of Jan/Apr/Jul/Oct (or next trading day) —
    an approximation of the real calendar, flagged as such in the report."""
    out = []
    for y in range(2011, idx[-1].year + 1):
        for m in (1, 4, 7, 10):
            d = pd.Timestamp(y, m, 2)
            j = int(np.searchsorted(idx, d))
            if j < len(idx):
                out.append(idx[j])
    return out


# ────────────────────────── engine ──────────────────────────
def run(df, entry_fn, exit_fn, label, start, end=None):
    """Signal at bar i close → fill at bar i+1 open (+slip); exit signal at close → fill next
    open (−slip). Open trade marked to last close."""
    if end is not None:
        df = df[df.index < pd.Timestamp(end)]
    idx, o, c = df.index, df["Open"].values, df["Close"].values
    start_i = max(int(np.searchsorted(idx, pd.Timestamp(start))), 210)
    trades, pos = [], None
    for i in range(start_i, len(df) - 1):
        if pos is None:
            e = entry_fn(df, i)
            if e is not None:
                pos = {"entry_i": i + 1, "entry": float(o[i + 1]) * (1 + SLIP), "sig_i": i, **e}
        else:
            if exit_fn(df, i, pos):
                px = float(o[i + 1]) * (1 - SLIP)
                trades.append({"strategy": label, "entry_date": str(idx[pos["entry_i"]].date()),
                               "exit_date": str(idx[i + 1].date()), "days": i + 1 - pos["entry_i"],
                               "ret": px / pos["entry"] - 1})
                pos = None
    if pos is not None:
        px = float(c[-1])
        trades.append({"strategy": label, "entry_date": str(idx[pos["entry_i"]].date()),
                       "exit_date": "OPEN" if end is None else f"EOW {idx[-1].date()}",
                       "days": len(df) - 1 - pos["entry_i"], "ret": px / pos["entry"] - 1})
    return trades


def summarize(trades):
    if not trades:
        return {"n": 0}
    r = np.array([t["ret"] for t in trades])
    wins, losses = r[r > 0], r[r <= 0]
    pf = float(wins.sum() / abs(losses.sum())) if losses.sum() != 0 else float("inf")
    eq = np.cumprod(1 + r)                       # full capital per trade, sequential
    mdd = float((eq / np.maximum.accumulate(eq) - 1).min())
    k = max(1, int(np.ceil(len(r) * 0.10)))
    top = np.sort(r)[-k:]
    tail_share = float(top[top > 0].sum() / wins.sum()) if wins.sum() > 0 else 0.0
    rest = np.sort(r)[:-k]
    rw, rl = rest[rest > 0], rest[rest <= 0]
    pf_ex = float(rw.sum() / abs(rl.sum())) if rl.sum() != 0 else float("inf")
    return {"n": int(len(r)), "win_rate": float((r > 0).mean()), "pf": pf,
            "avg_ret": float(r.mean()), "median_ret": float(np.median(r)),
            "max_dd": mdd, "tail_share": tail_share, "pf_ex_top10": pf_ex,
            "avg_days": float(np.mean([t["days"] for t in trades])),
            "total": float(eq[-1] - 1), "open": sum(1 for t in trades if t["exit_date"] == "OPEN")}


def verdict(s):
    if s["n"] == 0:
        return "无信号"
    if s["n"] < 30:
        return "样本不足→影子期" if s["pf"] >= 1.5 else "样本不足·弱"
    if s["pf"] >= 2.0 and s["pf_ex_top10"] >= 1.2:
        return "晋升"
    if s["pf"] >= 1.5:
        return "影子期"
    return "只当修正器"


# ────────────────────────── rules ──────────────────────────
# 打法1 — shared definition (uptrend, pullback to MA20 ±3.5%, close > prior high).
# 打法2/16 纯图: W-bottom neckline or 20d-high platform break; exit close<MA20 or stop.
def pb16_entry(df, i):
    if df["Close"].iloc[i] < df["ma50"].iloc[i]:
        return None
    return _w_bottom(df, i) or _plat_break(df, i)


def chart_exit(df, i, pos):
    c = df["Close"].iloc[i]
    return c < df["ma20"].iloc[i] or c < pos["stop"]


# 打法7 — shared entry; the design's quality gate (MA200 above) applied as a variant.
def pb7_exit(df, i, pos):
    c = df["Close"].iloc[i]
    return c >= df["ma20"].iloc[i] or c < pos["stop"] or i - pos["entry_i"] >= 15


def pb7q_entry(df, i):
    if df["Close"].iloc[i] < df["ma200"].iloc[i]:
        return None
    return pb7_entry(df, i)


# 打法15 金针: lower wick ≥2×body and ≥K×ATR, close in upper half, weak context.
# K=1.2 is the universe rule; on TSLA (ATR ≈ 4.6% of price, wick/ATR 95th pct ≈ 0.58) it never
# fires in 5 years, so a TSLA-scaled K=0.6 (≈ the 95th percentile wick) is tested alongside.
def make_pb15(k):
    def entry(df, i):
        o, h, l, c = (df["Open"].iloc[i], df["High"].iloc[i], df["Low"].iloc[i], df["Close"].iloc[i])
        body, wick, rng = abs(c - o), min(o, c) - l, (h - l) or 1e-9
        weak = c < df["ma20"].iloc[i] or df["Close"].iloc[i] / df["Close"].iloc[i - 5] - 1 <= -0.05
        if wick >= 2 * body and wick >= k * df["atr"].iloc[i] and (c - l) / rng >= 0.5 and weak:
            return {"stop": float(l - 0.25 * df["atr"].iloc[i])}
        return None
    return entry


def pb15_exit(df, i, pos):
    c = df["Close"].iloc[i]
    return c < pos["stop"] or c >= df["ma20"].iloc[i] or i - pos["entry_i"] >= 12


# 打法8 — shared entry (fresh %B≥0.8 in uptrend); exit = close<MA20 on RVOL≥1.3 (TSLA) or 2 closes.
def pb8_exit(df, i, pos):
    c, ma = df["Close"].iloc[i], df["ma20"].iloc[i]
    heavy = df["Volume"].iloc[i] >= 1.3 * df["vol20"].iloc[i]
    two = df["Close"].iloc[i - 1] < df["ma20"].iloc[i - 1]
    return c < ma and (heavy or two)


# 打法6 PEAD: event day (earnings = first session after AMC print; delivery day itself)
# gaps up ≥3%, closes in upper half of range → beat-pop. Enter on a pullback within the next
# 5 bars (close ≤ MA5×1.01 and > event low); stop = event-day low; exit close<MA20, stop, or 20 bars.
# (14 of TSLA's last 20 earnings reactions were down days — beat-pop is rare here by construction.)
def make_pead(event_days, idx):
    ev = set()
    for d in event_days:
        j = int(np.searchsorted(idx, d))
        if j < len(idx):
            ev.add(j)

    def entry(df, i):
        for k in (1, 2, 3, 4, 5):
            j = i - k
            if j in ev:
                o, h, l, c = df["Open"].iloc[j], df["High"].iloc[j], df["Low"].iloc[j], df["Close"].iloc[j]
                pc = df["Close"].iloc[j - 1]
                pop = o / pc - 1 >= 0.03 and (c - l) / ((h - l) or 1e-9) >= 0.5
                if pop and df["Close"].iloc[i] <= df["ma5"].iloc[i] * 1.01 and df["Close"].iloc[i] > l:
                    return {"stop": float(l), "ev": j}
        return None

    def exit_(df, i, pos):
        c = df["Close"].iloc[i]
        return c < pos["stop"] or c < df["ma20"].iloc[i] or i - pos["entry_i"] >= 20
    return entry, exit_


def earnings_sessions(earn, idx):
    """TSLA reports after the close → the reaction session is the next trading day."""
    out = []
    for d in earn:
        j = int(np.searchsorted(idx, d, side="right"))
        if j < len(idx):
            out.append(idx[j])
    return out


# 打法13 金叉闸: long from MA50 crossing above MA200 to the cross back down.
def gc_entry(df, i):
    if df["ma50"].iloc[i] > df["ma200"].iloc[i] and df["ma50"].iloc[i - 1] <= df["ma200"].iloc[i - 1]:
        return {}
    return None


def gc_exit(df, i, pos):
    return df["ma50"].iloc[i] < df["ma200"].iloc[i]


def buy_hold(df, start, end=None):
    c = df["Close"][df.index >= pd.Timestamp(start)]
    if end is not None:
        c = c[c.index < pd.Timestamp(end)]
    return float(c.iloc[-1] / c.iloc[0] - 1)


# ────────────────────────── main ──────────────────────────
def main():
    df, earn = load()
    idx = df.index
    pead_e, pead_x = make_pead(earnings_sessions(earn, idx), idx)
    dlv_e, dlv_x = make_pead(delivery_days(idx), idx)
    RULES = {
        "打法1 回踩企稳":           (pb1_entry, pb1_exit),
        "打法2/16 纯图突破":        (pb16_entry, chart_exit),
        "打法7 恐慌反转(无质量闸)":  (pb7_entry, pb7_exit),
        "打法7 恐慌反转(MA200闸)":   (pb7q_entry, pb7_exit),
        "打法15 金针探底(1.2×ATR)":  (make_pb15(1.2), pb15_exit),
        "打法15 金针探底(TSLA 0.6×ATR)": (make_pb15(0.6), pb15_exit),
        "打法6 财报 PEAD":          (pead_e, pead_x),
        "打法6 交付日 PEAD(近似日历)": (dlv_e, dlv_x),
        "打法8 带行+MA20离场":       (pb8_entry, pb8_exit),
        "打法13 金叉闸(长线)":       (gc_entry, gc_exit),
    }
    out = {"asof": TODAY, "ticker": TICKER, "bars": int(len(df)),
           "data_start": str(idx[0].date()), "data_end": str(idx[-1].date()),
           "earnings_dates_used": [str(d.date()) for d in earn if d >= pd.Timestamp("2021-01-01")],
           "windows": {}, "missing": {"情绪极值修正器": "无历史推文/新闻情绪序列 — 数据缺失",
                                      "鲸鱼流修正器": "无历史期权成交方向/鲸鱼打印 — 数据缺失"}}
    md = [f"# TSLA 单票回测 (as of {TODAY})",
          f"data {idx[0].date()} → {idx[-1].date()} · {len(df)} bars · 次日开盘成交 · 滑点 {SLIP:.1%}/边 · "
          f"财报日 {len(out['earnings_dates_used'])} 个 (yfinance) · 交付日为近似日历(每季首月 2 日)", ""]
    for label, start, end in [MAIN] + SLICES:
        res, all_trades = {}, {}
        for name, (efn, xfn) in RULES.items():
            s0 = "2012-01-01" if (name.startswith("打法13") and label == MAIN[0]) else start
            tr = run(df, efn, xfn, name, s0, end)
            all_trades[name] = tr
            s = summarize(tr)
            s["verdict"] = verdict(s)
            res[name] = s
        bh = buy_hold(df, start, end)
        out["windows"][label] = {"results": res, "buy_hold": bh, "trades": all_trades}
        md += [f"## {label} ({start} → {end or TODAY}) · 买入持有 {bh:+.1%}", "",
               "| 规则 | n | 胜率 | PF | 单笔均值 | 中位 | 最大回撤 | 右尾贡献 | 去顶10% PF | 持仓天 | 复利 | 判定 |",
               "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for name, s in res.items():
            if s["n"] == 0:
                md.append(f"| {name} | 0 | — | — | — | — | — | — | — | — | — | 无信号 |"); continue
            md.append(f"| {name} | {s['n']} | {s['win_rate']:.0%} | {s['pf']:.2f} | {s['avg_ret']:+.2%} | "
                      f"{s['median_ret']:+.2%} | {s['max_dd']:.1%} | {s['tail_share']:.0%} | {s['pf_ex_top10']:.2f} | "
                      f"{s['avg_days']:.0f} | {s['total']:+.1%} | {s['verdict']} |")
        md.append("")
        print(f"[{label}] " + " · ".join(f"{k.split()[0]}:{v['n']}/{v.get('pf', 0):.2f}" for k, v in res.items()))
    md += ["## 数据缺失", ""] + [f"- {k}: {v}" for k, v in out["missing"].items()]
    md += ["", "注: 打法13 主回测窗口从 2012 起以增加金叉样本; 其余规则 2021-10 起。判定门槛: n≥30 且 PF≥2.0 且去顶10% PF≥1.2 = 晋升; PF 1.5–2.0 = 影子期; 否则只当修正器; n<30 一律影子期或弱。"]
    (HERE / f"backtest_tsla_{TODAY}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (HERE / f"backtest_tsla_{TODAY}.md").write_text("\n".join(md), encoding="utf-8")
    print("saved", f"backtest_tsla_{TODAY}.md")


if __name__ == "__main__":
    main()
