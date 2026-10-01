"""
Warren Buffett strategy analysis (Berkshire / "wonderful business" framework).

Buffett's hierarchy, in order:
  1. A wonderful business with a durable economic moat   -> facet: moat
  2. Able, honest management & a fortress balance sheet  -> facet: management
  3. Bought with a margin of safety to intrinsic value   -> facet: valuation

"It's far better to buy a wonderful company at a fair price than a fair company
at a wonderful price." Moat comes first; price is the final gate, never the first.

Ticker-targeted (CLI args), pulls live yfinance, emits structured per-ticker
blocks the three Buffett specialist agents parse.

Intrinsic value = two-stage DCF of owner earnings (≈ free cash flow):
  10 yrs at conservative growth (capped 12%), 2.5% terminal, 9% discount rate.
  Margin of safety = (intrinsic - price) / intrinsic.  Buffett wants ≥ ~30%.

Usage:
  python warren_buffett_strategy.py KO AAPL BAC [--facet moat|management|valuation|all]
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

DISCOUNT = 0.09
TERMINAL_G = 0.025
GROWTH_CAP = 0.12   # Buffett is conservative on growth assumptions
GROWTH_FLOOR = 0.03
YEARS = 10
MOS_TARGET = 0.30   # desired margin of safety


def pct(x):
    return None if x is None else x * 100.0


def fnum(x, fmt="%.1f", dash="—"):
    return dash if x is None else (fmt % x)


def earnings_consistency(t):
    """% of recent years with positive net income + a trend note. Best-effort."""
    try:
        fin = t.financials
        if fin is not None and "Net Income" in fin.index:
            ni = fin.loc["Net Income"].dropna().astype(float)
            if len(ni):
                pos = sum(1 for v in ni if v > 0)
                frac = pos / len(ni)
                # financials columns are newest-first; rising = newest > oldest
                rising = ni.iloc[0] > ni.iloc[-1]
                return frac, rising, len(ni)
    except Exception:
        pass
    return None, None, None


def fetch(tk):
    t = yf.Ticker(tk)
    i = t.info or {}
    px = i.get("currentPrice") or i.get("regularMarketPrice")
    mc = i.get("marketCap")
    shares = i.get("sharesOutstanding")
    fcf = i.get("freeCashflow")

    feg = None
    te, fe = i.get("trailingEps"), i.get("forwardEps")
    if fe and te and te > 0:
        feg = (fe / te - 1.0) * 100.0
    rg = pct(i.get("revenueGrowth"))
    cands = [g for g in (feg, rg) if g is not None]
    gsust = min(feg, rg) if (feg is not None and rg is not None) else (cands[0] if cands else None)

    cons_frac, cons_rising, cons_n = earnings_consistency(t)

    share_trend = None
    try:
        cf = t.cashflow
        for key in ("Repurchase Of Capital Stock", "Common Stock Payments"):
            if cf is not None and key in cf.index:
                v = cf.loc[key].dropna()
                if len(v):
                    share_trend = "shrinking (buybacks)" if float(v.iloc[0]) < 0 else "flat/issuing"
                    break
    except Exception:
        pass

    return dict(
        tk=tk, name=i.get("shortName", tk), px=px, mc=mc, shares=shares, fcf=fcf,
        ni=i.get("netIncomeToCommon"),
        pe=i.get("trailingPE"), pb=i.get("priceToBook"), pef=i.get("forwardPE"),
        roe=pct(i.get("returnOnEquity")), roa=pct(i.get("returnOnAssets")),
        gm=pct(i.get("grossMargins")), om=pct(i.get("operatingMargins")), nm=pct(i.get("profitMargins")),
        de=i.get("debtToEquity"), debt=i.get("totalDebt"), cash=i.get("totalCash"),
        cr=i.get("currentRatio"), te=te, fe=fe, gsust=gsust,
        cons_frac=cons_frac, cons_rising=cons_rising, cons_n=cons_n,
        share_trend=share_trend, fcf_yield=(fcf / mc * 100.0) if (fcf and mc) else None,
        beta=i.get("beta"),
    )


def owner_earnings(d):
    """Normalized owner earnings ≈ FCF, but blend/fallback to net income when the
    spot FCF looks distorted (yfinance FCF is a noisy single-TTM snapshot)."""
    fcf, ni = d["fcf"], d["ni"]
    if (not fcf or fcf <= 0):
        return (ni * 0.9) if (ni and ni > 0) else None, "net income (FCF unusable)"
    if ni and ni > 0 and fcf < 0.5 * ni:
        return (fcf + ni) / 2.0, "FCF/NI blend (FCF looked depressed)"
    return fcf, "free cash flow"


def intrinsic_per_share(d):
    oe, basis = owner_earnings(d)
    if not oe or oe <= 0 or not d["shares"]:
        return None, None, None
    oe_ps = oe / d["shares"]
    g = d["gsust"]
    g1 = (min(max(g / 100.0, GROWTH_FLOOR), GROWTH_CAP)) if g is not None else 0.04
    cf, pv = oe_ps, 0.0
    for tyr in range(1, YEARS + 1):
        cf *= (1 + g1)
        pv += cf / ((1 + DISCOUNT) ** tyr)
    terminal = cf * (1 + TERMINAL_G) / (DISCOUNT - TERMINAL_G)
    pv += terminal / ((1 + DISCOUNT) ** YEARS)
    return pv, g1 * 100.0, basis


# ---------- facet blocks ----------

def moat_block(d):
    roe, gm, nm = d["roe"], d["gm"], d["nm"]
    pts = 0
    if roe is not None and roe >= 15: pts += 1
    if roe is not None and roe >= 20: pts += 1
    if gm is not None and gm >= 40: pts += 1
    if nm is not None and nm >= 15: pts += 1
    if d["cons_frac"] is not None and d["cons_frac"] >= 0.8: pts += 1

    if pts >= 4:
        moat, sig, conv = "Wide", "BUY", 8
    elif pts >= 2:
        moat, sig, conv = "Narrow", "HOLD", 6
    else:
        moat, sig, conv = "None", "AVOID", 3

    if roe is not None and roe < 8:
        sig, conv = "AVOID", min(conv, 3)

    key = {
        "Wide": "durable moat — high ROE, fat margins, consistent earnings",
        "Narrow": "some advantage but not bulletproof — watch it",
        "None": "commodity economics — not a wonderful business",
    }[moat]

    print(f"=== MOAT: {d['tk']} ===")
    print(f"TICKER: {d['tk']}")
    print(f"MOAT: {moat}")
    print(f"ROE: {fnum(d['roe'],'%.0f%%')}  ROA: {fnum(d['roa'],'%.0f%%')}")
    print(f"MARGINS: gross {fnum(d['gm'],'%.0f%%')} / oper {fnum(d['om'],'%.0f%%')} / net {fnum(d['nm'],'%.0f%%')}")
    print(f"EARNINGS_CONSISTENCY: " + (
        f"{d['cons_frac']*100:.0f}% positive over {d['cons_n']}y, {'rising' if d['cons_rising'] else 'flat/declining'}"
        if d['cons_frac'] is not None else "—"))
    print(f"SIGNAL: {sig}")
    print(f"CONVICTION: {conv}")
    print(f"KEY: {key}")
    print()


def management_block(d):
    de, cr = d["de"], d["cr"]
    cash, debt = d["cash"], d["debt"]
    net_cash = (cash - debt) if (cash is not None and debt is not None) else None
    flags = []
    if de is not None and de > 100: flags.append("high debt/equity")
    if cr is not None and cr < 1.0: flags.append("current ratio <1")
    if d["share_trend"] == "flat/issuing": flags.append("not buying back stock")

    if de is not None and de < 50 and d["share_trend"] == "shrinking (buybacks)":
        sig, conv, key = "BUY", 8, "fortress balance sheet + shrinking share count — textbook allocation"
    elif de is not None and de < 80 and (not flags):
        sig, conv, key = "BUY", 7, "low debt, clean balance sheet"
    elif de is not None and de > 200:
        sig, conv, key = "HOLD", 4, "heavy debt — Buffett wants a fortress, not leverage"
    elif flags:
        sig, conv, key = "HOLD", 5, "watch: " + ", ".join(flags)
    else:
        sig, conv, key = "HOLD", 6, "adequate financial strength"

    print(f"=== MANAGEMENT: {d['tk']} ===")
    print(f"TICKER: {d['tk']}")
    print(f"DEBT_EQUITY: {fnum(de,'%.0f%%')}")
    print(f"NET_CASH: {fnum((net_cash/1e9) if net_cash is not None else None,'$%.0fB')}  "
          f"(cash {fnum((cash or 0)/1e9,'$%.0fB')} / debt {fnum((debt or 0)/1e9,'$%.0fB')})")
    print(f"CURRENT_RATIO: {fnum(cr,'%.2f')}")
    print(f"SHARE_COUNT_TREND: {d['share_trend'] or '—'}")
    print(f"FCF: {fnum((d['fcf'] or 0)/1e9,'$%.0fB') if d['fcf'] else '—'}  FCF_YIELD: {fnum(d['fcf_yield'],'%.1f%%')}")
    print(f"SIGNAL: {sig}")
    print(f"CONVICTION: {conv}")
    print(f"KEY: {key}")
    print()


def valuation_block(d):
    iv, g_used, basis = intrinsic_per_share(d)
    px = d["px"]
    mos = ((iv - px) / iv) if (iv and px) else None

    if iv is None:
        sig, conv, key = "AVOID", 3, "no positive owner earnings (FCF) — can't value it the Buffett way"
    elif mos is None:
        sig, conv, key = "N/A", 1, "missing price"
    elif mos >= MOS_TARGET:
        sig, conv, key = "BUY", 8, "trades below intrinsic with a real margin of safety"
    elif mos >= 0.10:
        sig, conv, key = "BUY", 6, "modest discount to intrinsic — acceptable if the moat is wide"
    elif mos >= -0.10:
        sig, conv, key = "HOLD", 5, "near fair value — wait for a fatter pitch"
    else:
        sig, conv, key = "HOLD", 3, "above intrinsic value — wonderful or not, wrong price"

    print(f"=== VALUATION: {d['tk']} ===")
    print(f"TICKER: {d['tk']}")
    print(f"PRICE: {fnum(px,'$%.2f')}  INTRINSIC: {fnum(iv,'$%.2f')}  (DCF of owner earnings, g={fnum(g_used,'%.0f%%')}, basis={basis or '—'})")
    print(f"MARGIN_OF_SAFETY: {fnum(pct(mos),'%.0f%%')}   (target ≥ {MOS_TARGET*100:.0f}%)")
    print(f"PE: {fnum(d['pe'])}  PB: {fnum(d['pb'],'%.1f')}  FCF_YIELD: {fnum(d['fcf_yield'],'%.1f%%')}")
    print(f"SIGNAL: {sig}")
    print(f"CONVICTION: {conv}")
    print(f"KEY: {key}")
    print()


def main():
    facet = "all"
    argv = sys.argv[1:]
    for idx, a in enumerate(argv):
        if a.startswith("--facet"):
            if "=" in a:
                facet = a.split("=", 1)[1]
            elif idx + 1 < len(argv):
                facet = argv[idx + 1]
    skip = {facet.lower(), "--facet"}
    tickers = [a.upper() for a in argv if not a.startswith("--") and a.lower() not in skip]
    if not tickers:
        print("Usage: python warren_buffett_strategy.py TICKER [TICKER...] [--facet moat|management|valuation|all]")
        return

    for tk in tickers:
        try:
            d = fetch(tk)
            if d["px"] is None:
                print(f"=== {tk}: NO DATA (symbol not found / no price) ===\n")
                continue
            if facet in ("moat", "all"):
                moat_block(d)
            if facet in ("management", "all"):
                management_block(d)
            if facet in ("valuation", "all"):
                valuation_block(d)
        except Exception as e:
            print(f"=== {tk}: ERROR {str(e)[:80]} ===\n")


if __name__ == "__main__":
    main()
