"""Compute mechanical technical price targets for top BUY stocks.

Targets derived from:
- Resistance: 52-week high
- Breakout target: pivot + measured move (cup depth or 20D range)
- ATR-based 1-month projection: price + 4 * ATR(14) (typical 1-month range)
- Stop-loss: max(MA50, recent 20D swing-low) for trend followers
"""
import yfinance as yf
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")

TICKERS = ["GME", "INTC", "GOOGL", "AAPL", "CSCO", "BE", "SOUN", "WOLF", "DDOG", "AMD",
           "MU", "APLD", "APP", "CRWD", "QUBT", "AMZN", "QCOM", "UNH", "OSCR"]

def atr(df, n=14):
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean().iloc[-1]

rows = []
for tk in TICKERS:
    try:
        df = yf.download(tk, period="1y", progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.empty or len(df) < 50:
            continue

        price = float(df["Close"].iloc[-1])
        ma20 = float(df["Close"].rolling(20).mean().iloc[-1])
        ma50 = float(df["Close"].rolling(50).mean().iloc[-1])
        ma200 = float(df["Close"].rolling(200).mean().iloc[-1])
        hi52 = float(df["High"].rolling(252).max().iloc[-1])
        lo52 = float(df["Low"].rolling(252).min().iloc[-1])
        hi20 = float(df["High"].iloc[-21:-1].max())   # prior-20D high (pivot)
        lo20 = float(df["Low"].iloc[-21:-1].min())
        a = float(atr(df))

        # Cup-and-handle / breakout measured move: pivot + (pivot - 60D-low)
        lo60 = float(df["Low"].iloc[-61:-1].min())
        cup_depth = hi20 - lo60
        breakout_tgt = hi20 + cup_depth  # measured-move target above pivot

        # Conservative T1 = +1 ATR*5 over ~1 month
        t1 = price + 5 * a
        # Stop = max(MA50, 20d swing low) for trend follower
        stop = max(ma50, lo20)

        rows.append({
            "Ticker": tk,
            "Price": price,
            "T1 (~1mo, +5×ATR)": t1,
            "T2 (Resistance, 52wH)": hi52,
            "T3 (Measured move)": breakout_tgt,
            "Stop": stop,
            "% to T1": (t1/price - 1) * 100,
            "% to T2": (hi52/price - 1) * 100,
            "% to T3": (breakout_tgt/price - 1) * 100,
            "% to Stop": (stop/price - 1) * 100,
            "ATR(14)": a,
        })
    except Exception as e:
        print(f"  {tk} error: {e}")

out = pd.DataFrame(rows)
out = out.round(2)
print(out.to_string(index=False))
out.to_csv("technical_targets_2026-05-02.csv", index=False)
print("\nSaved: technical_targets_2026-05-02.csv")
