"""
打法17 OBV + 鲸鱼期权流 (smart money) backtest.
OBV part: fully testable 2024-26.  Whale part: REAL signals parsed from the
archived whale_options_<date>.md reports (2026-05-02 → today) — only that
window is a true whale test; for 2024-26 a volume-footprint PROXY is used and
labelled as such.  Old playbooks for standard windows are read from today's
backtest_pb16_<date>.json (same data day); the whale window re-runs everything.
Signals research only — not financial advice.
"""
import json
import re
import glob
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
from backtest_playbooks_2026 import (PLAYBOOKS, add_indicators, bench_returns, download_all,  # noqa: E402
                                     get_universe, run_trades, summarize)

HERE = Path(__file__).parent
TODAY = datetime.now().strftime("%Y-%m-%d")
WINDOWS = [("2024", "2024-01-01", "2025-01-01"), ("2025", "2025-01-01", "2026-01-01"),
           ("2026 YTD", "2026-01-01", None), ("3年累计", "2024-01-01", None)]
WHALE_START = "2026-05-04"

# ── whale report parser ──────────────────────────────────────────────
ROW = re.compile(r"^\*\*([A-Z0-9.\-^=]+)\*\* — .*?\*\*(STRONG BUY|BUY|HOLD|SELL|STRONG SELL|NO OPTIONS|NO DATA)\*\* \(score: ([+-]?[\d.]+)\)")


def load_whale():
    rows = []
    for f in sorted(glob.glob(str(HERE / "whale_options_20??-??-??.md"))):
        d = pd.Timestamp(Path(f).stem[-10:])
        for line in open(f, encoding="utf-8"):
            m = ROW.match(line.strip())
            if m and m.group(2) not in ("NO OPTIONS", "NO DATA"):
                rows.append((m.group(1), d, m.group(2), float(m.group(3))))
    return pd.DataFrame(rows, columns=["ticker", "date", "action", "score"])


WH = load_whale()
WH_BY_T = {t: g.set_index("date")["score"].sort_index() for t, g in WH.groupby("ticker")}


def whale_recent(t, d, days=5, thr=2.5):
    s = WH_BY_T.get(t)
    if s is None:
        return False
    win = s[(s.index > d - timedelta(days=days + 2)) & (s.index <= d)]
    return bool(len(win) and win.max() >= thr)


def whale_today(t, d, thr=4.0):
    s = WH_BY_T.get(t)
    if s is None:
        return False
    win = s[(s.index > d - timedelta(days=3)) & (s.index <= d)]
    return bool(len(win) and win.iloc[-1] >= thr)


# ── indicators ──────────────────────────────────────────────────────
def add17(df):
    step = np.sign(df["Close"].diff()).fillna(0) * df["Volume"]
    df["obv"] = step.cumsum()
    df["obv20"] = df["obv"].rolling(20).mean()
    df["obv_hi20"] = df["obv"].rolling(20).max().shift(1)
    df["lead"] = (df["obv"] > df["obv_hi20"]) & (df["Close"] <= df["hi20"])
    rng = (df["High"] - df["Low"]).replace(0, np.nan)
    df["foot"] = ((df["Volume"] >= 2.5 * df["vol20"]) & (df["Close"] > df["Open"])
                  & ((df["Close"] - df["Low"]) / rng >= 0.6))
    return df


def _chart_exit(df, i, pos):
    c = df["Close"].iloc[i]
    return c < df["ma20"].iloc[i] or c < pos["stop"]


def _obv_exit(df, i, pos):
    return _chart_exit(df, i, pos) or df["obv"].iloc[i] < df["obv20"].iloc[i]


def a_entry(df, i):   # OBV领先早入
    if (df["lead"].iloc[i] and df["Close"].iloc[i] > df["ma20"].iloc[i]
            and df["Close"].iloc[i] > df["ma50"].iloc[i]):
        return {"stop": float(df["Low"].iloc[i - 5:i + 1].min() - 0.5 * df["atr"].iloc[i])}
    return None


def b_entry(df, i):   # OBV领先 + 价格确认
    if (df["lead"].iloc[i - 10:i].any() and df["Close"].iloc[i] > df["hi20"].iloc[i]
            and df["Close"].iloc[i - 1] <= df["hi20"].iloc[i - 1]
            and df["Close"].iloc[i] > df["ma50"].iloc[i]):
        return {"stop": float(df["Low"].iloc[i] - 0.5 * df["atr"].iloc[i])}
    return None


def d_entry(df, i):   # 17b + 鲸鱼代理(放量阳线足迹)
    e = b_entry(df, i)
    return e if e and df["foot"].iloc[i - 5:i + 1].any() else None


def mk_whale(base):
    def f(df, i):
        e = base(df, i)
        return e if e and whale_recent(df.attrs["t"], df.index[i]) else None
    return f


def w_entry(df, i):   # 纯鲸鱼 STRONG BUY 当天, MA50上方
    if whale_today(df.attrs["t"], df.index[i]) and df["Close"].iloc[i] > df["ma50"].iloc[i]:
        return {"stop": float(df["Low"].iloc[i - 5:i + 1].min() - 0.5 * df["atr"].iloc[i])}
    return None


OBV_PB = {"打法17a OBV领先早入": (a_entry, _chart_exit),
          "打法17b OBV领先+价格确认": (b_entry, _chart_exit),
          "打法17c 17b+OBV离场": (b_entry, _obv_exit),
          "打法17d 17b+鲸鱼代理(放量足迹)": (d_entry, _chart_exit)}
WHALE_PB = {"打法17e 17b+真鲸鱼BUY(5日内)": (mk_whale(b_entry), _chart_exit),
            "打法17f 17a+真鲸鱼BUY(5日内)": (mk_whale(a_entry), _chart_exit),
            "打法17w 纯鲸鱼STRONG BUY": (w_entry, _chart_exit)}
KEEP = ["打法16 三重确认(形+量+MACD)", "打法1 回踩企稳", "打法2 缩量平台突破", "打法8 带行持有",
        "抄底1 MACD底背离", "基线 MACD金叉"]


def run_set(data, pbs, start, end):
    res = {}
    for name, (efn, xfn) in pbs.items():
        trades = []
        for t, df in data.items():
            df.attrs["t"] = t
            for tr in run_trades(df, efn, xfn, name, start, end):
                tr["ticker"] = t
                trades.append(tr)
        res[name] = summarize(trades)
        print(f"    {name}: {len(trades)}")
    return res


def table(md, res):
    md += ["| 打法 | 交易数 | 胜率 | 平均单笔 | 中位数 | PF | 持仓天 | 每票复利均值 |",
           "|---|---|---|---|---|---|---|---|"]
    for name, s in res.items():
        if not s:
            md.append(f"| {name} | 0 | — | — | — | — | — | — |")
            continue
        md.append(f"| {name} | {s['n_trades']} | {s['win_rate']:.0%} | {s['avg_ret']:+.2%} | "
                  f"{s['median_ret']:+.2%} | {s['profit_factor']:.2f} | {s['avg_days']:.0f} | "
                  f"{s['avg_ticker_ytd']:+.2%} |")


def main():
    print(f"whale reports parsed: {WH['date'].nunique()} days, {WH['ticker'].nunique()} tickers, {len(WH)} rows")
    tickers, _ = get_universe()
    data = download_all(tickers)
    for t in data:
        data[t] = add17(add_indicators(data[t]))
    print(f"data ok: {len(data)}")
    prev = json.loads((HERE / f"backtest_pb16_{TODAY}.json").read_text(encoding="utf-8"))
    out = {"asof": TODAY, "windows": {}}
    md = [f"# 打法17 OBV+鲸鱼流 回测 (as of {TODAY})",
          f"universe {len(data)} · entries at signal close · no costs",
          "· OBV领先 = OBV创20日新高而价格未创新高; 鲸鱼 = 每日 whale_options 报告评分 "
          "(真实信号仅 2026-05-02→今); 鲸鱼代理 = 近5日≥2.5×放量阳线(收在上40%)", ""]
    for label, start, end in WINDOWS:
        print(f"[{label}]")
        res = run_set(data, OBV_PB, start, end)
        for k in KEEP:
            res[k] = prev["windows"][label]["results"].get(k)
        out["windows"][label] = res
        md += [f"## {label} ({start} → {end or TODAY}) — OBV部件 + 代理 (老打法来自今日 pb16 json)", ""]
        table(md, res)
        md.append("\n基准: " + " · ".join(f"{b} {r:+.2%}" for b, r in prev["windows"][label]["benchmarks"].items()) + "\n")

    label = f"鲸鱼期 {WHALE_START}→{TODAY}"
    print(f"[{label}]")
    res = run_set(data, {**WHALE_PB, **OBV_PB}, WHALE_START, None)
    res.update(run_set(data, {k: PLAYBOOKS[k] for k in KEEP if k in PLAYBOOKS}, WHALE_START, None))
    bench = bench_returns(data, WHALE_START, None)
    out["windows"][label] = {"results": res, "benchmarks": bench}
    md += [f"## {label} — 真实鲸鱼信号窗口, 全部同场重跑", ""]
    table(md, res)
    md.append("\n基准: " + " · ".join(f"{b} {r:+.2%}" for b, r in bench.items()) + "\n")

    # event study of whale actions
    ev = []
    for t, s in WH_BY_T.items():
        df = data.get(t)
        if df is None:
            continue
        acts = WH[WH.ticker == t].drop_duplicates("date").set_index("date")["action"]
        for d, sc in s.items():
            i = int(np.searchsorted(df.index, d))
            if i >= len(df) or df.index[i] > d + timedelta(days=3):
                continue
            row = {"action": acts.loc[d]}
            for k in (5, 10, 20):
                if i + k < len(df):
                    row[f"f{k}"] = float(df["Close"].iloc[i + k] / df["Close"].iloc[i] - 1)
            ev.append(row)
    ev = pd.DataFrame(ev)
    es = {}
    md += ["## 鲸鱼信号事件研究 — 报告日收盘后前瞻收益 (2026-05-02→今)", "",
           "| 动作 | 次数 | 5日均值 | 10日均值 | 10日中位 | 10日上涨率 | 20日均值 | 20日上涨率 |",
           "|---|---|---|---|---|---|---|---|"]
    for act in ["STRONG BUY", "BUY", "HOLD", "SELL", "STRONG SELL"]:
        g = ev[ev.action == act]
        if not len(g):
            continue
        r = {"n": int(len(g))}
        for k in (5, 10, 20):
            v = g[f"f{k}"].dropna()
            r[f"mean{k}"] = float(v.mean()) if len(v) else float("nan")
            r[f"med{k}"] = float(v.median()) if len(v) else float("nan")
            r[f"up{k}"] = float((v > 0).mean()) if len(v) else float("nan")
        es[act] = r
        md.append(f"| {act} | {r['n']} | {r['mean5']:+.2%} | {r['mean10']:+.2%} | {r['med10']:+.2%} | "
                  f"{r['up10']:.0%} | {r['mean20']:+.2%} | {r['up20']:.0%} |")
    out["event_study"] = es
    (HERE / f"backtest_pb17_{TODAY}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (HERE / f"backtest_pb17_{TODAY}.md").write_text("\n".join(md), encoding="utf-8")
    print("saved")


if __name__ == "__main__":
    main()
