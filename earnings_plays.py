"""
AI Portfolio Earnings Play Strategy
====================================
Scans all stocks in AI_Portfolios.xlsx for upcoming earnings within the next 3 weeks.
For each, evaluates:

  1. Historical Earnings Reaction — avg absolute move on past 4-8 earnings days
  2. Pre-Earnings Run-Up Potential — momentum + volume building into the event
  3. IV Proxy / Volatility Expansion — ATR expansion vs baseline as earnings approach
  4. Technical Positioning — trend alignment, RSI, support/resistance into the event
  5. Post-Earnings Drift — does the stock tend to continue its earnings-day direction?

Play Types:
  📈 Pre-Earnings Run-Up  — buy 5-10 days before, sell before announcement
  🎯 Earnings Hold (Bullish) — strong trend + historical positive reaction → hold through
  🎯 Earnings Hold (Bearish) — weak trend + historical negative reaction → short/put
  ⚡ Post-Earnings Drift — wait for reaction, trade the continuation 1-5 days after
  🚫 Earnings Avoid — high uncertainty, no edge, or poor risk/reward

Output: earnings_plays_YYYY-MM-DD.md
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date as date_type
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
import sys
import io
import time

warnings.filterwarnings('ignore')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

TICKER_MAP = {
    'Alphabet': 'GOOGL', 'Amazon': 'AMZN', 'Meta': 'META', 'Microsoft': 'MSFT', 'Apple': 'AAPL',
    'Tesla': 'TSLA', 'PONY': 'PONY', 'Uber': 'UBER', 'GRAB': 'GRAB',
    'SERV': 'SERV', 'PATH': 'PATH', 'Intuitive Surgical': 'ISRG',
    'Nvdia': 'NVDA', 'AMD': 'AMD', 'Broadcom': 'AVGO', 'Taiwan Semis': 'TSM', 'ARMs': 'ARM',
    'Marvel': 'MRVL', 'Micron': 'MU', 'Intel': 'INTC', 'SMCI': 'SMCI', 'ANET': 'ANET',
    'Dell': 'DELL', 'ASML': 'ASML', 'QCOM': 'QCOM',
    'Coreweave': 'CRWV', 'Oracle': 'ORCL', 'Iren': 'IREN', 'NBIS': 'NBIS', 'CIFR': 'CIFR',
    'APLD': 'APLD', 'CSCO': 'CSCO',
    'Okolo': 'OKLO', 'LAC': 'LAC', 'MP': 'MP', 'SMR': 'SMR', 'BE': 'BE',
    'ONDS': 'ONDS', 'QS': 'QS', 'EOSE': 'EOSE',
    'Palantir': 'PLTR', 'Snowflake': 'SNOW', 'C3 AI': 'AI', 'IBM': 'IBM', 'Mongodb': 'MDB',
    'ServiceNow': 'NOW', 'Salesforce': 'CRM', 'ADBE': 'ADBE', 'OKTA': 'OKTA', 'SHOP': 'SHOP',
    'Soundhound': 'SOUN', 'BBAI': 'BBAI', 'UPST': 'UPST', 'Duolingo': 'DUOL', 'Rubrik': 'RBRK',
    'DDOG': 'DDOG', 'Netflix': 'NFLX', 'ZETA': 'ZETA', 'Spotify': 'SPOT', 'Applovin': 'APP',
    'RDDT': 'RDDT', 'TTD': 'TTD', 'RBLX': 'RBLX', 'U': 'U', 'INFY': 'INFY',
    'ALAB': 'ALAB', 'CRDO': 'CRDO', 'Wolfspeed': 'WOLF', 'SNPS': 'SNPS',
    'Crowdstrike': 'CRWD', 'Palo Alto': 'PANW', 'Zscaler': 'ZS',
    'United Health': 'UNH', 'Oscar': 'OSCR', 'HIMS': 'HIMS', 'RXRX': 'RXRX', 'LLY': 'LLY',
    'TEM': 'TEM', 'CRSP': 'CRSP', 'TMDX': 'TMDX',
    'Rocketlab': 'RKLB', 'FLY': 'FLY', 'JOBY': 'JOBY', 'ACHR': 'ACHR', 'LUNR': 'LUNR', 'ASTS': 'ASTS',
    'BABA': 'BABA', 'BIDU': 'BIDU', 'JD': 'JD', 'XPEV': 'XPEV', 'NIO': 'NIO', 'PDD': 'PDD',
    'FUTU': 'FUTU', 'Tencent': 'TCEHY',
    'Bitcoin': 'BTC-USD', 'Ethereum': 'ETH-USD', 'Ripple': 'XRP-USD', 'Solana': 'SOL-USD',
    'Cardana': 'ADA-USD', 'BMNR': 'BMNR', 'MSTR': 'MSTR', 'COIN': 'COIN',
    'CLSK': 'CLSK', 'RIOT': 'RIOT', 'MARA': 'MARA', 'SBET': 'SBET', 'HUT': 'HUT',
    'DOGE': 'DOGE-USD', 'PEPE': 'PEPE24478-USD', 'FIG': 'FIG', 'CRCL': 'CRCL', 'XYZ': 'XYZ',
    'Bullish': 'BULL', 'HIVE': 'HIVE',
    'Sofi': 'SOFI', 'OPEN': 'OPEN', 'LMND': 'LMND', 'HOOD': 'HOOD', 'BULL': 'BULL',
    'Paypal': 'PYPL', 'AFRM': 'AFRM',
    'RGTI': 'RGTI', 'IONQ': 'IONQ', 'QUBT': 'QUBT', 'QBTS': 'QBTS',
    'GME': 'GME', 'LULU': 'LULU', 'CMG': 'CMG', 'UPS': 'UPS', 'Airbnb': 'ABNB',
    'Peloton': 'PTON', 'Boeing': 'BA', 'Nike': 'NKE',
    # Commodity ETF proxies (2026-08-24 fix: these xlsx rows previously resolved
    # to invalid tickers via val.upper() — 'Gold' accidentally hit Barrick)
    'Gold': 'GLD', 'Silver': 'SLV', 'Copper': 'CPER', 'Oil(USO)': 'USO',
}

SKIP_TICKERS = {
    'BTC-USD', 'ETH-USD', 'XRP-USD', 'SOL-USD', 'ADA-USD', 'DOGE-USD',
    'PEPE24478-USD', '^IXIC', '^GSPC', '^DJI', '^RUT', '^HSI', '000001.SS',
}

SECTORS = {
    'Hyperscaler': ['GOOGL', 'AMZN', 'META', 'MSFT', 'AAPL'],
    'Self-Driving': ['TSLA', 'PONY', 'UBER', 'GRAB'],
    'Robotics': ['SERV', 'PATH', 'ISRG'],
    'Semis': ['NVDA', 'AMD', 'AVGO', 'TSM', 'ARM', 'MRVL', 'MU', 'INTC', 'SMCI', 'ANET', 'DELL', 'ASML', 'QCOM', 'SKHY'],
    'AI Infrastructure': ['CRWV', 'ORCL', 'IREN', 'NBIS', 'CIFR', 'APLD', 'CSCO'],
    'Energy': ['OKLO', 'LAC', 'MP', 'SMR', 'BE', 'ONDS', 'QS', 'EOSE'],
    'Software': ['PLTR', 'SNOW', 'AI', 'IBM', 'MDB', 'NOW', 'CRM', 'ADBE', 'OKTA', 'SHOP',
                 'SOUN', 'BBAI', 'UPST', 'DUOL', 'RBRK', 'DDOG', 'NFLX', 'ZETA', 'SPOT', 'APP',
                 'RDDT', 'TTD', 'RBLX', 'U', 'INFY', 'ALAB', 'CRDO', 'WOLF', 'SNPS',
                 'CRWD', 'PANW', 'ZS'],
    'Health': ['UNH', 'OSCR', 'HIMS', 'RXRX', 'LLY', 'TEM', 'CRSP', 'TMDX'],
    'Space': ['RKLB', 'FLY', 'JOBY', 'ACHR', 'LUNR', 'ASTS'],
    'China': ['BABA', 'BIDU', 'JD', 'XPEV', 'NIO', 'PDD', 'FUTU', 'TCEHY'],
    'Crypto': ['MSTR', 'COIN', 'CLSK', 'RIOT', 'MARA', 'HUT', 'BMNR', 'SBET', 'FIG', 'CRCL', 'XYZ', 'BULL', 'HIVE'],
    'Finance': ['SOFI', 'OPEN', 'LMND', 'HOOD', 'PYPL', 'AFRM'],
    'Quantum': ['RGTI', 'IONQ', 'QUBT', 'QBTS'],
    'Trading': ['GME', 'LULU', 'CMG', 'UPS', 'ABNB', 'PTON', 'BA', 'NKE'],
    'Rotation': ['JPM', 'GS', 'BRK-B', 'XOM', 'CVX', 'CAT', 'DE', 'GE', 'COST', 'WMT', 'JNJ'],  # no XLU/commodity ETFs — no earnings
}

TICKER_TO_SECTOR = {}
for sector, tickers in SECTORS.items():
    for t in tickers:
        TICKER_TO_SECTOR[t] = sector


def load_stocks_from_excel(filepath):
    df = pd.read_excel(filepath, sheet_name='AI')
    stocks, seen = [], set()
    for col in df.columns:
        if col == 'Index':
            continue
        for val in df[col].dropna():
            val = str(val).strip()
            if val and val != 'nan':
                ticker = TICKER_MAP.get(val, val.upper())
                if ticker not in seen and ticker not in SKIP_TICKERS:
                    seen.add(ticker)
                    sector = TICKER_TO_SECTOR.get(ticker, col)
                    stocks.append((val, ticker, sector))
    return stocks


def get_earnings_date(ticker_obj):
    try:
        cal = ticker_obj.calendar
        if cal is None:
            return None
        if isinstance(cal, pd.DataFrame):
            if 'Earnings Date' in cal.columns:
                d = cal['Earnings Date'].iloc[0]
            elif len(cal.columns) > 0:
                d = cal.iloc[0, 0]
            else:
                return None
        elif isinstance(cal, dict):
            if 'Earnings Date' in cal:
                d = cal['Earnings Date']
                if isinstance(d, list) and len(d) > 0:
                    d = d[0]
            elif 'earningsDate' in cal:
                d = cal['earningsDate']
                if isinstance(d, list) and len(d) > 0:
                    d = d[0]
            else:
                return None
        else:
            return None

        if isinstance(d, pd.Timestamp):
            return d.date()
        if isinstance(d, datetime):
            return d.date()
        if isinstance(d, date_type):
            return d
        if isinstance(d, str):
            return pd.to_datetime(d).date()
        return None
    except Exception:
        return None


def analyze_historical_earnings(ticker_obj, daily_data):
    """Analyze past earnings reactions using quarterly earnings dates."""
    try:
        earnings_hist = ticker_obj.earnings_dates
        if earnings_hist is None or earnings_hist.empty:
            return None

        past_dates = []
        today = datetime.now().date()
        for dt in earnings_hist.index:
            d = dt.date() if hasattr(dt, 'date') else dt
            if d < today:
                past_dates.append(d)

        if len(past_dates) < 2:
            return None

        past_dates = sorted(past_dates, reverse=True)[:8]

        earnings_moves = []
        post_drift_moves = []

        for edate in past_dates:
            ts = pd.Timestamp(edate)
            if daily_data.index.tz is not None:
                ts = ts.tz_localize(daily_data.index.tz)
            idx = daily_data.index.get_indexer([ts], method='nearest')[0]
            if idx < 1 or idx >= len(daily_data) - 3:
                continue

            pre_close = float(daily_data['Close'].iloc[idx - 1])
            post_close = float(daily_data['Close'].iloc[idx])
            if pre_close == 0:
                continue

            earnings_day_move = (post_close - pre_close) / pre_close * 100
            earnings_moves.append(earnings_day_move)

            drift_end = min(idx + 3, len(daily_data) - 1)
            drift_close = float(daily_data['Close'].iloc[drift_end])
            drift_move = (drift_close - post_close) / post_close * 100
            post_drift_moves.append(drift_move)

        if not earnings_moves:
            return None

        moves = np.array(earnings_moves)
        drifts = np.array(post_drift_moves) if post_drift_moves else np.array([0.0])

        return {
            'avg_abs_move': float(np.mean(np.abs(moves))),
            'avg_move': float(np.mean(moves)),
            'max_move': float(np.max(moves)),
            'min_move': float(np.min(moves)),
            'positive_rate': float(np.sum(moves > 0) / len(moves) * 100),
            'num_earnings': len(moves),
            'avg_drift': float(np.mean(drifts)),
            'drift_same_dir_rate': float(
                np.sum(np.sign(drifts[:len(moves)]) == np.sign(moves[:len(drifts)])) / max(len(drifts), 1) * 100
            ) if len(drifts) > 0 else 50.0,
            'moves': moves.tolist(),
        }
    except Exception:
        return None


def compute_pre_earnings_setup(daily_data, days_to_earnings):
    """Score the technical setup heading into earnings."""
    if len(daily_data) < 50:
        return None

    close = daily_data['Close'].astype(float)
    volume = daily_data['Volume'].astype(float)
    high = daily_data['High'].astype(float)
    low = daily_data['Low'].astype(float)

    px = float(close.iloc[-1])

    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()

    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain / loss))

    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    vol_ma20 = volume.rolling(20).mean()

    c_ma20 = float(ma20.iloc[-1])
    c_ma50 = float(ma50.iloc[-1])
    c_rsi = float(rsi.iloc[-1])
    c_macd = float(macd.iloc[-1])
    c_signal = float(signal.iloc[-1])
    c_atr = float(atr.iloc[-1])
    c_vol_ratio = float(volume.iloc[-1] / vol_ma20.iloc[-1]) if float(vol_ma20.iloc[-1]) > 0 else 1.0

    atr_baseline = float(atr.iloc[-30:-15].mean()) if len(atr) > 30 else float(atr.mean())
    atr_recent = float(atr.iloc[-5:].mean())
    iv_expansion = (atr_recent / atr_baseline - 1) * 100 if atr_baseline > 0 else 0

    pct_10d = (px - float(close.iloc[-11])) / float(close.iloc[-11]) * 100 if len(close) > 11 else 0
    pct_20d = (px - float(close.iloc[-21])) / float(close.iloc[-21]) * 100 if len(close) > 21 else 0

    trend_score = 0
    if px > c_ma20:
        trend_score += 1
    if px > c_ma50:
        trend_score += 1
    if c_ma20 > c_ma50:
        trend_score += 1
    if c_macd > c_signal:
        trend_score += 1

    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_up = float((bb_mid + 2 * bb_std).iloc[-1])
    bb_lo = float((bb_mid - 2 * bb_std).iloc[-1])
    bb_pos = (px - bb_lo) / (bb_up - bb_lo) * 100 if bb_up != bb_lo else 50

    high_52w = float(close.iloc[-252:].max()) if len(close) >= 252 else float(close.max())
    low_52w = float(close.iloc[-252:].min()) if len(close) >= 252 else float(close.min())
    range_pos = (px - low_52w) / (high_52w - low_52w) * 100 if high_52w != low_52w else 50

    return {
        'price': px,
        'ma20': c_ma20,
        'ma50': c_ma50,
        'rsi': c_rsi,
        'macd': c_macd,
        'signal': c_signal,
        'atr': c_atr,
        'atr_pct': c_atr / px * 100 if px > 0 else 0,
        'vol_ratio': c_vol_ratio,
        'iv_expansion': iv_expansion,
        'pct_10d': pct_10d,
        'pct_20d': pct_20d,
        'trend_score': trend_score,
        'bb_position': bb_pos,
        'range_52w': range_pos,
        'high_52w': high_52w,
        'low_52w': low_52w,
    }


def score_earnings_play(setup, hist, days_to_earnings):
    """Generate a composite score and play recommendation."""
    score = 0
    reasons = []

    if hist is None:
        return {
            'total_score': 0, 'play': '❓ No Earnings Data',
            'conviction': 'NONE', 'reasons': ['No historical earnings data available'],
            'expected_move': 0, 'direction_bias': 'NEUTRAL', 'drift_play': None,
        }

    avg_abs = hist['avg_abs_move']
    avg_dir = hist['avg_move']
    pos_rate = hist['positive_rate']

    # Historical move size (bigger = more opportunity)
    if avg_abs >= 10:
        score += 3
        reasons.append(f'Large avg earnings move ±{avg_abs:.1f}%')
    elif avg_abs >= 5:
        score += 2
        reasons.append(f'Moderate avg earnings move ±{avg_abs:.1f}%')
    elif avg_abs >= 3:
        score += 1
        reasons.append(f'Small avg earnings move ±{avg_abs:.1f}%')

    # Direction consistency
    if pos_rate >= 75:
        score += 3
        reasons.append(f'Strong bullish bias ({pos_rate:.0f}% positive)')
    elif pos_rate >= 60:
        score += 1
        reasons.append(f'Slight bullish lean ({pos_rate:.0f}% positive)')
    elif pos_rate <= 25:
        score += 2
        reasons.append(f'Strong bearish bias ({pos_rate:.0f}% positive)')
    elif pos_rate <= 40:
        score += 1
        reasons.append(f'Slight bearish lean ({pos_rate:.0f}% positive)')

    if setup:
        # Trend alignment
        ts = setup['trend_score']
        if ts >= 3:
            score += 2
            reasons.append(f'Strong uptrend (score {ts}/4)')
        elif ts <= 1:
            score += 1
            reasons.append(f'Weak/downtrend (score {ts}/4)')

        # RSI positioning
        if 40 <= setup['rsi'] <= 65:
            score += 1
            reasons.append(f"RSI {setup['rsi']:.0f} — healthy range")
        elif setup['rsi'] > 75:
            reasons.append(f"RSI {setup['rsi']:.0f} — overbought risk")
        elif setup['rsi'] < 30:
            reasons.append(f"RSI {setup['rsi']:.0f} — oversold, reversal possible")

        # IV expansion
        if setup['iv_expansion'] > 20:
            score += 1
            reasons.append(f"ATR expanding +{setup['iv_expansion']:.0f}% (vol building)")

        # Pre-earnings momentum
        if setup['pct_10d'] > 5:
            reasons.append(f"Strong pre-earnings run-up +{setup['pct_10d']:.1f}% (10d)")
        elif setup['pct_10d'] < -5:
            reasons.append(f"Pre-earnings selloff {setup['pct_10d']:.1f}% (10d)")

        # Volume
        if setup['vol_ratio'] > 1.5:
            score += 1
            reasons.append(f"Elevated volume {setup['vol_ratio']:.1f}x avg")

    # Post-earnings drift
    if hist['drift_same_dir_rate'] >= 65:
        score += 1
        reasons.append(f"Post-earnings drift continues {hist['drift_same_dir_rate']:.0f}% of the time")

    # Determine play type and direction
    direction = 'NEUTRAL'
    if pos_rate >= 60 and setup and setup['trend_score'] >= 3:
        direction = 'BULLISH'
    elif pos_rate <= 40 and setup and setup['trend_score'] <= 1:
        direction = 'BEARISH'
    elif pos_rate >= 60:
        direction = 'LEAN_BULL'
    elif pos_rate <= 40:
        direction = 'LEAN_BEAR'

    if days_to_earnings > 10:
        play = '📈 Pre-Earnings Run-Up'
        if direction in ('BULLISH', 'LEAN_BULL') and setup and setup['trend_score'] >= 2:
            play = '📈 Pre-Earnings Run-Up (Buy)'
        elif direction in ('BEARISH', 'LEAN_BEAR'):
            play = '📉 Pre-Earnings Fade (Sell/Put)'
        else:
            play = '👀 Pre-Earnings Watch'
    elif days_to_earnings <= 3:
        if score >= 7 and direction in ('BULLISH', 'LEAN_BULL'):
            play = '🎯 Earnings Hold (Bullish)'
        elif score >= 7 and direction in ('BEARISH', 'LEAN_BEAR'):
            play = '🎯 Earnings Hold (Bearish)'
        elif avg_abs >= 8:
            play = '🎰 High-Vol Earnings Gamble'
        else:
            play = '🚫 Earnings Avoid'
    else:
        if direction == 'BULLISH':
            play = '📈 Pre-Earnings Run-Up (Buy)'
        elif direction == 'BEARISH':
            play = '📉 Pre-Earnings Fade'
        else:
            play = '👀 Pre-Earnings Watch'

    # Post-earnings drift play
    if hist['drift_same_dir_rate'] >= 70 and hist['avg_drift'] != 0:
        drift_play = f"⚡ Post-Earnings Drift ({'up' if hist['avg_drift'] > 0 else 'down'} avg {hist['avg_drift']:+.1f}%)"
    else:
        drift_play = None

    if score >= 8:
        conviction = 'HIGH'
    elif score >= 5:
        conviction = 'MED'
    else:
        conviction = 'LOW'

    return {
        'total_score': score,
        'play': play,
        'drift_play': drift_play,
        'conviction': conviction,
        'reasons': reasons,
        'expected_move': avg_abs,
        'direction_bias': direction,
    }


def compute_entry_exit(setup, hist, play_info, days_to_earnings):
    """Calculate entry, stop, and target levels."""
    if setup is None:
        return None

    px = setup['price']
    atr = setup['atr']
    expected = play_info['expected_move']
    direction = play_info['direction_bias']

    if 'Run-Up' in play_info['play'] or 'Watch' in play_info['play']:
        if direction in ('BULLISH', 'LEAN_BULL', 'NEUTRAL'):
            entry = px * 0.998
            stop = px - atr * 1.5
            target1 = px * (1 + expected * 0.3 / 100)
            target2 = px * (1 + expected * 0.6 / 100)
            sell_before = 'Sell day before earnings'
        else:
            entry = px * 1.002
            stop = px + atr * 1.5
            target1 = px * (1 - expected * 0.3 / 100)
            target2 = px * (1 - expected * 0.6 / 100)
            sell_before = 'Cover day before earnings'
    elif 'Hold' in play_info['play']:
        if 'Bullish' in play_info['play']:
            entry = px * 0.998
            stop = px - atr * 2.0
            target1 = px * (1 + expected / 100)
            target2 = px * (1 + expected * 1.5 / 100)
            sell_before = 'Hold through earnings'
        else:
            entry = px * 1.002
            stop = px + atr * 2.0
            target1 = px * (1 - expected / 100)
            target2 = px * (1 - expected * 1.5 / 100)
            sell_before = 'Hold short through earnings'
    else:
        return None

    return {
        'entry': entry,
        'stop': stop,
        'target1': target1,
        'target2': target2,
        'exit_note': sell_before,
        'risk_pct': abs(px - stop) / px * 100,
        'reward1_pct': abs(target1 - px) / px * 100,
        'reward2_pct': abs(target2 - px) / px * 100,
    }


def analyze_single_stock(name, ticker, sector):
    """Full earnings analysis for one stock."""
    try:
        t = yf.Ticker(ticker)
        today = datetime.now().date()

        earnings_date = get_earnings_date(t)
        if earnings_date is None:
            return None

        days_to = (earnings_date - today).days
        if days_to < -1 or days_to > 21:
            return None

        daily = t.history(period='2y', interval='1d', auto_adjust=True)
        if daily.empty or len(daily) < 60:
            return None
        if isinstance(daily.columns, pd.MultiIndex):
            daily.columns = daily.columns.get_level_values(0)
        daily = daily.dropna(subset=['Close'])

        hist = analyze_historical_earnings(t, daily)
        setup = compute_pre_earnings_setup(daily, days_to)
        play_info = score_earnings_play(setup, hist, days_to)
        levels = compute_entry_exit(setup, hist, play_info, days_to)

        return {
            'name': name,
            'ticker': ticker,
            'sector': sector,
            'earnings_date': earnings_date,
            'days_to_earnings': days_to,
            'setup': setup,
            'hist': hist,
            'play': play_info,
            'levels': levels,
        }
    except Exception as e:
        return {
            'name': name,
            'ticker': ticker,
            'sector': sector,
            'error': str(e)[:80],
        }


def format_earnings_card(r):
    """Format a single earnings play into readable text."""
    lines = []
    p = r['play']
    s = r['setup']
    h = r['hist']
    lv = r['levels']

    date_str = r['earnings_date'].strftime('%Y-%m-%d (%a)')
    urgency = ''
    if r['days_to_earnings'] <= 2:
        urgency = ' ⚠️ IMMINENT'
    elif r['days_to_earnings'] <= 5:
        urgency = ' ⏰ THIS WEEK'

    lines.append(f"### {p['play']} — {r['name']} ({r['ticker']})")
    lines.append(f"**Sector:** {r['sector']} | **Earnings:** {date_str} ({r['days_to_earnings']}d away){urgency}")
    lines.append(f"**Score:** {p['total_score']}/12 | **Conviction:** {p['conviction']} | **Bias:** {p['direction_bias']}")
    lines.append("")

    if h:
        moves_str = ', '.join(f"{m:+.1f}%" for m in h['moves'][:6])
        lines.append(f"**Historical Earnings Moves** (last {h['num_earnings']}): {moves_str}")
        lines.append(f"- Avg absolute move: ±{h['avg_abs_move']:.1f}% | Avg directional: {h['avg_move']:+.1f}%")
        lines.append(f"- Positive rate: {h['positive_rate']:.0f}% | Best: {h['max_move']:+.1f}% | Worst: {h['min_move']:+.1f}%")
        lines.append(f"- Post-earnings drift: {h['avg_drift']:+.1f}% avg, continues same direction {h['drift_same_dir_rate']:.0f}%")
        lines.append("")

    if s:
        trend_label = ['Bearish', 'Weak', 'Neutral', 'Bullish', 'Strong Bull'][s['trend_score']]
        lines.append(f"**Technical Setup:**")
        lines.append(f"- Price: ${s['price']:.2f} | RSI: {s['rsi']:.0f} | Trend: {trend_label} ({s['trend_score']}/4)")
        lines.append(f"- 10d momentum: {s['pct_10d']:+.1f}% | 20d: {s['pct_20d']:+.1f}%")
        lines.append(f"- ATR: ${s['atr']:.2f} ({s['atr_pct']:.1f}%) | Vol expansion: {s['iv_expansion']:+.0f}%")
        lines.append(f"- BB position: {s['bb_position']:.0f}% | 52w range: {s['range_52w']:.0f}%")
        lines.append(f"- Volume ratio: {s['vol_ratio']:.1f}x")
        lines.append("")

    if lv:
        lines.append(f"**Trade Plan:**")
        if 'Bullish' in p['play'] or 'Buy' in p['play'] or 'Run-Up' in p['play']:
            lines.append(f"- Entry: ${lv['entry']:.2f}")
            lines.append(f"- Stop: ${lv['stop']:.2f} (-{lv['risk_pct']:.1f}%)")
            lines.append(f"- Target 1: ${lv['target1']:.2f} (+{lv['reward1_pct']:.1f}%)")
            lines.append(f"- Target 2: ${lv['target2']:.2f} (+{lv['reward2_pct']:.1f}%)")
        else:
            lines.append(f"- Entry (short): ${lv['entry']:.2f}")
            lines.append(f"- Stop: ${lv['stop']:.2f} ({lv['risk_pct']:.1f}% risk)")
            lines.append(f"- Target 1: ${lv['target1']:.2f}")
            lines.append(f"- Target 2: ${lv['target2']:.2f}")
        lines.append(f"- Exit note: {lv['exit_note']}")
        lines.append("")

    if p['drift_play']:
        lines.append(f"**Alt Play:** {p['drift_play']}")
        lines.append("")

    lines.append("**Key Factors:**")
    for reason in p['reasons']:
        lines.append(f"- {reason}")
    lines.append("")
    lines.append("---")
    lines.append("")
    return '\n'.join(lines)


def write_report(results, out_path):
    """Write the full earnings play report."""
    lines = []
    now = datetime.now()

    with_earnings = [r for r in results if 'error' not in r and r is not None]
    errors = [r for r in results if r is not None and 'error' in r]

    with_earnings.sort(key=lambda r: r['days_to_earnings'])

    imminent = [r for r in with_earnings if r['days_to_earnings'] <= 2]
    this_week = [r for r in with_earnings if 3 <= r['days_to_earnings'] <= 7]
    next_week = [r for r in with_earnings if 8 <= r['days_to_earnings'] <= 14]
    further = [r for r in with_earnings if r['days_to_earnings'] > 14]

    actionable = [r for r in with_earnings
                  if r['play']['conviction'] in ('HIGH', 'MED')
                  and 'Avoid' not in r['play']['play']
                  and 'No Earnings' not in r['play']['play']
                  and '❓' not in r['play']['play']]

    lines.append("# 📊 Earnings Play Strategy Report")
    lines.append("")
    lines.append(f"**Generated:** {now.strftime('%Y-%m-%d %H:%M')} | **Horizon:** Next 3 weeks")
    lines.append(f"**Stocks with upcoming earnings:** {len(with_earnings)} | **Actionable plays:** {len(actionable)}")
    lines.append("")

    # Summary table
    lines.append("## 🗓️ Earnings Calendar Overview")
    lines.append("")
    lines.append("| Ticker | Name | Sector | Earnings Date | Days | Expected Move | Play | Conviction |")
    lines.append("|--------|------|--------|---------------|------|---------------|------|------------|")
    for r in with_earnings:
        exp = f"±{r['play']['expected_move']:.1f}%" if r['play']['expected_move'] > 0 else '—'
        lines.append(
            f"| **{r['ticker']}** | {r['name']} | {r['sector']} | "
            f"{r['earnings_date'].strftime('%m/%d')} | {r['days_to_earnings']}d | "
            f"{exp} | {r['play']['play']} | {r['play']['conviction']} |"
        )
    lines.append("")

    # Top plays
    if actionable:
        actionable.sort(key=lambda r: r['play']['total_score'], reverse=True)
        lines.append("## 🎯 Top Actionable Plays (by Score)")
        lines.append("")
        for r in actionable:
            lines.append(format_earnings_card(r))

    # Imminent earnings
    if imminent:
        lines.append("## ⚠️ Imminent Earnings (0-2 days)")
        lines.append("")
        for r in imminent:
            if r not in actionable:
                lines.append(format_earnings_card(r))

    # This week
    if this_week:
        lines.append("## ⏰ This Week (3-7 days)")
        lines.append("")
        for r in this_week:
            if r not in actionable:
                lines.append(format_earnings_card(r))

    # Next week
    if next_week:
        lines.append("## 📅 Next Week (8-14 days)")
        lines.append("")
        for r in next_week:
            if r not in actionable:
                lines.append(format_earnings_card(r))

    # Further out
    if further:
        lines.append("## 🔮 2-3 Weeks Out (15-21 days)")
        lines.append("")
        for r in further:
            if r not in actionable:
                lines.append(format_earnings_card(r))

    # Sector summary
    lines.append("## 📊 Sector Earnings Density")
    lines.append("")
    sector_counts = {}
    for r in with_earnings:
        sector_counts[r['sector']] = sector_counts.get(r['sector'], 0) + 1
    for sec, count in sorted(sector_counts.items(), key=lambda x: -x[1]):
        tickers = [r['ticker'] for r in with_earnings if r['sector'] == sec]
        lines.append(f"- **{sec}** ({count}): {', '.join(tickers)}")
    lines.append("")

    # Strategy notes
    lines.append("## 📖 Earnings Play Strategy Guide")
    lines.append("")
    lines.append("### Play Types")
    lines.append("- **📈 Pre-Earnings Run-Up**: Buy 5-10 days before earnings, sell the day before. Works best with bullish trend + historical positive bias.")
    lines.append("- **🎯 Earnings Hold**: High-conviction directional bet through earnings. Requires strong trend alignment + consistent historical reaction.")
    lines.append("- **⚡ Post-Earnings Drift**: Wait for the earnings reaction, then trade the continuation 1-5 days after. Lower risk, captures follow-through.")
    lines.append("- **👀 Pre-Earnings Watch**: Setup is forming but not yet actionable. Monitor for entry triggers.")
    lines.append("- **🚫 Earnings Avoid**: No clear edge — stay flat through this report.")
    lines.append("")
    lines.append("### Risk Management")
    lines.append("- **Pre-earnings positions**: Exit or reduce before the announcement unless running an explicit hold-through play")
    lines.append("- **Position sizing**: HIGH conviction = standard size (2-5%), MED = half, LOW = quarter or skip")
    lines.append("- **Stop discipline**: Pre-earnings stops are wider (1.5-2x ATR) since you're trading a known catalyst")
    lines.append("- **Correlation risk**: If multiple stocks in the same sector report the same week, the first one's reaction often previews the rest")
    lines.append("")

    if errors:
        lines.append("## ❌ Data Errors")
        lines.append("")
        for r in errors:
            lines.append(f"- {r['ticker']} ({r['name']}): {r['error']}")
        lines.append("")

    out_path.write_text('\n'.join(lines), encoding='utf-8')
    return out_path


def main():
    filepath = Path(__file__).parent / 'AI_Portfolios.xlsx'
    now = datetime.now()

    print(f"{'='*90}")
    print(f"  📊 AI Portfolio Earnings Play Strategy")
    print(f"  Generated: {now.strftime('%Y-%m-%d %H:%M')}")
    print(f"  Scanning for earnings within next 21 days")
    print(f"{'='*90}\n")

    stocks = load_stocks_from_excel(str(filepath))
    total = len(stocks)
    print(f"Loaded {total} stocks from portfolio (excluding crypto/indices).\n")
    print(f"Fetching earnings dates and analyzing historical patterns (max_workers=12)...\n")

    results = []
    done = 0
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(analyze_single_stock, name, ticker, sector): (name, ticker)
                for name, ticker, sector in stocks}
        for fut in as_completed(futs):
            done += 1
            try:
                r = fut.result()
                if r is not None:
                    results.append(r)
            except Exception as e:
                name, ticker = futs[fut]
                print(f"  ❌ {ticker}: {str(e)[:60]}")
            if done % 25 == 0 or done == total:
                print(f"  Scanned {done}/{total}...", flush=True)

    with_earnings = [r for r in results if 'error' not in r]
    errors = [r for r in results if 'error' in r]
    with_earnings.sort(key=lambda r: r['days_to_earnings'])

    print(f"\n{'='*90}")
    print(f"  Results: {len(with_earnings)} stocks with earnings in next 21 days")
    print(f"{'='*90}\n")

    for r in with_earnings:
        p = r['play']
        urgency = '⚠️' if r['days_to_earnings'] <= 2 else '⏰' if r['days_to_earnings'] <= 7 else '📅'
        exp = f"±{p['expected_move']:.1f}%" if p['expected_move'] > 0 else '—'
        print(f"  {urgency} {r['ticker']:<8} {r['earnings_date'].strftime('%m/%d'):>5} "
              f"({r['days_to_earnings']:>2}d)  {exp:>7}  {p['conviction']:<4}  {p['play']}")

    out_path = Path(__file__).parent / f"earnings_plays_{now.strftime('%Y-%m-%d')}.md"
    write_report(results, out_path)
    print(f"\n  ✅ Report saved: {out_path.name}")
    print(f"{'='*90}\n")


if __name__ == '__main__':
    main()
