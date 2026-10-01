# -*- coding: utf-8 -*-
"""$3M forward paper-trading portfolio driven by the 7-analyst team composite.

Live (forward) version of backtest_team_composite.py. State on disk, one run
per trading day (after close). NO REAL TRADES — signals and bookkeeping only.

Rules (identical to the backtest):
  - entry: composite verdict BUY (comp >= regime threshold, >=2 bullish, 0 bearish)
  - size:  min(8% NAV, NAV/12), max 12 positions, RISK_OFF halves new entries
  - exit:  SELL verdict, close <= -8% vs entry, close <= -12% vs peak
  - fills: orders decided on day T fill at day T+1 OPEN, 5bp slippage per side

Files: paper_3m_state.json / paper_3m_trades.csv / paper_3m_equity.csv

Usage:
  python paper_3m_portfolio.py            # daily run (also does first-time init)
  python paper_3m_portfolio.py --report   # comparison vs SPY/QQQ so far / final
"""
import json, csv, sys, io, argparse, warnings
from datetime import date, datetime
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import daily_quant_system as dqs

HERE = Path(__file__).parent
STATE_F = HERE / "paper_3m_state.json"
TRADES_F = HERE / "paper_3m_trades.csv"
EQUITY_F = HERE / "paper_3m_equity.csv"

START_CAP = 3_000_000.0
SLIP = 0.0005
MAX_POS = 12
CAP_PCT = 0.08
HARD_STOP = -0.08
TRAIL_STOP = -0.12
START_DATE = "2026-08-19"          # signal day 0 (fills begin 2026-08-20)
END_DATE = "2026-09-18"            # last MTM date; final report on/after 09-21


def load_state():
    if STATE_F.exists():
        return json.loads(STATE_F.read_text(encoding="utf-8"))
    return {"cash": START_CAP, "pos": {}, "pending_buys": [], "pending_sells": [],
            "bench": {}, "last_run": None, "initialized": False}


def save_state(s):
    STATE_F.write_text(json.dumps(s, indent=2), encoding="utf-8")


def append_csv(path, row, fields):
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new:
            w.writeheader()
        w.writerow(row)


TRADE_FIELDS = ["date", "action", "ticker", "shares", "fill", "notional",
                "reason", "entry_price", "ret_pct", "pnl"]
EQ_FIELDS = ["date", "nav", "cash", "n_pos", "invested_pct", "spy", "qqq"]


def todays_signals(ds):
    reports = {}
    for key, pat, _s, _w in dqs.STRATEGIES:
        p = dqs.find_report(pat.format(d=ds))
        if p:
            reports[key] = p
    if len(reports) < 4:
        return None, None, len(reports)
    regime, mult = dqs.market_regime(reports)
    rows = dqs.composite(reports)
    verd = {r["ticker"]: (dqs.verdict(r, mult, regime), r["comp"]) for r in rows}
    return {"regime": regime, "mult": mult, "verd": verd}, reports, len(reports)


def fetch_prices(tickers, start="2026-08-14"):
    tickers = sorted(set(tickers) | {"SPY", "QQQ"})
    raw = yf.download(tickers, start=start, interval="1d", group_by="ticker",
                      auto_adjust=True, threads=True, progress=False)
    px = {}
    for t in tickers:
        try:
            df = raw[t].dropna(subset=["Close"])
            if len(df):
                px[t] = df
        except Exception:
            pass
    return px


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--date", default=None, help="override run date YYYY-MM-DD")
    args = ap.parse_args()

    s = load_state()
    ds = args.date or date.today().strftime("%Y-%m-%d")

    if args.report:
        report(s)
        return

    if s["last_run"] == ds:
        print(f"[skip] already ran for {ds}")
        report(s)
        return

    need = list(s["pos"]) + [t for t, _ in s["pending_buys"]] + [t for t, _ in s["pending_sells"]]
    px = fetch_prices(need)
    spy = px["SPY"]
    if ds not in spy.index.strftime("%Y-%m-%d"):
        print(f"[{ds}] not a trading day — no action")
        s["last_run"] = ds
        save_state(s)
        return
    ts = spy.index[spy.index.strftime("%Y-%m-%d") == ds][0]

    # ---- 1. fill pending SELLS at today's open ----
    for t, reason in s["pending_sells"]:
        p = s["pos"].get(t)
        if not p or t not in px or ts not in px[t].index:
            continue
        fill = float(px[t].loc[ts, "Open"]) * (1 - SLIP)
        pnl = p["shares"] * (fill - p["entry"])
        s["cash"] += p["shares"] * fill
        append_csv(TRADES_F, {"date": ds, "action": "SELL", "ticker": t,
                              "shares": round(p["shares"], 4), "fill": round(fill, 4),
                              "notional": round(p["shares"] * fill, 2), "reason": reason,
                              "entry_price": p["entry"],
                              "ret_pct": round((fill / p["entry"] - 1) * 100, 2),
                              "pnl": round(pnl, 2)}, TRADE_FIELDS)
        print(f"SELL {t:6s} {p['shares']:.1f} sh @ {fill:.2f}  ({reason})  P&L ${pnl:+,.0f}")
        del s["pos"][t]
    s["pending_sells"] = []

    # ---- 2. fill pending BUYS at today's open ----
    nav_now = s["cash"] + sum(p["shares"] * float(px[t].loc[:ts, "Close"].iloc[-1])
                              for t, p in s["pos"].items() if t in px)
    for t, mult in s["pending_buys"]:
        if t in s["pos"] or len(s["pos"]) >= MAX_POS or t not in px or ts not in px[t].index:
            continue
        fill = float(px[t].loc[ts, "Open"]) * (1 + SLIP)
        size = min(min(CAP_PCT * nav_now, nav_now / MAX_POS) * mult, s["cash"])
        if size < 10_000:
            continue
        sh = size / fill
        s["cash"] -= sh * fill
        s["pos"][t] = {"shares": sh, "entry": fill, "peak": fill, "entry_date": ds}
        append_csv(TRADES_F, {"date": ds, "action": "BUY", "ticker": t,
                              "shares": round(sh, 4), "fill": round(fill, 4),
                              "notional": round(sh * fill, 2), "reason": "signal",
                              "entry_price": fill, "ret_pct": "", "pnl": ""}, TRADE_FIELDS)
        print(f"BUY  {t:6s} {sh:.1f} sh @ {fill:.2f}  (${sh*fill:,.0f})")
    s["pending_buys"] = []

    # ---- 3. benchmark basis on first fill day ----
    if not s["bench"] and s["initialized"]:
        s["bench"] = {"date": ds,
                      "SPY": float(spy.loc[ts, "Open"]) * (1 + SLIP),
                      "QQQ": float(px["QQQ"].loc[ts, "Open"]) * (1 + SLIP)}
        print(f"benchmark basis set {ds}: SPY {s['bench']['SPY']:.2f} QQQ {s['bench']['QQQ']:.2f}")

    # ---- 4. mark to market ----
    nav = s["cash"]
    for t, p in s["pos"].items():
        if t in px:
            c = float(px[t].loc[:ts, "Close"].iloc[-1])
            p["peak"] = max(p["peak"], c)
            nav += p["shares"] * c
    append_csv(EQUITY_F, {"date": ds, "nav": round(nav, 2), "cash": round(s["cash"], 2),
                          "n_pos": len(s["pos"]),
                          "invested_pct": round((nav - s["cash"]) / nav * 100, 1),
                          "spy": round(float(spy.loc[ts, "Close"]), 2),
                          "qqq": round(float(px["QQQ"].loc[ts, "Close"]), 2)}, EQ_FIELDS)
    print(f"[{ds}] NAV ${nav:,.0f}  cash ${s['cash']:,.0f}  positions {len(s['pos'])}")

    # ---- 5. tomorrow's orders from today's signals + stops ----
    if ds <= END_DATE:
        sig, _reports, n_rep = todays_signals(ds)
        for t, p in s["pos"].items():
            if t not in px:
                continue
            c = float(px[t].loc[:ts, "Close"].iloc[-1])
            if c / p["entry"] - 1 <= HARD_STOP:
                s["pending_sells"].append([t, "hard_stop"]); continue
            if c / p["peak"] - 1 <= TRAIL_STOP:
                s["pending_sells"].append([t, "trail_stop"]); continue
            if sig and t in sig["verd"] and sig["verd"][t][0] == "SELL":
                s["pending_sells"].append([t, "signal"])
        if sig:
            sells = {t for t, _ in s["pending_sells"]}
            cands = sorted(((v[1], t) for t, v in sig["verd"].items()
                            if v[0] == "BUY" and t not in s["pos"] and t not in sells),
                           reverse=True)
            slots = MAX_POS - (len(s["pos"]) - len(sells & set(s["pos"])))
            m = sig["mult"] if sig["regime"] == "RISK_OFF" else 1.0
            for comp, t in cands[:max(0, slots)]:
                s["pending_buys"].append([t, m])
            print(f"signals[{ds}] regime={sig['regime']} ({n_rep}/6 reports) -> "
                  f"pending buys {len(s['pending_buys'])}, sells {len(s['pending_sells'])}")
        else:
            print(f"[warn] only {n_rep}/6 reports for {ds} — stops only, no new signals")
        if not s["initialized"]:
            s["initialized"] = True
    else:
        print(f"[{ds}] past END_DATE {END_DATE} — managing exits only, no new buys")
        for t, p in s["pos"].items():
            if t not in px:
                continue
            c = float(px[t].loc[:ts, "Close"].iloc[-1])
            if c / p["entry"] - 1 <= HARD_STOP:
                s["pending_sells"].append([t, "hard_stop"])
            elif c / p["peak"] - 1 <= TRAIL_STOP:
                s["pending_sells"].append([t, "trail_stop"])

    s["last_run"] = ds
    save_state(s)


def report(s):
    if not EQUITY_F.exists():
        print("no equity history yet")
        return
    eq = pd.read_csv(EQUITY_F, parse_dates=["date"]).drop_duplicates("date", keep="last")
    last = eq.iloc[-1]
    port_ret = last["nav"] / START_CAP - 1
    line = f"\n===== $3M PAPER PORTFOLIO — {last['date'].date()} ====="
    print(line)
    print(f"NAV ${last['nav']:,.0f}   return {port_ret*100:+.2f}%   "
          f"positions {int(last['n_pos'])}   cash ${last['cash']:,.0f}")
    if s.get("bench"):
        spy_r = last["spy"] / s["bench"]["SPY"] - 1
        qqq_r = last["qqq"] / s["bench"]["QQQ"] - 1
        print(f"vs SPY {spy_r*100:+.2f}%  (alpha {(port_ret-spy_r)*100:+.2f}pp)   "
              f"vs QQQ {qqq_r*100:+.2f}%  (alpha {(port_ret-qqq_r)*100:+.2f}pp)")
        print(f"(benchmarks basis: {s['bench']['date']} open, same slippage)")
    if len(eq) > 2:
        r = eq.set_index("date")["nav"].pct_change().dropna()
        dd = (eq["nav"] / eq["nav"].cummax() - 1).min()
        sharpe = r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else 0
        print(f"maxDD {dd*100:.2f}%   sharpe(ann) {sharpe:.2f}   days {len(eq)}")
    if TRADES_F.exists():
        td = pd.read_csv(TRADES_F)
        sells = td[td.action == "SELL"]
        print(f"trades: {len(td[td.action=='BUY'])} buys, {len(sells)} sells", end="")
        if len(sells):
            print(f", realized P&L ${sells.pnl.sum():+,.0f}, win rate "
                  f"{(sells.pnl > 0).mean()*100:.0f}%")
        else:
            print()
    if s.get("pos"):
        print("open positions:")
        for t, p in sorted(s["pos"].items()):
            print(f"  {t:6s} {p['shares']:9.1f} sh  entry {p['entry']:9.2f}  since {p['entry_date']}")


if __name__ == "__main__":
    main()
