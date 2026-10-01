"""
Peter Lynch strategy analysis (One Up on Wall Street framework).

Ticker-targeted (pass symbols on the CLI) rather than xlsx-batch, because the
Lynch team is used on specific names. Pulls live yfinance data and emits
structured per-ticker blocks the Lynch specialist agents parse.

Three facets (the three Lynch specialists each run one):
  category   -> 6-bucket classification + growth durability
  valuation  -> P/E vs growth, PEG, and Lynch's dividend-adjusted PEG
  balance    -> debt, net cash, FCF, buyback trend, "can it survive"

Lynch's core ratios:
  PEG                 = P/E / growth%            (fair ~1.0, cheap <1.0)
  Lynch ratio (yield-adjusted PEG) = (growth% + dividend%) / P/E
                        >1.5 pound the table | 1.0-1.5 fair | <1.0 poor
Growth is capped at 30% — Lynch never trusted triple-digit growth rates.

Usage:
  python peter_lynch_strategy.py IBM MSFT META [--facet category|valuation|balance|all]
"""
import sys
import io
import warnings
import yfinance as yf

warnings.filterwarnings('ignore')
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
except Exception:
    pass

GROWTH_CAP = 30.0  # Lynch discounts anything faster as unsustainable


def pct(x):
    return None if x is None else x * 100.0


def fnum(x, fmt="%.1f", dash="—"):
    return dash if x is None else (fmt % x)


def fetch(tk):
    """Pull the raw fields we need for all three facets. Returns a dict."""
    t = yf.Ticker(tk)
    i = t.info or {}
    px = i.get("currentPrice") or i.get("regularMarketPrice")
    te = i.get("trailingEps")
    fe = i.get("forwardEps")
    pe = i.get("trailingPE")
    pef = i.get("forwardPE")
    mc = i.get("marketCap")

    # dividend yield: compute from rate/price (yfinance .dividendYield is inconsistent)
    dr = i.get("dividendRate") or i.get("trailingAnnualDividendRate")
    dy = (dr / px * 100.0) if (dr and px) else 0.0

    # sustainable growth: forward EPS growth, sanity-checked against revenue growth, take the lower
    feg = ((fe / te - 1.0) * 100.0) if (fe and te and te > 0) else None
    rg = pct(i.get("revenueGrowth"))
    cands = [g for g in (feg, rg) if g is not None]
    if feg is not None and rg is not None:
        gsust = min(feg, rg)
    elif cands:
        gsust = cands[0]
    else:
        gsust = None
    gcap = min(gsust, GROWTH_CAP) if gsust is not None else None

    fcf = i.get("freeCashflow")
    fcf_yield = (fcf / mc * 100.0) if (fcf and mc) else None

    # buyback trend from cashflow (best-effort)
    share_trend = None
    try:
        cf = t.cashflow
        for key in ("Repurchase Of Capital Stock", "Repurchase Of Capital Stock ",
                    "Common Stock Payments"):
            if cf is not None and key in cf.index:
                v = cf.loc[key].dropna()
                if len(v):
                    share_trend = "shrinking (buybacks)" if float(v.iloc[0]) < 0 else "flat/issuing"
                    break
    except Exception:
        pass

    return dict(
        tk=tk, px=px, te=te, fe=fe, pe=pe, pef=pef, mc=mc,
        dy=dy, feg=feg, rg=rg, gsust=gsust, gcap=gcap,
        de=i.get("debtToEquity"), debt=i.get("totalDebt"), cash=i.get("totalCash"),
        cr=i.get("currentRatio"), fcf=fcf, fcf_yield=fcf_yield,
        roe=pct(i.get("returnOnEquity")), gm=pct(i.get("grossMargins")),
        beta=i.get("beta"), hi=i.get("fiftyTwoWeekHigh"), lo=i.get("fiftyTwoWeekLow"),
        share_trend=share_trend, name=i.get("shortName", tk),
    )


def classify(d):
    """Lynch's 6 buckets (best-effort heuristic)."""
    g = d["gsust"]
    mc = d["mc"] or 0
    te = d["te"]
    fe = d["fe"]
    dy = d["dy"]
    beta = d["beta"] or 1.0

    # Turnaround: currently losing money but forecast to earn
    if te is not None and te <= 0 and fe is not None and fe > 0:
        return "Turnaround", "speculative — losses turning to profit"
    # Forward earnings negative → a story, not an earnings stream
    if fe is not None and fe <= 0:
        return "Unclassifiable", "forward earnings negative — a story, not an earnings stream"
    if g is None:
        return "Unclassifiable", "no earnings/growth data — not a classic Lynch stock"
    if g >= 25:
        return "Fast Grower", "the tenbagger hunting ground — verify growth is durable"
    if g >= 20:
        return "Fast Grower", "fast but watch for deceleration"
    if mc >= 50e9 and 8 <= g < 20:
        return "Stalwart", "big, steady — buy on weakness, ring register at +30-50%"
    if g < 8 and dy >= 2.0:
        return "Slow Grower", "own it for the dividend, not the growth"
    if beta >= 1.4 and g < 15:
        return "Cyclical", "time the cycle — wrong entry can halve you"
    if g < 8:
        return "Slow Grower", "low growth, thin/no dividend — little to like"
    return "Stalwart", "moderate grower"


def category_block(d):
    cat, note = classify(d)
    g = d["gsust"]
    # signal from category + durable growth
    if cat == "Fast Grower" and g and g >= 20:
        sig, conv = "BUY", 8
    elif cat == "Stalwart":
        sig, conv = "HOLD", 6
    elif cat == "Slow Grower":
        sig, conv = "HOLD", 4
    elif cat == "Turnaround":
        sig, conv = "HOLD", 4
    elif cat == "Cyclical":
        sig, conv = "HOLD", 5
    else:
        sig, conv = "AVOID", 3
    print(f"=== CATEGORY: {d['tk']} ===")
    print(f"TICKER: {d['tk']}")
    print(f"CATEGORY: {cat}")
    print(f"GROWTH_SUST: {fnum(g, '%.0f%%')}  (fwdEPS={fnum(d['feg'],'%.0f%%')} rev={fnum(d['rg'],'%.0f%%')})")
    print(f"MKTCAP: {fnum((d['mc'] or 0)/1e9, '$%.0fB')}")
    print(f"SIGNAL: {sig}")
    print(f"CONVICTION: {conv}")
    print(f"KEY: {note}")
    print()


def valuation_block(d):
    pe, g, dy = d["pe"], d["gcap"], d["dy"]
    peg = (pe / g) if (pe and pe > 0 and g and g > 0) else None
    lynch = ((g + dy) / pe) if (pe and pe > 0 and g is not None) else None

    if pe is None or pe <= 0:
        sig, conv, key = "AVOID", 3, "no positive P/E — outside Lynch's earnings-based method"
    elif (d["fe"] is not None and d["fe"] <= 0) or (g is not None and g < 0):
        sig, conv, key = "AVOID", 3, "forward earnings negative/shrinking — not a Lynch earnings stream"
    elif lynch is None:
        sig, conv, key = "N/A", 1, "insufficient growth data"
    elif lynch >= 1.5:
        sig, conv, key = "BUY", 8, "pound the table — cheap relative to growth+yield"
    elif lynch >= 1.0:
        sig, conv, key = "BUY", 6, "fair price for the growth"
    elif lynch >= 0.7:
        sig, conv, key = "HOLD", 5, "paying up a bit — not a bargain"
    else:
        sig, conv, key = "HOLD", 3, "expensive vs growth — Lynch passes"

    print(f"=== VALUATION: {d['tk']} ===")
    print(f"TICKER: {d['tk']}")
    print(f"PE: {fnum(pe)}  FWD_PE: {fnum(d['pef'])}")
    print(f"PEG: {fnum(peg, '%.2f')}")
    print(f"LYNCH_RATIO: {fnum(lynch, '%.2f')}   (=(growth%+yield%)/PE; >1.5 pound, 1-1.5 fair, <1 poor)")
    print(f"GROWTH_CAPPED: {fnum(g, '%.0f%%')}  DIV_YIELD: {fnum(dy, '%.1f%%')}")
    print(f"SIGNAL: {sig}")
    print(f"CONVICTION: {conv}")
    print(f"KEY: {key}")
    print()


def balance_block(d):
    de, debt, cash = d["de"], d["debt"], d["cash"]
    net_cash = (cash - debt) if (cash is not None and debt is not None) else None

    flags = []
    if de is not None and de > 100:
        flags.append("high debt/equity")
    if net_cash is not None and net_cash < 0:
        flags.append("net debt")
    if d["cr"] is not None and d["cr"] < 1.0:
        flags.append("current ratio <1")

    # Lynch loved net cash + buybacks; disliked heavy debt
    if net_cash is not None and net_cash > 0 and (de is None or de < 50):
        sig, conv, key = "BUY", 7, "net cash, low debt — balance sheet can't kill it"
    elif de is not None and de > 200:
        sig, conv, key = "HOLD", 4, "heavy debt — check FCF covers it before buying"
    elif flags:
        sig, conv, key = "HOLD", 5, "watch: " + ", ".join(flags)
    else:
        sig, conv, key = "HOLD", 6, "balance sheet adequate"
    if d["fcf"] and d["fcf"] > 0 and de is not None and de > 200:
        key += " (FCF positive, so debt serviceable)"

    print(f"=== BALANCE: {d['tk']} ===")
    print(f"TICKER: {d['tk']}")
    print(f"DEBT_EQUITY: {fnum(de, '%.0f%%')}")
    print(f"NET_CASH: {fnum((net_cash/1e9) if net_cash is not None else None, '$%.0fB')}  "
          f"(cash {fnum((cash or 0)/1e9,'$%.0fB')} / debt {fnum((debt or 0)/1e9,'$%.0fB')})")
    print(f"CURRENT_RATIO: {fnum(d['cr'], '%.2f')}")
    print(f"FCF: {fnum((d['fcf'] or 0)/1e9, '$%.0fB') if d['fcf'] else '—'}  "
          f"FCF_YIELD: {fnum(d['fcf_yield'], '%.1f%%')}")
    print(f"SHARE_COUNT_TREND: {d['share_trend'] or '—'}")
    print(f"SIGNAL: {sig}")
    print(f"CONVICTION: {conv}")
    print(f"KEY: {key}")
    print()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    facet = "all"
    for a in sys.argv[1:]:
        if a.startswith("--facet"):
            if "=" in a:
                facet = a.split("=", 1)[1]
            else:
                idx = sys.argv.index(a)
                if idx + 1 < len(sys.argv):
                    facet = sys.argv[idx + 1]
    tickers = [a.upper() for a in args if a.lower() != facet.lower()]
    if not tickers:
        print("Usage: python peter_lynch_strategy.py TICKER [TICKER...] [--facet category|valuation|balance|all]")
        return

    for tk in tickers:
        try:
            d = fetch(tk)
            if d["px"] is None:
                print(f"=== {tk}: NO DATA (symbol not found / no price) ===\n")
                continue
            if facet in ("category", "all"):
                category_block(d)
            if facet in ("valuation", "all"):
                valuation_block(d)
            if facet in ("balance", "all"):
                balance_block(d)
        except Exception as e:
            print(f"=== {tk}: ERROR {str(e)[:80]} ===\n")


if __name__ == "__main__":
    main()
