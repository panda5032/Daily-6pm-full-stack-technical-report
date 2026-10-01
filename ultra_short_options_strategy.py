"""
Ultra-Short-Term Options Trading Scanner — 1-5 DTE
====================================================
Scans every stock/asset in AI_Portfolios.xlsx (132 tickers, sector-mapped
in whale_options_strategy.py) for the 5 BEST ultra-short-term options
trade opportunities expiring in 1-5 calendar days.

WHO THIS IS FOR
  Intraday options swing trader looking for asymmetric setups with
  defined risk over the next 1-5 trading days. NOT a long-term scanner.

DATA SOURCES (all free)
  1. yfinance option_chain                  full call/put chain per expiry
  2. yfinance history (5m + daily)          spot, intraday momentum, HV30
  3. Black-Scholes greeks (computed local)  delta, gamma, theta, vega
  4. Computed liquidity / flow metrics      vol/OI, premium $, spread %

THE 8 SIGNALS (per contract)
  S1 LIQUIDITY GATE  - vol >= 50, OI >= 100, mid > 0.05, bid-ask <= 30%
                       (HARD GATE — fails => contract dropped)
  S2 WHALE FLOW      - vol/OI ratio (>=1.5 = +1, >=3 = +2, >=5 = +3)
                       and premium $ (>= $250K = +1, >= $1M = +2)
  S3 DIRECTIONAL     - call+uptrend / put+downtrend = +2; mismatch = -2
                       Trend = sign of (1d % chg) AND (5d % chg)
  S4 DELTA SWEET     - |delta| in [0.25, 0.55] = +2 (asymmetric)
                       |delta| > 0.70 = -1 (deep ITM, no leverage)
                       |delta| < 0.15 = -1 (lottery ticket)
  S5 GAMMA / THETA   - gamma/|theta| ratio (per $1 of premium):
                       >= 0.50 = +2 (strong gamma per theta burn)
                       >= 0.25 = +1
  S6 IV vs HV30      - IV/HV ratio:
                       <= 0.85 = +2 (cheap vol)
                       <= 1.10 = +1 (fair)
                       >= 1.60 = -2 (event premium, theta trap)
  S7 TECHNICAL       - RSI14 + dist from 20DMA:
                       call + RSI 40-65 + price <=3% above 20DMA = +1.5
                       put  + RSI 35-60 + price >=3% below 20DMA = +1.5
                       overbought call (RSI>75) / oversold put (RSI<25) = -1
  S8 EXPIRY EDGE     - 2-3 DTE preferred over 1 DTE (enough time to play
                       move, less 0DTE noise): 2-3 DTE = +0.5; 1 DTE = -0.5

FINAL SCORE  = sum of S2..S8 weights (S1 is gate, not weighted)
RECOMMENDATION  = top 5 by score across all tickers, both calls and puts

OUTPUT
  ultra_short_options_YYYY-MM-DD_HHMM.md   raw dated report (data pipeline)
  stdout (chat-ready summary of Top 5)

SCHEDULE
  hourly 8am - 3pm Central Time, Mon - Fri
  via Claude Code scheduled-tasks routine (cron in local time).

DISCLAIMER
  Algorithmic screen of public delayed options data. NOT financial advice.
  Theta burn on 1-5 DTE options is severe. Pre-define stops, size small.
"""
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
import math
import sys
import io

warnings.filterwarnings('ignore')
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
except Exception:
    pass

# ── Reuse the AI_Portfolios.xlsx sector map (132 tickers) ────────────
# This dict is the canonical mapping of company-name -> ticker derived
# from AI_Portfolios.xlsx, identical to whale_options_strategy.py.
SECTORS = {
    'Hyperscaler':       ['GOOGL', 'AMZN', 'META', 'MSFT', 'AAPL'],
    'Self-Driving':      ['TSLA', 'PONY', 'UBER', 'GRAB'],
    'Robotics':          ['SERV', 'PATH', 'ISRG'],
    'Semis':             ['NVDA', 'AMD', 'AVGO', 'TSM', 'ARM', 'MRVL', 'MU', 'INTC',
                          'SMCI', 'ANET', 'DELL', 'ASML', 'QCOM', 'SKHY'],
    'AI Infrastructure': ['CRWV', 'ORCL', 'IREN', 'NBIS', 'CIFR', 'APLD', 'CSCO'],
    'Energy':            ['OKLO', 'LAC', 'MP', 'SMR', 'BE', 'ONDS', 'QS', 'EOSE'],
    'Software':          ['PLTR', 'SNOW', 'AI', 'IBM', 'MDB', 'NOW', 'CRM', 'ADBE',
                          'OKTA', 'SHOP', 'SOUN', 'BBAI', 'UPST', 'DUOL', 'RBRK',
                          'DDOG', 'NFLX', 'ZETA', 'SPOT', 'APP', 'RDDT', 'TTD',
                          'RBLX', 'U', 'INFY', 'ALAB', 'CRDO', 'WOLF', 'SNPS',
                          'CRWD', 'PANW', 'ZS'],
    'Health':            ['UNH', 'OSCR', 'HIMS', 'RXRX', 'LLY', 'TEM', 'CRSP', 'TMDX'],
    'Space':             ['RKLB', 'FLY', 'JOBY', 'ACHR', 'LUNR', 'ASTS'],
    'China':             ['BABA', 'BIDU', 'JD', 'XPEV', 'NIO', 'PDD', 'FUTU', 'TCEHY'],
    # Crypto-equity proxies (coins themselves don't have listed equity options)
    'Crypto':            ['MSTR', 'COIN', 'CLSK', 'RIOT', 'MARA', 'HUT', 'BMNR',
                          'SBET', 'BULL', 'HIVE'],
    'Finance':           ['SOFI', 'OPEN', 'LMND', 'HOOD', 'PYPL', 'AFRM'],
    'Quantum':           ['RGTI', 'IONQ', 'QUBT', 'QBTS'],
    'Trading':           ['GME', 'LULU', 'CMG', 'UPS', 'ABNB', 'PTON', 'BA', 'NKE'],
    'Rotation':          ['JPM', 'GS', 'BRK-B', 'XOM', 'CVX', 'CAT', 'DE', 'GE', 'COST', 'WMT', 'JNJ', 'XLU'],
    'Commodity':         ['GLD', 'SLV', 'USO'],
    # Index ETFs derived from the "Index" column (Nasdaq, S&P500, Dow, HS, China A)
    'Index':             ['QQQ', 'SPY', 'DIA', 'EWH', 'FXI'],
}

TICKER_TO_SECTOR = {}
for _sector, _tickers in SECTORS.items():
    for _t in _tickers:
        TICKER_TO_SECTOR.setdefault(_t, _sector)

ALL_TICKERS = sorted({t for tickers in SECTORS.values() for t in tickers})

# ── Tunable parameters ──────────────────────────────────────────────
MIN_DTE = 1                  # include 1 DTE
MAX_DTE = 5                  # cap at 5 DTE
MIN_VOL = 50                 # contract daily volume
MIN_OI = 100                 # open interest
MAX_SPREAD_PCT = 0.30        # bid-ask spread / mid (live mode only)
MIN_MID = 0.05               # avoid penny options
RISK_FREE_RATE = 0.045       # short-rate proxy for B-S (~T-bill)
MAX_WORKERS = 5              # yfinance throttle (lowered to dodge rate limits)
TOP_N_REPORT = 5             # surface top N trade ideas


# ── Black-Scholes greeks (no scipy: erf-based normal CDF) ──────────
def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _bs_price(S: float, K: float, T_years: float, sigma: float,
              r: float, side: str) -> float:
    """Black-Scholes theoretical price."""
    if T_years <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    sqrt_T = math.sqrt(T_years)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T_years) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    if side == 'call':
        return S * _norm_cdf(d1) - K * math.exp(-r * T_years) * _norm_cdf(d2)
    return K * math.exp(-r * T_years) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def _implied_vol_from_price(S: float, K: float, T_years: float,
                            target: float, side: str,
                            r: float = RISK_FREE_RATE) -> float:
    """Bisection IV solver for settled chains (when chain IV is degenerate)."""
    if target <= 0 or T_years <= 0 or S <= 0 or K <= 0:
        return 0.0
    intrinsic = max(S - K, 0) if side == 'call' else max(K - S, 0)
    if target < intrinsic - 0.01:
        return 0.0
    lo, hi = 0.01, 5.0
    for _ in range(40):
        mid_sigma = (lo + hi) / 2.0
        price = _bs_price(S, K, T_years, mid_sigma, r, side)
        if price < target:
            lo = mid_sigma
        else:
            hi = mid_sigma
        if hi - lo < 1e-4:
            break
    return (lo + hi) / 2.0


def _bs_greeks(S: float, K: float, T_years: float, sigma: float,
               r: float = RISK_FREE_RATE, side: str = 'call') -> dict:
    """
    Black-Scholes greeks. Returns delta, gamma, theta (per day), vega (per 1% IV).
    """
    if T_years <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return {'delta': 0.0, 'gamma': 0.0, 'theta': 0.0, 'vega': 0.0}
    sqrt_T = math.sqrt(T_years)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T_years) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    pdf_d1 = _norm_pdf(d1)
    if side == 'call':
        delta = _norm_cdf(d1)
        theta = (-(S * pdf_d1 * sigma) / (2.0 * sqrt_T)
                 - r * K * math.exp(-r * T_years) * _norm_cdf(d2)) / 365.0
    else:
        delta = _norm_cdf(d1) - 1.0
        theta = (-(S * pdf_d1 * sigma) / (2.0 * sqrt_T)
                 + r * K * math.exp(-r * T_years) * _norm_cdf(-d2)) / 365.0
    gamma = pdf_d1 / (S * sigma * sqrt_T)
    vega = S * pdf_d1 * sqrt_T / 100.0  # per 1% IV
    return {'delta': float(delta), 'gamma': float(gamma),
            'theta': float(theta), 'vega': float(vega)}


# ── Data fetchers ───────────────────────────────────────────────────
def _live_price(ticker: str) -> float:
    """Best-effort spot price (real-time / 1m / daily fallthrough).

    yfinance>=0.2 changed fast_info from a dict to an object — must use
    attribute access (getattr), not .get(). Concurrent .get() calls return
    None and silently break the live-quote path.
    """
    try:
        fi = yf.Ticker(ticker).fast_info
        for attr in ('last_price', 'regularMarketPrice', 'previous_close'):
            try:
                p = getattr(fi, attr, None)
                if p is not None and float(p) > 0:
                    return float(p)
            except Exception:
                continue
    except Exception:
        pass
    try:
        intra = yf.Ticker(ticker).history(period='1d', interval='5m', auto_adjust=False)
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
    return 0.0


def _technicals(ticker: str) -> dict:
    """Underlying technicals: 1d %, 5d %, RSI14, 20DMA, HV30."""
    out = {'chg1d': 0.0, 'chg5d': 0.0, 'rsi14': 50.0,
           'pct_from_20dma': 0.0, 'hv30': 0.0}
    try:
        h = yf.download(ticker, period='3mo', progress=False, auto_adjust=True)
        if h.empty or len(h) < 25:
            return out
        if isinstance(h.columns, pd.MultiIndex):
            h.columns = h.columns.get_level_values(0)
        c = h['Close'].dropna()
        if len(c) < 25:
            return out
        out['chg1d'] = float((c.iloc[-1] / c.iloc[-2] - 1.0) * 100.0)
        out['chg5d'] = float((c.iloc[-1] / c.iloc[-6] - 1.0) * 100.0)
        # RSI14
        delta = c.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100.0 - 100.0 / (1.0 + rs)
        out['rsi14'] = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0
        # 20-day MA
        ma20 = c.rolling(20).mean()
        if not pd.isna(ma20.iloc[-1]) and ma20.iloc[-1] > 0:
            out['pct_from_20dma'] = float((c.iloc[-1] / ma20.iloc[-1] - 1.0) * 100.0)
        # HV30
        rets = c.pct_change().dropna().tail(30)
        out['hv30'] = float(rets.std() * np.sqrt(252))
    except Exception:
        pass
    return out


# ── Per-contract scoring ────────────────────────────────────────────
def _score_contract(row: pd.Series, side: str, ticker: str, sector: str,
                    expiry: str, dte: int, spot: float, tech: dict) -> dict | None:
    """Apply S1..S8 to a single option row. Returns None if S1 gate fails.

    Two data states:
      LIVE     — bid > 0 AND ask > 0. Spread gate enforced. IV from chain.
      SETTLED  — bid == ask == 0 (post-close / pre-open). Use lastPrice as
                 mid and IV is computed by inverting Black-Scholes from
                 lastPrice. S6 (IV vs HV) score applied to inverted IV.
    """
    bid = float(row.get('bid', 0) or 0)
    ask = float(row.get('ask', 0) or 0)
    last = float(row.get('lastPrice', 0) or 0)
    vol = int(row.get('volume', 0) or 0)
    oi = int(row.get('openInterest', 0) or 0)
    iv = float(row.get('impliedVolatility', 0) or 0)
    strike = float(row.get('strike', 0) or 0)
    if strike <= 0:
        return None

    # ── S1 LIQUIDITY GATE ──
    if bid > 0 and ask > 0:
        data_state = 'LIVE'
        mid = (bid + ask) / 2.0
        spread_pct = (ask - bid) / mid if mid > 0 else 1.0
        if spread_pct > MAX_SPREAD_PCT:
            return None
    elif last > 0:
        # Settled chain: rely on last-trade price; spread filter not applicable.
        data_state = 'SETTLED'
        mid = last
        spread_pct = 0.0
    else:
        return None

    if mid < MIN_MID:
        return None
    if vol < MIN_VOL or oi < MIN_OI:
        return None

    # If yfinance IV is degenerate (~0 in settled chains), invert from price
    if iv <= 0.005:
        iv = _implied_vol_from_price(spot, strike, max(dte, 1) / 365.0,
                                     mid, side)
        if iv <= 0:
            iv = max(tech.get('hv30', 0.0), 0.20)  # last-resort fallback

    premium_usd = vol * mid * 100.0
    vol_oi = vol / oi if oi > 0 else (99.0 if vol > 0 else 0.0)
    moneyness = (strike - spot) / spot * 100.0  # call: + = OTM | put: - = OTM
    T_years = max(dte, 1) / 365.0
    g = _bs_greeks(spot, strike, T_years, iv, side=side)

    # ── Sanity gate for SETTLED mode ──
    # When bid=ask=0, lastPrice can be stale (from a much earlier session
    # at a different spot). Drop contracts whose Greeks look degenerate:
    #   - |delta| < 0.05 or > 0.97 with |moneyness| > 12% on <=5 DTE
    #   - inverted IV < 8% (unrealistic for any 1-5 DTE option)
    if data_state == 'SETTLED':
        if iv < 0.08:
            return None
        if abs(g['delta']) < 0.05 or abs(g['delta']) > 0.97:
            return None
        if abs(moneyness) > 25:
            return None

    score = 0.0
    flags = []

    # ── S2 WHALE FLOW ──
    s2 = 0.0
    if vol_oi >= 5: s2 += 3
    elif vol_oi >= 3: s2 += 2
    elif vol_oi >= 1.5: s2 += 1
    if premium_usd >= 1_000_000: s2 += 2
    elif premium_usd >= 250_000: s2 += 1
    if s2:
        flags.append(('S2_whale_flow', +s2,
                      f'vol/OI {vol_oi:.1f}x | ${premium_usd/1e3:.0f}K notional'))
    score += s2

    # ── S3 DIRECTIONAL alignment with underlying trend ──
    trend_up = (tech['chg1d'] >= 0) and (tech['chg5d'] >= 0)
    trend_dn = (tech['chg1d'] <= 0) and (tech['chg5d'] <= 0)
    if side == 'call' and trend_up:
        score += 2
        flags.append(('S3_call_uptrend', +2,
                      f'1d {tech["chg1d"]:+.1f}% / 5d {tech["chg5d"]:+.1f}% — call aligned'))
    elif side == 'put' and trend_dn:
        score += 2
        flags.append(('S3_put_downtrend', +2,
                      f'1d {tech["chg1d"]:+.1f}% / 5d {tech["chg5d"]:+.1f}% — put aligned'))
    elif (side == 'call' and trend_dn) or (side == 'put' and trend_up):
        score -= 2
        flags.append(('S3_against_trend', -2,
                      f'1d {tech["chg1d"]:+.1f}% / 5d {tech["chg5d"]:+.1f}% — fighting trend'))

    # ── S4 DELTA SWEET SPOT ──
    abs_d = abs(g['delta'])
    if 0.25 <= abs_d <= 0.55:
        score += 2
        flags.append(('S4_delta_sweet', +2, f'|Δ| {abs_d:.2f} (asymmetric leverage zone)'))
    elif abs_d > 0.70:
        score -= 1
        flags.append(('S4_delta_deep_itm', -1, f'|Δ| {abs_d:.2f} too deep ITM (low leverage)'))
    elif abs_d < 0.15:
        score -= 1
        flags.append(('S4_delta_lottery', -1, f'|Δ| {abs_d:.2f} too far OTM (lottery)'))

    # ── S5 GAMMA / THETA edge per $ premium ──
    if g['theta'] != 0 and mid > 0:
        gt_per_dollar = abs(g['gamma'] / g['theta']) / mid
        if gt_per_dollar >= 0.5:
            score += 2
            flags.append(('S5_gamma_strong', +2,
                          f'γ/|θ| per $ = {gt_per_dollar:.2f} — strong gamma payoff'))
        elif gt_per_dollar >= 0.25:
            score += 1
            flags.append(('S5_gamma_ok', +1,
                          f'γ/|θ| per $ = {gt_per_dollar:.2f} — adequate gamma'))

    # ── S6 IV vs HV30 ──
    if tech['hv30'] > 0 and iv > 0:
        iv_ratio = iv / tech['hv30']
        if iv_ratio <= 0.85:
            score += 2
            flags.append(('S6_iv_cheap', +2,
                          f'IV {iv*100:.0f}% vs HV30 {tech["hv30"]*100:.0f}% '
                          f'({iv_ratio:.2f}x) — cheap vol'))
        elif iv_ratio <= 1.10:
            score += 1
            flags.append(('S6_iv_fair', +1,
                          f'IV/HV {iv_ratio:.2f}x — fair'))
        elif iv_ratio >= 1.60:
            score -= 2
            flags.append(('S6_iv_event', -2,
                          f'IV {iv*100:.0f}% vs HV30 {tech["hv30"]*100:.0f}% '
                          f'({iv_ratio:.2f}x) — event-pumped, theta trap'))

    # ── S7 TECHNICAL setup ──
    rsi = tech['rsi14']
    pct20 = tech['pct_from_20dma']
    if side == 'call':
        if 40 <= rsi <= 65 and -3 <= pct20 <= 3:
            score += 1.5
            flags.append(('S7_call_setup', +1.5,
                          f'RSI {rsi:.0f} + {pct20:+.1f}% from 20DMA — clean call setup'))
        elif rsi >= 75:
            score -= 1
            flags.append(('S7_overbought', -1, f'RSI {rsi:.0f} overbought — chase risk'))
    else:
        if 35 <= rsi <= 60 and pct20 <= -3:
            score += 1.5
            flags.append(('S7_put_setup', +1.5,
                          f'RSI {rsi:.0f} + {pct20:+.1f}% from 20DMA — clean put setup'))
        elif rsi <= 25:
            score -= 1
            flags.append(('S7_oversold', -1, f'RSI {rsi:.0f} oversold — bounce risk'))

    # ── S8 EXPIRY EDGE ──
    if dte in (2, 3):
        score += 0.5
        flags.append(('S8_2_3_dte', +0.5, f'{dte} DTE — sweet spot for short-term moves'))
    elif dte == 1:
        score -= 0.5
        flags.append(('S8_1_dte', -0.5, '1 DTE — minimal time for thesis to play'))

    return {
        'ticker': ticker, 'sector': sector, 'side': side,
        'strike': strike, 'expiry': expiry, 'dte': dte,
        'spot': spot, 'mid': mid, 'bid': bid, 'ask': ask,
        'volume': vol, 'oi': oi, 'iv': iv,
        'premium_usd': premium_usd, 'vol_oi': vol_oi, 'moneyness': moneyness,
        'delta': g['delta'], 'gamma': g['gamma'],
        'theta': g['theta'], 'vega': g['vega'],
        'spread_pct': spread_pct, 'data_state': data_state,
        'rsi14': tech['rsi14'], 'pct_from_20dma': tech['pct_from_20dma'],
        'hv30': tech['hv30'], 'chg1d': tech['chg1d'], 'chg5d': tech['chg5d'],
        'score': score, 'flags': flags,
    }


# ── Per-ticker scan ────────────────────────────────────────────────
def scan_ticker(ticker: str) -> list[dict]:
    """Return list of scored contracts (1-5 DTE) for one ticker."""
    sector = TICKER_TO_SECTOR.get(ticker, 'Other')
    spot = _live_price(ticker)
    if spot <= 0:
        return []
    tech = _technicals(ticker)
    if tech['hv30'] <= 0:
        # still possible to score, but IV/HV becomes neutral
        pass

    contracts: list[dict] = []
    try:
        yt = yf.Ticker(ticker)
        expirations = list(yt.options) if yt.options else []
    except Exception:
        return []
    if not expirations:
        return []

    today = datetime.now().date()
    for exp in expirations:
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
            for col in ('volume', 'openInterest', 'lastPrice', 'bid', 'ask',
                        'impliedVolatility', 'strike'):
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            for _, row in df.iterrows():
                rec = _score_contract(row, side, ticker, sector, exp, dte, spot, tech)
                if rec is not None:
                    contracts.append(rec)
    return contracts


# ── Reporting ──────────────────────────────────────────────────────
def _fmt_trade_plan(c: dict) -> str:
    """Generate suggested entry / target / stop levels for a contract."""
    mid = c['mid']
    side = c['side']
    iv = c['iv']
    dte = c['dte']
    spot = c['spot']
    strike = c['strike']
    delta = abs(c['delta'])
    # Expected 1-stdev move over remaining life
    one_sigma = spot * iv * math.sqrt(max(dte, 1) / 365.0)
    if side == 'call':
        target_spot = spot + one_sigma
        intrinsic_at_target = max(target_spot - strike, 0)
    else:
        target_spot = spot - one_sigma
        intrinsic_at_target = max(strike - target_spot, 0)
    # Approximate option value at +1σ (intrinsic + half remaining time value)
    time_val = max(mid - max((spot - strike) if side == 'call' else (strike - spot), 0), 0)
    target_premium = intrinsic_at_target + 0.4 * time_val  # half-decayed
    target_premium = max(target_premium, mid * 1.5)         # floor 50% gain
    # Stop = 50% premium loss (max acceptable for 1-5 DTE)
    stop_premium = mid * 0.50
    return (f"Entry ≤ ${mid*1.05:.2f} | Target ${target_premium:.2f} "
            f"(spot ${target_spot:.2f}) | Stop ${stop_premium:.2f} (-50%) "
            f"| 1σ move ±${one_sigma:.2f}")


def write_report(top_all: list[dict], out_path: Path,
                 scanned_tickers: int, contracts_evaluated: int):
    ts_now = datetime.now().strftime('%Y-%m-%d %H:%M %Z').strip()
    lines = []
    lines.append('# ⚡ Ultra-Short-Term Options Scanner (1-5 DTE)')
    lines.append(f'**Generated**: {ts_now}  |  '
                 f'**Tickers scanned**: {scanned_tickers}  |  '
                 f'**Contracts evaluated**: {contracts_evaluated}')
    lines.append('')
    lines.append('> **Disclaimer**: Algorithmic screen of public delayed options data via yfinance. '
                 'NOT financial advice. Theta burn on 1-5 DTE options is severe — pre-define stops, '
                 'size small. Recommendations are for educational purposes only.')
    lines.append('')

    # Methodology
    lines.append('## Methodology — 8-Signal Per-Contract Scoring')
    lines.append('')
    lines.append('| Signal | Description | Range |')
    lines.append('|--------|-------------|-------|')
    lines.append('| S1 LIQUIDITY GATE | vol≥50, OI≥100, mid≥$0.05, spread≤30% | HARD GATE |')
    lines.append('| S2 WHALE FLOW | vol/OI ratio + premium $ notional | 0 to +5 |')
    lines.append('| S3 DIRECTIONAL | call+uptrend / put+downtrend / mismatch | -2 to +2 |')
    lines.append('| S4 DELTA SWEET | Δ in [0.25, 0.55] = asymmetric leverage | -1 to +2 |')
    lines.append('| S5 GAMMA/THETA | γ/|θ| per $ premium = gamma payoff | 0 to +2 |')
    lines.append('| S6 IV vs HV30 | cheap vol = +2, event-pumped = -2 | -2 to +2 |')
    lines.append('| S7 TECHNICAL | RSI14 + dist from 20DMA setup quality | -1 to +1.5 |')
    lines.append('| S8 EXPIRY EDGE | 2-3 DTE preferred over 1 DTE | -0.5 to +0.5 |')
    lines.append('')

    # Top N
    if not top_all:
        lines.append('## ⚠ No qualifying contracts found this scan')
        lines.append('')
        lines.append('Possible reasons: market closed (weekend/holiday), low intraday volume, '
                     'or thin liquidity in 1-5 DTE chains. Re-run during US market hours.')
        out_path.write_text('\n'.join(lines), encoding='utf-8')
        return out_path

    lines.append(f'## 🎯 Top {min(TOP_N_REPORT, len(top_all))} Ultra-Short-Term Trade Ideas')
    lines.append('')
    lines.append('| # | Ticker | Side | Strike | Exp | DTE | Mid | Δ | IV | Vol | OI | Vol/OI | $Notional | Score |')
    lines.append('|---|--------|------|--------|-----|-----|-----|---|----|-----|----|--------|-----------|-------|')
    for i, c in enumerate(top_all[:TOP_N_REPORT], 1):
        side_emoji = '🟢' if c['side'] == 'call' else '🔴'
        state_tag = '⚡' if c['data_state'] == 'LIVE' else '🌙'
        lines.append(
            f"| {i} | **{c['ticker']}** {state_tag} | {side_emoji} {c['side'].upper()} | "
            f"${c['strike']:.2f} | {c['expiry']} | {c['dte']}d | "
            f"${c['mid']:.2f} | {c['delta']:+.2f} | {c['iv']*100:.0f}% | "
            f"{c['volume']:,} | {c['oi']:,} | {c['vol_oi']:.1f}x | "
            f"${c['premium_usd']/1e3:.0f}K | **{c['score']:+.1f}** |"
        )
    lines.append('')
    lines.append('> ⚡ = LIVE quote (bid/ask available)  '
                 '🌙 = SETTLED chain (last-trade price, US market closed)')
    lines.append('')

    # Detail for each top idea
    lines.append('### Trade Plans')
    lines.append('')
    for i, c in enumerate(top_all[:TOP_N_REPORT], 1):
        side_emoji = '🟢' if c['side'] == 'call' else '🔴'
        lines.append(f'#### #{i}  {side_emoji} {c["ticker"]} {c["side"].upper()} '
                     f'${c["strike"]:.2f} exp {c["expiry"]} ({c["dte"]} DTE)')
        lines.append('')
        lines.append(f'- **Sector**: {c["sector"]}  |  '
                     f'**Spot**: ${c["spot"]:.2f}  |  '
                     f'**Mid premium**: ${c["mid"]:.2f}  '
                     f'(bid ${c["bid"]:.2f} / ask ${c["ask"]:.2f}, spread {c["spread_pct"]*100:.0f}%)')
        lines.append(f'- **Greeks**: Δ {c["delta"]:+.3f}  |  '
                     f'Γ {c["gamma"]:.4f}  |  '
                     f'Θ ${c["theta"]:.3f}/day  |  '
                     f'Vega ${c["vega"]:.3f}/1%IV')
        lines.append(f'- **Flow**: vol {c["volume"]:,} / OI {c["oi"]:,} = {c["vol_oi"]:.1f}x  |  '
                     f'${c["premium_usd"]/1e3:.0f}K notional  |  '
                     f'IV {c["iv"]*100:.0f}% vs HV30 {c["hv30"]*100:.0f}%')
        lines.append(f'- **Underlying tech**: 1d {c["chg1d"]:+.1f}% / 5d {c["chg5d"]:+.1f}%  |  '
                     f'RSI14 {c["rsi14"]:.0f}  |  '
                     f'{c["pct_from_20dma"]:+.1f}% from 20DMA')
        lines.append(f'- **Trade plan**: {_fmt_trade_plan(c)}')
        lines.append(f'- **Score**: **{c["score"]:+.1f}**  |  Signals fired:')
        for rule, pts, desc in c['flags']:
            sign = '+' if pts > 0 else ''
            lines.append(f'  - `[{rule}]` ({sign}{pts:.1f}) {desc}')
        lines.append('')

    # Sector summary (count of qualifying contracts and avg score)
    by_sector: dict[str, list[float]] = {}
    for c in top_all:
        by_sector.setdefault(c['sector'], []).append(c['score'])
    if by_sector:
        lines.append('### Qualifying contracts by sector (after S1 gate)')
        lines.append('')
        lines.append('| Sector | Qualifying Count | Avg Score | Best Score |')
        lines.append('|--------|------------------|-----------|------------|')
        for sec, scores in sorted(by_sector.items(),
                                  key=lambda x: max(x[1]), reverse=True):
            lines.append(f'| {sec} | {len(scores)} | '
                         f'{np.mean(scores):.2f} | {max(scores):.2f} |')
        lines.append('')

    out_path.write_text('\n'.join(lines), encoding='utf-8')
    return out_path


def print_chat_summary(top_all: list[dict], scanned: int, contracts: int):
    """Compact stdout block for chat-display by the calling routine."""
    print('\n' + '=' * 78)
    print(f'  ULTRA-SHORT-TERM OPTIONS — TOP {TOP_N_REPORT} IDEAS '
          f'(1-5 DTE)  scanned={scanned}  contracts={contracts}')
    print('=' * 78)
    if not top_all:
        print('  No qualifying contracts (market closed / thin liquidity / no setups).')
        return
    for i, c in enumerate(top_all[:TOP_N_REPORT], 1):
        side_e = '🟢 CALL' if c['side'] == 'call' else '🔴 PUT '
        ds = '⚡' if c['data_state'] == 'LIVE' else '🌙'
        print(f"  #{i} {ds} {c['ticker']:5s} {side_e}  ${c['strike']:>7.2f}  "
              f"exp {c['expiry']} ({c['dte']}d)  mid ${c['mid']:>5.2f}  "
              f"Δ{c['delta']:+.2f}  IV{c['iv']*100:>3.0f}%  "
              f"v/oi {c['vol_oi']:>4.1f}x  ${c['premium_usd']/1e3:>5.0f}K  "
              f"score {c['score']:+5.1f}")
    print('=' * 78 + '\n')


def main():
    print('=' * 78)
    print('  Ultra-Short-Term Options Trading Scanner — 1-5 DTE')
    print(f'  {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 78)
    total = len(ALL_TICKERS)
    print(f'\nScanning {total} tickers '
          f'(workers={MAX_WORKERS}) for {MIN_DTE}-{MAX_DTE} DTE contracts...\n')

    all_contracts: list[dict] = []
    done = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(scan_ticker, t): t for t in ALL_TICKERS}
        for fut in as_completed(futures):
            t = futures[fut]
            done += 1
            try:
                contracts = fut.result(timeout=60)
                all_contracts.extend(contracts)
            except Exception as e:
                failed += 1
                print(f'  ! {t}: {str(e)[:60]}', flush=True)
            if done % 15 == 0 or done == total:
                print(f'  {done}/{total} scanned | '
                      f'qualified contracts so far: {len(all_contracts)}', flush=True)

    all_contracts.sort(key=lambda c: c['score'], reverse=True)

    # ── Two-tier ranking ─────────────────────────────────────────
    # Tier 1 (priority): high-score AND real money flow
    #   premium_usd >= $250K  AND  vol/OI >= 1.5
    # Tier 2 (fallback): high-score even if flow is modest
    # Top-5 picks come from Tier 1 first, then Tier 2 to fill any gap.
    tier1 = [c for c in all_contracts
             if c['premium_usd'] >= 250_000 and c['vol_oi'] >= 1.5]
    tier2 = [c for c in all_contracts if c not in tier1]
    top = tier1[:TOP_N_REPORT]
    if len(top) < TOP_N_REPORT:
        top.extend(tier2[:TOP_N_REPORT - len(top)])
    # Keep extras for the report's qualifying-pool sector breakdown
    extras = [c for c in all_contracts if c not in top][:25]
    top = top + extras

    print_chat_summary(top, done - failed, len(all_contracts))

    ts = datetime.now()
    out_path = Path(__file__).parent / f'ultra_short_options_{ts.strftime("%Y-%m-%d_%H%M")}.md'
    write_report(top, out_path, done - failed, len(all_contracts))
    print(f'  Report written: {out_path.name}')
    print('=' * 78)


if __name__ == '__main__':
    main()
