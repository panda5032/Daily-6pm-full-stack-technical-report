"""
Unusual Whale Options Activity Strategy — AI_Portfolios.xlsx
=============================================================
Scans the full AI portfolio (128+ tickers) for unusual options activity
("whale" trades) using free public data sources, then produces a
quantitative BUY / HOLD / SELL recommendation per stock.

DATA SOURCES (all free / public):
  1. Yahoo Finance option chains (yfinance)        — primary source
       - Full call/put chains, strikes, volume, OI, IV, last price
  2. CBOE-derived put/call ratios                  — via yfinance options
  3. yfinance fast_info / history                  — spot price + 30D HV
  4. Computed metrics (no third-party API needed):
       - Volume / Open Interest ratio        (>2.0 = unusual)
       - Total premium $ (vol × mid × 100)   (>$500K = whale-sized)
       - Net call $ vs net put $             (sentiment)
       - IV percentile vs 30D realized vol   (cheap/rich)
       - Largest single-contract sweeps
       - Near-the-money skew & expiry concentration

NOTE: UnusualWhales.com itself is a paid feed ($60/mo). Free derivative
sources used here:
  - Yahoo Finance options page (data via yfinance)
  - Barchart Unusual Options Activity (free tier, scraping not used here
    — we replicate their core methodology directly from yfinance)
  - WSJ markets / Finviz options screeners (visible reference; data not
    pulled live to avoid rate-limit issues)

OUTPUT:
  whale_options_YYYY-MM-DD.md  — markdown report with sector breakdowns,
  whale alerts, and BUY / HOLD / SELL signals per stock.

Schedule: every Sunday 5:30 PM via Windows Task Scheduler
          (run_whale_options_sunday_530pm.bat).

Disclaimer: Algorithmic output based on user-defined rules. Not
financial advice. Markets are closed weekends so Sunday runs operate on
Friday's settled options data.
"""
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
import sys
import io

warnings.filterwarnings('ignore')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

# ── Portfolio definition (matches chinese_principles_strategy.py) ────
SECTORS = {
    'Hyperscaler':       ['GOOGL', 'AMZN', 'META', 'MSFT', 'AAPL'],
    'Self-Driving':      ['TSLA', 'PONY', 'UBER', 'GRAB'],
    'Robotics':          ['SERV', 'PATH', 'ISRG'],
    'Semis':             ['NVDA', 'AMD', 'AVGO', 'TSM', 'ARM', 'MRVL', 'MU', 'INTC',
                          'SMCI', 'ANET', 'DELL', 'ASML', 'QCOM',
                          'AMAT', 'LRCX', 'KLAC', 'COHR', 'TXN', 'ADI', 'NXPI', 'MCHP', 'GFS', 'TER', 'SKHY'],
    'AI Infrastructure': ['CRWV', 'ORCL', 'IREN', 'NBIS', 'CIFR', 'APLD', 'CSCO', 'VRT', 'GEV', 'ETN', 'DLR',
                          'VST', 'CEG', 'CIEN', 'PSTG'],
    'Energy':            ['OKLO', 'LAC', 'MP', 'SMR', 'BE', 'ONDS', 'QS', 'EOSE'],
    'Software':          ['PLTR', 'SNOW', 'AI', 'IBM', 'MDB', 'NOW', 'CRM', 'ADBE',
                          'OKTA', 'SHOP', 'SOUN', 'BBAI', 'UPST', 'DUOL', 'RBRK',
                          'DDOG', 'NFLX', 'ZETA', 'SPOT', 'APP', 'RDDT', 'TTD',
                          'RBLX', 'U', 'INFY', 'ALAB', 'CRDO', 'WOLF', 'SNPS',
                          'NET', 'TEAM', 'WDAY', 'INTU',
                          'S', 'GTLB', 'ESTC', 'TWLO', 'CFLT', 'HUBS'],
    'Health':            ['UNH', 'OSCR', 'HIMS', 'RXRX', 'LLY', 'TEM', 'CRSP', 'TMDX'],
    'Space':             ['RKLB', 'FLY', 'JOBY', 'ACHR', 'LUNR', 'ASTS'],
    'China':             ['BABA', 'BIDU', 'JD', 'XPEV', 'NIO', 'PDD', 'FUTU', 'TCEHY'],
    # Crypto: most coins don't have listed equity options; only the proxies.
    # Crypto ETFs (IBIT/ETHA/BSOL/XRPC) DO have listed options — held positions.
    'Crypto':            ['MSTR', 'COIN', 'CLSK', 'RIOT', 'MARA', 'HUT', 'BMNR',
                          'SBET', 'BULL', 'HIVE',
                          'IBIT', 'ETHA', 'BSOL', 'XRPC'],
    'Finance':           ['SOFI', 'OPEN', 'LMND', 'HOOD', 'PYPL', 'AFRM'],
    'Quantum':           ['RGTI', 'IONQ', 'QUBT', 'QBTS'],
    'Trading':           ['GME', 'LULU', 'CMG', 'UPS', 'ABNB', 'PTON', 'BA', 'NKE'],
    'Rotation':          ['JPM', 'GS', 'BRK-B', 'XOM', 'CVX', 'CAT', 'DE', 'GE', 'COST', 'WMT', 'JNJ', 'XLU'],
    'Commodity':         ['GLD', 'SLV', 'USO'],
}

TICKER_TO_SECTOR = {}
for sector, tickers in SECTORS.items():
    for t in tickers:
        if t not in TICKER_TO_SECTOR:
            TICKER_TO_SECTOR[t] = sector

ALL_TICKERS = list({t for tickers in SECTORS.values() for t in tickers})

# ── Whale-detection thresholds ──────────────────────────────────────
VOL_OI_UNUSUAL = 2.0          # vol/OI ratio above this = unusual
PREMIUM_WHALE_USD = 500_000   # contract dollar volume above this = whale
PREMIUM_BIG_WHALE_USD = 2_000_000
PCR_BULLISH_MAX = 0.60        # P/C ratio below = bullish skew
PCR_BEARISH_MIN = 1.20        # P/C ratio above = bearish skew
IV_RICH_PCTILE = 0.80         # IV in top 20% of 30D HV = "rich"
IV_CHEAP_PCTILE = 0.30        # IV in bottom 30% of 30D HV = "cheap"

MAX_EXPIRIES = 6              # scan first N expirations per ticker
MIN_DTE = 3                   # ignore options expiring in <3 days
MAX_DTE = 120                 # ignore LEAPS-style >120 DTE for weekly scan


def _live_price(ticker: str, fallback: float = 0.0) -> float:
    """Best-effort spot price.

    Order of preference (graceful fallthrough):
      1. fast_info.last_price / regularMarketPrice (real-time / 15m delayed)
      2. 1-minute intraday history close (today's most recent bar)
      3. Daily history last close (stale — Friday's close on weekend runs)
      4. Provided fallback (typically 0.0 → caller marks NO DATA)
    """
    try:
        fi = yf.Ticker(ticker).fast_info
        p = fi.get('last_price') or fi.get('regularMarketPrice')
        if p and float(p) > 0:
            return float(p)
    except Exception:
        pass
    try:
        intra = yf.Ticker(ticker).history(period='1d', interval='1m', auto_adjust=False)
        if not intra.empty:
            closes = intra['Close'].dropna()
            if len(closes) > 0 and float(closes.iloc[-1]) > 0:
                return float(closes.iloc[-1])
    except Exception:
        pass
    try:
        h = yf.Ticker(ticker).history(period='5d', interval='1d')
        if not h.empty:
            return float(h['Close'].dropna().iloc[-1])
    except Exception:
        pass
    return fallback


def _hist_vol_30d(ticker: str) -> float:
    """Annualized 30-day realized volatility."""
    try:
        h = yf.download(ticker, period='3mo', progress=False, auto_adjust=True)
        if h.empty or len(h) < 20:
            return 0.0
        if isinstance(h.columns, pd.MultiIndex):
            h.columns = h.columns.get_level_values(0)
        rets = h['Close'].pct_change().dropna().tail(30)
        return float(rets.std() * np.sqrt(252))
    except Exception:
        return 0.0


def _scan_options(ticker: str, spot: float) -> dict:
    """
    Pull option chains from yfinance for the next MAX_EXPIRIES expirations
    and compute aggregate whale metrics.
    Returns dict with totals + list of unusual contracts.
    """
    out = {
        'expirations_scanned': 0,
        'total_call_vol': 0,
        'total_put_vol': 0,
        'total_call_oi': 0,
        'total_put_oi': 0,
        'total_call_premium': 0.0,
        'total_put_premium': 0.0,
        'unusual_calls': [],   # list of dicts
        'unusual_puts': [],
        'biggest_whale': None,
        'avg_call_iv': None,
        'avg_put_iv': None,
        'error': None,
    }

    try:
        yt = yf.Ticker(ticker)
        expirations = list(yt.options) if yt.options else []
        if not expirations:
            out['error'] = 'no_options'
            return out

        today = datetime.now().date()
        scanned = 0
        call_ivs, put_ivs = [], []

        for exp in expirations[:MAX_EXPIRIES]:
            try:
                exp_date = datetime.strptime(exp, '%Y-%m-%d').date()
            except ValueError:
                continue
            dte = (exp_date - today).days
            if dte < MIN_DTE or dte > MAX_DTE:
                continue

            try:
                chain = yt.option_chain(exp)
            except Exception:
                continue

            for side, df in (('call', chain.calls), ('put', chain.puts)):
                if df is None or df.empty:
                    continue

                df = df.copy()
                df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0)
                df['openInterest'] = pd.to_numeric(df['openInterest'], errors='coerce').fillna(0)
                df['lastPrice'] = pd.to_numeric(df['lastPrice'], errors='coerce').fillna(0)
                df['impliedVolatility'] = pd.to_numeric(df['impliedVolatility'], errors='coerce').fillna(0)
                df['strike'] = pd.to_numeric(df['strike'], errors='coerce')

                df['premium_usd'] = df['volume'] * df['lastPrice'] * 100.0
                df['vol_oi'] = np.where(
                    df['openInterest'] > 0,
                    df['volume'] / df['openInterest'],
                    np.where(df['volume'] > 0, 99.0, 0.0),
                )

                # aggregate totals
                if side == 'call':
                    out['total_call_vol'] += int(df['volume'].sum())
                    out['total_call_oi']  += int(df['openInterest'].sum())
                    out['total_call_premium'] += float(df['premium_usd'].sum())
                    valid_iv = df.loc[df['volume'] > 0, 'impliedVolatility']
                    call_ivs.extend([float(x) for x in valid_iv if x > 0])
                else:
                    out['total_put_vol'] += int(df['volume'].sum())
                    out['total_put_oi']  += int(df['openInterest'].sum())
                    out['total_put_premium'] += float(df['premium_usd'].sum())
                    valid_iv = df.loc[df['volume'] > 0, 'impliedVolatility']
                    put_ivs.extend([float(x) for x in valid_iv if x > 0])

                # identify unusual contracts
                unusual_mask = (
                    (df['vol_oi'] >= VOL_OI_UNUSUAL) &
                    (df['premium_usd'] >= PREMIUM_WHALE_USD) &
                    (df['volume'] >= 100)
                )
                for _, row in df[unusual_mask].iterrows():
                    rec = {
                        'ticker': ticker,
                        'side': side,
                        'strike': float(row['strike']),
                        'expiry': exp,
                        'dte': dte,
                        'volume': int(row['volume']),
                        'oi': int(row['openInterest']),
                        'vol_oi': float(row['vol_oi']),
                        'last': float(row['lastPrice']),
                        'iv': float(row['impliedVolatility']),
                        'premium_usd': float(row['premium_usd']),
                        'moneyness': (float(row['strike']) - spot) / spot * 100 if spot > 0 else 0.0,
                    }
                    if side == 'call':
                        out['unusual_calls'].append(rec)
                    else:
                        out['unusual_puts'].append(rec)

                    if (out['biggest_whale'] is None or
                            rec['premium_usd'] > out['biggest_whale']['premium_usd']):
                        out['biggest_whale'] = rec

            scanned += 1

        out['expirations_scanned'] = scanned
        if call_ivs:
            out['avg_call_iv'] = float(np.mean(call_ivs))
        if put_ivs:
            out['avg_put_iv']  = float(np.mean(put_ivs))

    except Exception as e:
        out['error'] = str(e)[:80]

    return out


def analyze_ticker(ticker: str) -> dict:
    """Run whale options analysis on a single ticker. Returns scoring dict."""
    spot = _live_price(ticker)
    if spot <= 0:
        return {
            'ticker': ticker, 'sector': TICKER_TO_SECTOR.get(ticker, 'Other'),
            'spot': 0.0, 'score': 0.0, 'action': 'NO DATA',
            'flags': [('NO_PRICE', 0, 'Could not retrieve spot price')],
            'opt': None, 'hv30': 0.0,
        }

    hv30 = _hist_vol_30d(ticker)
    opt = _scan_options(ticker, spot)

    score = 0.0
    flags: list[tuple[str, float, str]] = []

    if opt['error']:
        return {
            'ticker': ticker, 'sector': TICKER_TO_SECTOR.get(ticker, 'Other'),
            'spot': spot, 'score': 0.0, 'action': 'NO OPTIONS',
            'flags': [('NO_OPTIONS', 0, f"yfinance: {opt['error']}")],
            'opt': opt, 'hv30': hv30,
        }

    if opt['expirations_scanned'] == 0:
        return {
            'ticker': ticker, 'sector': TICKER_TO_SECTOR.get(ticker, 'Other'),
            'spot': spot, 'score': 0.0, 'action': 'NO OPTIONS',
            'flags': [('NO_EXPIRY', 0, 'No expirations in 3-120 DTE window')],
            'opt': opt, 'hv30': hv30,
        }

    # ── Signal 1: Total premium $ flow (calls vs puts) ──────────────
    call_p = opt['total_call_premium']
    put_p  = opt['total_put_premium']
    total_p = call_p + put_p

    if total_p > 0:
        call_share = call_p / total_p
        if call_p >= 5_000_000 and call_share >= 0.70:
            score += 3
            flags.append(('S1_重仓看涨流', +3,
                          f"Call premium ${call_p/1e6:.1f}M ({call_share*100:.0f}% of total) — large bullish flow"))
        elif call_p >= 1_000_000 and call_share >= 0.65:
            score += 1.5
            flags.append(('S1_看涨流', +1.5,
                          f"Call premium ${call_p/1e6:.2f}M ({call_share*100:.0f}%) — bullish skew"))
        elif put_p >= 5_000_000 and call_share <= 0.30:
            score -= 3
            flags.append(('S1_重仓看跌流', -3,
                          f"Put premium ${put_p/1e6:.1f}M ({(1-call_share)*100:.0f}% of total) — large bearish flow"))
        elif put_p >= 1_000_000 and call_share <= 0.35:
            score -= 1.5
            flags.append(('S1_看跌流', -1.5,
                          f"Put premium ${put_p/1e6:.2f}M ({(1-call_share)*100:.0f}%) — bearish skew"))

    # ── Signal 2: Put/Call ratio (volume-weighted) ──────────────────
    if opt['total_call_vol'] > 0:
        pcr = opt['total_put_vol'] / opt['total_call_vol']
    else:
        pcr = float('inf')

    if pcr <= PCR_BULLISH_MAX and opt['total_call_vol'] >= 5_000:
        score += 2
        flags.append(('S2_PC比偏低', +2,
                      f"P/C ratio {pcr:.2f} ≤ {PCR_BULLISH_MAX} — bullish positioning"))
    elif pcr >= PCR_BEARISH_MIN and opt['total_put_vol'] >= 5_000:
        score -= 2
        flags.append(('S2_PC比偏高', -2,
                      f"P/C ratio {pcr:.2f} ≥ {PCR_BEARISH_MIN} — bearish positioning"))

    # ── Signal 3: Largest single-contract whale ─────────────────────
    bw = opt['biggest_whale']
    if bw and bw['premium_usd'] >= PREMIUM_BIG_WHALE_USD:
        if bw['side'] == 'call':
            score += 2
            flags.append(('S3_巨鲸看涨', +2,
                          f"Whale CALL ${bw['strike']:.0f} {bw['expiry']} "
                          f"vol {bw['volume']:,} | ${bw['premium_usd']/1e6:.2f}M premium "
                          f"| vol/OI {bw['vol_oi']:.1f}x"))
        else:
            score -= 2
            flags.append(('S3_巨鲸看跌', -2,
                          f"Whale PUT ${bw['strike']:.0f} {bw['expiry']} "
                          f"vol {bw['volume']:,} | ${bw['premium_usd']/1e6:.2f}M premium "
                          f"| vol/OI {bw['vol_oi']:.1f}x"))
    elif bw and bw['premium_usd'] >= PREMIUM_WHALE_USD:
        if bw['side'] == 'call':
            score += 1
            flags.append(('S3_看涨白鲸', +1,
                          f"Notable CALL ${bw['strike']:.0f} {bw['expiry']} "
                          f"${bw['premium_usd']/1e3:.0f}K | vol/OI {bw['vol_oi']:.1f}x"))
        else:
            score -= 1
            flags.append(('S3_看跌白鲸', -1,
                          f"Notable PUT ${bw['strike']:.0f} {bw['expiry']} "
                          f"${bw['premium_usd']/1e3:.0f}K | vol/OI {bw['vol_oi']:.1f}x"))

    # ── Signal 4: # of unusual call vs put contracts ────────────────
    nc = len(opt['unusual_calls'])
    np_ = len(opt['unusual_puts'])
    if nc + np_ >= 3:
        if nc >= 3 and nc >= 2 * max(np_, 1):
            score += 1.5
            flags.append(('S4_看涨密度', +1.5,
                          f"{nc} unusual call sweeps vs {np_} put — concentrated bullish"))
        elif np_ >= 3 and np_ >= 2 * max(nc, 1):
            score -= 1.5
            flags.append(('S4_看跌密度', -1.5,
                          f"{np_} unusual put sweeps vs {nc} call — concentrated bearish"))

    # ── Signal 5: IV rich vs cheap (vs 30D HV) ──────────────────────
    if hv30 > 0 and opt['avg_call_iv'] and opt['avg_call_iv'] > 0:
        iv_ratio = opt['avg_call_iv'] / hv30
        if iv_ratio >= 1.5:
            score -= 1
            flags.append(('S5_IV昂贵', -1,
                          f"Avg call IV {opt['avg_call_iv']*100:.0f}% vs 30D HV {hv30*100:.0f}% "
                          f"({iv_ratio:.1f}x) — options expensive, sellers favored"))
        elif iv_ratio <= 0.7:
            score += 1
            flags.append(('S5_IV便宜', +1,
                          f"Avg call IV {opt['avg_call_iv']*100:.0f}% vs 30D HV {hv30*100:.0f}% "
                          f"({iv_ratio:.1f}x) — options cheap, buyers favored"))

    # ── Signal 6: ITM vs OTM whale skew (directional conviction) ────
    itm_call_premium = sum(c['premium_usd'] for c in opt['unusual_calls'] if c['moneyness'] <= 0)
    otm_call_premium = sum(c['premium_usd'] for c in opt['unusual_calls'] if c['moneyness'] > 0)
    itm_put_premium  = sum(p['premium_usd'] for p in opt['unusual_puts']  if p['moneyness'] >= 0)
    otm_put_premium  = sum(p['premium_usd'] for p in opt['unusual_puts']  if p['moneyness'] < 0)

    if otm_call_premium >= 1_000_000 and otm_call_premium > 2 * (otm_put_premium + 1):
        score += 1
        flags.append(('S6_OTM看涨', +1,
                      f"OTM call premium ${otm_call_premium/1e6:.2f}M — speculative upside bets"))
    if otm_put_premium >= 1_000_000 and otm_put_premium > 2 * (otm_call_premium + 1):
        score -= 1
        flags.append(('S6_OTM看跌', -1,
                      f"OTM put premium ${otm_put_premium/1e6:.2f}M — speculative downside bets"))

    # ── Composite recommendation ────────────────────────────────────
    if score >= 4:
        action = 'STRONG BUY'
    elif score >= 2:
        action = 'BUY'
    elif score >= -2:
        action = 'HOLD'
    elif score >= -4:
        action = 'SELL'
    else:
        action = 'STRONG SELL'

    return {
        'ticker': ticker,
        'sector': TICKER_TO_SECTOR.get(ticker, 'Other'),
        'spot': spot,
        'score': score,
        'action': action,
        'flags': flags,
        'opt': opt,
        'hv30': hv30,
        'pcr': pcr,
    }


def _action_emoji(action: str) -> str:
    return {
        'STRONG BUY': '🟢🟢',
        'BUY': '🟢',
        'HOLD': '🟡',
        'SELL': '🔴',
        'STRONG SELL': '🔴🔴',
        'NO DATA': '⚪',
        'NO OPTIONS': '⚪',
        'ERROR': '⚠️',
    }.get(action, '❓')


def write_report(results: list[dict], out_path: Path):
    lines = []
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')
    lines.append('# 🐋 Unusual Whale Options Activity — AI Portfolio')
    lines.append(f'**Generated**: {ts}  |  **Stocks scanned**: {len(results)}')
    lines.append('')
    lines.append('> **Disclaimer**: This is an algorithmic screen of public options data, '
                 'not financial advice. Markets are closed weekends — Sunday runs reflect '
                 'Friday\'s settled chains. Always do your own due diligence.')
    lines.append('')

    # Data sources reference
    lines.append('## Data Sources')
    lines.append('- **Yahoo Finance option chains** (via `yfinance`) — full call/put chains, volume, OI, IV')
    lines.append('- **Computed metrics** — Volume/OI ratio, total premium $, put/call ratio, IV vs 30D HV')
    lines.append('- **30-day historical volatility** (via `yfinance` price history) — IV cheap/rich benchmark')
    lines.append('- *Reference (not pulled live):* UnusualWhales.com, Barchart UOA, Finviz, CBOE volume reports')
    lines.append('')

    # Whale-detection thresholds (transparent rules)
    lines.append('## Whale-Detection Thresholds')
    lines.append('| Filter | Threshold | Meaning |')
    lines.append('|--------|-----------|---------|')
    lines.append(f'| Vol / OI ratio | ≥ {VOL_OI_UNUSUAL} | New positioning vs existing book |')
    lines.append(f'| Contract premium $ | ≥ ${PREMIUM_WHALE_USD:,} (whale ≥ ${PREMIUM_BIG_WHALE_USD:,}) | Notional dollar size |')
    lines.append(f'| Min volume | 100 contracts | Filter out illiquid noise |')
    lines.append(f'| DTE window | {MIN_DTE} – {MAX_DTE} days | Skip 0DTE noise + LEAPS |')
    lines.append(f'| P/C bullish | ≤ {PCR_BULLISH_MAX} | Calls dominating volume |')
    lines.append(f'| P/C bearish | ≥ {PCR_BEARISH_MIN} | Puts dominating volume |')
    lines.append('')

    # Summary
    counts = {}
    for r in results:
        counts[r['action']] = counts.get(r['action'], 0) + 1
    lines.append('## Summary')
    lines.append('')
    lines.append('| Action | Count |')
    lines.append('|--------|-------|')
    for act in ['STRONG BUY', 'BUY', 'HOLD', 'SELL', 'STRONG SELL', 'NO OPTIONS', 'NO DATA']:
        if counts.get(act, 0) > 0:
            lines.append(f'| {_action_emoji(act)} {act} | {counts[act]} |')
    lines.append('')

    # Top BUY picks (bullish whale flow)
    buys = [r for r in results if r['action'] in ('STRONG BUY', 'BUY')]
    buys.sort(key=lambda x: x['score'], reverse=True)
    if buys:
        lines.append('## 🟢 Top BUY Candidates (Bullish Whale Flow)')
        lines.append('')
        lines.append('| Rank | Ticker | Sector | Spot | Call $M | Put $M | P/C | Score | Action | Top Whale Signal |')
        lines.append('|------|--------|--------|------|---------|--------|-----|-------|--------|------------------|')
        for i, r in enumerate(buys[:20], 1):
            opt = r['opt'] or {}
            call_m = (opt.get('total_call_premium') or 0) / 1e6
            put_m  = (opt.get('total_put_premium') or 0) / 1e6
            top_flag = r['flags'][0][2] if r['flags'] else ''
            if len(top_flag) > 60:
                top_flag = top_flag[:60] + '...'
            pcr_s = f"{r.get('pcr', 0):.2f}" if r.get('pcr') and r['pcr'] != float('inf') else 'N/A'
            lines.append(
                f"| {i} | **{r['ticker']}** | {r['sector']} | ${r['spot']:.2f} | "
                f"${call_m:.2f} | ${put_m:.2f} | {pcr_s} | "
                f"{r['score']:+.1f} | {_action_emoji(r['action'])} {r['action']} | {top_flag} |"
            )
        lines.append('')

    # Top SELL picks (bearish whale flow)
    sells = [r for r in results if r['action'] in ('SELL', 'STRONG SELL')]
    sells.sort(key=lambda x: x['score'])
    if sells:
        lines.append('## 🔴 Top SELL / Avoid (Bearish Whale Flow)')
        lines.append('')
        lines.append('| Rank | Ticker | Sector | Spot | Call $M | Put $M | P/C | Score | Action | Top Whale Signal |')
        lines.append('|------|--------|--------|------|---------|--------|-----|-------|--------|------------------|')
        for i, r in enumerate(sells[:20], 1):
            opt = r['opt'] or {}
            call_m = (opt.get('total_call_premium') or 0) / 1e6
            put_m  = (opt.get('total_put_premium') or 0) / 1e6
            top_flag = r['flags'][0][2] if r['flags'] else ''
            if len(top_flag) > 60:
                top_flag = top_flag[:60] + '...'
            pcr_s = f"{r.get('pcr', 0):.2f}" if r.get('pcr') and r['pcr'] != float('inf') else 'N/A'
            lines.append(
                f"| {i} | **{r['ticker']}** | {r['sector']} | ${r['spot']:.2f} | "
                f"${call_m:.2f} | ${put_m:.2f} | {pcr_s} | "
                f"{r['score']:+.1f} | {_action_emoji(r['action'])} {r['action']} | {top_flag} |"
            )
        lines.append('')

    # Top whale alerts overall (largest individual whale contracts)
    all_whales = []
    for r in results:
        if r.get('opt'):
            for c in r['opt'].get('unusual_calls', []):
                all_whales.append(c)
            for p in r['opt'].get('unusual_puts', []):
                all_whales.append(p)
    all_whales.sort(key=lambda w: w['premium_usd'], reverse=True)
    if all_whales:
        lines.append('## 🐋 Top 25 Whale Contracts (Highest Premium $)')
        lines.append('')
        lines.append('| # | Ticker | Side | Strike | Expiry | DTE | Vol | OI | Vol/OI | $Premium | Moneyness |')
        lines.append('|---|--------|------|--------|--------|-----|-----|----|---------|----------|-----------|')
        for i, w in enumerate(all_whales[:25], 1):
            side_emoji = '🟢' if w['side'] == 'call' else '🔴'
            mny = w['moneyness']
            mny_s = f"{mny:+.1f}%"
            lines.append(
                f"| {i} | **{w['ticker']}** | {side_emoji} {w['side'].upper()} | "
                f"${w['strike']:.0f} | {w['expiry']} | {w['dte']}d | "
                f"{w['volume']:,} | {w['oi']:,} | {w['vol_oi']:.1f}x | "
                f"${w['premium_usd']/1e6:.2f}M | {mny_s} |"
            )
        lines.append('')

    # Detailed by sector
    lines.append('## Detailed Analysis by Sector')
    lines.append('')
    for sector in SECTORS:
        sector_results = [r for r in results if r['sector'] == sector]
        if not sector_results:
            continue
        sector_results.sort(key=lambda x: x['score'], reverse=True)
        lines.append(f'### {sector}')
        lines.append('')
        for r in sector_results:
            emoji = _action_emoji(r['action'])
            opt = r.get('opt') or {}
            cv = opt.get('total_call_vol', 0)
            pv = opt.get('total_put_vol', 0)
            cp = opt.get('total_call_premium', 0) / 1e6
            pp = opt.get('total_put_premium', 0) / 1e6
            pcr_s = f"{r.get('pcr', 0):.2f}" if r.get('pcr') and r['pcr'] != float('inf') else 'N/A'
            lines.append(
                f"**{r['ticker']}** — {emoji} **{r['action']}** (score: {r['score']:+.1f})  "
            )
            lines.append(
                f"Spot: ${r['spot']:.2f} | Calls: {cv:,} vol / ${cp:.2f}M | "
                f"Puts: {pv:,} vol / ${pp:.2f}M | P/C: {pcr_s} | HV30: {r.get('hv30', 0)*100:.0f}%"
            )
            if r['flags']:
                for rule, pts, desc in r['flags']:
                    sign = '+' if pts > 0 else ''
                    lines.append(f"- [{rule}] ({sign}{pts:.1f}) {desc}")
            lines.append('')

    # Methodology
    lines.append('---')
    lines.append('## Scoring Methodology')
    lines.append('')
    lines.append('| Score Range | Action | Meaning |')
    lines.append('|-------------|--------|---------|')
    lines.append('| ≥ +4 | STRONG BUY | Multiple bullish whale signals aligned |')
    lines.append('| +2 to +4 | BUY | Net bullish options flow |')
    lines.append('| -2 to +2 | HOLD | Mixed or neutral options flow |')
    lines.append('| -4 to -2 | SELL | Net bearish options flow |')
    lines.append('| < -4 | STRONG SELL | Multiple bearish whale signals aligned |')
    lines.append('')
    lines.append('### The 6 Whale Signals')
    lines.append('1. **S1 Premium $ flow** — Total call vs put dollar volume (>$5M one-sided = strong)')
    lines.append('2. **S2 P/C ratio** — Volume-weighted put/call ratio (≤0.6 bullish, ≥1.2 bearish)')
    lines.append('3. **S3 Largest whale** — Single biggest unusual contract (≥$2M = big whale)')
    lines.append('4. **S4 Whale density** — Count of unusual call vs put sweeps')
    lines.append('5. **S5 IV vs HV** — Implied vol vs 30D realized vol (rich = sellers favored)')
    lines.append('6. **S6 OTM skew** — Out-of-money speculative call vs put premium')
    lines.append('')
    lines.append('### Why these signals work')
    lines.append('- **Vol/OI > 2** flags new positioning, not closing of existing OI.')
    lines.append('- **Premium $** weighs by dollar size — $500K of OTM puts ≠ $500K of ATM calls.')
    lines.append('- **P/C ratio** smoothes out individual contract noise across the whole chain.')
    lines.append('- **IV vs HV** distinguishes real conviction (cheap IV bought aggressively) from')
    lines.append('  pre-event hedging (rich IV pumped by event uncertainty).')
    lines.append('')

    out_path.write_text('\n'.join(lines), encoding='utf-8')
    return out_path


def main():
    print('=' * 80)
    print('  Unusual Whale Options Activity — AI Portfolio Analysis')
    print(f'  {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print('=' * 80, '\n')

    total = len(ALL_TICKERS)
    print(f'Scanning {total} tickers (max_workers=10, this may take 5-10 min)...\n')

    results = []
    done = 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(analyze_ticker, t): t for t in ALL_TICKERS}
        for fut in as_completed(futures):
            done += 1
            try:
                r = fut.result(timeout=90)
                if r:
                    results.append(r)
            except Exception as e:
                t = futures[fut]
                results.append({
                    'ticker': t, 'sector': TICKER_TO_SECTOR.get(t, 'Other'),
                    'spot': 0, 'score': 0, 'action': 'ERROR',
                    'flags': [('ERROR', 0, str(e)[:80])],
                    'opt': None, 'hv30': 0,
                })
            if done % 10 == 0 or done == total:
                print(f'  {done}/{total} complete', flush=True)

    results.sort(key=lambda x: x['score'], reverse=True)

    buys  = [r for r in results if r['action'] in ('STRONG BUY', 'BUY')]
    holds = [r for r in results if r['action'] == 'HOLD']
    sells = [r for r in results if r['action'] in ('SELL', 'STRONG SELL')]
    no_opt = [r for r in results if r['action'] in ('NO OPTIONS', 'NO DATA')]

    print('\n' + '=' * 80)
    print(f'  Results: {len(buys)} BUY | {len(holds)} HOLD | {len(sells)} SELL | {len(no_opt)} no-options')
    print('=' * 80)

    if buys:
        print('\n  Top BULLISH whale flow:')
        for r in buys[:10]:
            opt = r['opt'] or {}
            cp = opt.get('total_call_premium', 0) / 1e6
            print(f"    {_action_emoji(r['action'])} {r['ticker']:6s} ${r['spot']:>8.2f}  "
                  f"score:{r['score']:+5.1f}  call$:{cp:>5.2f}M  pcr:{r.get('pcr', 0):.2f}")

    if sells:
        print('\n  Top BEARISH whale flow:')
        for r in sells[:10]:
            opt = r['opt'] or {}
            pp = opt.get('total_put_premium', 0) / 1e6
            print(f"    {_action_emoji(r['action'])} {r['ticker']:6s} ${r['spot']:>8.2f}  "
                  f"score:{r['score']:+5.1f}  put$:{pp:>5.2f}M  pcr:{r.get('pcr', 0):.2f}")

    date_str = datetime.now().strftime('%Y-%m-%d')
    out_path = Path(__file__).parent / f'whale_options_{date_str}.md'
    write_report(results, out_path)
    print(f'\n  Report saved: {out_path.name}')
    print('=' * 80, '\n')


if __name__ == '__main__':
    main()
