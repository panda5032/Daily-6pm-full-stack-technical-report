# -*- coding: utf-8 -*-
"""B-Xtrender (Puppytherapy) scan over the TradingView 🐎Portfolio watchlist.

shortTermXtrender = RSI(EMA(close,5) - EMA(close,20), 15) - 50   (histogram)
longTermXtrender  = RSI(EMA(close,20), 15) - 50                  (line)
RSI is Wilder's (TradingView ta.rsi). Signals follow the standard reading:
histogram color = rising/falling vs prior bar; zero-line crosses confirm.

Usage: python bxtrender_scan.py [--json out.json]
"""
import json, sys, math, datetime
import numpy as np
import pandas as pd
import yfinance as yf

# TradingView 🐎Portfolio (id 191597165), pulled 2026-07-20 -> yfinance mapping
TV_SYMBOLS = ["NASDAQ:TSLA","NASDAQ:NVDA","NASDAQ:MSFT","NASDAQ:META","NASDAQ:GOOG","NASDAQ:AMZN","NASDAQ:AAPL","NASDAQ:AVGO","NASDAQ:QCOM","NYSE:ORCL","NASDAQ:CRWV","NASDAQ:PLTR","NYSE:NOW","NYSE:IBM","NASDAQ:NFLX","NASDAQ:SERV","NYSE:PATH","NASDAQ:KTOS","NASDAQ:ONDS","NASDAQ:RKLB","NASDAQ:ASTS","NASDAQ:SPCX","NYSE:OKLO","NYSE:MP","NASDAQ:USAR","NASDAQ:SOFI","NYSE:BABA","NASDAQ:BIDU","CRYPTO:BTCUSD","CRYPTO:ETHUSD","NASDAQ:COIN","NYSE:ANET","NASDAQ:ADBE","NYSE:CRM","NASDAQ:DDOG","NASDAQ:PANW","NYSE:RBRK","NYSE:ZETA","NASDAQ:SOUN","NYSE:BBAI","NASDAQ:DUOL","NASDAQ:AMD","NASDAQ:APLD","NASDAQ:ALAB","NASDAQ:CSCO","NASDAQ:HOOD","NYSE:LMND","NYSE:NVO","NYSE:LLY","NASDAQ:PDD","NASDAQ:IBIT","NASDAQ:ETHA","NYSE:CRCL","CRYPTO:SOLUSD","CRYPTO:XRPUSD","NASDAQ:MSTR","NASDAQ:CLSK","NASDAQ:MARA","NASDAQ:RIOT","NYSE:SNOW","NASDAQ:TTD","AMEX:KWEB","NASDAQ:MU","NASDAQ:NBIS","NASDAQ:PONY","NYSE:IONQ","NYSE:DELL","NYSE:UNH","NYSE:HIMS","NYSE:OSCR","NASDAQ:LUNR","NASDAQ:FLY","NASDAQ:MDB","NYSE:GME","CRYPTO:DOGEUSD","CRYPTO:PEPEUSD","SSE:000001","SSE:000688","HSI:HSI","AMEX:ASHR","NASDAQ:JD","HKEX:981","HKEX:2050","SZSE:002050","SSE:601689","SZSE:002747","SZSE:002230","SSE:603501","SSE:600460","SPCFD:SPX","AMEX:SPY","TVC:NDQ","NASDAQ:QQQ","NASDAQ:INTC","NYSE:FIG","NASDAQ:SBET","NASDAQ:UPST","CBOE:FBTC","CBOE:ETHV","AMEX:BSOL","NASDAQ:XRPC","NASDAQ:GRAB","NYSE:NIO","TVC:GOLD","TVC:SILVER","NASDAQ:SHOP","CBOE:IGV","CBOE:MAGS","NYSE:DOCN","NYSE:NET","NASDAQ:SMCI","NASDAQ:CRDO","NASDAQ:MNDY","NASDAQ:INOD","NASDAQ:EVLV","NYSE:ONTO","NYSE:NKE","NYSE:TSM","NASDAQ:CIFR","NASDAQ:APP","AMEX:UUUU","NYSE:FCX","NYSE:VRT","NASDAQ:CEG","NASDAQ:OSS","AMEX:USO","NYSE:DT","NYSE:ESTC","NASDAQ:AAOI","NASDAQ:NVTS","NYSE:BE","NYSE:BA","NASDAQ:CBRS","NASDAQ:IREN","NASDAQ:ZS","NASDAQ:OKTA","NASDAQ:SNPS","NASDAQ:EQIX","NASDAQ:CRWD","NASDAQ:ADUR","NASDAQ:MRVL","NASDAQ:ABNB","NYSE:RDDT","TVC:VIX","NASDAQ:LRCX"]

SPECIAL = {
    "CRYPTO:BTCUSD":"BTC-USD","CRYPTO:ETHUSD":"ETH-USD","CRYPTO:SOLUSD":"SOL-USD",
    "CRYPTO:XRPUSD":"XRP-USD","CRYPTO:DOGEUSD":"DOGE-USD","CRYPTO:PEPEUSD":"PEPE24478-USD",
    "SSE:000001":"000001.SS","SSE:000688":"000688.SS","SSE:601689":"601689.SS",
    "SSE:603501":"603501.SS","SSE:600460":"600460.SS",
    "SZSE:002050":"002050.SZ","SZSE:002747":"002747.SZ","SZSE:002230":"002230.SZ",
    "HKEX:981":"0981.HK","HKEX:2050":"2050.HK","HSI:HSI":"^HSI",
    "SPCFD:SPX":"^GSPC","TVC:NDQ":"^NDX","TVC:VIX":"^VIX",
    "TVC:GOLD":"GC=F","TVC:SILVER":"SI=F",
}

def to_yf(tv):
    if tv in SPECIAL: return SPECIAL[tv]
    return tv.split(":",1)[1]

def wilder_rsi(series, n):
    delta = series.diff()
    up = delta.clip(lower=0.0)
    dn = (-delta).clip(lower=0.0)
    # Wilder smoothing = EMA with alpha 1/n
    ru = up.ewm(alpha=1.0/n, min_periods=n, adjust=False).mean()
    rd = dn.ewm(alpha=1.0/n, min_periods=n, adjust=False).mean()
    rs = ru / rd.replace(0.0, np.nan)
    rsi = 100.0 - 100.0/(1.0+rs)
    return rsi.fillna(100.0).where(rd.notna(), np.nan)

def bxtrender(close, s1=5, s2=20, s3=15, l1=20, l2=15):
    short = wilder_rsi(close.ewm(span=s1, adjust=False).mean()
                       - close.ewm(span=s2, adjust=False).mean(), s3) - 50.0
    long_ = wilder_rsi(close.ewm(span=l1, adjust=False).mean(), l2) - 50.0
    return short, long_

def classify(short, long_):
    """Return (signal, detail) from the last bars of the two series."""
    s0, s1v = float(short.iloc[-1]), float(short.iloc[-2])
    l0, l1v = float(long_.iloc[-1]), float(long_.iloc[-2])
    s_rising, l_rising = s0 > s1v, l0 > l1v
    # bars since short-term zero cross (sign change), scan last 5
    cross_up = None
    sv = short.values
    for k in range(1, 6):
        if len(sv) > k and sv[-k] > 0 >= sv[-k-1]:
            cross_up = k-1; break
    if l0 > 0 and s0 > 0 and s_rising and l_rising:  sig = "STRONG BUY"
    elif cross_up is not None and l0 > 0:            sig = "FRESH BUY"
    elif cross_up is not None:                       sig = "EARLY BUY (long<0)"
    elif s0 < 0 and s_rising and l_rising:           sig = "TURNING"
    elif s0 > 0 and not s_rising:                    sig = "HOLD (fading)"
    elif s0 > 0:                                     sig = "HOLD"
    elif not s_rising and l0 < 0:                    sig = "SELL"
    else:                                            sig = "WEAK"
    return sig, dict(short=round(s0,2), short_prev=round(s1v,2), long=round(l0,2),
                     long_prev=round(l1v,2), short_rising=s_rising, long_rising=l_rising,
                     cross_up_bars_ago=cross_up)

def main():
    yfs = {tv: to_yf(tv) for tv in TV_SYMBOLS}
    tickers = sorted(set(yfs.values()))
    raw = yf.download(tickers, period="1y", interval="1d", group_by="ticker",
                      auto_adjust=True, threads=True, progress=False)
    rows, missing = [], []
    for tv, y in yfs.items():
        try:
            df = raw[y].dropna(subset=["Close"])
            if len(df) < 60: missing.append(tv); continue
            short, long_ = bxtrender(df["Close"])
            if math.isnan(short.iloc[-1]) or math.isnan(long_.iloc[-1]):
                missing.append(tv); continue
            sig, det = classify(short, long_)
            rows.append(dict(tv=tv, yf=y, close=round(float(df["Close"].iloc[-1]),2),
                             asof=str(df.index[-1].date()), signal=sig, **det))
        except Exception:
            missing.append(tv)
    order = {"STRONG BUY":0,"FRESH BUY":1,"EARLY BUY (long<0)":2,"TURNING":3,
             "HOLD":4,"HOLD (fading)":5,"WEAK":6,"SELL":7}
    rows.sort(key=lambda r: (order.get(r["signal"], 9), -r["long"]))
    out = dict(generated=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
               n=len(rows), missing=missing, rows=rows)
    if "--json" in sys.argv:
        json.dump(out, open(sys.argv[sys.argv.index("--json")+1], "w"), indent=1)
    hdr = f"{'TICKER':10s} {'CLOSE':>10s} {'SHORT':>7s} {'LONG':>7s} {'S^':>3s} {'L^':>3s} {'XUP':>4s}  SIGNAL"
    print("B-Xtrender scan", out["generated"], "| bars as of", rows[0]["asof"] if rows else "?")
    cur = None
    for r in rows:
        if r["signal"] != cur:
            cur = r["signal"]; print(f"\n== {cur} =="); print(hdr)
        print(f"{r['tv'].split(':')[1]:10s} {r['close']:>10.2f} {r['short']:>7.2f} {r['long']:>7.2f} "
              f"{'Y' if r['short_rising'] else '.':>3s} {'Y' if r['long_rising'] else '.':>3s} "
              f"{str(r['cross_up_bars_ago']) if r['cross_up_bars_ago'] is not None else '-':>4s}  {r['signal']}")
    if missing: print("\nMISSING:", ", ".join(missing))

if __name__ == "__main__":
    main()
