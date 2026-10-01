"""
Strategy Backtester - Automated Run
Tests 5 common trading strategies across major US indices and stocks.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ─── Configuration ────────────────────────────────────────────────────────────
TODAY = datetime.today()
PERIODS = {
    "6M": (TODAY - timedelta(days=183), TODAY),
    "1Y": (TODAY - timedelta(days=365), TODAY),
}

TICKERS = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA", "META"]

# ─── Data Fetching ─────────────────────────────────────────────────────────────
def fetch_data(ticker, start, end):
    df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    if df.empty:
        return None
    # Flatten MultiIndex if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[['Open','High','Low','Close','Volume']].copy()
    df.dropna(inplace=True)
    return df

# ─── Trade Simulation Helper ──────────────────────────────────────────────────
def simulate_trades(signals, prices):
    """
    signals: pd.Series of 1 (buy), -1 (sell/short), 0 (flat)
    prices: pd.Series of closing prices aligned to signals index
    Returns list of trade returns (log returns per trade).
    """
    trades = []
    in_trade = False
    entry_price = None

    for i in range(len(signals)):
        sig = signals.iloc[i]
        price = prices.iloc[i]
        if not in_trade and sig == 1:
            in_trade = True
            entry_price = price
        elif in_trade and sig == -1:
            ret = (price - entry_price) / entry_price
            trades.append(ret)
            in_trade = False
            entry_price = None

    # Close any open trade at last price
    if in_trade and entry_price is not None:
        ret = (prices.iloc[-1] - entry_price) / entry_price
        trades.append(ret)

    return trades

def compute_stats(trades, label=""):
    if len(trades) == 0:
        return {
            "n_trades": 0, "win_rate": None, "profit_factor": None,
            "max_drawdown": None, "avg_win": None, "avg_loss": None,
            "sharpe": None
        }
    t = np.array(trades)
    wins = t[t > 0]
    losses = t[t <= 0]
    win_rate = len(wins) / len(t) if len(t) > 0 else 0
    gross_profit = wins.sum() if len(wins) > 0 else 0
    gross_loss = abs(losses.sum()) if len(losses) > 0 else 0.0001
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    avg_win = wins.mean() if len(wins) > 0 else 0
    avg_loss = losses.mean() if len(losses) > 0 else 0

    # Max drawdown over cumulative equity curve
    equity = np.cumprod(1 + t)
    rolling_max = np.maximum.accumulate(equity)
    drawdowns = (equity - rolling_max) / rolling_max
    max_dd = drawdowns.min() if len(drawdowns) > 0 else 0

    # Sharpe (annualised, assume ~252 trade-days/year rough proxy)
    mean_r = t.mean()
    std_r = t.std() if t.std() > 0 else 1e-9
    sharpe = (mean_r / std_r) * np.sqrt(min(len(t), 252))

    return {
        "n_trades": len(t),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "max_drawdown": max_dd,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "sharpe": sharpe
    }

# ─── Strategy 1: MA Crossover (50/200 SMA) ───────────────────────────────────
def strategy_ma_crossover(df):
    df = df.copy()
    df['sma50'] = df['Close'].rolling(50).mean()
    df['sma200'] = df['Close'].rolling(200).mean()
    df.dropna(inplace=True)
    if len(df) < 5:
        return []
    signal = pd.Series(0, index=df.index)
    signal[df['sma50'] > df['sma200']] = 1   # bullish
    signal[df['sma50'] < df['sma200']] = -1  # bearish

    # Generate entry/exit events
    trades = []
    in_trade = False
    entry_price = None
    prev_sig = 0

    for i in range(len(df)):
        curr_sig = signal.iloc[i]
        price = df['Close'].iloc[i]
        if not in_trade and prev_sig <= 0 and curr_sig == 1:
            in_trade = True
            entry_price = price
        elif in_trade and curr_sig == -1:
            trades.append((price - entry_price) / entry_price)
            in_trade = False
        prev_sig = curr_sig

    if in_trade and entry_price:
        trades.append((df['Close'].iloc[-1] - entry_price) / entry_price)

    return trades

# ─── Strategy 2: RSI Divergence (14-period) ───────────────────────────────────
def strategy_rsi(df, period=14, oversold=30, overbought=70):
    df = df.copy()
    delta = df['Close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    df['rsi'] = 100 - (100 / (1 + rs))
    df.dropna(inplace=True)
    if len(df) < 5:
        return []

    trades = []
    in_trade = False
    entry_price = None
    prev_rsi = df['rsi'].iloc[0]

    for i in range(1, len(df)):
        rsi = df['rsi'].iloc[i]
        price = df['Close'].iloc[i]
        if not in_trade and prev_rsi < oversold and rsi >= oversold:
            in_trade = True
            entry_price = price
        elif in_trade and rsi >= overbought:
            trades.append((price - entry_price) / entry_price)
            in_trade = False
        prev_rsi = rsi

    if in_trade and entry_price:
        trades.append((df['Close'].iloc[-1] - entry_price) / entry_price)

    return trades

# ─── Strategy 3: MACD Crossover (12/26/9) ─────────────────────────────────────
def strategy_macd(df):
    df = df.copy()
    ema12 = df['Close'].ewm(span=12).mean()
    ema26 = df['Close'].ewm(span=26).mean()
    df['macd'] = ema12 - ema26
    df['signal_line'] = df['macd'].ewm(span=9).mean()
    df.dropna(inplace=True)
    if len(df) < 5:
        return []

    trades = []
    in_trade = False
    entry_price = None
    prev_macd = df['macd'].iloc[0]
    prev_sig = df['signal_line'].iloc[0]

    for i in range(1, len(df)):
        macd_val = df['macd'].iloc[i]
        sig_val = df['signal_line'].iloc[i]
        price = df['Close'].iloc[i]
        # Bullish crossover
        if not in_trade and prev_macd <= prev_sig and macd_val > sig_val:
            in_trade = True
            entry_price = price
        # Bearish crossover
        elif in_trade and prev_macd >= prev_sig and macd_val < sig_val:
            trades.append((price - entry_price) / entry_price)
            in_trade = False
        prev_macd = macd_val
        prev_sig = sig_val

    if in_trade and entry_price:
        trades.append((df['Close'].iloc[-1] - entry_price) / entry_price)

    return trades

# ─── Strategy 4: Bollinger Band Mean Reversion (20, 2σ) ──────────────────────
def strategy_bollinger(df, period=20, std_dev=2):
    df = df.copy()
    df['mid'] = df['Close'].rolling(period).mean()
    df['std'] = df['Close'].rolling(period).std()
    df['upper'] = df['mid'] + std_dev * df['std']
    df['lower'] = df['mid'] - std_dev * df['std']
    df.dropna(inplace=True)
    if len(df) < 5:
        return []

    trades = []
    in_trade = False
    entry_price = None

    for i in range(len(df)):
        price = df['Close'].iloc[i]
        lower = df['lower'].iloc[i]
        mid = df['mid'].iloc[i]
        upper = df['upper'].iloc[i]
        if not in_trade and price < lower:
            in_trade = True
            entry_price = price
        elif in_trade and price >= mid:
            trades.append((price - entry_price) / entry_price)
            in_trade = False

    if in_trade and entry_price:
        trades.append((df['Close'].iloc[-1] - entry_price) / entry_price)

    return trades

# ─── Strategy 5: Volume-Weighted Breakout ─────────────────────────────────────
def strategy_volume_breakout(df, lookback=20, vol_mult=1.5):
    df = df.copy()
    df['roll_high'] = df['High'].rolling(lookback).max().shift(1)
    df['avg_vol'] = df['Volume'].rolling(lookback).mean().shift(1)
    df.dropna(inplace=True)
    if len(df) < 5:
        return []

    trades = []
    in_trade = False
    entry_price = None
    entry_high = None

    for i in range(len(df)):
        price = df['Close'].iloc[i]
        high_today = df['High'].iloc[i]
        vol = df['Volume'].iloc[i]
        avg_vol = df['avg_vol'].iloc[i]
        roll_high = df['roll_high'].iloc[i]

        if not in_trade and high_today > roll_high and vol > vol_mult * avg_vol:
            in_trade = True
            entry_price = price
            entry_high = roll_high
        elif in_trade:
            # Exit: price falls back below entry breakout level (stop) or +10% target
            if price < entry_high or (price - entry_price) / entry_price >= 0.10:
                trades.append((price - entry_price) / entry_price)
                in_trade = False

    if in_trade and entry_price:
        trades.append((df['Close'].iloc[-1] - entry_price) / entry_price)

    return trades

# ─── Run All Strategies ───────────────────────────────────────────────────────
STRATEGIES = {
    "MA Crossover (50/200 SMA)": strategy_ma_crossover,
    "RSI (14-period, 30/70)": strategy_rsi,
    "MACD (12/26/9)": strategy_macd,
    "Bollinger Bands (20, 2σ)": strategy_bollinger,
    "Volume Breakout (20d, 1.5× vol)": strategy_volume_breakout,
}

results = {}  # results[period][strategy][ticker] = stats

for period_label, (start, end) in PERIODS.items():
    results[period_label] = {}
    for strat_name, strat_fn in STRATEGIES.items():
        results[period_label][strat_name] = {}
        for ticker in TICKERS:
            df = fetch_data(ticker, start, end)
            if df is None or len(df) < 60:
                results[period_label][strat_name][ticker] = None
                continue
            try:
                trades = strat_fn(df)
                stats = compute_stats(trades)
                results[period_label][strat_name][ticker] = stats
            except Exception as e:
                results[period_label][strat_name][ticker] = None

# ─── Save results as Python pickle for use in report generator ────────────────
import pickle, os

out_dir = r"C:\Users\alienware\Desktop\Claude\StockInvesting"
with open(os.path.join(out_dir, "backtest_results.pkl"), "wb") as f:
    pickle.dump(results, f)

print("Backtest complete. Results saved.")
print("Tickers:", TICKERS)
for p in PERIODS:
    for s in STRATEGIES:
        total = sum(1 for t in TICKERS if results[p][s].get(t) and results[p][s][t]['n_trades'] > 0)
        print(f"  [{p}] {s}: {total}/{len(TICKERS)} tickers with trades")
