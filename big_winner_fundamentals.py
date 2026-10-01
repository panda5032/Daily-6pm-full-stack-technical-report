"""
big_winner_fundamentals.py — BUSINESS-fundamentals data layer for the Big Winner routine
========================================================================================
NOT a technical-analysis tool and NOT a scorer. Its only job is to pull a clean,
consistent set of *business* fundamentals so the daily local-Claude routine can spend
its reasoning on TAM / moat / competitive position / industry / catalysts instead of
scraping basic numbers.

Two layers per name:
  1. GROWTH layer — multi-year revenue trajectory + CAGR, YoY + acceleration, gross/op/net
     margins + trend, FCF margin, cash/burn/runway, dilution, Rule-of-40, forward growth,
     analyst targets, business description.
  2. BUFFETT / QUALITY layer — ROE, ROIC, ROA, debt/equity, current/quick ratio, interest
     coverage, EBITDA + margin, net-debt/EBITDA, FCF yield, P/B, book value, insider &
     institutional ownership, buyback yield, earnings/revenue stability, effective tax rate,
     plus a transparent **3-year price scaffold** (bear/base/bull from revenue×exit-P/S).
     The 3yr scaffold is MECHANICAL — Claude overrides it with judgment in the report.
  3. PETER LYNCH growth layer — the PRIMARY lens for this hypergrowth watchlist (Lynch hunted
     "tenbaggers" in fast growers, which Buffett's mature-moat lens misses): Lynch 6-category
     classification, **PEG (fwd P/E ÷ growth%)** + dividend-adjusted Lynch ratio, has-earnings
     flag, institutional ownership (low = undiscovered), and a 0-5 tenbagger-flag tally.

The judgment + scoring happens in the Claude routine (see
.claude/scheduled-tasks/big-winner-scan/SKILL.md), on a 3-5 YEAR horizon rubric:
  TAM(20) Growth-durability(20) Business-model(15) Moat(15) Tailwind(10)
  Runway(10) Management(5) Valuation-vs-upside(5)  + a parallel Buffett quality scorecard.

Outputs:
    big_winner_fundamentals_YYYY-MM-DD.json   full structured data (Claude reads this)
    big_winner_fundamentals_YYYY-MM-DD.md     compact growth table + Buffett/quality table

Usage:
    python big_winner_fundamentals.py                 # default 34-name watchlist
    python big_winner_fundamentals.py TSLA NVDA AMD   # ad-hoc
"""
import sys, io, json, time, warnings
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import yfinance as yf

warnings.filterwarnings('ignore')
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
except Exception:
    pass

HERE = Path(__file__).parent

WATCHLIST = [
    # --- original 34 ---
    'TSLA', 'AVGO', 'ORCL', 'CRWV', 'ANET', 'NOW', 'IBM', 'CRM', 'PLTR', 'SERV',
    'PATH', 'ONDS', 'SOFI', 'ZETA', 'SOUN', 'BBAI', 'ASTS', 'RKLB', 'APLD', 'IREN',
    'BABA', 'BIDU', 'CRCL', 'COIN', 'MSTR', 'PONY', 'USAR', 'HIMS', 'OSCR', 'OKLO',
    'SHOP', 'ZS', 'ADUR', 'MP',
    # --- added 2026-06-07 (mega-cap AI + semis + biotech/GLP-1 + space + fintech + cyber) ---
    'AAPL', 'MSFT', 'META', 'GOOG', 'AMZN', 'NVDA', 'ADBE', 'DDOG', 'PANW', 'RBRK',
    'DUOL', 'AMD', 'ALAB', 'CSCO', 'HOOD', 'LMND', 'LLY', 'NVO', 'SNOW', 'TTD',
    'MU', 'IONQ', 'DELL', 'UNH', 'LUNR', 'FLY', 'MDB', 'FIG', 'UPST',
    'DOCN', 'NET', 'SMCI', 'CRDO', 'MNDY', 'INDO', 'TSM', 'CIFR', 'APP', 'RDDT',
    'KTOS', 'QCOM', 'CRWD', 'MRVL',
]

# Secular theme + strength (0-10). Feeds the routine's "secular tailwind" dimension.
THEMES = {
    'TSLA': ('Autonomy / EV / Robotics', 9),      'PONY': ('Autonomy / Robotaxi', 9),
    'SERV': ('Robotics / Autonomous Delivery', 8), 'PATH': ('AI Automation (RPA)', 7),
    'CRWV': ('AI Compute / GPU Cloud', 10),        'ORCL': ('AI Cloud Infrastructure', 9),
    'ANET': ('AI Networking / Datacenter', 9),     'AVGO': ('AI Semis / Custom Silicon', 9),
    'APLD': ('AI Datacenter / HPC Hosting', 9),    'IREN': ('AI/HPC + Bitcoin Compute', 8),
    'PLTR': ('AI Software / Defense', 9),          'NOW':  ('Enterprise AI Software', 7),
    'CRM':  ('Enterprise AI Software', 6),         'IBM':  ('Enterprise AI / Hybrid Cloud', 5),
    'ZS':   ('Cybersecurity / Zero Trust', 7),     'SHOP': ('E-commerce Platform', 6),
    'ZETA': ('AI Marketing Cloud', 7),             'SOUN': ('Voice / Conversational AI', 8),
    'BBAI': ('AI / Defense Analytics', 8),         'ASTS': ('Space / Sat-to-Cell', 9),
    'RKLB': ('Space / Launch + Systems', 9),       'OKLO': ('Advanced Nuclear (SMR)', 9),
    'ONDS': ('Drones / Defense Autonomy', 8),      'MP':   ('Rare Earth / Critical Minerals', 9),
    'USAR': ('Rare Earth Magnets', 9),             'COIN': ('Crypto Exchange Infra', 8),
    'MSTR': ('Bitcoin Treasury', 8),               'CRCL': ('Stablecoin / Crypto Infra', 8),
    'SOFI': ('Fintech Disruptor', 7),              'HIMS': ('Telehealth / Consumer Health', 7),
    'OSCR': ('Health Insurance Tech', 7),          'BABA': ('China Tech / AI / Cloud', 5),
    'BIDU': ('China AI / Autonomy', 5),            'ADUR': ('Clean Tech / Chemical Recycling', 6),
    # --- added 2026-06-07 ---
    'AAPL': ('Consumer Tech / On-device AI', 6),   'MSFT': ('AI Software / Azure Cloud', 9),
    'META': ('AI / Social / Ads', 8),              'GOOG': ('AI / Search / Cloud', 8),
    'AMZN': ('AI Cloud (AWS) / E-commerce', 8),    'NVDA': ('AI Compute / GPUs', 10),
    'ADBE': ('Creative / AI Software', 6),         'DDOG': ('Observability / Cloud Monitoring', 8),
    'PANW': ('Cybersecurity Platform', 8),         'RBRK': ('Cyber Resilience / Data Security', 8),
    'DUOL': ('EdTech / Consumer AI', 8),           'AMD':  ('AI Semis / GPUs + CPUs', 9),
    'ALAB': ('AI Connectivity Silicon', 9),        'CSCO': ('Networking / AI Infra', 6),
    'HOOD': ('Fintech / Brokerage / Crypto', 8),   'LMND': ('Insurtech / AI Insurance', 7),
    'LLY':  ('GLP-1 / Pharma', 9),                 'NVO':  ('GLP-1 / Pharma', 8),
    'SNOW': ('Data Cloud / AI', 8),                'TTD':  ('AdTech / Connected TV', 8),
    'MU':   ('Memory / HBM Semis', 9),
    'IONQ': ('Quantum Computing', 8),              'DELL': ('AI Servers / Infrastructure', 8),
    'UNH':  ('Health Insurance / Care', 5),        'LUNR': ('Space / Lunar Services', 8),
    'FLY':  ('Space / Launch', 9),                 'MDB':  ('Database / AI Data', 8),
    'FIG':  ('Design Software / AI', 8),           'UPST': ('AI Lending / Fintech', 7),
    'DOCN': ('Cloud for SMB / AI', 7),             'NET':  ('Edge / Cloud Security', 9),
    'SMCI': ('AI Servers / Infrastructure', 8),    'CRDO': ('AI Connectivity (AECs)', 9),
    'MNDY': ('Work Management SaaS', 7),           'INDO': ('Energy (Indonesia O&G)', 4),
    'TSM':  ('Semiconductor Foundry', 9),          'CIFR': ('Bitcoin Mining / AI Datacenter', 8),
    'APP':  ('AdTech / AI (AppLovin)', 9),         'RDDT': ('Social / AI Data Licensing', 8),
    'KTOS': ('Defense / Drones', 8),               'QCOM': ('Mobile / Edge AI Semis', 6),
    'CRWD': ('Cybersecurity (CrowdStrike)', 9),    'MRVL': ('AI Semis / Custom Silicon', 9),
}


def _row(df, *names):
    """First matching row of a financial-statement DataFrame, newest-first values."""
    if df is None or getattr(df, 'empty', True):
        return None
    for n in names:
        if n in df.index:
            try:
                return [float(v) if v == v else None for v in df.loc[n].values]
            except Exception:
                return None
    return None


def _cagr(series):
    """CAGR across a newest-first series, using oldest positive -> newest positive."""
    if not series:
        return None
    vals = [v for v in series if v is not None]
    if len(vals) < 2:
        return None
    newest = vals[0]
    oldest = vals[-1]
    yrs = len(vals) - 1
    if newest is None or oldest is None or oldest <= 0 or newest <= 0 or yrs < 1:
        return None
    return (newest / oldest) ** (1 / yrs) - 1


def _stability(series):
    """Earnings/revenue predictability: 1 - coefficient-of-variation, clamped 0..1.
    High = smooth & predictable (Buffett likes this); low = lumpy. None if can't compute."""
    if not series:
        return None
    vals = [v for v in series if v is not None]
    if len(vals) < 3:
        return None
    mean = sum(vals) / len(vals)
    if mean == 0:
        return None
    var = sum((v - mean) ** 2 for v in vals) / len(vals)
    cv = (var ** 0.5) / abs(mean)
    return max(0.0, min(1.0, 1.0 - cv))


def lynch_category(rev_yoy, fwd_growth, market_cap, profitable, sector, div_yield, losses_narrowing):
    """Peter Lynch's 6-bucket classification (suggested — Claude finalizes in the report).
    Fast Grower (20%+, where tenbaggers live) · Stalwart (10-20%, large) · Slow Grower (<10%) ·
    Cyclical (sector tag) · Turnaround (declining/recovering) · Asset Play (Claude-assigned)."""
    g = fwd_growth if fwd_growth is not None else rev_yoy
    cyclical = sector in ('Energy', 'Basic Materials')
    if g is None:
        base = 'Unclassified'
    elif g >= 0.20:
        base = 'Fast Grower'
    elif g >= 0.10:
        base = 'Stalwart' if (market_cap or 0) > 5e10 else 'Medium Grower'
    elif g >= 0.0:
        base = 'Slow Grower'
    else:
        base = 'Turnaround' if (losses_narrowing or not profitable) else 'Slow Grower'
    return base + (' / Cyclical' if cyclical else '')


def lynch_peg(forward_pe, earnings_growth, fwd_rev_growth, rev_cagr, div_yield):
    """Lynch's signature tools. Returns (PEG, dividend-adjusted Lynch ratio).
    PEG = P/E ÷ growth%  — <1 attractive, ~0.5 great, >2 expensive ("a fairly priced
    company has P/E = its growth rate").  Lynch ratio = (growth% + yield%) ÷ P/E —
    >2 great, 1-2 ok, <1 poor.  None when there are no earnings (not a Lynch buy yet)."""
    g = None
    for cand in (earnings_growth, fwd_rev_growth, rev_cagr):
        if cand is not None and cand > 0:
            g = cand
            break
    if not forward_pe or forward_pe <= 0 or not g or g <= 0:
        return None, None
    g_pct = g * 100
    div_pct = 0.0
    if div_yield:
        div_pct = div_yield * 100 if div_yield < 1 else div_yield   # handle frac vs pct
    peg = forward_pe / g_pct
    lynch_ratio = (g_pct + div_pct) / forward_pe
    return round(peg, 2), round(lynch_ratio, 2)


def three_year_scenarios(price, rev_ttm, ps_ttm, fwd_growth, cagr, dilution_yoy):
    """MECHANICAL 3-year price scaffold (NOT a forecast) — gives Claude a transparent
    starting point it then overrides with judgment in the report.
    Method: project revenue 3 yrs (near-term growth decaying toward ~12% terminal),
    apply exit P/S bands (multiple compression for rich names, re-rating room for cheap),
    and drag for ongoing dilution. Returns bear/base/bull implied price + base 3yr CAGR."""
    if not price or not rev_ttm or not ps_ttm or ps_ttm <= 0:
        return None
    g0 = fwd_growth if fwd_growth is not None else (cagr if cagr is not None else 0.15)
    try:
        g0 = float(g0)
    except Exception:
        return None
    g0 = max(min(g0, 2.5), -0.30)
    rev = rev_ttm
    g = g0
    for _ in range(3):
        rev *= (1 + g)
        g = g * 0.60 + 0.12 * 0.40          # decay toward ~12% terminal
    rev_mult = rev / rev_ttm
    # exit P/S as a fraction of TODAY's multiple
    if ps_ttm >= 20:    bear, base, bull = 0.28, 0.50, 0.85   # rich -> heavy compression
    elif ps_ttm >= 8:   bear, base, bull = 0.45, 0.72, 1.10
    elif ps_ttm >= 3:   bear, base, bull = 0.55, 0.85, 1.25
    else:               bear, base, bull = 0.70, 1.10, 1.65   # cheap -> re-rating room
    dil = dilution_yoy if dilution_yoy is not None else 0.0
    dil = max(min(dil, 0.45), -0.10)
    share_infl = (1 + dil) ** 3
    def implied(frac):
        return price * rev_mult * frac / share_infl
    p_base = implied(base)
    cagr_base = ((p_base / price) ** (1 / 3) - 1) if (p_base and price) else None
    return {
        'rev_growth_assumed_y1': round(g0, 4),
        'rev_mult_3y': round(rev_mult, 3),
        'exit_ps_bear': round(ps_ttm * bear, 2),
        'exit_ps_base': round(ps_ttm * base, 2),
        'exit_ps_bull': round(ps_ttm * bull, 2),
        'price_bear_3y': round(implied(bear), 2),
        'price_base_3y': round(implied(base), 2),
        'price_bull_3y': round(implied(bull), 2),
        'implied_cagr_base': round(cagr_base, 4) if cagr_base is not None else None,
    }


def fetch_one(ticker, max_retries=3):
    for attempt in range(max_retries):
        try:
            t = yf.Ticker(ticker)
            info = {}
            try:
                info = t.info or {}
            except Exception:
                info = {}

            g = info.get
            # live price
            px = g('currentPrice')
            try:
                fi = t.fast_info
                p = (fi.get('last_price') if hasattr(fi, 'get') else None) or getattr(fi, 'last_price', None)
                if p and float(p) > 0:
                    px = float(p)
            except Exception:
                pass
            if not px:
                px = g('previousClose')

            # annual statements
            inc = None; cf = None; bs = None
            try: inc = t.income_stmt
            except Exception: pass
            try: cf = t.cashflow
            except Exception: pass
            try: bs = t.balance_sheet
            except Exception: pass

            rev = _row(inc, 'Total Revenue')
            gp = _row(inc, 'Gross Profit')
            oi = _row(inc, 'Operating Income')
            ni = _row(inc, 'Net Income', 'Net Income Common Stockholders')
            rd = _row(inc, 'Research And Development')
            fcf = _row(cf, 'Free Cash Flow')
            shares_hist = _row(bs, 'Ordinary Shares Number', 'Share Issued')

            rev_latest = rev[0] if rev else g('totalRevenue')
            rev_yoy = (rev[0] / rev[1] - 1) if (rev and len(rev) >= 2 and rev[1]) else g('revenueGrowth')
            rev_yoy_prior = (rev[1] / rev[2] - 1) if (rev and len(rev) >= 3 and rev[2]) else None
            rev_cagr = _cagr(rev)
            rev_accel = (rev_yoy is not None and rev_yoy_prior is not None and rev_yoy > rev_yoy_prior)

            gm = (gp[0] / rev[0]) if (gp and rev and rev[0]) else g('grossMargins')
            gm_prior = (gp[1] / rev[1]) if (gp and rev and len(gp) >= 2 and len(rev) >= 2 and rev[1]) else None
            gm_trend = (gm is not None and gm_prior is not None and gm > gm_prior)
            opm = (oi[0] / rev[0]) if (oi and rev and rev[0]) else g('operatingMargins')
            nim = (ni[0] / rev[0]) if (ni and rev and rev[0]) else g('profitMargins')

            ni_latest = ni[0] if ni else None
            profitable = (ni_latest is not None and ni_latest > 0)
            losses_narrowing = (ni is not None and len(ni) >= 2 and ni[0] is not None and ni[1] is not None
                                and ni[0] < 0 and ni[0] > ni[1])

            fcf_latest = fcf[0] if fcf else g('freeCashflow')
            fcf_margin = (fcf_latest / rev_latest) if (fcf_latest is not None and rev_latest) else None
            cash = g('totalCash')
            runway_years = (cash / abs(fcf_latest)) if (fcf_latest and fcf_latest < 0 and cash) else None

            dilution_yoy = None
            if shares_hist and len(shares_hist) >= 2 and shares_hist[0] and shares_hist[1]:
                dilution_yoy = shares_hist[0] / shares_hist[1] - 1

            rd_intensity = (rd[0] / rev[0]) if (rd and rev and rev[0] and rd[0]) else None

            # Rule of 40 = revenue growth % + FCF margin %  (fallback to op margin)
            r40 = None
            if rev_yoy is not None:
                prof = fcf_margin if fcf_margin is not None else opm
                if prof is not None:
                    r40 = rev_yoy * 100 + prof * 100

            tgt_mean = g('targetMeanPrice'); tgt_high = g('targetHighPrice')

            # ---- Buffett / quality layer -------------------------------------------------
            mcap = g('marketCap')
            ebit_row = _row(inc, 'EBIT', 'Operating Income')
            ebitda_row = _row(inc, 'EBITDA', 'Normalized EBITDA')
            pretax_row = _row(inc, 'Pretax Income')
            tax_row = _row(inc, 'Tax Provision')
            int_row = _row(inc, 'Interest Expense', 'Interest Expense Non Operating')
            equity_row = _row(bs, 'Stockholders Equity', 'Common Stock Equity',
                              'Total Equity Gross Minority Interest')
            invcap_row = _row(bs, 'Invested Capital')
            ocf = _row(cf, 'Operating Cash Flow')

            ebit0 = ebit_row[0] if ebit_row else None
            ebitda0 = (ebitda_row[0] if ebitda_row else None) or g('ebitda')
            ebitda_margin = (ebitda0 / rev_latest) if (ebitda0 and rev_latest) else None
            equity0 = equity_row[0] if equity_row else None
            total_debt = g('totalDebt')

            # effective tax rate (clamp to a sane band), default 21%
            tax_rate = None
            if pretax_row and tax_row and pretax_row[0] and pretax_row[0] > 0 and tax_row[0] is not None:
                tax_rate = max(0.0, min(0.45, tax_row[0] / pretax_row[0]))
            if tax_rate is None:
                tax_rate = 0.21

            invested_capital = (invcap_row[0] if invcap_row else
                                (((total_debt or 0) + (equity0 or 0)) if (total_debt or equity0) else None))
            nopat = (ebit0 * (1 - tax_rate)) if ebit0 is not None else None
            roic = (nopat / invested_capital) if (nopat is not None and invested_capital and invested_capital > 0) else None

            roe = g('returnOnEquity')
            if roe is None and ni_latest is not None and equity0 and equity0 > 0:
                roe = ni_latest / equity0
            roa = g('returnOnAssets')

            interest_coverage = (ebit0 / abs(int_row[0])) if (ebit0 is not None and int_row and int_row[0]) else None
            net_debt = (((total_debt or 0) - (cash or 0))
                        if (total_debt is not None or cash is not None) else None)
            net_debt_to_ebitda = (net_debt / ebitda0) if (net_debt is not None and ebitda0 and ebitda0 > 0) else None
            fcf_yield = (fcf_latest / mcap) if (fcf_latest is not None and mcap) else None
            buyback_yield = (-dilution_yoy) if (dilution_yoy is not None and dilution_yoy < 0) else None
            rev_per_share_cagr = rev_cagr  # proxy; share count adj is in dilution
            earnings_stability = _stability(ni)
            revenue_stability = _stability(rev)

            scenarios_3y = three_year_scenarios(px, g('totalRevenue'),
                                                g('priceToSalesTrailing12Months'),
                                                g('revenueGrowth'), rev_cagr, dilution_yoy)

            # ---- Peter Lynch growth lens -------------------------------------------------
            lynch_cat = lynch_category(rev_yoy, g('revenueGrowth'), mcap, profitable,
                                       g('sector'), g('dividendYield'), losses_narrowing)
            peg_fwd, lynch_ratio = lynch_peg(g('forwardPE'), g('earningsGrowth'),
                                             g('revenueGrowth'), rev_cagr, g('dividendYield'))
            inst_pct = g('heldPercentInstitutions')
            # Lynch loved small + fast + reasonably priced + under-owned (room for a tenbagger)
            is_small = (mcap is not None and mcap < 15e9)
            is_fast = (lynch_cat.startswith('Fast Grower'))
            peg_ok = (peg_fwd is not None and peg_fwd < 1.5)
            under_owned = (inst_pct is not None and inst_pct < 0.60)
            tenbagger_flags = sum([is_small, is_fast, peg_ok, under_owned, bool(profitable)])

            theme_label, theme_strength = THEMES.get(ticker, ('—', 5))

            return {
                'ticker': ticker,
                'name': g('longName') or g('shortName') or ticker,
                'business_summary': (g('longBusinessSummary') or '')[:900],
                'sector': g('sector'), 'industry': g('industry'),
                'theme': theme_label, 'theme_strength': theme_strength,
                'price': px,
                'market_cap': g('marketCap'),
                'enterprise_value': g('enterpriseValue'),
                'revenue_ttm': g('totalRevenue'),
                'revenue_latest_fy': rev_latest,
                'revenue_series_fy': rev,
                'rev_yoy': rev_yoy, 'rev_yoy_prior': rev_yoy_prior,
                'rev_cagr_multiyr': rev_cagr, 'rev_accelerating': rev_accel,
                'fwd_rev_growth_est': g('revenueGrowth'),
                'gross_margin': gm, 'gross_margin_improving': gm_trend,
                'operating_margin': opm, 'net_margin': nim,
                'net_income_latest': ni_latest, 'profitable': profitable,
                'losses_narrowing': losses_narrowing,
                'fcf_latest': fcf_latest, 'fcf_margin': fcf_margin,
                'total_cash': cash, 'total_debt': g('totalDebt'),
                'cash_runway_years': runway_years,
                'shares_outstanding': g('sharesOutstanding'),
                'dilution_yoy': dilution_yoy,
                'rd_intensity': rd_intensity,
                'rule_of_40': r40,
                'ps_ttm': g('priceToSalesTrailing12Months'),
                'forward_pe': g('forwardPE'), 'trailing_pe': g('trailingPE'),
                'peg': g('pegRatio'),
                'tgt_mean': tgt_mean, 'tgt_high': tgt_high,
                'tgt_low': g('targetLowPrice'), 'tgt_median': g('targetMedianPrice'),
                'analyst_upside': (tgt_mean / px - 1) if (tgt_mean and px) else None,
                'analyst_upside_high': (tgt_high / px - 1) if (tgt_high and px) else None,
                'num_analysts': g('numberOfAnalystOpinions'),
                'recommendation': g('recommendationKey'),

                # ---- Buffett / quality scorecard ----
                'roe': roe, 'roa': roa, 'roic': roic,
                'ebitda': ebitda0, 'ebitda_margin': ebitda_margin,
                'debt_to_equity': g('debtToEquity'),        # yfinance reports as % (e.g. 50 = 0.5x)
                'net_debt': net_debt, 'net_debt_to_ebitda': net_debt_to_ebitda,
                'current_ratio': g('currentRatio'), 'quick_ratio': g('quickRatio'),
                'interest_coverage': interest_coverage,
                'price_to_book': g('priceToBook'), 'book_value_ps': g('bookValue'),
                'fcf_yield': fcf_yield, 'operating_cashflow': (ocf[0] if ocf else g('operatingCashflow')),
                'buyback_yield': buyback_yield,
                'insider_pct': g('heldPercentInsiders'), 'institution_pct': g('heldPercentInstitutions'),
                'earnings_growth': g('earningsGrowth'),
                'dividend_yield': g('dividendYield'), 'payout_ratio': g('payoutRatio'),
                'net_income_series_fy': ni,
                'earnings_stability': earnings_stability, 'revenue_stability': revenue_stability,
                'effective_tax_rate': tax_rate,
                'scenarios_3y': scenarios_3y,

                # ---- Peter Lynch growth lens ----
                'lynch_category': lynch_cat,
                'peg_forward': peg_fwd,           # P/E ÷ growth% : <1 good, ~0.5 great, >2 dear
                'lynch_ratio': lynch_ratio,       # (growth%+yield%)/PE : >2 great, <1 poor
                'has_earnings': bool(profitable), # Lynch: no earnings = a story, not a buy (yet)
                'tenbagger_flags': tenbagger_flags,  # 0-5: small·fast·PEG<1.5·under-owned·profitable
            }
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(0.6 * (attempt + 1))
    return None


def pct(v, d=0):
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return "—"
    return f"{v*100:+.{d}f}%"

def cap(v):
    if not v: return "—"
    if v >= 1e12: return f"${v/1e12:.2f}T"
    if v >= 1e9:  return f"${v/1e9:.1f}B"
    if v >= 1e6:  return f"${v/1e6:.0f}M"
    return f"${v:.0f}"

def num(v, d=0, suf=""):
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return "—"
    return f"{v:.{d}f}{suf}"


def main(tickers):
    now = datetime.now()
    date_str = now.strftime('%Y-%m-%d')
    print(f"\n{'='*72}\n  BIG WINNER — business fundamentals layer")
    print(f"  {now.strftime('%Y-%m-%d %H:%M')} · {len(tickers)} names\n{'='*72}\n")

    data = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(fetch_one, t): t for t in tickers}
        done = 0
        for fut in as_completed(futs):
            t = futs[fut]
            try: r = fut.result()
            except Exception: r = None
            if r: data[t] = r
            done += 1
            print(f"  [{done:>2}/{len(tickers)}] {t:<6} {'ok' if r else 'FAILED'}")

    rows = [data[t] for t in tickers if t in data]
    failed = [t for t in tickers if t not in data]

    # JSON (full detail — the routine reads this)
    out_json = HERE / f'big_winner_fundamentals_{date_str}.json'
    out_json.write_text(json.dumps({'generated': now.isoformat(), 'date': date_str,
                                    'stocks': {r['ticker']: r for r in rows}}, indent=2,
                                   default=str), encoding='utf-8')

    # Compact markdown table
    L = [f"# Big Winner — business fundamentals ({date_str})",
         f"*generated {now.strftime('%Y-%m-%d %H:%M')} · data: Yahoo Finance · scaffolding for the Big Winner routine*", "",
         "| Ticker | Mkt Cap | Rev(FY) | Rev YoY | Rev CAGR | GM | OpM | NetM | FCF mgn | Rule40 | Runway | Dilut | Fwd P/E | P/S | Analyst↑ | Theme |",
         "|--------|---------|---------|---------|----------|-----|-----|------|---------|--------|--------|-------|---------|-----|----------|-------|"]
    for r in rows:
        runway = (f"{r['cash_runway_years']:.1f}y" if r['cash_runway_years'] else ("FCF+" if (r['fcf_margin'] or 0) > 0 else "—"))
        L.append(
            f"| **{r['ticker']}** | {cap(r['market_cap'])} | {cap(r['revenue_latest_fy'])} | "
            f"{pct(r['rev_yoy'])} | {pct(r['rev_cagr_multiyr'])} | {pct(r['gross_margin'])} | "
            f"{pct(r['operating_margin'])} | {pct(r['net_margin'])} | {pct(r['fcf_margin'])} | "
            f"{num(r['rule_of_40'])} | {runway} | {pct(r['dilution_yoy'],1)} | {num(r['forward_pe'],1)} | "
            f"{num(r['ps_ttm'],1)} | {pct(r['analyst_upside']) if r['analyst_upside'] is not None else '—'} | {r['theme']} |")
    if failed:
        L += ["", f"> ⚠️ No data: {', '.join(failed)}"]

    # ---- Buffett / quality + 3yr-scenario table -------------------------------------
    def x_mult(v, d=1):  # debt/equity arrives as a percent in yfinance
        if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
            return "—"
        return f"{v/100:.{d}f}x"
    def ratio(v, d=1, suf="x"):
        if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
            return "—"
        return f"{v:.{d}f}{suf}"
    def money(v):
        return cap(v) if (v and v > 0) else (f"-{cap(abs(v))}" if v else "—")

    L += ["", "## Buffett / quality scorecard + 3-year price scaffold",
          "*ROIC/ROE = return on capital · D/E from yfinance (÷100 → ×) · IntCov = EBIT/interest · "
          "FCF yld = FCF/mktcap · Insider = % held by insiders · 3yr base = mechanical revenue×exit-P/S "
          "scaffold (NOT a forecast — Claude overrides with judgment).*", "",
          "| Ticker | ROE | ROIC | ROA | D/E | Cur | IntCov | EBITDA mgn | FCF yld | P/B | Insider | EarnStab | 3yr Bear | 3yr Base | 3yr Bull | Base CAGR |",
          "|--------|-----|------|-----|-----|-----|--------|-----------|---------|-----|---------|----------|----------|----------|----------|-----------|"]
    for r in rows:
        s = r.get('scenarios_3y') or {}
        L.append(
            f"| **{r['ticker']}** | {pct(r.get('roe'))} | {pct(r.get('roic'))} | {pct(r.get('roa'))} | "
            f"{x_mult(r.get('debt_to_equity'))} | {ratio(r.get('current_ratio'))} | {ratio(r.get('interest_coverage'),1,'x')} | "
            f"{pct(r.get('ebitda_margin'))} | {pct(r.get('fcf_yield'),1)} | {ratio(r.get('price_to_book'),1,'')} | "
            f"{pct(r.get('insider_pct'),1)} | {ratio(r.get('earnings_stability'),2,'')} | "
            f"{('$'+format(s['price_bear_3y'],',.0f')) if s.get('price_bear_3y') is not None else '—'} | "
            f"{('$'+format(s['price_base_3y'],',.0f')) if s.get('price_base_3y') is not None else '—'} | "
            f"{('$'+format(s['price_bull_3y'],',.0f')) if s.get('price_bull_3y') is not None else '—'} | "
            f"{pct(s.get('implied_cagr_base')) if s.get('implied_cagr_base') is not None else '—'} |")

    # ---- Peter Lynch growth-lens table ----------------------------------------------
    L += ["", "## Peter Lynch growth lens (PEG · category · tenbagger flags)",
          "*Lynch's tools for finding tenbaggers: classify the company, then buy growth at a "
          "reasonable price. PEG = fwd P/E ÷ growth% (<1 good, ~0.5 great, >2 dear). Lynch ratio = "
          "(growth%+yield%)÷P/E (>2 great, <1 poor). Inst% = institutional ownership (Lynch liked "
          "LOW = undiscovered). Earn? = has earnings (no = a story, not a Lynch buy yet). "
          "Flags 0-5 = small·fast·PEG<1.5·under-owned·profitable.*", "",
          "| Ticker | Mkt Cap | Lynch category | Rev YoY | PEG (fwd) | Lynch ratio | Inst % | Earnings? | Tenbagger flags |",
          "|--------|---------|----------------|---------|-----------|-------------|--------|-----------|-----------------|"]
    for r in rows:
        L.append(
            f"| **{r['ticker']}** | {cap(r['market_cap'])} | {r.get('lynch_category','—')} | "
            f"{pct(r['rev_yoy'])} | {num(r.get('peg_forward'),2) if r.get('peg_forward') is not None else '—'} | "
            f"{num(r.get('lynch_ratio'),2) if r.get('lynch_ratio') is not None else '—'} | "
            f"{pct(r.get('institution_pct'),0) if r.get('institution_pct') is not None else '—'} | "
            f"{'yes' if r.get('has_earnings') else 'NO'} | {r.get('tenbagger_flags','—')}/5 |")

    out_md = HERE / f'big_winner_fundamentals_{date_str}.md'
    out_md.write_text("\n".join(L), encoding='utf-8')

    # console
    print(f"\n  {'TICK':<6} {'MCAP':>8} {'RevYoY':>8} {'CAGR':>7} {'GM':>6} {'NetM':>7} {'Rule40':>7} {'Runway':>7}  THEME")
    for r in sorted(rows, key=lambda x: -(x['rev_yoy'] or -9)):
        runway = (f"{r['cash_runway_years']:.1f}y" if r['cash_runway_years'] else ("FCF+" if (r['fcf_margin'] or 0) > 0 else "—"))
        print(f"  {r['ticker']:<6} {cap(r['market_cap']):>8} {pct(r['rev_yoy']):>8} "
              f"{pct(r['rev_cagr_multiyr']):>7} {pct(r['gross_margin']):>6} {pct(r['net_margin']):>7} "
              f"{num(r['rule_of_40']):>7} {runway:>7}  {r['theme']}")
    if failed:
        print(f"\n  ⚠️ No data: {', '.join(failed)}")
    print(f"\n  ✅ JSON: {out_json.name}\n  ✅ Table: {out_md.name}\n")
    return out_json


if __name__ == '__main__':
    args = [a.upper() for a in sys.argv[1:] if not a.startswith('-')]
    main(args or WATCHLIST)
