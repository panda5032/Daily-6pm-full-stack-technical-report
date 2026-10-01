# -*- coding: utf-8 -*-
"""Backtest of the 7-analyst team composite ("这套打法") by REPLAYING the actual
dated strategy reports archived in this repo (2026-05-01 -> 2026-08-18).

Signals: daily_quant_system's parsers/weights over the 6 mechanized analysts
(right_side .20 / macd .20 / short_term .15 / long_term .15 / principles .15 /
elliott .15). Whale flow & earnings analysts have no historical data -> excluded.

Portfolio rules (the system's own discipline):
  - $3,000,000 start, long only, no leverage
  - entry: verdict BUY (comp >= regime threshold, >=2 bullish analysts, 0 bearish)
  - size: min(8% of NAV, NAV/12); max 12 positions; RISK_OFF halves new-entry size
  - exit: SELL verdict, or close <= -8% vs entry, or close <= -12% vs peak
  - fills: next trading day's OPEN, 5bp slippage each side
"""
import sys, io, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")

import daily_quant_system as dqs

START_CAP = 3_000_000.0
SLIP = 0.0005
MAX_POS = 12
CAP_PCT = 0.08
HARD_STOP = -0.08
TRAIL_STOP = -0.12
BT_START, BT_END = "2026-05-01", "2026-08-18"

# ---------- 1. collect signal days ----------
days = []
for d in pd.date_range(BT_START, BT_END, freq="B"):
    ds = d.strftime("%Y-%m-%d")
    reports = {}
    for key, pat, _s, _w in dqs.STRATEGIES:
        p = dqs.find_report(pat.format(d=ds))
        if p:
            reports[key] = p
    if len(reports) >= 4:
        days.append((ds, reports))
print(f"signal days with >=4 reports: {len(days)}  ({days[0][0]} -> {days[-1][0]})")

signals = {}   # date -> {"regime":..., "rows": {ticker: (comp, bull, bear)}}
coverage = []
for ds, reports in days:
    regime, mult = dqs.market_regime(reports)
    rows = dqs.composite(reports)
    verd = {}
    for r in rows:
        v = dqs.verdict(r, mult, regime)
        verd[r["ticker"]] = (v, r["comp"], r["bull"], r["bear"])
    signals[ds] = {"regime": regime, "mult": mult, "verd": verd}
    coverage.append((ds, regime, len(rows),
                     sum(1 for v in verd.values() if v[0] == "BUY"),
                     sum(1 for v in verd.values() if v[0] == "SELL")))

cov = pd.DataFrame(coverage, columns=["date", "regime", "n_scored", "n_buy", "n_sell"])
print(cov.groupby("regime").agg(days=("date", "count"), avg_scored=("n_scored", "mean"),
                                avg_buy=("n_buy", "mean")).round(1))
low = cov[cov.n_scored < 40]
if len(low):
    print(f"[warn] {len(low)} days with <40 scored tickers (parser/format drift):")
    print(low.to_string(index=False))

# ---------- 2. prices ----------
all_tk = sorted({t for s in signals.values() for t in s["verd"]} | {"SPY", "QQQ"})
raw = yf.download(all_tk, start="2026-04-20", end="2026-08-20", interval="1d",
                  group_by="ticker", auto_adjust=True, threads=True, progress=False)
px = {}
for t in all_tk:
    try:
        df = raw[t].dropna(subset=["Close"])
        if len(df) >= 10:
            px[t] = df
    except Exception:
        pass
print(f"price data for {len(px)}/{len(all_tk)} tickers")

cal = px["SPY"].loc[BT_START:"2026-08-19"].index  # trading calendar incl. day after last signal

def next_open(t, after_ts):
    df = px.get(t)
    if df is None:
        return None, None
    nxt = df.loc[df.index > after_ts]
    if nxt.empty:
        return None, None
    return float(nxt["Open"].iloc[0]), nxt.index[0]

# ---------- 3. simulate ----------
cash = START_CAP
pos = {}       # ticker -> dict(shares, entry, peak, entry_date)
trades = []
equity = []
pending_buys, pending_sells = [], []   # executed at today's open, decided yesterday

for ts in cal:
    ds = ts.strftime("%Y-%m-%d")
    # --- execute pending orders at today's open ---
    for t, reason in pending_sells:
        if t not in pos:
            continue
        o, ots = next_open(t, ts - pd.Timedelta(days=1))
        if o is None or ots != ts:
            odf = px.get(t)
            if odf is None or ts not in odf.index:
                continue
            o = float(odf.loc[ts, "Open"])
        fill = o * (1 - SLIP)
        p = pos.pop(t)
        cash += p["shares"] * fill
        trades.append({"ticker": t, "entry_date": p["entry_date"], "exit_date": ds,
                       "ret": fill / p["entry"] - 1, "reason": reason,
                       "pnl": p["shares"] * (fill - p["entry"])})
    nav_now = cash + sum(p["shares"] * float(px[t].loc[:ts, "Close"].iloc[-1])
                         for t, p in pos.items())
    for t, mult in pending_buys:
        if t in pos or len(pos) >= MAX_POS or t not in px or ts not in px[t].index:
            continue
        o = float(px[t].loc[ts, "Open"])
        fill = o * (1 + SLIP)
        size = min(CAP_PCT * nav_now, nav_now / MAX_POS) * mult
        size = min(size, cash)
        if size < 10_000:
            continue
        sh = size / fill
        cash -= sh * fill
        pos[t] = {"shares": sh, "entry": fill, "peak": fill, "entry_date": ds}
    pending_buys, pending_sells = [], []

    # --- mark to market at close ---
    nav = cash
    for t, p in pos.items():
        c = float(px[t].loc[:ts, "Close"].iloc[-1])
        p["peak"] = max(p["peak"], c)
        nav += p["shares"] * c
    equity.append((ds, nav, len(pos), cash))

    # --- generate tomorrow's orders from today's signals/stops ---
    sig = signals.get(ds)
    for t, p in list(pos.items()):
        c = float(px[t].loc[:ts, "Close"].iloc[-1])
        if c / p["entry"] - 1 <= HARD_STOP:
            pending_sells.append((t, "hard_stop")); continue
        if c / p["peak"] - 1 <= TRAIL_STOP:
            pending_sells.append((t, "trail_stop")); continue
        if sig and t in sig["verd"] and sig["verd"][t][0] == "SELL":
            pending_sells.append((t, "signal"))
    if sig:
        sells = {t for t, _ in pending_sells}
        cands = sorted(((v[1], t) for t, v in sig["verd"].items()
                        if v[0] == "BUY" and t not in pos and t not in sells and t in px),
                       reverse=True)
        slots = MAX_POS - (len(pos) - len([1 for t, _ in pending_sells if t in pos]))
        for comp, t in cands[:max(0, slots)]:
            pending_buys.append((t, sig["mult"] if sig["regime"] == "RISK_OFF" else 1.0))

eq = pd.DataFrame(equity, columns=["date", "nav", "n_pos", "cash"]).set_index("date")
eq.index = pd.to_datetime(eq.index)

# ---------- 4. metrics ----------
def stats(series, label):
    r = series.pct_change().dropna()
    total = series.iloc[-1] / series.iloc[0] - 1
    ann = (1 + total) ** (252 / len(r)) - 1
    sharpe = r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else 0
    dd = (series / series.cummax() - 1).min()
    return {"label": label, "total": total, "ann": ann, "sharpe": sharpe, "maxdd": dd}

spy = px["SPY"].loc[eq.index[0]:eq.index[-1], "Close"]
qqq = px["QQQ"].loc[eq.index[0]:eq.index[-1], "Close"]
res = [stats(eq["nav"], "Team composite ($3M)"), stats(spy, "SPY"), stats(qqq, "QQQ")]

print("\n========== RESULTS", eq.index[0].date(), "->", eq.index[-1].date(), "==========")
for s in res:
    print(f"{s['label']:22s} total {s['total']*100:+7.2f}%  ann {s['ann']*100:+7.2f}%  "
          f"sharpe {s['sharpe']:5.2f}  maxDD {s['maxdd']*100:6.2f}%")
print(f"\nfinal NAV: ${eq['nav'].iloc[-1]:,.0f}   P&L: ${eq['nav'].iloc[-1]-START_CAP:+,.0f}")

tdf = pd.DataFrame(trades)
open_pnl = [{"ticker": t, "ret": float(px[t].loc[:eq.index[-1], 'Close'].iloc[-1]) / p['entry'] - 1,
             "pnl": p['shares'] * (float(px[t].loc[:eq.index[-1], 'Close'].iloc[-1]) - p['entry'])}
            for t, p in pos.items()]
if len(tdf):
    closed = tdf
    wr = (closed.ret > 0).mean()
    print(f"\nclosed trades: {len(closed)}  win rate {wr*100:.0f}%  "
          f"avg win {closed[closed.ret>0].ret.mean()*100:+.1f}%  avg loss {closed[closed.ret<=0].ret.mean()*100:+.1f}%")
    print("exit reasons:", closed.reason.value_counts().to_dict())
    print("\nTop 5 winners (closed):")
    print(closed.nlargest(5, "pnl")[["ticker", "entry_date", "exit_date", "ret", "pnl"]].to_string(index=False))
    print("Top 5 losers (closed):")
    print(closed.nsmallest(5, "pnl")[["ticker", "entry_date", "exit_date", "ret", "pnl"]].to_string(index=False))
print(f"\nstill open: {len(pos)} positions")
if open_pnl:
    od = pd.DataFrame(open_pnl).sort_values("pnl", ascending=False)
    print(od.to_string(index=False))

eq.to_csv("backtest_team_composite_equity.csv")
if len(tdf):
    tdf.to_csv("backtest_team_composite_trades.csv", index=False)
print("\nsaved: backtest_team_composite_equity.csv / _trades.csv")
