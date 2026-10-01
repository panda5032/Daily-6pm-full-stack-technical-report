"""
PROP TRADER OPTIONS MODEL — End-to-end edge engine
====================================================
Built to win and scale capital at a prop options seat.

Job requirements this model serves directly:
  - "Identify high-probability options setups"        → Edge scorer + IV regime
  - "Use Greeks to construct deliberate exposures"    → Strategy selector + position constructor
  - "Portfolio-level risk: concentration, correlation,
     drawdown"                                        → Greek budget + DD throttle
  - "Review fills, P&L, execution quality daily"      → Hooks for journal
  - "Organized trade journal: quantitative + qual"    → prop_trade_journal.py

THE 7-STAGE PIPELINE
  Stage 1   UNIVERSE        AI_Portfolios.xlsx tickers + indices
  Stage 2   IV REGIME       Classify each ticker: HIGH_IV / NEUTRAL / LOW_IV
                            (IVR, IVP, IV/HV ratio, term structure, skew)
  Stage 3   DIRECTION       Pull from team_master / right_side / short_term
                            (or compute trend score live)
  Stage 4   STRATEGY        Direction × IV Regime → optimal options strategy
                            (8 defined-risk structures supported)
  Stage 5   CONSTRUCT       Build the actual legs from live chain
                            Returns max P, max L, breakevens, P(profit), Greeks
  Stage 6   SIZE            Kelly-fractional sizer with DD throttle + caps
                            Respects portfolio Greek budget
  Stage 7   JOURNAL         Emit pre-trade thesis row for prop_trade_journal

OUTPUT
  prop_model_YYYY-MM-DD_HHMM.md   ranked playable trades
  _prop_candidates.json           machine-readable for journal/automation
  stdout                          terse top 5 chat summary

USAGE
  python prop_options_model.py                       # full scan
  python prop_options_model.py --tickers NVDA,TSLA   # targeted
  python prop_options_model.py --capital 50000       # set account size
  python prop_options_model.py --dd 0.07             # tell model current DD
  python prop_options_model.py --regime-only         # just IV regime read

DISCLAIMER
  Algorithmic screen of public delayed options data. Decisions are yours.
  Defined-risk structures only — no naked sells. Verify fills before trusting
  the model's max-loss number.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import io
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# Bulletproof data layer (handles the curl_cffi SSL issue, retry, caching)
from data_fetch import (
    get_history, get_spot, get_expiries, get_option_chain, get_session
)

warnings.filterwarnings('ignore')
try:
    if (getattr(sys.stdout, 'encoding', '') or '').lower() != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
except Exception:
    pass

ROOT = Path(__file__).parent

# ── Universe: synced to AI_Portfolios.xlsx (2026-08-08 version) ──────
# Every Excel name mapped to its optionable US listing.
# Skipped (no listed US options): SK Hynix (OTC HXSCL), Tencent (OTC TCEHY),
#   Cardano / DOGE / PEPE (no ETF with listed options yet).
# Proxied: Bitcoin→IBIT, Ethereum→ETHA, Solana→BSOL, Ripple→XRPC,
#   Gold→GLD, Silver→SLV, Copper→CPER, Oil→USO,
#   Hang Seng→EWH, China A-share→ASHR.
SECTORS = {
    'Hyperscaler':       ['GOOGL', 'AMZN', 'META', 'MSFT', 'AAPL'],
    'Self-Driving':      ['TSLA', 'PONY', 'UBER', 'GRAB'],
    'Robotics':          ['SERV', 'PATH', 'ISRG'],
    'Semis':             ['NVDA', 'AMD', 'AVGO', 'TSM', 'ARM', 'MRVL', 'MU', 'INTC',
                          'ASML', 'QCOM', 'AMAT', 'LRCX', 'KLAC', 'COHR'],
    'AI Infrastructure': ['CRWV', 'ORCL', 'IREN', 'NBIS', 'CIFR', 'APLD', 'CSCO',
                          'ALAB', 'ANET', 'DELL', 'SMCI', 'CRDO', 'EQIX', 'VRT',
                          'GEV', 'ETN', 'DLR'],
    'Energy':            ['OKLO', 'LAC', 'MP', 'SMR', 'BE', 'QS', 'EOSE', 'USAR', 'FCX'],
    'Software':          ['PLTR', 'SNOW', 'AI', 'IBM', 'MDB', 'NOW', 'CRM', 'ADBE',
                          'OKTA', 'SHOP', 'SOUN', 'BBAI', 'UPST', 'DUOL', 'RBRK',
                          'DDOG', 'NFLX', 'ZETA', 'SPOT', 'APP', 'RDDT', 'TTD',
                          'RBLX', 'U', 'INFY', 'WOLF', 'SNPS',
                          'CRWD', 'PANW', 'ZS', 'DOCN', 'NET', 'MNDY', 'DT',
                          'ESTC', 'KTOS', 'TEAM', 'WDAY', 'INTU'],
    'Health':            ['UNH', 'OSCR', 'HIMS', 'RXRX', 'LLY', 'TEM', 'CRSP', 'TMDX'],
    'Space':             ['RKLB', 'FLY', 'JOBY', 'ACHR', 'LUNR', 'ASTS', 'ONDS'],
    'China':             ['BABA', 'BIDU', 'JD', 'XPEV', 'NIO', 'PDD', 'FUTU'],
    'Crypto':            ['IBIT', 'ETHA', 'XRPC', 'BSOL', 'BMNR', 'MSTR', 'COIN',
                          'CLSK', 'RIOT', 'MARA', 'SBET', 'HUT', 'FIG', 'CRCL',
                          'XYZ', 'BULL', 'HIVE'],
    'Finance':           ['SOFI', 'OPEN', 'LMND', 'HOOD', 'PYPL', 'AFRM'],
    'Quantum':           ['RGTI', 'IONQ', 'QUBT', 'QBTS'],
    'Trading':           ['GME', 'LULU', 'CMG', 'UPS', 'ABNB', 'PTON', 'BA', 'NKE'],
    'Rotation':          ['JPM', 'GS', 'BRK-B', 'XOM', 'CVX', 'CAT', 'DE', 'GE', 'COST', 'WMT', 'JNJ', 'XLU'],
    'Commodity':         ['GLD', 'SLV', 'CPER', 'USO'],
    'Index':             ['QQQ', 'SPY', 'DIA', 'EWH', 'ASHR'],
}

TICKER_TO_SECTOR = {t: s for s, ts in SECTORS.items() for t in ts}
ALL_TICKERS = sorted({t for ts in SECTORS.values() for t in ts})

# Beta-to-SPY proxies (used in portfolio Greek aggregator). Set to ~1.0 if unknown.
# Index ETFs anchor at 1.0; high-beta AI names ~1.6; defensives ~0.8.
BETA_HINTS = {
    'SPY': 1.0, 'QQQ': 1.15, 'IWM': 1.20, 'DIA': 0.95,
    'NVDA': 1.85, 'TSLA': 2.20, 'AMD': 2.10, 'META': 1.50, 'GOOGL': 1.20,
    'MSFT': 1.05, 'AAPL': 1.15, 'AMZN': 1.30,
    'PLTR': 2.40, 'COIN': 2.80, 'MSTR': 3.20, 'SMCI': 2.50, 'ARM': 2.00,
    'AVGO': 1.40, 'TSM': 1.30, 'MU': 2.00,
}

# ── Risk / sizing knobs (tunable but defaulted to "prop-acceptable") ─
RISK_FREE_RATE = 0.045

# Kelly + sizing
KELLY_FRACTION_BASE = 0.50              # half-Kelly default
KELLY_FLOOR = 0.10                      # never below 10% of Kelly when DD severe
MAX_RISK_PER_TRADE_PCT = 0.02           # 2% of capital max defined risk per trade
MAX_RISK_PER_TICKER_PCT = 0.05          # 5% of capital across all trades on one ticker
MAX_PORTFOLIO_RISK_PCT = 0.15           # 15% capital at risk across all open positions
MAX_SECTOR_RISK_PCT = 0.08              # 8% capital at risk per sector

# Greek budget (per $100K notional)
MAX_NET_DELTA_PCT = 0.40                # net beta-weighted delta as % of capital (in $)
MAX_VEGA_PER_1PCT_IV = 0.005            # 0.5% of capital P&L per 1 vol point move
MAX_NEG_THETA_PER_DAY = 0.003           # 0.3% of capital decay per day (when net short premium)

# Drawdown throttle
DD_TIER_1 = 0.05                        # 5% DD → 0.5x size
DD_TIER_2 = 0.10                        # 10% DD → 0.25x size
DD_TIER_3 = 0.15                        # 15% DD → stop, review

# Trade quality gates — these are the "would I risk firm capital on this?" filters
MIN_EDGE_SCORE = 55                     # 0-100; below this don't enter
MIN_PROB_PROFIT = 0.25                  # 25% floor — defines no "pure lottery" trades
MIN_EXPECTANCY = 0.0                    # require positive expected value PER CONTRACT
MIN_MAX_LOSS_DOLLARS = 25               # reject "$1 risk" data-anomaly trades
MAX_CONTRACTS_PER_TRADE = 50            # sanity cap regardless of Kelly math
MIN_RR = 0.5                            # min reward:risk on debit structures (credits can be <1)
MIN_LIQUIDITY_OI = 100
MIN_LIQUIDITY_VOL = 50
MAX_BID_ASK_PCT = 0.15                  # 15% spread max for entries (tight!)

# Strategy DTE preferences
SHORT_DTE_RANGE = (1, 7)                # 0DTE / week plays
SWING_DTE_RANGE = (14, 45)              # core swing
EVENT_DTE_RANGE = (5, 30)               # around earnings / catalysts

MAX_WORKERS = 5
MAX_EXPIRIES_TO_SCAN = 20    # covers ~3 months of weeklies + first monthlies


# ╔════════════════════════════════════════════════════════════════════╗
# ║  PRIMITIVES: Black-Scholes Greeks + IV solver                      ║
# ╚════════════════════════════════════════════════════════════════════╝

def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _npdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def bs_price(S, K, T, sigma, r=RISK_FREE_RATE, side='call'):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return max((S - K) if side == 'call' else (K - S), 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if side == 'call':
        return S * _ncdf(d1) - K * math.exp(-r * T) * _ncdf(d2)
    return K * math.exp(-r * T) * _ncdf(-d2) - S * _ncdf(-d1)


def bs_greeks(S, K, T, sigma, r=RISK_FREE_RATE, side='call') -> dict:
    """Returns delta, gamma, theta (per day), vega (per 1% IV move)."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return {'delta': 0.0, 'gamma': 0.0, 'theta': 0.0, 'vega': 0.0}
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    pdf1 = _npdf(d1)
    gamma = pdf1 / (S * sigma * math.sqrt(T))
    vega = S * pdf1 * math.sqrt(T) / 100.0  # per 1% IV
    if side == 'call':
        delta = _ncdf(d1)
        theta_year = -(S * pdf1 * sigma) / (2 * math.sqrt(T)) - r * K * math.exp(-r * T) * _ncdf(d2)
    else:
        delta = _ncdf(d1) - 1.0
        theta_year = -(S * pdf1 * sigma) / (2 * math.sqrt(T)) + r * K * math.exp(-r * T) * _ncdf(-d2)
    return {
        'delta': delta,
        'gamma': gamma,
        'theta': theta_year / 365.0,
        'vega': vega,
    }


def implied_vol(S, K, T, target, side='call', r=RISK_FREE_RATE) -> float:
    if target <= 0 or T <= 0 or S <= 0 or K <= 0:
        return 0.0
    intrinsic = max(S - K, 0) if side == 'call' else max(K - S, 0)
    if target < intrinsic - 0.01:
        return 0.0
    lo, hi = 0.005, 5.0
    for _ in range(50):
        m = (lo + hi) / 2
        if bs_price(S, K, T, m, r, side) < target:
            lo = m
        else:
            hi = m
        if hi - lo < 1e-4:
            break
    return (lo + hi) / 2


# ╔════════════════════════════════════════════════════════════════════╗
# ║  STAGE 2: IV REGIME — IVR, IVP, IV/HV, term structure, skew        ║
# ╚════════════════════════════════════════════════════════════════════╝

@dataclass
class IVRegime:
    ticker: str
    spot: float
    iv30: float                     # current ATM 30D IV
    hv30: float                     # 30-day realized vol
    ivr: float                      # IV rank 0-100 (52w)
    ivp: float                      # IV percentile 0-100 (52w)
    iv_hv_ratio: float              # IV30 / HV30
    term_slope: float               # (back IV - front IV) / front IV
    put_skew: float                 # (25-delta put IV - ATM IV) / ATM IV
    regime: str                     # HIGH_IV / NEUTRAL / LOW_IV
    label: str                      # human-readable summary


def compute_hv30(prices: pd.Series) -> float:
    if prices is None or len(prices) < 22:
        return 0.0
    rets = np.log(prices / prices.shift(1)).dropna()
    if len(rets) < 21:
        return 0.0
    return float(rets.tail(30).std() * math.sqrt(252))


def fetch_iv_regime(ticker: str) -> Optional[IVRegime]:
    """Build the IV regime for one ticker. Returns None on data failure."""
    try:
        hist = get_history(ticker, period='1y')
        if hist is None or hist.empty:
            return None
        closes = hist['Close']
        spot = float(closes.iloc[-1])
        hv30 = compute_hv30(closes)

        # Pull the front-month ATM IV
        expiries = list(get_expiries(ticker))
        if not expiries:
            return None
        target_dte = 30
        today = datetime.now().date()

        def _dte(e: str) -> int:
            return (datetime.strptime(e, '%Y-%m-%d').date() - today).days

        front_exp = min(expiries[:8], key=lambda e: abs(_dte(e) - 30))
        back_exp = min(expiries[:12], key=lambda e: abs(_dte(e) - 90)) if len(expiries) > 4 else front_exp

        def _atm_iv(exp: str) -> tuple[float, float, float]:
            """Return (atm_iv, put25_iv, dte). Falls back to nearest-strike IV."""
            calls, puts = get_option_chain(ticker, exp)
            if calls is None or puts is None or calls.empty or puts.empty:
                return 0.0, 0.0, _dte(exp)
            T = max(_dte(exp), 1) / 365.0
            # ATM IV: average of ATM call + ATM put IV (after sanity check)
            cidx = (calls['strike'] - spot).abs().idxmin()
            pidx = (puts['strike'] - spot).abs().idxmin()
            call_iv = float(calls.loc[cidx, 'impliedVolatility'] or 0)
            put_iv = float(puts.loc[pidx, 'impliedVolatility'] or 0)
            atm_iv = np.mean([v for v in (call_iv, put_iv) if 0.05 < v < 4.0]) if (call_iv or put_iv) else 0.0
            # 25-delta put IV (target delta -0.25; scan puts and pick closest)
            put25_iv = 0.0
            try:
                deltas = []
                for _, row in puts.iterrows():
                    iv = float(row.get('impliedVolatility', 0) or 0)
                    if iv <= 0 or T <= 0:
                        continue
                    d = bs_greeks(spot, float(row['strike']), T, iv, side='put')['delta']
                    deltas.append((abs(d - (-0.25)), iv))
                if deltas:
                    deltas.sort()
                    put25_iv = deltas[0][1]
            except Exception:
                pass
            return float(atm_iv or 0), float(put25_iv or atm_iv), _dte(exp)

        iv_front, put25_iv, dte_f = _atm_iv(front_exp)
        iv_back, _, dte_b = _atm_iv(back_exp)

        if iv_front <= 0:
            return None

        # IVR / IVP approximation:
        # Without a full historical IV series we approximate using HV proxy series.
        # Use 1y HV history as a stand-in for IV percentile rank (correlated ~0.7+).
        hv_series = np.log(closes / closes.shift(1)).rolling(30).std() * math.sqrt(252)
        hv_series = hv_series.dropna()
        if len(hv_series) >= 50:
            hv_min, hv_max = float(hv_series.min()), float(hv_series.max())
            ivr_proxy = ((iv_front - hv_min) / max(hv_max - hv_min, 1e-6)) * 100.0
            ivp_proxy = float((hv_series < iv_front).mean() * 100.0)
        else:
            ivr_proxy = 50.0
            ivp_proxy = 50.0
        ivr_proxy = max(0.0, min(100.0, ivr_proxy))

        iv_hv = iv_front / hv30 if hv30 > 0 else 1.0
        term_slope = (iv_back - iv_front) / iv_front if iv_front > 0 else 0.0
        put_skew = (put25_iv - iv_front) / iv_front if iv_front > 0 else 0.0

        # Regime classification — three voters: IVR, IV/HV, IVP
        score = 0
        if ivr_proxy >= 60: score += 1
        elif ivr_proxy <= 30: score -= 1
        if iv_hv >= 1.25: score += 1
        elif iv_hv <= 0.90: score -= 1
        if ivp_proxy >= 60: score += 1
        elif ivp_proxy <= 30: score -= 1

        if score >= 2:
            regime = 'HIGH_IV'
        elif score <= -2:
            regime = 'LOW_IV'
        else:
            regime = 'NEUTRAL'

        label = (f"{regime} | IVR {ivr_proxy:.0f} | IV/HV {iv_hv:.2f} | "
                 f"term {'contango' if term_slope > 0.05 else 'backwardation' if term_slope < -0.05 else 'flat'} "
                 f"({term_slope:+.1%}) | put skew {put_skew:+.1%}")

        return IVRegime(
            ticker=ticker, spot=spot, iv30=iv_front, hv30=hv30,
            ivr=ivr_proxy, ivp=ivp_proxy, iv_hv_ratio=iv_hv,
            term_slope=term_slope, put_skew=put_skew,
            regime=regime, label=label,
        )
    except Exception as e:
        return None


# ╔════════════════════════════════════════════════════════════════════╗
# ║  STAGE 3: DIRECTION — read team_master / right_side / fallback     ║
# ╚════════════════════════════════════════════════════════════════════╝

def load_directional_bias() -> dict[str, dict]:
    """
    Pull latest directional view per ticker.
    Priority: team_master CSV > most recent right_side_trading md > live trend.
    Returns: {ticker: {'bias': 'BULL'|'BEAR'|'NEUTRAL', 'src': str, 'conviction': 0-1}}
    """
    out: dict[str, dict] = {}

    # 1. team_master_*.csv (best — already-synthesized view)
    # Analyst views go stale: ignore files older than 21 days, and halve
    # conviction past 7 days so a fresh live-trend read can compete.
    tm_files = sorted(ROOT.glob('team_master_*.csv'))
    if tm_files:
        try:
            age_days = (datetime.now()
                        - datetime.fromtimestamp(tm_files[-1].stat().st_mtime)).days
            if age_days > 21:
                return out
            stale_mult = 0.5 if age_days > 7 else 1.0
            df = pd.read_csv(tm_files[-1])
            tcol = next((c for c in df.columns if c.lower() in ('ticker', 'symbol')), None)
            vcol = next((c for c in df.columns if 'verdict' in c.lower() or 'recommendation' in c.lower() or 'rating' in c.lower()), None)
            if tcol and vcol:
                for _, row in df.iterrows():
                    t = str(row[tcol]).upper()
                    v = str(row[vcol]).upper()
                    if 'BUY' in v or 'BULL' in v:
                        bias = 'BULL'
                    elif 'SELL' in v or 'BEAR' in v:
                        bias = 'BEAR'
                    else:
                        bias = 'NEUTRAL'
                    conv = (0.8 if 'STRONG' in v else 0.5) * stale_mult
                    src = tm_files[-1].name + (f' (stale {age_days}d)' if stale_mult < 1 else '')
                    out[t] = {'bias': bias, 'src': src, 'conviction': conv}
        except Exception:
            pass

    return out


def live_trend_bias(ticker: str, hist: pd.DataFrame = None) -> dict:
    """Cheap directional fallback when no analyst signal exists."""
    try:
        if hist is None:
            hist = get_history(ticker, period='6mo')
        if hist is None or hist.empty or len(hist) < 60:
            return {'bias': 'NEUTRAL', 'src': 'live_trend', 'conviction': 0.3}
        c = hist['Close']
        ma20 = c.rolling(20).mean().iloc[-1]
        ma50 = c.rolling(50).mean().iloc[-1]
        last = c.iloc[-1]
        chg_5d = (last / c.iloc[-6] - 1) if len(c) > 6 else 0
        chg_20d = (last / c.iloc[-21] - 1) if len(c) > 21 else 0
        score = 0
        if last > ma20 > ma50: score += 2
        elif last < ma20 < ma50: score -= 2
        if chg_5d > 0.02: score += 1
        elif chg_5d < -0.02: score -= 1
        if chg_20d > 0.05: score += 1
        elif chg_20d < -0.05: score -= 1
        if score >= 2: return {'bias': 'BULL', 'src': 'live_trend', 'conviction': 0.5}
        if score <= -2: return {'bias': 'BEAR', 'src': 'live_trend', 'conviction': 0.5}
        return {'bias': 'NEUTRAL', 'src': 'live_trend', 'conviction': 0.4}
    except Exception:
        return {'bias': 'NEUTRAL', 'src': 'live_trend', 'conviction': 0.3}


# ╔════════════════════════════════════════════════════════════════════╗
# ║  STAGE 4: STRATEGY SELECTOR — Direction × IV Regime matrix         ║
# ╚════════════════════════════════════════════════════════════════════╝
#
# STRATEGY MATRIX
# ───────────────────────────────────────────────────────────────────────
#                  HIGH_IV (sell vol)    NEUTRAL              LOW_IV (buy vol)
# BULL             Bull Put Spread       Long Call DEBIT      Long Call
#                                        Vertical             Call Calendar (event)
# BEAR             Bear Call Spread      Long Put DEBIT       Long Put
#                                        Vertical             Put Calendar (event)
# NEUTRAL          Iron Condor           Iron Butterfly       Long Straddle/
#                  (or Iron Butterfly                         Strangle (catalyst)
#                  if low vol of vol)                         Calendar
#
# All structures are DEFINED RISK — no naked sales.
# ───────────────────────────────────────────────────────────────────────

STRATEGY_MATRIX = {
    ('BULL', 'HIGH_IV'):    'BULL_PUT_SPREAD',
    ('BULL', 'NEUTRAL'):    'BULL_CALL_DEBIT_SPREAD',
    ('BULL', 'LOW_IV'):     'LONG_CALL',
    ('BEAR', 'HIGH_IV'):    'BEAR_CALL_SPREAD',
    ('BEAR', 'NEUTRAL'):    'BEAR_PUT_DEBIT_SPREAD',
    ('BEAR', 'LOW_IV'):     'LONG_PUT',
    ('NEUTRAL', 'HIGH_IV'): 'IRON_CONDOR',
    ('NEUTRAL', 'NEUTRAL'): 'IRON_BUTTERFLY',
    ('NEUTRAL', 'LOW_IV'):  'LONG_STRADDLE',
}


# ╔════════════════════════════════════════════════════════════════════╗
# ║  STAGE 5: POSITION CONSTRUCTOR — build legs from live chain        ║
# ╚════════════════════════════════════════════════════════════════════╝

@dataclass
class OptionLeg:
    side: str            # 'call' / 'put'
    action: str          # 'BUY' / 'SELL'
    strike: float
    expiry: str
    dte: int
    mid: float           # mid price (model assumes mid fill)
    iv: float
    delta: float
    gamma: float
    theta: float
    vega: float
    vol: int = 0
    oi: int = 0
    bid: float = 0.0
    ask: float = 0.0


@dataclass
class TradeStructure:
    ticker: str
    sector: str
    spot: float
    strategy: str
    regime: str
    bias: str
    bias_src: str
    legs: list[OptionLeg] = field(default_factory=list)
    debit_credit: str = 'DEBIT'      # DEBIT / CREDIT
    net_premium: float = 0.0          # per share (× 100 = $/contract)
    max_profit: float = 0.0           # $ per contract
    max_loss: float = 0.0             # $ per contract (positive number)
    breakevens: list[float] = field(default_factory=list)
    prob_profit: float = 0.0          # 0-1
    rr_ratio: float = 0.0             # max_profit / max_loss
    expectancy_per_contract: float = 0.0
    # Greeks summed across legs (per 1 contract bundle)
    net_delta: float = 0.0
    net_gamma: float = 0.0
    net_theta: float = 0.0
    net_vega: float = 0.0
    # Quality
    liquidity_ok: bool = False
    spread_pct: float = 0.0
    edge_score: float = 0.0
    notes: list[str] = field(default_factory=list)


class _ChainBundle:
    """Lightweight shim: lets old code that did `ch.calls / ch.puts` keep working."""
    __slots__ = ('calls', 'puts')
    def __init__(self, calls, puts):
        self.calls, self.puts = calls, puts


def _safe_chain(ticker: str, exp: str):
    calls, puts = get_option_chain(ticker, exp)
    if calls is None or puts is None or (calls.empty and puts.empty):
        return None
    return _ChainBundle(calls, puts)


def _pick_target_dte(expiries: list[str], target: int, dte_range: tuple) -> str | None:
    today = datetime.now().date()
    lo, hi = dte_range
    cands = []
    for e in expiries[:MAX_EXPIRIES_TO_SCAN]:
        try:
            d = (datetime.strptime(e, '%Y-%m-%d').date() - today).days
            if lo <= d <= hi:
                cands.append((abs(d - target), e))
        except Exception:
            continue
    if not cands:
        return None
    cands.sort()
    return cands[0][1]


def _pick_strike_by_delta(rows: pd.DataFrame, spot: float, T: float,
                          side: str, target_abs_delta: float) -> Optional[pd.Series]:
    """Pick the strike whose computed |delta| is closest to target."""
    if rows is None or rows.empty:
        return None
    best, best_diff = None, 1e9
    for _, row in rows.iterrows():
        iv = float(row.get('impliedVolatility', 0) or 0)
        if iv <= 0 or T <= 0:
            continue
        K = float(row['strike'])
        d = bs_greeks(spot, K, T, iv, side=side)['delta']
        diff = abs(abs(d) - target_abs_delta)
        if diff < best_diff:
            best_diff = diff
            best = row
    return best


def _leg_from_row(row: pd.Series, side: str, action: str, expiry: str,
                  spot: float) -> OptionLeg:
    today = datetime.now().date()
    dte = max((datetime.strptime(expiry, '%Y-%m-%d').date() - today).days, 1)
    T = dte / 365.0
    iv = float(row.get('impliedVolatility', 0) or 0)
    bid = float(row.get('bid', 0) or 0)
    ask = float(row.get('ask', 0) or 0)
    mid = (bid + ask) / 2 if (bid > 0 and ask > 0) else float(row.get('lastPrice', 0) or 0)
    g = bs_greeks(spot, float(row['strike']), T, iv, side=side)
    sgn = 1 if action == 'BUY' else -1
    return OptionLeg(
        side=side, action=action, strike=float(row['strike']),
        expiry=expiry, dte=dte, mid=float(mid), iv=iv,
        delta=sgn * g['delta'], gamma=sgn * g['gamma'],
        theta=sgn * g['theta'], vega=sgn * g['vega'],
        vol=int(row.get('volume', 0) or 0),
        oi=int(row.get('openInterest', 0) or 0),
        bid=bid, ask=ask,
    )


def _summarize_structure(ts: TradeStructure):
    """Aggregate legs → net premium, max P/L, breakevens, Greeks, liquidity."""
    if not ts.legs:
        return
    net_debit = 0.0
    nd = ng = nt = nv = 0.0
    spreads = []
    illiq = False
    for L in ts.legs:
        sgn_cost = 1 if L.action == 'BUY' else -1
        net_debit += sgn_cost * L.mid
        nd += L.delta; ng += L.gamma; nt += L.theta; nv += L.vega
        if L.oi < MIN_LIQUIDITY_OI:
            illiq = True
        if L.bid > 0 and L.ask > 0:
            spreads.append((L.ask - L.bid) / max((L.ask + L.bid) / 2, 0.01))
    ts.net_premium = net_debit
    ts.debit_credit = 'DEBIT' if net_debit > 0 else 'CREDIT'
    ts.net_delta, ts.net_gamma, ts.net_theta, ts.net_vega = nd, ng, nt, nv
    ts.spread_pct = float(np.mean(spreads)) if spreads else 1.0
    ts.liquidity_ok = (not illiq) and ts.spread_pct <= MAX_BID_ASK_PCT

    # Per-strategy max P/L
    strat = ts.strategy
    spot = ts.spot
    if strat in ('LONG_CALL', 'LONG_PUT'):
        L = ts.legs[0]
        ts.max_loss = max(L.mid * 100, 1.0)
        ts.max_profit = float('inf')          # unbounded — use 3x debit as planning target
        be = L.strike + L.mid if L.side == 'call' else L.strike - L.mid
        ts.breakevens = [round(be, 2)]
        # P(profit) ≈ |delta| of the long leg
        ts.prob_profit = abs(L.delta)
        ts.rr_ratio = 3.0                      # planning assumption
        ts.expectancy_per_contract = ts.prob_profit * (3 * L.mid * 100) - (1 - ts.prob_profit) * (L.mid * 100)

    elif strat in ('BULL_CALL_DEBIT_SPREAD', 'BEAR_PUT_DEBIT_SPREAD'):
        long_leg = next(L for L in ts.legs if L.action == 'BUY')
        short_leg = next(L for L in ts.legs if L.action == 'SELL')
        width = abs(long_leg.strike - short_leg.strike)
        debit = ts.net_premium
        ts.max_loss = max(debit * 100, 1.0)
        ts.max_profit = max((width - debit) * 100, 1.0)
        ts.rr_ratio = ts.max_profit / ts.max_loss
        if long_leg.side == 'call':
            be = long_leg.strike + debit
        else:
            be = long_leg.strike - debit
        ts.breakevens = [round(be, 2)]
        ts.prob_profit = abs(short_leg.delta)  # short-leg delta ≈ P(expire OTM of short)
        ts.expectancy_per_contract = ts.prob_profit * ts.max_profit - (1 - ts.prob_profit) * ts.max_loss

    elif strat in ('BULL_PUT_SPREAD', 'BEAR_CALL_SPREAD'):
        short_leg = next(L for L in ts.legs if L.action == 'SELL')
        long_leg = next(L for L in ts.legs if L.action == 'BUY')
        width = abs(long_leg.strike - short_leg.strike)
        credit = -ts.net_premium               # negative net debit = credit
        ts.max_profit = max(credit * 100, 1.0)
        ts.max_loss = max((width - credit) * 100, 1.0)
        ts.rr_ratio = ts.max_profit / ts.max_loss
        if short_leg.side == 'put':
            be = short_leg.strike - credit
        else:
            be = short_leg.strike + credit
        ts.breakevens = [round(be, 2)]
        ts.prob_profit = 1 - abs(short_leg.delta)
        ts.expectancy_per_contract = ts.prob_profit * ts.max_profit - (1 - ts.prob_profit) * ts.max_loss

    elif strat == 'IRON_CONDOR':
        short_put = next(L for L in ts.legs if L.side == 'put' and L.action == 'SELL')
        long_put = next(L for L in ts.legs if L.side == 'put' and L.action == 'BUY')
        short_call = next(L for L in ts.legs if L.side == 'call' and L.action == 'SELL')
        long_call = next(L for L in ts.legs if L.side == 'call' and L.action == 'BUY')
        put_width = abs(short_put.strike - long_put.strike)
        call_width = abs(long_call.strike - short_call.strike)
        width = max(put_width, call_width)
        credit = -ts.net_premium
        ts.max_profit = max(credit * 100, 1.0)
        ts.max_loss = max((width - credit) * 100, 1.0)
        ts.rr_ratio = ts.max_profit / ts.max_loss
        ts.breakevens = [round(short_put.strike - credit, 2),
                         round(short_call.strike + credit, 2)]
        # P(profit) ≈ 1 - |delta_short_put| - delta_short_call
        ts.prob_profit = max(0.0, 1 - abs(short_put.delta) - abs(short_call.delta))
        ts.expectancy_per_contract = ts.prob_profit * ts.max_profit - (1 - ts.prob_profit) * ts.max_loss

    elif strat == 'IRON_BUTTERFLY':
        short_put = next(L for L in ts.legs if L.side == 'put' and L.action == 'SELL')
        long_put = next(L for L in ts.legs if L.side == 'put' and L.action == 'BUY')
        short_call = next(L for L in ts.legs if L.side == 'call' and L.action == 'SELL')
        long_call = next(L for L in ts.legs if L.side == 'call' and L.action == 'BUY')
        width = max(abs(short_put.strike - long_put.strike), abs(long_call.strike - short_call.strike))
        credit = -ts.net_premium
        ts.max_profit = max(credit * 100, 1.0)
        ts.max_loss = max((width - credit) * 100, 1.0)
        ts.rr_ratio = ts.max_profit / ts.max_loss
        ts.breakevens = [round(short_put.strike - credit, 2),
                         round(short_call.strike + credit, 2)]
        # P(profit) tighter than condor — use 0.35 default if both shorts ~ATM
        ts.prob_profit = 0.35
        ts.expectancy_per_contract = ts.prob_profit * ts.max_profit - (1 - ts.prob_profit) * ts.max_loss

    elif strat == 'LONG_STRADDLE':
        call_leg = next(L for L in ts.legs if L.side == 'call')
        put_leg = next(L for L in ts.legs if L.side == 'put')
        debit = ts.net_premium
        ts.max_loss = max(debit * 100, 1.0)
        ts.max_profit = float('inf')
        ts.breakevens = [round(call_leg.strike - debit, 2), round(call_leg.strike + debit, 2)]
        # P(profit) ≈ probability stock moves > debit before exp; roughly 30-40% for ATM
        # Use call_iv to estimate via 1-sigma vs needed-move
        T = max(call_leg.dte, 1) / 365.0
        expected_move = ts.spot * call_leg.iv * math.sqrt(T)
        needed_move = debit
        # crude: P = 2 * (1 - N(needed/expected))
        if expected_move > 0:
            z = needed_move / expected_move
            ts.prob_profit = max(0.0, min(1.0, 2 * (1 - _ncdf(z))))
        else:
            ts.prob_profit = 0.3
        ts.rr_ratio = 3.0
        ts.expectancy_per_contract = ts.prob_profit * (3 * debit * 100) - (1 - ts.prob_profit) * (debit * 100)


# ── Per-strategy builders ────────────────────────────────────────────

def build_long_single(ticker: str, spot: float, sector: str,
                      regime: IVRegime, bias_info: dict, side: str,
                      dte_range: tuple = SWING_DTE_RANGE,
                      target_dte: int = 30) -> Optional[TradeStructure]:
    expiries = list(get_expiries(ticker))
    exp = _pick_target_dte(expiries, target_dte, dte_range)
    if not exp:
        return None
    ch = _safe_chain(ticker, exp)
    if not ch:
        return None
    today = datetime.now().date()
    T = max((datetime.strptime(exp, '%Y-%m-%d').date() - today).days, 1) / 365.0
    rows = ch.calls if side == 'call' else ch.puts
    # Target 50-delta (slightly ITM bias for long)
    row = _pick_strike_by_delta(rows, spot, T, side, 0.55)
    if row is None:
        return None
    leg = _leg_from_row(row, side, 'BUY', exp, spot)
    strat = 'LONG_CALL' if side == 'call' else 'LONG_PUT'
    ts = TradeStructure(
        ticker=ticker, sector=sector, spot=spot, strategy=strat,
        regime=regime.regime, bias=bias_info['bias'], bias_src=bias_info['src'],
        legs=[leg],
    )
    _summarize_structure(ts)
    return ts


def _build_vertical_one(ticker, spot, sector, regime, bias_info, kind,
                        exp, T, ch, long_delta, short_delta) -> Optional[TradeStructure]:
    """Build one vertical at the specified delta pair. Helper for the scanner."""
    if kind == 'BULL_CALL_DEBIT_SPREAD':
        long_row = _pick_strike_by_delta(ch.calls, spot, T, 'call', long_delta)
        short_row = _pick_strike_by_delta(ch.calls, spot, T, 'call', short_delta)
        if long_row is None or short_row is None or long_row['strike'] >= short_row['strike']:
            return None
        legs = [_leg_from_row(long_row, 'call', 'BUY', exp, spot),
                _leg_from_row(short_row, 'call', 'SELL', exp, spot)]
    elif kind == 'BEAR_PUT_DEBIT_SPREAD':
        long_row = _pick_strike_by_delta(ch.puts, spot, T, 'put', long_delta)
        short_row = _pick_strike_by_delta(ch.puts, spot, T, 'put', short_delta)
        if long_row is None or short_row is None or long_row['strike'] <= short_row['strike']:
            return None
        legs = [_leg_from_row(long_row, 'put', 'BUY', exp, spot),
                _leg_from_row(short_row, 'put', 'SELL', exp, spot)]
    elif kind == 'BULL_PUT_SPREAD':
        short_row = _pick_strike_by_delta(ch.puts, spot, T, 'put', short_delta)
        long_row = _pick_strike_by_delta(ch.puts, spot, T, 'put', long_delta)
        if long_row is None or short_row is None or long_row['strike'] >= short_row['strike']:
            return None
        legs = [_leg_from_row(short_row, 'put', 'SELL', exp, spot),
                _leg_from_row(long_row, 'put', 'BUY', exp, spot)]
    elif kind == 'BEAR_CALL_SPREAD':
        short_row = _pick_strike_by_delta(ch.calls, spot, T, 'call', short_delta)
        long_row = _pick_strike_by_delta(ch.calls, spot, T, 'call', long_delta)
        if long_row is None or short_row is None or long_row['strike'] <= short_row['strike']:
            return None
        legs = [_leg_from_row(short_row, 'call', 'SELL', exp, spot),
                _leg_from_row(long_row, 'call', 'BUY', exp, spot)]
    else:
        return None

    ts = TradeStructure(
        ticker=ticker, sector=sector, spot=spot, strategy=kind,
        regime=regime.regime, bias=bias_info['bias'], bias_src=bias_info['src'],
        legs=legs,
    )
    _summarize_structure(ts)
    return ts


# Delta combos to try per vertical kind: (long_delta, short_delta)
# Goal: scan a grid to find a +EV combination at the current chain pricing.
VERTICAL_DELTA_GRID = {
    'BULL_CALL_DEBIT_SPREAD': [(0.65, 0.35), (0.55, 0.30), (0.50, 0.25), (0.60, 0.20)],
    'BEAR_PUT_DEBIT_SPREAD':  [(0.65, 0.35), (0.55, 0.30), (0.50, 0.25), (0.60, 0.20)],
    # For credit spreads: (wing_long_delta, short_delta) — wing is OTM beyond short
    'BULL_PUT_SPREAD':        [(0.20, 0.35), (0.15, 0.30), (0.10, 0.25), (0.10, 0.20), (0.08, 0.16)],
    'BEAR_CALL_SPREAD':       [(0.20, 0.35), (0.15, 0.30), (0.10, 0.25), (0.10, 0.20), (0.08, 0.16)],
}


def build_vertical(ticker: str, spot: float, sector: str,
                   regime: IVRegime, bias_info: dict, kind: str,
                   target_dte: int = 30) -> Optional[TradeStructure]:
    """
    Scans (a) several DTE candidates and (b) several delta combinations,
    and returns the variant with the best edge_score among +EV candidates.
    Falls back to the best (least-bad) -EV candidate ONLY if no +EV exists,
    but only above a minimum prob_profit floor (lets the caller's gate reject it).
    """
    expiries = list(get_expiries(ticker))
    # Try the target DTE first, then ±1 nearby expiries
    candidate_exps = []
    today = datetime.now().date()
    for tgt in (target_dte, target_dte - 7, target_dte + 7, target_dte - 14, target_dte + 14):
        e = _pick_target_dte(expiries, tgt, SWING_DTE_RANGE)
        if e and e not in candidate_exps:
            candidate_exps.append(e)
    if not candidate_exps:
        return None

    grid = VERTICAL_DELTA_GRID.get(kind, [(0.50, 0.30)])
    best_pos = None       # best +EV
    best_neg = None       # best -EV fallback (for diagnostics)

    for exp in candidate_exps:
        ch = _safe_chain(ticker, exp)
        if not ch:
            continue
        T = max((datetime.strptime(exp, '%Y-%m-%d').date() - today).days, 1) / 365.0
        for (ld, sd) in grid:
            ts = _build_vertical_one(ticker, spot, sector, regime, bias_info,
                                     kind, exp, T, ch, ld, sd)
            if ts is None:
                continue
            # Quick score to rank candidates
            edge, _ = score_trade(ts, regime, bias_info)
            ts.edge_score = edge
            key = (ts.expectancy_per_contract, edge)
            if ts.expectancy_per_contract > 0:
                if best_pos is None or key > (best_pos.expectancy_per_contract, best_pos.edge_score):
                    best_pos = ts
            else:
                if best_neg is None or edge > best_neg.edge_score:
                    best_neg = ts

    return best_pos or best_neg


def _build_iron_condor_one(ticker, spot, sector, regime, bias_info,
                            exp, T, ch, short_delta, wing_delta) -> Optional[TradeStructure]:
    sp = _pick_strike_by_delta(ch.puts, spot, T, 'put', short_delta)
    lp = _pick_strike_by_delta(ch.puts, spot, T, 'put', wing_delta)
    sc = _pick_strike_by_delta(ch.calls, spot, T, 'call', short_delta)
    lc = _pick_strike_by_delta(ch.calls, spot, T, 'call', wing_delta)
    if any(r is None for r in (sp, lp, sc, lc)):
        return None
    if not (lp['strike'] < sp['strike'] < sc['strike'] < lc['strike']):
        return None
    legs = [_leg_from_row(sp, 'put', 'SELL', exp, spot),
            _leg_from_row(lp, 'put', 'BUY', exp, spot),
            _leg_from_row(sc, 'call', 'SELL', exp, spot),
            _leg_from_row(lc, 'call', 'BUY', exp, spot)]
    ts = TradeStructure(ticker=ticker, sector=sector, spot=spot,
                        strategy='IRON_CONDOR', regime=regime.regime,
                        bias=bias_info['bias'], bias_src=bias_info['src'], legs=legs)
    _summarize_structure(ts)
    return ts


IC_DELTA_GRID = [(0.20, 0.10), (0.16, 0.08), (0.25, 0.12), (0.30, 0.15), (0.16, 0.05)]


def build_iron_condor(ticker: str, spot: float, sector: str,
                      regime: IVRegime, bias_info: dict,
                      target_dte: int = 35) -> Optional[TradeStructure]:
    expiries = list(get_expiries(ticker))
    today = datetime.now().date()
    candidate_exps = []
    for tgt in (target_dte, target_dte - 7, target_dte + 7, target_dte - 14):
        e = _pick_target_dte(expiries, tgt, (21, 60))
        if e and e not in candidate_exps:
            candidate_exps.append(e)
    if not candidate_exps:
        return None

    best_pos = None
    best_neg = None
    for exp in candidate_exps:
        ch = _safe_chain(ticker, exp)
        if not ch:
            continue
        T = max((datetime.strptime(exp, '%Y-%m-%d').date() - today).days, 1) / 365.0
        for (sd, wd) in IC_DELTA_GRID:
            ts = _build_iron_condor_one(ticker, spot, sector, regime, bias_info,
                                         exp, T, ch, sd, wd)
            if ts is None: continue
            edge, _ = score_trade(ts, regime, bias_info)
            ts.edge_score = edge
            if ts.expectancy_per_contract > 0:
                if best_pos is None or (ts.expectancy_per_contract, edge) > \
                        (best_pos.expectancy_per_contract, best_pos.edge_score):
                    best_pos = ts
            else:
                if best_neg is None or edge > best_neg.edge_score:
                    best_neg = ts
    return best_pos or best_neg


IFLY_WING_GRID = [0.35, 0.30, 0.25, 0.20, 0.15, 0.10]


def build_iron_butterfly(ticker: str, spot: float, sector: str,
                         regime: IVRegime, bias_info: dict,
                         target_dte: int = 30) -> Optional[TradeStructure]:
    expiries = list(get_expiries(ticker))
    today = datetime.now().date()
    candidate_exps = []
    for tgt in (target_dte, target_dte - 7, target_dte + 7):
        e = _pick_target_dte(expiries, tgt, (14, 45))
        if e and e not in candidate_exps:
            candidate_exps.append(e)
    if not candidate_exps:
        return None

    best_pos = None
    best_neg = None
    for exp in candidate_exps:
        ch = _safe_chain(ticker, exp)
        if not ch:
            continue
        T = max((datetime.strptime(exp, '%Y-%m-%d').date() - today).days, 1) / 365.0
        atm_put = _pick_strike_by_delta(ch.puts, spot, T, 'put', 0.50)
        atm_call = _pick_strike_by_delta(ch.calls, spot, T, 'call', 0.50)
        if atm_put is None or atm_call is None:
            continue
        for wd in IFLY_WING_GRID:
            wing_put = _pick_strike_by_delta(ch.puts, spot, T, 'put', wd)
            wing_call = _pick_strike_by_delta(ch.calls, spot, T, 'call', wd)
            if wing_put is None or wing_call is None:
                continue
            legs = [_leg_from_row(atm_put, 'put', 'SELL', exp, spot),
                    _leg_from_row(wing_put, 'put', 'BUY', exp, spot),
                    _leg_from_row(atm_call, 'call', 'SELL', exp, spot),
                    _leg_from_row(wing_call, 'call', 'BUY', exp, spot)]
            ts = TradeStructure(
                ticker=ticker, sector=sector, spot=spot, strategy='IRON_BUTTERFLY',
                regime=regime.regime, bias=bias_info['bias'], bias_src=bias_info['src'],
                legs=legs,
            )
            _summarize_structure(ts)
            edge, _ = score_trade(ts, regime, bias_info)
            ts.edge_score = edge
            if ts.expectancy_per_contract > 0:
                if best_pos is None or (ts.expectancy_per_contract, edge) > \
                        (best_pos.expectancy_per_contract, best_pos.edge_score):
                    best_pos = ts
            else:
                if best_neg is None or edge > best_neg.edge_score:
                    best_neg = ts
    return best_pos or best_neg


def build_long_straddle(ticker: str, spot: float, sector: str,
                        regime: IVRegime, bias_info: dict,
                        target_dte: int = 21) -> Optional[TradeStructure]:
    expiries = list(get_expiries(ticker))
    exp = _pick_target_dte(expiries, target_dte, EVENT_DTE_RANGE)
    if not exp:
        return None
    ch = _safe_chain(ticker, exp)
    if not ch:
        return None
    today = datetime.now().date()
    T = max((datetime.strptime(exp, '%Y-%m-%d').date() - today).days, 1) / 365.0
    atm_call = _pick_strike_by_delta(ch.calls, spot, T, 'call', 0.50)
    atm_put = _pick_strike_by_delta(ch.puts, spot, T, 'put', 0.50)
    if atm_call is None or atm_put is None:
        return None
    legs = [_leg_from_row(atm_call, 'call', 'BUY', exp, spot),
            _leg_from_row(atm_put, 'put', 'BUY', exp, spot)]
    ts = TradeStructure(
        ticker=ticker, sector=sector, spot=spot, strategy='LONG_STRADDLE',
        regime=regime.regime, bias=bias_info['bias'], bias_src=bias_info['src'],
        legs=legs,
    )
    _summarize_structure(ts)
    return ts


STRATEGY_BUILDERS = {
    'LONG_CALL':              lambda t, s, sec, r, b: build_long_single(t, s, sec, r, b, 'call'),
    'LONG_PUT':               lambda t, s, sec, r, b: build_long_single(t, s, sec, r, b, 'put'),
    'BULL_CALL_DEBIT_SPREAD': lambda t, s, sec, r, b: build_vertical(t, s, sec, r, b, 'BULL_CALL_DEBIT_SPREAD'),
    'BEAR_PUT_DEBIT_SPREAD':  lambda t, s, sec, r, b: build_vertical(t, s, sec, r, b, 'BEAR_PUT_DEBIT_SPREAD'),
    'BULL_PUT_SPREAD':        lambda t, s, sec, r, b: build_vertical(t, s, sec, r, b, 'BULL_PUT_SPREAD'),
    'BEAR_CALL_SPREAD':       lambda t, s, sec, r, b: build_vertical(t, s, sec, r, b, 'BEAR_CALL_SPREAD'),
    'IRON_CONDOR':            build_iron_condor,
    'IRON_BUTTERFLY':         build_iron_butterfly,
    'LONG_STRADDLE':          build_long_straddle,
}


# ╔════════════════════════════════════════════════════════════════════╗
# ║  EDGE SCORE — 0-100 quality score combining all signals            ║
# ╚════════════════════════════════════════════════════════════════════╝

def score_trade(ts: TradeStructure, regime: IVRegime,
                bias_info: dict) -> tuple[float, list[str]]:
    """
    Edge score: 0-100. Combines:
      - Setup quality (regime + strategy fit)            25 pts
      - Directional conviction                           15 pts
      - IV edge (IVR + IV/HV)                            15 pts
      - Probability of profit                            15 pts
      - Risk/reward                                      15 pts
      - Liquidity (OI, vol, spread)                      15 pts
    """
    score = 0.0
    notes: list[str] = []

    # 1) Regime/strategy fit (25 pts)
    expected_strat = STRATEGY_MATRIX.get((bias_info['bias'], regime.regime))
    if ts.strategy == expected_strat:
        score += 25
        notes.append(f"strategy fits {bias_info['bias']}×{regime.regime}")
    else:
        score += 10

    # 2) Conviction (15 pts)
    score += 15 * float(bias_info.get('conviction', 0.5))
    notes.append(f"conviction {bias_info.get('conviction', 0.5):.2f} from {bias_info['src']}")

    # 3) IV edge (15 pts)
    iv_edge = 0
    if ts.debit_credit == 'CREDIT':
        # Want HIGH IV (premium rich) when selling
        if regime.iv_hv_ratio >= 1.25: iv_edge += 8
        elif regime.iv_hv_ratio >= 1.10: iv_edge += 4
        if regime.ivr >= 60: iv_edge += 7
        elif regime.ivr >= 40: iv_edge += 3
    else:
        # Want LOW IV (cheap premium) when buying
        if regime.iv_hv_ratio <= 0.90: iv_edge += 8
        elif regime.iv_hv_ratio <= 1.10: iv_edge += 4
        if regime.ivr <= 30: iv_edge += 7
        elif regime.ivr <= 50: iv_edge += 3
    score += iv_edge
    notes.append(f"iv_edge {iv_edge}/15")

    # 4) P(profit) (15 pts)
    pp = min(max(ts.prob_profit, 0), 1)
    score += 15 * pp
    notes.append(f"P(profit) {pp:.0%}")

    # 5) R:R (15 pts) — scale up to R:R >= 2.0
    rr_pts = min(ts.rr_ratio / 2.0, 1.0) * 15 if math.isfinite(ts.rr_ratio) else 15
    score += rr_pts

    # 6) Liquidity (15 pts)
    liq_pts = 0
    if ts.liquidity_ok: liq_pts += 7
    if ts.spread_pct <= 0.05: liq_pts += 5
    elif ts.spread_pct <= 0.10: liq_pts += 3
    elif ts.spread_pct <= 0.15: liq_pts += 1
    avg_oi = np.mean([L.oi for L in ts.legs]) if ts.legs else 0
    if avg_oi >= 500: liq_pts += 3
    elif avg_oi >= 200: liq_pts += 1
    score += liq_pts
    notes.append(f"liq spread {ts.spread_pct:.1%} avg_oi {avg_oi:.0f}")

    # Penalties
    if ts.expectancy_per_contract < 0:
        score -= 15
        notes.append("WARN: negative expectancy")
    if pp < MIN_PROB_PROFIT:
        score -= 10
        notes.append(f"WARN: P(profit) < {MIN_PROB_PROFIT:.0%}")

    return max(0, min(100, score)), notes


# ╔════════════════════════════════════════════════════════════════════╗
# ║  STAGE 6: SIZER — Kelly-fractional with DD throttle + caps         ║
# ╚════════════════════════════════════════════════════════════════════╝

def kelly_fraction(p_win: float, win: float, loss: float) -> float:
    """Kelly criterion for binary outcomes. Returns f* (0-1)."""
    if loss <= 0 or win <= 0 or p_win <= 0 or p_win >= 1:
        return 0.0
    b = win / loss
    f = (p_win * b - (1 - p_win)) / b
    return max(0.0, min(f, 1.0))


def dd_throttle(current_dd: float) -> float:
    if current_dd >= DD_TIER_3:
        return 0.0
    if current_dd >= DD_TIER_2:
        return 0.25
    if current_dd >= DD_TIER_1:
        return 0.5
    return 1.0


def size_position(ts: TradeStructure, capital: float, current_dd: float = 0.0) -> dict:
    """Returns: contracts, dollar_risk, dollar_capital, sizing_notes."""
    notes: list[str] = []
    if not math.isfinite(ts.max_profit):
        win = ts.max_loss * 3  # planning assumption for unbounded long premium
    else:
        win = ts.max_profit
    loss = max(ts.max_loss, 1.0)
    k = kelly_fraction(ts.prob_profit, win, loss)
    k_used = k * KELLY_FRACTION_BASE
    throttle = dd_throttle(current_dd)
    k_used *= throttle
    if k_used < KELLY_FLOOR * KELLY_FRACTION_BASE and current_dd > 0:
        k_used = max(k_used, KELLY_FLOOR * KELLY_FRACTION_BASE * throttle)

    notes.append(f"kelly_full {k:.2%} → half-kelly × DD-throttle({throttle:.2f}) = {k_used:.2%}")

    target_risk_dollars = capital * k_used
    cap_risk_dollars = capital * MAX_RISK_PER_TRADE_PCT
    risk_dollars = min(target_risk_dollars, cap_risk_dollars)
    if risk_dollars == cap_risk_dollars:
        notes.append(f"capped by MAX_RISK_PER_TRADE_PCT ({MAX_RISK_PER_TRADE_PCT:.0%})")

    contracts = max(int(risk_dollars // loss), 0)
    # Sanity cap regardless of Kelly math (prevents "$1 risk → 1000 contracts" data anomalies)
    if contracts > MAX_CONTRACTS_PER_TRADE:
        contracts = MAX_CONTRACTS_PER_TRADE
        notes.append(f"capped at MAX_CONTRACTS_PER_TRADE={MAX_CONTRACTS_PER_TRADE}")
    if contracts == 0:
        notes.append("size = 0 (defined risk per contract > per-trade cap)")
    actual_risk = contracts * loss

    return {
        'contracts': contracts,
        'dollar_risk': round(actual_risk, 2),
        'dollar_capital_required': round(contracts * (abs(ts.net_premium) * 100), 2)
            if ts.debit_credit == 'DEBIT' else round(actual_risk, 2),
        'kelly_full_pct': round(k * 100, 2),
        'kelly_used_pct': round(k_used * 100, 2),
        'dd_throttle': throttle,
        'notes': notes,
    }


# ╔════════════════════════════════════════════════════════════════════╗
# ║  PORTFOLIO GREEK AGGREGATOR — checks budget across open positions  ║
# ╚════════════════════════════════════════════════════════════════════╝

def aggregate_portfolio_greeks(trades: list[tuple[TradeStructure, int]],
                                capital: float) -> dict:
    """trades: list of (structure, contracts_to_open). Returns budget check."""
    total_delta = 0.0
    total_gamma = 0.0
    total_theta = 0.0
    total_vega = 0.0
    beta_weighted_delta = 0.0
    sector_risk: dict[str, float] = {}
    ticker_risk: dict[str, float] = {}
    total_risk = 0.0

    for ts, n in trades:
        if n <= 0:
            continue
        beta = BETA_HINTS.get(ts.ticker, 1.0)
        # Greeks scale per share (100 shares per contract)
        total_delta += ts.net_delta * n * 100
        total_gamma += ts.net_gamma * n * 100
        total_theta += ts.net_theta * n * 100
        total_vega += ts.net_vega * n * 100
        beta_weighted_delta += ts.net_delta * n * 100 * beta * ts.spot
        risk = ts.max_loss * n
        total_risk += risk
        sector_risk[ts.sector] = sector_risk.get(ts.sector, 0) + risk
        ticker_risk[ts.ticker] = ticker_risk.get(ts.ticker, 0) + risk

    warnings_list = []
    # Delta budget (in $ exposure)
    delta_dollar_exposure = total_delta * 1.0  # already share-weighted; per $1 move per share
    # Convert to % of capital using SPY beta-weighted
    delta_pct = abs(beta_weighted_delta) / capital if capital > 0 else 0
    if delta_pct > MAX_NET_DELTA_PCT:
        warnings_list.append(f"DELTA BUDGET: beta-weighted |Δ| ${abs(beta_weighted_delta):,.0f} = {delta_pct:.1%} of capital > {MAX_NET_DELTA_PCT:.0%}")
    # Vega budget
    vega_pct = abs(total_vega) / capital if capital > 0 else 0
    if vega_pct > MAX_VEGA_PER_1PCT_IV:
        warnings_list.append(f"VEGA BUDGET: |vega| ${abs(total_vega):,.0f} = {vega_pct:.2%} of capital per 1% IV > {MAX_VEGA_PER_1PCT_IV:.2%}")
    # Theta (only penalize negative theta — short premium decay against you)
    if total_theta < 0:
        theta_pct = abs(total_theta) / capital if capital > 0 else 0
        if theta_pct > MAX_NEG_THETA_PER_DAY:
            warnings_list.append(f"THETA BUDGET: net |θ| ${abs(total_theta):,.0f}/day = {theta_pct:.2%} > {MAX_NEG_THETA_PER_DAY:.2%}")
    # Total risk
    risk_pct = total_risk / capital if capital > 0 else 0
    if risk_pct > MAX_PORTFOLIO_RISK_PCT:
        warnings_list.append(f"PORTFOLIO RISK: ${total_risk:,.0f} = {risk_pct:.1%} > {MAX_PORTFOLIO_RISK_PCT:.0%}")
    # Sector concentration
    for sec, r in sector_risk.items():
        if r / capital > MAX_SECTOR_RISK_PCT:
            warnings_list.append(f"SECTOR {sec}: {r/capital:.1%} > {MAX_SECTOR_RISK_PCT:.0%}")
    for t, r in ticker_risk.items():
        if r / capital > MAX_RISK_PER_TICKER_PCT:
            warnings_list.append(f"TICKER {t}: {r/capital:.1%} > {MAX_RISK_PER_TICKER_PCT:.0%}")

    return {
        'net_delta_shares': round(total_delta, 1),
        'beta_weighted_delta_$': round(beta_weighted_delta, 0),
        'net_gamma': round(total_gamma, 3),
        'net_theta_$_per_day': round(total_theta, 1),
        'net_vega_$_per_1pct': round(total_vega, 1),
        'total_risk_$': round(total_risk, 0),
        'total_risk_pct': round(risk_pct, 4),
        'sector_risk': {k: round(v, 0) for k, v in sector_risk.items()},
        'warnings': warnings_list,
        'budget_clean': len(warnings_list) == 0,
    }


# ╔════════════════════════════════════════════════════════════════════╗
# ║  MAIN PIPELINE — per-ticker scan → ranked candidates                ║
# ╚════════════════════════════════════════════════════════════════════╝

def scan_ticker(ticker: str, bias_map: dict, capital: float, current_dd: float) -> dict | None:
    """Run full pipeline for one ticker. Returns dict or None on data failure."""
    try:
        regime = fetch_iv_regime(ticker)
        if regime is None:
            return None

        bias_info = bias_map.get(ticker)
        if bias_info is None:
            bias_info = live_trend_bias(ticker)

        strat = STRATEGY_MATRIX.get((bias_info['bias'], regime.regime))
        if strat is None:
            return None

        builder = STRATEGY_BUILDERS[strat]
        ts = builder(ticker, regime.spot, TICKER_TO_SECTOR.get(ticker, 'Other'),
                     regime, bias_info)
        if ts is None:
            return None

        # Score
        edge, notes = score_trade(ts, regime, bias_info)
        ts.edge_score = edge
        ts.notes = notes

        # Size
        size = size_position(ts, capital, current_dd)

        return {
            'ticker': ticker,
            'sector': ts.sector,
            'strategy': ts.strategy,
            'regime_label': regime.label,
            'bias': bias_info['bias'],
            'bias_src': bias_info['src'],
            'edge_score': ts.edge_score,
            'prob_profit': ts.prob_profit,
            'rr_ratio': ts.rr_ratio if math.isfinite(ts.rr_ratio) else 999,
            'debit_credit': ts.debit_credit,
            'max_profit_$': round(ts.max_profit, 2) if math.isfinite(ts.max_profit) else 'unbounded',
            'max_loss_$': round(ts.max_loss, 2),
            'breakevens': ts.breakevens,
            'expectancy_per_contract_$': round(ts.expectancy_per_contract, 2),
            'net_delta': round(ts.net_delta, 3),
            'net_gamma': round(ts.net_gamma, 4),
            'net_theta_$_day': round(ts.net_theta * 100, 2),
            'net_vega_$_1pct': round(ts.net_vega * 100, 2),
            'spread_pct': round(ts.spread_pct, 3),
            'liquidity_ok': ts.liquidity_ok,
            'legs': [asdict(L) for L in ts.legs],
            'sizing': size,
            'notes': notes,
            'structure': ts,  # for in-process portfolio aggregation
        }
    except Exception as e:
        return {'ticker': ticker, 'error': str(e)}


def run_scan(tickers: list[str], capital: float, current_dd: float,
             max_workers: int = MAX_WORKERS) -> list[dict]:
    bias_map = load_directional_bias()
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(scan_ticker, t, bias_map, capital, current_dd): t for t in tickers}
        for fut in as_completed(futs):
            r = fut.result()
            if r and 'error' not in r:
                results.append(r)
    # Filter + rank
    # Primary gates: edge quality + positive expectancy + actually sizeable + realistic risk
    # NOTE: we use +EV (not P-win) as the floor because high-R:R structures
    # (long premium, iron butterflies) can be +EV at P(win) < 50%.
    playable = [r for r in results
                if r['edge_score'] >= MIN_EDGE_SCORE
                and r['prob_profit'] >= MIN_PROB_PROFIT
                and r['expectancy_per_contract_$'] > MIN_EXPECTANCY
                and r['sizing']['contracts'] > 0
                and r['max_loss_$'] >= MIN_MAX_LOSS_DOLLARS]      # reject data-anomaly trades
    # Rank by composite: expectancy × edge_score / 100  (rewards both quality AND EV)
    playable.sort(key=lambda r: r['expectancy_per_contract_$'] * (r['edge_score'] / 100),
                  reverse=True)
    return playable


# ╔════════════════════════════════════════════════════════════════════╗
# ║  REPORTING — markdown + JSON + stdout summary                       ║
# ╚════════════════════════════════════════════════════════════════════╝

def fmt_leg(L: dict) -> str:
    sgn = '+' if L['action'] == 'BUY' else '-'
    return (f"{sgn}1 {L['side'].upper()} {L['strike']:.1f} {L['expiry']} "
            f"({L['dte']}D) @ ${L['mid']:.2f} | IV {L['iv']*100:.0f}% | "
            f"Δ{L['delta']:+.2f}")


def render_report(playable: list[dict], capital: float, current_dd: float) -> str:
    today = datetime.now().strftime('%Y-%m-%d %H:%M')
    out: list[str] = []
    out.append(f"# PROP TRADER OPTIONS MODEL — {today}")
    out.append("")
    out.append(f"**Capital**: ${capital:,.0f}  |  **Current DD**: {current_dd:.1%}  |  "
               f"**DD throttle**: ×{dd_throttle(current_dd):.2f}  |  "
               f"**Candidates**: {len(playable)}")
    out.append("")
    out.append("## Top 10 Playable Trades")
    out.append("")
    out.append("| # | Ticker | Sec | Strategy | Bias×Regime | Edge | P(W) | R:R | "
               "Risk $ | Reward $ | E[V] $ | Contracts | Total Risk $ |")
    out.append("|---|--------|-----|----------|-------------|------|------|-----|"
               "--------|----------|--------|-----------|--------------|")
    for i, r in enumerate(playable[:10], 1):
        mp = r['max_profit_$']
        mp_s = f"{mp:.0f}" if isinstance(mp, (int, float)) else str(mp)
        rr_s = f"{r['rr_ratio']:.2f}" if r['rr_ratio'] < 100 else "open"
        out.append(f"| {i} | {r['ticker']} | {r['sector'][:6]} | {r['strategy']} | "
                   f"{r['bias']}×{r['regime_label'].split('|')[0].strip()} | "
                   f"{r['edge_score']:.0f} | {r['prob_profit']:.0%} | {rr_s} | "
                   f"{r['max_loss_$']:.0f} | {mp_s} | "
                   f"{r['expectancy_per_contract_$']:+.0f} | "
                   f"{r['sizing']['contracts']} | "
                   f"{r['sizing']['dollar_risk']:.0f} |")
    out.append("")
    out.append("## Detail per Trade")
    for i, r in enumerate(playable[:10], 1):
        out.append(f"\n### #{i} {r['ticker']} — {r['strategy']}  (Edge {r['edge_score']:.0f}/100)")
        out.append(f"- **Regime**: {r['regime_label']}")
        out.append(f"- **Direction**: {r['bias']} (src: {r['bias_src']})")
        out.append(f"- **Net premium**: {r['debit_credit']} ${abs(r['legs'][0]['mid']):.2f} (per share, summed)")
        rr_disp = f"{r['rr_ratio']:.2f}" if r['rr_ratio'] < 100 else "OPEN"
        out.append(f"- **Max profit**: {r['max_profit_$']}  |  **Max loss**: ${r['max_loss_$']:.2f}/contract  |  **R:R**: {rr_disp}")
        out.append(f"- **P(profit)**: {r['prob_profit']:.0%}  |  **Expectancy/contract**: ${r['expectancy_per_contract_$']:+.2f}")
        out.append(f"- **Breakevens**: {r['breakevens']}")
        out.append(f"- **Greeks/contract**: Δ {r['net_delta']:+.3f}  Γ {r['net_gamma']:+.4f}  "
                   f"θ ${r['net_theta_$_day']:+.2f}/day  ν ${r['net_vega_$_1pct']:+.2f}/1%IV")
        out.append(f"- **Liquidity**: avg spread {r['spread_pct']:.1%}  |  ok? {r['liquidity_ok']}")
        out.append(f"- **Sizing**: {r['sizing']['contracts']} contracts → "
                   f"risk ${r['sizing']['dollar_risk']:.0f} | "
                   f"capital req ${r['sizing']['dollar_capital_required']:.0f} | "
                   f"kelly used {r['sizing']['kelly_used_pct']:.2f}%")
        out.append(f"- **Legs**:")
        for L in r['legs']:
            out.append(f"  - {fmt_leg(L)}")
        out.append(f"- **Notes**: " + "; ".join(r['notes']))

    # Portfolio Greek check assuming we open the top 5 at sized contracts
    top5 = [(r['structure'], r['sizing']['contracts']) for r in playable[:5]]
    portfolio = aggregate_portfolio_greeks(top5, capital)
    out.append("")
    out.append("## Portfolio Greek Budget — IF top 5 are all opened at sized size")
    out.append("")
    out.append(f"- Net Δ (shares-equiv): **{portfolio['net_delta_shares']:.0f}**")
    out.append(f"- Beta-weighted Δ ($): **${portfolio['beta_weighted_delta_$']:,.0f}**")
    out.append(f"- Net Γ: **{portfolio['net_gamma']:.3f}**")
    out.append(f"- Net θ ($/day): **${portfolio['net_theta_$_per_day']:+,.0f}**")
    out.append(f"- Net ν ($/1%IV): **${portfolio['net_vega_$_per_1pct']:+,.0f}**")
    out.append(f"- Total risk: **${portfolio['total_risk_$']:,.0f}** ({portfolio['total_risk_pct']:.1%} of capital)")
    out.append(f"- Sector risk: {portfolio['sector_risk']}")
    if portfolio['warnings']:
        out.append(f"- **⚠ WARNINGS**:")
        for w in portfolio['warnings']:
            out.append(f"  - {w}")
    else:
        out.append(f"- **✓ Budget clean** — all checks pass.")

    return "\n".join(out)


# ╔════════════════════════════════════════════════════════════════════╗
# ║  CLI                                                                ║
# ╚════════════════════════════════════════════════════════════════════╝

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--tickers', type=str, default=None,
                   help='comma-separated; default = full AI portfolio')
    p.add_argument('--capital', type=float, default=50_000,
                   help='account size in $; default 50k (prop tier 1)')
    p.add_argument('--dd', type=float, default=0.0,
                   help='current drawdown 0-1; auto-throttles sizing')
    p.add_argument('--regime-only', action='store_true',
                   help='print IV regime per ticker and exit')
    p.add_argument('--workers', type=int, default=MAX_WORKERS)
    p.add_argument('--out-dir', type=str, default=str(ROOT))
    args = p.parse_args()

    tickers = ([t.strip().upper() for t in args.tickers.split(',') if t.strip()]
               if args.tickers else ALL_TICKERS)

    if args.regime_only:
        print(f"IV regime scan — {len(tickers)} tickers")
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(fetch_iv_regime, t): t for t in tickers}
            for fut in as_completed(futs):
                r = fut.result()
                if r is None:
                    continue
                print(f"  {r.ticker:6s}  ${r.spot:8.2f}  {r.label}")
        return

    print(f"Running prop options model on {len(tickers)} tickers...")
    print(f"  capital=${args.capital:,.0f}  DD={args.dd:.1%}  throttle=×{dd_throttle(args.dd):.2f}")
    playable = run_scan(tickers, args.capital, args.dd, args.workers)

    report = render_report(playable, args.capital, args.dd)
    ts = datetime.now().strftime('%Y-%m-%d_%H%M')
    md_path = Path(args.out_dir) / f"prop_model_{ts}.md"
    md_path.write_text(report, encoding='utf-8')

    # JSON for downstream consumers (journal, automation)
    json_path = Path(args.out_dir) / "_prop_candidates.json"
    json_records = []
    for r in playable:
        rr = {k: v for k, v in r.items() if k != 'structure'}
        json_records.append(rr)
    json_path.write_text(json.dumps(json_records, indent=2, default=str), encoding='utf-8')

    print(f"\nWrote {md_path.name}  ({len(playable)} playable candidates)")
    print(f"Wrote {json_path.name}")

    print(f"\nTop 5:")
    for i, r in enumerate(playable[:5], 1):
        mp = r['max_profit_$']
        mp_s = f"${mp:.0f}" if isinstance(mp, (int, float)) else str(mp)
        print(f"  #{i} {r['ticker']:5s} {r['strategy']:26s} "
              f"edge {r['edge_score']:5.1f}  P(W) {r['prob_profit']:.0%}  "
              f"risk ${r['max_loss_$']:.0f}  rew {mp_s}  "
              f"size {r['sizing']['contracts']}c → ${r['sizing']['dollar_risk']:.0f}")


if __name__ == '__main__':
    main()
