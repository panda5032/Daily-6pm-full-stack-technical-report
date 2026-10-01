#!/usr/bin/env python3
"""
whale_deep_dive.py — Print-level options-flow forensics for specific tickers.

Complements whale_options_strategy.py (the broad 150-ticker screen, which gets
yfinance-throttled). This script pulls ONE ticker at a time at a low request
rate, then classifies every large print:

  - FRESH vs CHURN            : Vol/OI >= 2.0 (or OI 0) = new positioning
  - WHALE                     : premium >= $2M and fresh
  - ARB                       : fresh deep-ITM calls AND deep-ITM puts paired in
                                the same expiry = box/conversion financing trade
                                -> excluded from directional totals
  - SYNTH_SHORT / STOCK_REPL  : unpaired fresh deep-ITM puts (bearish) / calls
                                (bullish) = defined-risk stock replacement
  - Directional $ P/C          : put$/call$ AFTER removing ARB rows

Also reports per-expiry ATM IV term structure, 30D HV, and the front-expiry
expected move (ATM straddle / spot) so IV richness / event premium is visible.

Usage:
  python whale_deep_dive.py --tickers TSLA ORCL COIN
  python whale_deep_dive.py --tickers NOW --min-premium 200000
Writes whale_deep_dive_<YYYY-MM-DD>.md (appends per run) and prints to stdout.
"""
import argparse, datetime as dt, math, time, sys

import numpy as np
import pandas as pd
import yfinance as yf

DEEP_ITM_CALL = 0.88   # strike < spot * this -> deep ITM call
DEEP_ITM_PUT = 1.12    # strike > spot * this -> deep ITM put
FRESH_VOLOI = 2.0
WHALE_PREM = 2_000_000
MIN_VOL = 100


def hv30(tkr):
    try:
        px = tkr.history(period="3mo")["Close"]
        r = np.log(px / px.shift(1)).dropna()
        return float(r.tail(30).std() * math.sqrt(252))
    except Exception:
        return None


def classify(rows, spot):
    """Tag ARB pairs, synthetic shorts, stock replacement. rows mutated in place."""
    by_exp = {}
    for r in rows:
        by_exp.setdefault(r["exp"], []).append(r)
    for exp, rs in by_exp.items():
        deep_c = [r for r in rs if r["kind"] == "CALL" and r["strike"] < spot * DEEP_ITM_CALL and r["fresh"]]
        deep_p = [r for r in rs if r["kind"] == "PUT" and r["strike"] > spot * DEEP_ITM_PUT and r["fresh"]]
        if deep_c and deep_p:  # both legs present in same expiry -> financing arb
            for r in deep_c + deep_p:
                r["struct"] = "ARB"
        else:
            for r in deep_c:
                r["struct"] = "STOCK_REPL"
            for r in deep_p:
                r["struct"] = "SYNTH_SHORT"


def scan(sym, args, today):
    t = yf.Ticker(sym)
    try:
        spot = float(t.history(period="1d")["Close"].iloc[-1])
    except Exception as e:
        return f"\n## {sym} — ERROR: no price data ({e})\n"
    exps, tries = [], 0
    while tries < 2:
        try:
            exps = [e for e in t.options if 3 <= (dt.date.fromisoformat(e) - today).days <= 120][: args.max_exps]
            if exps:
                break
        except Exception:
            pass
        tries += 1
        time.sleep(10)  # throttle backoff, then one retry
    if not exps:
        return f"\n## {sym} — spot ${spot:.2f} — NO OPTION CHAINS (delisted options or yfinance throttling; retried once)\n"

    rows, term = [], []
    for e in exps:
        try:
            ch = t.option_chain(e)
        except Exception:
            time.sleep(8)
            try:
                ch = t.option_chain(e)
            except Exception:
                continue
        time.sleep(args.sleep)
        dte = (dt.date.fromisoformat(e) - today).days
        atm_ivs, straddle = [], 0.0
        for kind, df in (("CALL", ch.calls), ("PUT", ch.puts)):
            df = df.copy()
            df["mid"] = (df["bid"].fillna(0) + df["ask"].fillna(0)) / 2
            df["prem"] = df["volume"].fillna(0) * df["mid"] * 100
            # ATM IV + straddle leg (nearest strike)
            if len(df):
                near = df.iloc[(df["strike"] - spot).abs().argsort()[:1]]
                iv = float(near["impliedVolatility"].iloc[0] or 0)
                if 0 < iv < 5:
                    atm_ivs.append(iv)
                straddle += float(near["mid"].iloc[0] or 0)
            big = df[(df["volume"] >= MIN_VOL) & (df["prem"] >= args.min_premium)]
            for _, r in big.iterrows():
                oi = int(r["openInterest"]) if pd.notna(r["openInterest"]) else 0
                voloi = (r["volume"] / oi) if oi else float("inf")
                rows.append(dict(kind=kind, strike=float(r["strike"]), exp=e, dte=dte,
                                 vol=int(r["volume"]), oi=oi, voloi=voloi,
                                 prem=float(r["prem"]), iv=float(r["impliedVolatility"] or 0),
                                 fresh=voloi >= FRESH_VOLOI, struct=""))
        term.append((e, dte, np.mean(atm_ivs) if atm_ivs else None, straddle / spot if straddle else None))

    classify(rows, spot)
    raw = {"CALL": 0.0, "PUT": 0.0}
    dire = {"CALL": 0.0, "PUT": 0.0}
    for r in rows:
        raw[r["kind"]] += r["prem"]
        if r["struct"] != "ARB":
            dire[r["kind"]] += r["prem"]
    raw_pc = raw["PUT"] / max(raw["CALL"], 1)
    dir_pc = dire["PUT"] / max(dire["CALL"], 1)
    n_wc = sum(1 for r in rows if r["kind"] == "CALL" and r["prem"] >= WHALE_PREM and r["fresh"] and r["struct"] != "ARB")
    n_wp = sum(1 for r in rows if r["kind"] == "PUT" and r["prem"] >= WHALE_PREM and r["fresh"] and r["struct"] != "ARB")

    if dire["CALL"] + dire["PUT"] < 1_000_000:
        verdict = "NO SIGNAL (flow too thin)"
    elif dir_pc <= 0.6 and n_wc >= n_wp:
        verdict = "BULLISH FLOW"
    elif dir_pc >= 1.5 and n_wp >= n_wc:
        verdict = "BEARISH FLOW"
    elif n_wc and n_wp:
        verdict = "MIXED / TWO-SIDED"
    else:
        verdict = "NEUTRAL"

    hv = hv30(t)
    front_iv = term[0][2] if term and term[0][2] else None
    ivhv = (f"{front_iv/hv:.1f}x HV" if front_iv and hv else "—")

    L = [f"\n## {sym} — spot ${spot:.2f} — **{verdict}**",
         f"- Raw $P/C **{raw_pc:.2f}** (calls ${raw['CALL']/1e6:.1f}M / puts ${raw['PUT']/1e6:.1f}M)"
         f" · Directional (arb-excluded) $P/C **{dir_pc:.2f}** (calls ${dire['CALL']/1e6:.1f}M / puts ${dire['PUT']/1e6:.1f}M)",
         f"- Fresh whale prints: {n_wc} call-side / {n_wp} put-side · 30D HV {hv:.0%} · front ATM IV "
         f"{front_iv:.0%} ({ivhv})" if hv and front_iv else
         f"- Fresh whale prints: {n_wc} call-side / {n_wp} put-side",
         "- Term structure (ATM IV / expected move): " +
         "  ".join(f"{e[5:]}({d}d) {iv:.0%}/{em:+.1%}" for e, d, iv, em in term if iv and em)]
    rows.sort(key=lambda r: -r["prem"])
    L.append("\n| Type | Strike | Exp | DTE | Vol | OI | V/OI | Premium | IV | Tags |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows[: args.top]:
        tags = ",".join(x for x in [r["struct"],
                                    "WHALE" if r["prem"] >= WHALE_PREM and r["fresh"] else "",
                                    "fresh" if r["fresh"] else "churn"] if x)
        voloi = "inf" if r["voloi"] == float("inf") else f"{r['voloi']:.1f}"
        L.append(f"| {r['kind']} | {r['strike']:.0f} | {r['exp']} | {r['dte']} | {r['vol']:,} | {r['oi']:,} "
                 f"| {voloi} | ${r['prem']:,.0f} | {r['iv']:.0%} | {tags} |")
    if not rows:
        L.append(f"(no prints >= ${args.min_premium:,})")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="+", required=True)
    ap.add_argument("--min-premium", type=int, default=250_000)
    ap.add_argument("--max-exps", type=int, default=7)
    ap.add_argument("--sleep", type=float, default=1.2)
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()

    today = dt.date.today()
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    out = [f"# 🐋 Whale Deep Dive — {stamp}",
           f"Tickers: {', '.join(t.upper() for t in args.tickers)} · min print ${args.min_premium:,} "
           f"· DTE 3–120 · fresh = Vol/OI ≥ {FRESH_VOLOI} · whale ≥ ${WHALE_PREM:,}",
           "> ARB rows (paired deep-ITM call+put, same expiry) are financing trades — "
           "excluded from the directional $P/C. Volume shows both sides of a trade; "
           "aggressor side is inferred, not known. Not financial advice."]
    for s in args.tickers:
        block = scan(s.upper(), args, today)
        out.append(block)
        print(block)
    fn = f"whale_deep_dive_{today.isoformat()}.md"
    with open(fn, "a", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n\n---\n")
    print(f"[saved -> {fn}]")


if __name__ == "__main__":
    main()
