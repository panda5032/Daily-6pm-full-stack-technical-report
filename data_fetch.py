"""
DATA_FETCH — Bulletproof market data layer
============================================
Single point of access for ALL market data in this codebase.

WHY THIS EXISTS
  yfinance 1.2.2 on this Windows install fails silently because the system
  trust store contains an EXPIRED root cert (DST Root CA X3, expired 2021).
  Result: yf.Ticker(t).history() returns 0 rows and prints "possibly delisted"
  for every ticker. This module fixes that by:
    1. Using curl_cffi.requests.Session(impersonate='chrome', verify=False)
    2. Module-level singleton session reused across all calls
    3. Retry with exponential backoff for transient failures
    4. On-disk pickle cache (configurable TTL) to dodge rate limits
    5. Fallback to direct Yahoo HTTP for history when yfinance flakes

WHAT IT EXPOSES
  get_session()                       singleton curl_cffi session
  get_history(ticker, period, interval)
                                      → pd.DataFrame indexed by date
  get_spot(ticker)                    → float (latest close)
  get_expiries(ticker)                → tuple[str, ...]  YYYY-MM-DD
  get_option_chain(ticker, expiry)    → (calls_df, puts_df)
  get_fast_info(ticker)               → dict (fast_info)
  get_history_bulk(tickers, period)   → {ticker: df}  (parallel)
  invalidate_cache()                  → clear cache

USAGE
  from data_fetch import get_history, get_option_chain, get_expiries
  hist = get_history('SPY', period='1y')
  exps = get_expiries('NVDA')
  calls, puts = get_option_chain('NVDA', exps[0])

DROP-IN REPLACEMENT
  Any module that currently does:
      tk = yf.Ticker(ticker)
      h = tk.history(...)
  should switch to:
      from data_fetch import get_history
      h = get_history(ticker, ...)
  And keep yf.Ticker(ticker, session=get_session()) when stuck with the
  yfinance object pattern.

DISCLAIMER
  verify=False is acceptable for read-only public market data from Yahoo
  but NEVER for endpoints involving auth or POST. Don't reuse this session
  for anything except yfinance / public market data.
"""
from __future__ import annotations

import io
import pickle
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Optional

import pandas as pd

warnings.filterwarnings('ignore')
# Idempotent UTF-8 wrap (avoids closing an existing wrapper if another module
# in the same process already did this).
try:
    if (getattr(sys.stdout, 'encoding', '') or '').lower() != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
except Exception:
    pass

ROOT = Path(__file__).parent
CACHE_DIR = ROOT / '_data_cache'
CACHE_DIR.mkdir(exist_ok=True)

# ── Session singleton ────────────────────────────────────────────────
_SESSION = None
_SESSION_LOCK = Lock()


def get_session():
    """Return module-level curl_cffi Session — initialised lazily, thread-safe."""
    global _SESSION
    if _SESSION is None:
        with _SESSION_LOCK:
            if _SESSION is None:
                try:
                    from curl_cffi import requests as creq
                    # impersonate=chrome → full TLS fingerprint matches a real browser
                    # verify=False bypasses the broken system CA store
                    _SESSION = creq.Session(impersonate='chrome', verify=False)
                except ImportError as e:
                    raise RuntimeError(
                        "curl_cffi not installed. Run: pip install curl_cffi"
                    ) from e
    return _SESSION


# ── Cache helpers ────────────────────────────────────────────────────
# TTL strategy:
#   - history (daily bars):       60 min during market hours, 12h after-hours
#   - option chains:              5 min during market hours, 4h after-hours
#   - expiry list:                4 h
#   - fast_info / spot price:     2 min

def _is_market_hours() -> bool:
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    # 8:30 AM - 3:15 PM Central (catches pre-open + after-close buffers)
    t = now.time()
    return (t.hour > 8 or (t.hour == 8 and t.minute >= 30)) and (t.hour < 16)


def _cache_path(key: str) -> Path:
    safe = key.replace('/', '_').replace(':', '_')
    return CACHE_DIR / f"{safe}.pkl"


def _cache_get(key: str, ttl_seconds: int):
    p = _cache_path(key)
    if not p.exists():
        return None
    if time.time() - p.stat().st_mtime > ttl_seconds:
        return None
    try:
        return pickle.loads(p.read_bytes())
    except Exception:
        return None


def _cache_put(key: str, value):
    try:
        _cache_path(key).write_bytes(pickle.dumps(value))
    except Exception:
        pass


def invalidate_cache(prefix: str = ''):
    """Clear all cache (prefix='') or files matching a prefix."""
    n = 0
    for p in CACHE_DIR.glob(f"{prefix}*.pkl"):
        try:
            p.unlink()
            n += 1
        except Exception:
            pass
    return n


# ── Retry decorator ──────────────────────────────────────────────────
def _retry(fn, retries=3, base_delay=1.0):
    """Retry a callable with exponential backoff. Returns None on all-failed."""
    last_exc = None
    for i in range(retries):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            if i == retries - 1:
                break
            time.sleep(base_delay * (2 ** i))
    return None


# ── HISTORY ─────────────────────────────────────────────────────────
def get_history(ticker: str, period: str = '1y',
                interval: str = '1d', use_cache: bool = True) -> pd.DataFrame:
    """
    Robust OHLC history fetcher.

    period:   '5d' '1mo' '3mo' '6mo' '1y' '2y' '5y' 'max'
    interval: '1d' '1h' '5m' '1m'

    Returns DataFrame with columns Open, High, Low, Close, Volume.
    Returns empty DataFrame on total failure (caller should check .empty).
    """
    ttl = 3600 if _is_market_hours() else 12 * 3600
    cache_key = f"hist_{ticker}_{period}_{interval}"
    if use_cache:
        cached = _cache_get(cache_key, ttl)
        if cached is not None and not cached.empty:
            return cached

    # Try 1: yfinance with our SSL-fixed session
    def _yf():
        import yfinance as yf
        tk = yf.Ticker(ticker, session=get_session())
        df = tk.history(period=period, interval=interval, auto_adjust=False)
        if df is None or df.empty:
            raise RuntimeError("empty")
        return df

    df = _retry(_yf, retries=3, base_delay=1.0)
    if df is not None and not df.empty:
        _cache_put(cache_key, df)
        return df

    # Try 2: direct Yahoo chart API (bypasses yfinance's parsing)
    def _direct():
        ranges = {'5d': '5d', '1mo': '1mo', '3mo': '3mo', '6mo': '6mo',
                  '1y': '1y', '2y': '2y', '5y': '5y', 'max': 'max'}
        r = ranges.get(period, '1y')
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
               f"?range={r}&interval={interval}")
        resp = get_session().get(url, timeout=15)
        if resp.status_code != 200:
            raise RuntimeError(f"http {resp.status_code}")
        d = resp.json()
        res = d.get('chart', {}).get('result')
        if not res:
            raise RuntimeError("no chart result")
        r0 = res[0]
        ts = r0.get('timestamp', [])
        if not ts:
            raise RuntimeError("no timestamps")
        q = r0['indicators']['quote'][0]
        out = pd.DataFrame({
            'Open': q.get('open', []),
            'High': q.get('high', []),
            'Low': q.get('low', []),
            'Close': q.get('close', []),
            'Volume': q.get('volume', []),
        }, index=pd.to_datetime(ts, unit='s'))
        # Drop rows with NaN close (rare but happens on incomplete bars)
        out = out.dropna(subset=['Close'])
        if out.empty:
            raise RuntimeError("all-nan")
        return out

    df = _retry(_direct, retries=2, base_delay=1.0)
    if df is not None and not df.empty:
        _cache_put(cache_key, df)
        return df

    return pd.DataFrame()


def get_history_bulk(tickers: list[str], period: str = '1y',
                     interval: str = '1d', max_workers: int = 5,
                     use_cache: bool = True) -> dict[str, pd.DataFrame]:
    """Parallel history fetch. Returns {ticker: df}; missing tickers omitted."""
    out: dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(get_history, t, period, interval, use_cache): t for t in tickers}
        for fut in as_completed(futs):
            t = futs[fut]
            try:
                df = fut.result()
                if df is not None and not df.empty:
                    out[t] = df
            except Exception:
                pass
    return out


# ── SPOT ────────────────────────────────────────────────────────────
def get_spot(ticker: str) -> float:
    """Latest close. Returns 0.0 on failure."""
    cache_key = f"spot_{ticker}"
    cached = _cache_get(cache_key, ttl_seconds=120)
    if cached is not None:
        return cached
    h = get_history(ticker, period='5d', interval='1d')
    if h is None or h.empty:
        return 0.0
    spot = float(h['Close'].iloc[-1])
    _cache_put(cache_key, spot)
    return spot


# ── FAST INFO ───────────────────────────────────────────────────────
def get_fast_info(ticker: str) -> dict:
    """yfinance fast_info as a plain dict. Returns {} on failure."""
    cache_key = f"fastinfo_{ticker}"
    cached = _cache_get(cache_key, ttl_seconds=120)
    if cached is not None:
        return cached

    def _go():
        import yfinance as yf
        tk = yf.Ticker(ticker, session=get_session())
        fi = tk.fast_info
        out = {}
        for k in ('lastPrice', 'previousClose', 'open', 'dayHigh', 'dayLow',
                  'marketCap', 'shares', 'currency', 'exchange', 'fiftyDayAverage',
                  'twoHundredDayAverage'):
            try:
                v = getattr(fi, k, None)
                if v is not None:
                    out[k] = v
            except Exception:
                pass
        return out

    r = _retry(_go, retries=2)
    if r:
        _cache_put(cache_key, r)
        return r
    return {}


# ── OPTIONS ─────────────────────────────────────────────────────────
def get_expiries(ticker: str) -> tuple[str, ...]:
    """Available option expiration dates, sorted ascending. Empty tuple on failure."""
    ttl = 600 if _is_market_hours() else 4 * 3600
    cache_key = f"expiries_{ticker}"
    cached = _cache_get(cache_key, ttl_seconds=ttl)
    if cached is not None:
        return cached

    def _go():
        import yfinance as yf
        tk = yf.Ticker(ticker, session=get_session())
        exps = tk.options
        if not exps:
            raise RuntimeError("no expiries")
        return tuple(exps)

    r = _retry(_go, retries=3, base_delay=1.5)
    if r:
        _cache_put(cache_key, r)
        return r
    return tuple()


def get_option_chain(ticker: str, expiry: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns (calls_df, puts_df) for the given expiry.
    Both DataFrames have columns:
      strike, bid, ask, lastPrice, volume, openInterest, impliedVolatility
    Returns (empty, empty) on failure — caller must check.
    """
    ttl = 300 if _is_market_hours() else 4 * 3600
    cache_key = f"chain_{ticker}_{expiry}"
    cached = _cache_get(cache_key, ttl_seconds=ttl)
    if cached is not None:
        return cached

    def _go():
        import yfinance as yf
        tk = yf.Ticker(ticker, session=get_session())
        ch = tk.option_chain(expiry)
        if ch is None:
            raise RuntimeError("no chain")
        calls, puts = ch.calls, ch.puts
        if calls is None or puts is None or (calls.empty and puts.empty):
            raise RuntimeError("empty chain")
        return calls, puts

    r = _retry(_go, retries=3, base_delay=1.5)
    if r is not None:
        _cache_put(cache_key, r)
        return r
    return pd.DataFrame(), pd.DataFrame()


# ── Diagnostic CLI ──────────────────────────────────────────────────
if __name__ == '__main__':
    import sys
    tickers = sys.argv[1:] or ['SPY', 'NVDA', 'TSLA']
    print(f"data_fetch diagnostic — {len(tickers)} ticker(s)\n")
    print(f"  session: curl_cffi impersonate=chrome verify=False")
    print(f"  cache dir: {CACHE_DIR}")
    print(f"  market hours? {_is_market_hours()}\n")
    for t in tickers:
        print(f"── {t} ──")
        h = get_history(t, period='1mo')
        print(f"  history: {len(h)} rows, last close = {h['Close'].iloc[-1]:.2f}"
              if not h.empty else "  history: EMPTY")
        spot = get_spot(t)
        print(f"  spot   : ${spot:.2f}")
        exps = get_expiries(t)
        print(f"  expiries: {len(exps)} avail, first 3: {exps[:3]}")
        if exps:
            calls, puts = get_option_chain(t, exps[min(2, len(exps)-1)])
            print(f"  chain @ {exps[min(2, len(exps)-1)]}: {len(calls)} calls / {len(puts)} puts")
        print()
