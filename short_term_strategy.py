"""
AI Portfolio 短线交易策略 (1-5 日持仓)
=====================================
针对 AI_Portfolios.xlsx 中所有股票、大盘指数和加密货币,
识别 4 类短线交易设置并给出入场/止损/目标/R:R。

设置类型:
  🚀 动量突破 Momentum Breakout  — 突破 20 日高点 + 放量, 1-3 日
  📉📈 回调买入 Pullback Buy     — 上升趋势回调至 MA10, 2-5 日
  📈 趋势跟随 Momentum Continue  — MA5>MA10>MA20 + MACD 放大, 2-5 日
  ⚡ 超卖反弹 Oversold Bounce    — RSI<32 阳线反转, 1-3 日 (高风险)
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
import sys
import io

warnings.filterwarnings('ignore')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)


# ══════════════════════════════════════════════════════════════════════════
#  TICKER 映射 (与 stock_analysis.py 对齐, 涵盖 Excel 中所有标的)
# ══════════════════════════════════════════════════════════════════════════
TICKER_MAP = {
    # Hyperscaler
    'Alphabet': 'GOOGL', 'Amazon': 'AMZN', 'Meta': 'META', 'Microsoft': 'MSFT', 'Apple': 'AAPL',
    # Self-Driving
    'Tesla': 'TSLA', 'PONY': 'PONY', 'Uber': 'UBER', 'GRAB': 'GRAB',
    # Robotics
    'SERV': 'SERV', 'PATH': 'PATH', 'Intuitive Surgical': 'ISRG',
    # Semis
    'Nvdia': 'NVDA', 'AMD': 'AMD', 'Broadcom': 'AVGO', 'Taiwan Semis': 'TSM', 'ARMs': 'ARM',
    'Marvel': 'MRVL', 'Micron': 'MU', 'Intel': 'INTC', 'SMCI': 'SMCI', 'ANET': 'ANET',
    'Dell': 'DELL', 'ASML': 'ASML', 'QCOM': 'QCOM',
    # AI Infrastructure
    'Coreweave': 'CRWV', 'Oracle': 'ORCL', 'Iren': 'IREN', 'NBIS': 'NBIS', 'CIFR': 'CIFR',
    'APLD': 'APLD', 'CSCO': 'CSCO',
    # Energy
    'Okolo': 'OKLO', 'LAC': 'LAC', 'MP': 'MP', 'SMR': 'SMR', 'BE': 'BE',
    'ONDS': 'ONDS', 'QS': 'QS', 'EOSE': 'EOSE',
    # Software
    'Palantir': 'PLTR', 'Snowflake': 'SNOW', 'C3 AI': 'AI', 'IBM': 'IBM', 'Mongodb': 'MDB',
    'ServiceNow': 'NOW', 'Salesforce': 'CRM', 'ADBE': 'ADBE', 'OKTA': 'OKTA', 'SHOP': 'SHOP',
    'Soundhound': 'SOUN', 'BBAI': 'BBAI', 'UPST': 'UPST', 'Duolingo': 'DUOL', 'Rubrik': 'RBRK',
    'DDOG': 'DDOG', 'Netflix': 'NFLX', 'ZETA': 'ZETA', 'Spotify': 'SPOT', 'Applovin': 'APP',
    'RDDT': 'RDDT', 'TTD': 'TTD', 'RBLX': 'RBLX', 'U': 'U', 'INFY': 'INFY',
    'ALAB': 'ALAB', 'CRDO': 'CRDO', 'Wolfspeed': 'WOLF', 'SNPS': 'SNPS',
    'Crowdstrike': 'CRWD', 'Palo Alto': 'PANW', 'Zscaler': 'ZS',
    # Health
    'United Health': 'UNH', 'Oscar': 'OSCR', 'HIMS': 'HIMS', 'RXRX': 'RXRX', 'LLY': 'LLY',
    'TEM': 'TEM', 'CRSP': 'CRSP', 'TMDX': 'TMDX',
    # Space
    'Rocketlab': 'RKLB', 'FLY': 'FLY', 'JOBY': 'JOBY', 'ACHR': 'ACHR', 'LUNR': 'LUNR', 'ASTS': 'ASTS',
    # China
    'BABA': 'BABA', 'BIDU': 'BIDU', 'JD': 'JD', 'XPEV': 'XPEV', 'NIO': 'NIO', 'PDD': 'PDD',
    'FUTU': 'FUTU', 'Tencent': 'TCEHY',
    # Crypto
    'Bitcoin': 'BTC-USD', 'Ethereum': 'ETH-USD', 'Ripple': 'XRP-USD', 'Solana': 'SOL-USD',
    'Cardana': 'ADA-USD', 'BMNR': 'BMNR', 'MSTR': 'MSTR', 'COIN': 'COIN',
    'CLSK': 'CLSK', 'RIOT': 'RIOT', 'MARA': 'MARA', 'SBET': 'SBET', 'HUT': 'HUT',
    'DOGE': 'DOGE-USD', 'PEPE': 'PEPE24478-USD', 'FIG': 'FIG', 'CRCL': 'CRCL', 'XYZ': 'XYZ',
    'Bullish': 'BULL', 'HIVE': 'HIVE',
    # Finance
    'Sofi': 'SOFI', 'OPEN': 'OPEN', 'LMND': 'LMND', 'HOOD': 'HOOD', 'BULL': 'BULL',
    'Paypal': 'PYPL', 'AFRM': 'AFRM',
    # Quantum
    'RGTI': 'RGTI', 'IONQ': 'IONQ', 'QUBT': 'QUBT', 'QBTS': 'QBTS',
    # Trading
    'GME': 'GME', 'LULU': 'LULU', 'CMG': 'CMG', 'UPS': 'UPS', 'Airbnb': 'ABNB',
    'Peloton': 'PTON', 'Boeing': 'BA', 'Nike': 'NKE',
    # Commodity ETF proxies (2026-08-24 fix: these xlsx rows previously resolved
    # to invalid tickers via val.upper() — 'Gold' accidentally hit Barrick)
    'Gold': 'GLD', 'Silver': 'SLV', 'Copper': 'CPER', 'Oil(USO)': 'USO',
}

INDEX_MAP = {
    'Nasdaq':       '^IXIC',
    'S&P 500':      '^GSPC',
    'Dow Jones':    '^DJI',
    'Russell 2000': '^RUT',
    'Hang Seng':    '^HSI',
    'A股上证':       '000001.SS',
}


def load_stocks_from_excel(filepath):
    """读取 Excel 中所有标的, 去重返回 (name, ticker, sector) 列表。"""
    df = pd.read_excel(filepath, sheet_name='AI')
    stocks, skip_cols = [], ['Index']
    for col in df.columns:
        if col in skip_cols:
            continue
        for val in df[col].dropna():
            val = str(val).strip()
            if val and val != 'nan':
                ticker = TICKER_MAP.get(val, val.upper())
                stocks.append((val, ticker, col))
    seen, unique = set(), []
    for name, ticker, sector in stocks:
        if ticker not in seen:
            seen.add(ticker)
            unique.append((name, ticker, sector))
    return unique


def compute_indicators(df):
    """短线技术指标。"""
    close, high, low, volume = df['Close'], df['High'], df['Low'], df['Volume']

    df['MA5']  = close.rolling(5).mean()
    df['MA10'] = close.rolling(10).mean()
    df['MA20'] = close.rolling(20).mean()
    df['MA50'] = close.rolling(50).mean()

    # ATR(14) - 用于基于波动率的止损/目标位
    tr = pd.concat([high - low,
                    (high - close.shift()).abs(),
                    (low  - close.shift()).abs()], axis=1).max(axis=1)
    df['ATR']     = tr.rolling(14).mean()
    df['ATR_pct'] = df['ATR'] / close * 100

    # RSI(14) 和 RSI(7) - 快 RSI 用于短线
    for p in (14, 7):
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(p).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(p).mean()
        rs = gain / loss.replace(0, np.nan)
        df[f'RSI{p}'] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    df['MACD']      = ema12 - ema26
    df['Signal']    = df['MACD'].ewm(span=9).mean()
    df['MACD_Hist'] = df['MACD'] - df['Signal']

    # 随机指标 Stochastic(14,3)
    low14  = low.rolling(14).min()
    high14 = high.rolling(14).max()
    df['Stoch_K'] = 100 * (close - low14) / (high14 - low14).replace(0, np.nan)
    df['Stoch_D'] = df['Stoch_K'].rolling(3).mean()

    # 成交量比率 (vs 20 日均量)
    df['Vol_MA20']  = volume.rolling(20).mean()
    df['Vol_Ratio'] = volume / df['Vol_MA20'].replace(0, np.nan)

    return df


def _f(row, k):
    v = row.get(k, np.nan)
    try:
        v = float(v)
    except (TypeError, ValueError):
        return np.nan
    return v if not np.isnan(v) else np.nan


def detect_setup(data):
    """识别最佳短线交易设置, 返回 dict 或 None。"""
    if len(data) < 25:
        return None

    latest = data.iloc[-1]
    prev   = data.iloc[-2]

    close = _f(latest, 'Close')
    high  = _f(latest, 'High')
    low   = _f(latest, 'Low')
    open_ = _f(latest, 'Open')
    prev_close = _f(prev, 'Close')
    prev_hist  = _f(prev, 'MACD_Hist')

    ma5, ma10, ma20, ma50 = _f(latest,'MA5'), _f(latest,'MA10'), _f(latest,'MA20'), _f(latest,'MA50')
    rsi14, rsi7 = _f(latest,'RSI14'), _f(latest,'RSI7')
    atr   = _f(latest,'ATR')
    stoch_k = _f(latest,'Stoch_K')
    hist  = _f(latest,'MACD_Hist')
    vol_ratio = _f(latest,'Vol_Ratio')

    bullish = close > open_

    prior20_high = float(data['High'].iloc[-21:-1].max()) if len(data) >= 21 else np.nan
    recent_high10 = float(data['High'].iloc[-11:-1].max()) if len(data) >= 11 else np.nan

    setups = []

    # ─── 1. 动量突破 ───────────────────────────────
    if not np.isnan(prior20_high) and not np.isnan(atr) and not np.isnan(ma20):
        if (close > prior20_high and close > ma20 and bullish
                and not np.isnan(vol_ratio) and vol_ratio > 1.3):
            conv = 'HIGH' if (vol_ratio > 1.8 and not np.isnan(rsi14) and rsi14 < 75) else 'MED'
            # 止损: 突破位或当日低点下方 0.3 ATR 中较高者, 限制最大风险
            stop = max(prior20_high - atr * 0.3, low - atr * 0.3, close - atr * 1.5)
            setups.append({
                'type': '动量突破', 'emoji': '🚀', 'conviction': conv,
                'entry_low':  close * 0.998,
                'entry_high': close * 1.005,
                'stop':       stop,
                'target1':    close + atr * 1.5,
                'target2':    close + atr * 3.0,
                'horizon':    '1-3 日',
                'notes': [
                    f'突破 20 日高点 ${prior20_high:.2f}',
                    f'量能 {vol_ratio:.1f}x 均量',
                    f'RSI14 {rsi14:.0f}' if not np.isnan(rsi14) else '',
                ],
            })

    # ─── 2. 回调买入 (上升趋势中) ────────────────
    if all(not np.isnan(x) for x in (ma5, ma10, ma20, atr)):
        uptrend         = close > ma20 * 0.98 and ma5 > ma20 and ma10 > ma20
        pullback_ma10   = low <= ma10 * 1.01 and close >= ma10 * 0.98
        short_oversold  = ((not np.isnan(rsi7) and rsi7 < 45)
                           or (not np.isnan(stoch_k) and stoch_k < 35))
        if uptrend and pullback_ma10 and short_oversold:
            conv = 'HIGH' if (bullish and close > prev_close) else 'MED'
            # 止损: 取 MA10-0.5ATR 和近期低点-0.3ATR 中更低者, 但不宽于 close-1.5ATR
            stop = max(min(ma10 - atr * 0.5, low - atr * 0.3), close - atr * 1.5)
            t1 = close + atr * 1.5
            t2 = max(recent_high10 if not np.isnan(recent_high10) else 0,
                     close + atr * 3.0, t1 * 1.02)
            setups.append({
                'type': '回调买入', 'emoji': '📉📈', 'conviction': conv,
                'entry_low':  ma10 * 0.995,
                'entry_high': close * 1.005,
                'stop':       stop,
                'target1':    t1,
                'target2':    t2,
                'horizon':    '2-5 日',
                'notes': [
                    '上升趋势中回调至 MA10',
                    f'RSI7 {rsi7:.0f} 短线超卖' if not np.isnan(rsi7) else '',
                    ('今日阳线反弹确认' if (bullish and close > prev_close)
                     else '待阳线反弹确认'),
                ],
            })

    # ─── 3. 趋势跟随 ──────────────────────────────
    if all(not np.isnan(x) for x in (ma5, ma10, ma20, hist, rsi14, atr)):
        trend_ok      = ma5 > ma10 > ma20 and close > ma5
        macd_rising   = hist > 0 and (np.isnan(prev_hist) or hist > prev_hist)
        rsi_healthy   = 50 < rsi14 < 72
        not_new_high  = np.isnan(prior20_high) or close <= prior20_high
        if trend_ok and macd_rising and rsi_healthy and not_new_high:
            conv = 'HIGH' if (not np.isnan(vol_ratio) and vol_ratio > 1.2) else 'MED'
            # 止损: MA10 下方 0.3 ATR, 但不超过 close - 1.5*ATR (限制过热股的止损宽度)
            stop = max(ma10 - atr * 0.3, close - atr * 1.5)
            t1 = close + atr * 1.5
            # 目标2: 突破前高或 3 ATR, 取较大者; 确保 > t1
            t2 = max(prior20_high if not np.isnan(prior20_high) else 0,
                     close + atr * 3.0, t1 * 1.02)
            setups.append({
                'type': '趋势跟随', 'emoji': '📈', 'conviction': conv,
                'entry_low':  close * 0.998,
                'entry_high': close * 1.005,
                'stop':       stop,
                'target1':    t1,
                'target2':    t2,
                'horizon':    '2-5 日',
                'notes': [
                    'MA5 > MA10 > MA20 多头排列',
                    f'MACD 柱放大, RSI {rsi14:.0f}',
                    f'量能 {vol_ratio:.1f}x' if not np.isnan(vol_ratio) else '',
                ],
            })

    # ─── 4. 超卖反弹 (逆势, 高风险) ───────────────
    if not np.isnan(rsi14) and rsi14 < 32 and not np.isnan(atr):
        bullish_rev = bullish and close > prev_close
        in_range    = not np.isnan(ma50) and close > ma50 * 0.9
        if bullish_rev and in_range:
            t1 = ma20 if (not np.isnan(ma20) and ma20 > close) else close + atr * 1.5
            t2 = max(close + atr * 3.0, t1 * 1.02)
            setups.append({
                'type': '超卖反弹', 'emoji': '⚡', 'conviction': 'LOW',
                'entry_low':  close * 0.995,
                'entry_high': close * 1.005,
                'stop':       max(low - atr * 0.3, close - atr * 1.5),
                'target1':    t1,
                'target2':    t2,
                'horizon':    '1-3 日 (高风险)',
                'notes': [
                    f'RSI14 {rsi14:.0f} 深度超卖',
                    '阳线反转确认',
                    '逆势反弹, 仓位宜轻',
                ],
            })

    if not setups:
        return None
    rank = {'HIGH': 3, 'MED': 2, 'LOW': 1}
    setups.sort(key=lambda s: rank[s['conviction']], reverse=True)
    return setups[0]


def classify_avoid(data):
    """判断该标的是否应短线回避, 返回原因列表。"""
    latest = data.iloc[-1]
    close = _f(latest, 'Close')
    ma5, ma10, ma20 = _f(latest,'MA5'), _f(latest,'MA10'), _f(latest,'MA20')
    rsi14 = _f(latest, 'RSI14')
    hist  = _f(latest, 'MACD_Hist')

    pct_5d = 0.0
    if len(data) >= 5:
        p5 = float(data['Close'].iloc[-5])
        if p5 != 0:
            pct_5d = (close - p5) / p5 * 100

    reasons = []
    if all(not np.isnan(x) for x in (ma5, ma10, ma20)):
        if ma5 < ma10 < ma20 and close < ma5:
            reasons.append('短线空头排列')
    if not np.isnan(hist) and hist < 0 and close < (ma10 if not np.isnan(ma10) else close + 1):
        reasons.append('MACD 零轴下方')
    if not np.isnan(rsi14) and rsi14 > 80:
        reasons.append(f'RSI {rsi14:.0f} 严重超买')
    if pct_5d < -10:
        reasons.append(f'5 日跌幅 {pct_5d:.1f}%')
    return reasons


def _get_live_price(ticker: str, fallback: float) -> float:
    """Return the most recent traded price.

    Order of preference (each gracefully falls through on failure):
      1. fast_info.last_price / regularMarketPrice (real-time / 15m delayed quote)
      2. 1-minute intraday history close (today's most recent bar)
      3. Provided fallback (typically last daily close — flagged as stale)
    """
    try:
        fi = yf.Ticker(ticker).fast_info
        p = fi.get('last_price') or fi.get('regularMarketPrice')
        if p and float(p) > 0:
            return float(p)
    except Exception:
        pass
    try:
        intraday = yf.Ticker(ticker).history(period='1d', interval='1m', auto_adjust=False)
        if not intraday.empty:
            closes = intraday['Close'].dropna()
            if len(closes) > 0 and float(closes.iloc[-1]) > 0:
                return float(closes.iloc[-1])
    except Exception:
        pass
    return fallback


def analyze_short_term(ticker, name, sector):
    """对单只标的执行短线分析。"""
    try:
        data = yf.download(ticker, period='6mo', progress=False, auto_adjust=True)
        if data.empty or len(data) < 30:
            return None
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        data = compute_indicators(data)

        latest = data.iloc[-1]
        close = _get_live_price(ticker, float(latest['Close']))

        setup = detect_setup(data)
        avoid = classify_avoid(data)

        if setup:
            action = '✅ 入场'
        elif len(avoid) >= 2:
            action = '🚫 回避'
        else:
            action = '👀 观察'

        def pct(n):
            if len(data) < n + 1: return 0.0
            p = float(data['Close'].iloc[-n-1])
            return (close - p) / p * 100 if p != 0 else 0.0

        def gg(k):
            v = latest.get(k, np.nan)
            return float(v) if pd.notna(v) else None

        return {
            'name': name, 'ticker': ticker, 'sector': sector, 'price': close,
            'pct_1d': pct(1), 'pct_3d': pct(3), 'pct_5d': pct(5),
            'rsi14': gg('RSI14'), 'rsi7': gg('RSI7'),
            'atr': gg('ATR'), 'atr_pct': gg('ATR_pct'),
            'vol_ratio': gg('Vol_Ratio'),
            'action': action, 'setup': setup, 'avoid_reasons': avoid,
        }
    except Exception as e:
        return {
            'name': name, 'ticker': ticker, 'sector': sector, 'price': 0.0,
            'action': '❌ 失败', 'setup': None, 'avoid_reasons': [str(e)[:40]],
            'pct_1d': 0, 'pct_3d': 0, 'pct_5d': 0,
            'rsi14': None, 'rsi7': None, 'atr': None, 'atr_pct': None, 'vol_ratio': None,
        }


def format_entry_card(r):
    """打印入场机会的详细卡片。"""
    s = r['setup']
    price = r['price']

    lines = []
    lines.append(f"  [{r['sector']}] {r['name']} ({r['ticker']})")

    rsi_s = f"RSI14={r['rsi14']:.0f}" if r['rsi14'] is not None else 'RSI=-'
    atr_s = f"ATR={r['atr_pct']:.1f}%" if r['atr_pct'] is not None else 'ATR=-'
    vol_s = f"量={r['vol_ratio']:.1f}x" if r['vol_ratio'] is not None else '量=-'
    lines.append(
        f"    价格: ${price:.2f}  |  "
        f"日{r['pct_1d']:+.2f}% / 3日{r['pct_3d']:+.2f}% / 5日{r['pct_5d']:+.2f}%  |  "
        f"{rsi_s} / {atr_s} / {vol_s}"
    )
    lines.append(f"    设置: {s['emoji']} {s['type']}  ({s['conviction']} 信心, 持仓 {s['horizon']})")

    stop_pct = (price - s['stop']) / price * 100 if price else 0
    t1_pct   = (s['target1'] - price) / price * 100 if price else 0
    t2_pct   = (s['target2'] - price) / price * 100 if price else 0
    rr1 = abs(t1_pct / stop_pct) if stop_pct else 0
    rr2 = abs(t2_pct / stop_pct) if stop_pct else 0

    lines.append(f"    入场区: ${s['entry_low']:.2f} - ${s['entry_high']:.2f}")
    lines.append(f"    止损:   ${s['stop']:.2f} (-{stop_pct:.1f}%)")
    lines.append(f"    目标1:  ${s['target1']:.2f} (+{t1_pct:.1f}%)  R:R = {rr1:.1f}")
    lines.append(f"    目标2:  ${s['target2']:.2f} (+{t2_pct:.1f}%)  R:R = {rr2:.1f}")
    notes = [n for n in s['notes'] if n]
    if notes:
        lines.append(f"    要点:   {' | '.join(notes)}")
    return '\n'.join(lines)


def compute_index_short_term(ticker, name):
    """Fetch + compute index short-term snapshot. Returns dict or None.
    Pure compute (no print) so it can run in a ThreadPoolExecutor."""
    try:
        data = yf.download(ticker, period='6mo', progress=False, auto_adjust=True)
        if data.empty or len(data) < 30:
            return None
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        data = compute_indicators(data)
        latest = data.iloc[-1]
        # Use live price so macro index headers reflect intraday move, not yesterday's close.
        close = _get_live_price(ticker, float(latest['Close']))
        rsi14 = latest.get('RSI14')
        ma5, ma10, ma20 = latest.get('MA5'), latest.get('MA10'), latest.get('MA20')
        atr_pct = latest.get('ATR_pct')

        def pct(n):
            if len(data) < n + 1: return 0.0
            p = float(data['Close'].iloc[-n-1])
            return (close - p) / p * 100 if p else 0.0

        if all(pd.notna(x) for x in (ma5, ma10, ma20)):
            if close > ma5 > ma10 > ma20:    dir_ = '多头 🟢'
            elif close < ma5 < ma10 < ma20:  dir_ = '空头 🔴'
            elif close > ma10 and ma5 > ma10: dir_ = '偏多 🟡'
            elif close < ma10 and ma5 < ma10: dir_ = '偏空 🟠'
            else:                             dir_ = '震荡 ⚪'
        else:
            dir_ = '-'

        return {
            'name': name, 'ticker': ticker, 'close': close,
            'rsi14': float(rsi14) if pd.notna(rsi14) else None,
            'atr_pct': float(atr_pct) if pd.notna(atr_pct) else None,
            'pct_1d': pct(1), 'pct_3d': pct(3), 'pct_5d': pct(5),
            'dir_': dir_,
        }
    except Exception:
        return None


def print_index_short_term(idx):
    """Print one index snapshot dict produced by compute_index_short_term."""
    if idx is None:
        return  # caller already printed the placeholder line
    rsi_s = f"RSI={idx['rsi14']:.0f}" if idx['rsi14'] is not None else 'RSI=-'
    atr_s = f"ATR={idx['atr_pct']:.1f}%" if idx['atr_pct'] is not None else 'ATR=-'
    price_s = f"${idx['close']:,.2f}" if idx['close'] > 10 else f"${idx['close']:.4f}"
    print(f"  {idx['name']:<14} {price_s:<13} "
          f"日{idx['pct_1d']:+.2f}% / 3日{idx['pct_3d']:+.2f}% / 5日{idx['pct_5d']:+.2f}%  "
          f"{rsi_s}  {atr_s}  {idx['dir_']}")


def write_markdown_report(results, indices_data, entries, watches, avoids, failed, out_path):
    """Persist a deterministic markdown digest so the SKILL doesn't have to scrape stdout."""
    lines = []
    lines.append("# 短线交易策略报告 (持仓 1-5 日)")
    lines.append("")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**分析范围**: {len(results)} 只标的")
    lines.append("")

    # 大盘
    lines.append("## 🌐 大盘短线状态")
    lines.append("")
    lines.append("| 指数 | 现价 | 1日 | 3日 | 5日 | RSI | ATR | 方向 |")
    lines.append("|------|------|------|------|------|-----|-----|------|")
    for name in INDEX_MAP.keys():
        idx = indices_data.get(name)
        if idx is None:
            lines.append(f"| {name} | - | - | - | - | - | - | 数据获取失败 |")
            continue
        price_s = f"${idx['close']:,.2f}" if idx['close'] > 10 else f"${idx['close']:.4f}"
        rsi_s = f"{idx['rsi14']:.0f}" if idx['rsi14'] is not None else '-'
        atr_s = f"{idx['atr_pct']:.1f}%" if idx['atr_pct'] is not None else '-'
        lines.append(
            f"| **{name}** | {price_s} | {idx['pct_1d']:+.2f}% | {idx['pct_3d']:+.2f}% | "
            f"{idx['pct_5d']:+.2f}% | {rsi_s} | {atr_s} | {idx['dir_']} |"
        )
    lines.append("")

    # 入场机会
    lines.append(f"## 🎯 短线入场机会 ({len(entries)})")
    lines.append("")
    if not entries:
        lines.append("今日无明确短线入场信号。")
        lines.append("")
    else:
        lines.append("| 信心 | 设置 | 标的 | 板块 | 价格 | 入场区 | 止损 | 目标1 | 目标2 | RR1 | RSI14 | 5日 |")
        lines.append("|------|------|------|------|------|--------|------|-------|-------|-----|-------|------|")
        for r in entries:
            s = r['setup']
            stop_pct = (r['price'] - s['stop']) / r['price'] * 100 if r['price'] else 0
            t1_pct = (s['target1'] - r['price']) / r['price'] * 100 if r['price'] else 0
            rr1 = abs(t1_pct / stop_pct) if stop_pct else 0
            rsi_s = f"{r['rsi14']:.0f}" if r['rsi14'] is not None else '-'
            lines.append(
                f"| **{s['conviction']}** | {s['emoji']} {s['type']} | **{r['ticker']}** ({r['name']}) | "
                f"{r['sector']} | ${r['price']:.2f} | ${s['entry_low']:.2f} - ${s['entry_high']:.2f} | "
                f"${s['stop']:.2f} (-{stop_pct:.1f}%) | ${s['target1']:.2f} (+{t1_pct:.1f}%) | "
                f"${s['target2']:.2f} | {rr1:.1f} | {rsi_s} | {r['pct_5d']:+.2f}% |"
            )
        lines.append("")

        # Per-entry detail with notes
        lines.append("### 入场卡详情")
        lines.append("")
        for r in entries:
            s = r['setup']
            lines.append(f"#### {s['emoji']} {r['name']} ({r['ticker']}) — {s['type']} ({s['conviction']} 信心)")
            lines.append(f"- 板块: {r['sector']} · 价格 ${r['price']:.2f} · 持仓 {s['horizon']}")
            stop_pct = (r['price'] - s['stop']) / r['price'] * 100 if r['price'] else 0
            t1_pct = (s['target1'] - r['price']) / r['price'] * 100 if r['price'] else 0
            t2_pct = (s['target2'] - r['price']) / r['price'] * 100 if r['price'] else 0
            rr1 = abs(t1_pct / stop_pct) if stop_pct else 0
            rr2 = abs(t2_pct / stop_pct) if stop_pct else 0
            lines.append(f"- 入场区: ${s['entry_low']:.2f} - ${s['entry_high']:.2f}")
            lines.append(f"- 止损: ${s['stop']:.2f} (-{stop_pct:.1f}%)")
            lines.append(f"- 目标1: ${s['target1']:.2f} (+{t1_pct:.1f}%) RR={rr1:.1f}")
            lines.append(f"- 目标2: ${s['target2']:.2f} (+{t2_pct:.1f}%) RR={rr2:.1f}")
            notes = [n for n in s['notes'] if n]
            if notes:
                lines.append(f"- 要点: {' | '.join(notes)}")
            lines.append("")

    # 观察
    lines.append(f"## 👀 观察区 ({len(watches)})")
    lines.append("")
    if watches:
        lines.append("| 板块 | 标的 | 价格 | 1日 | 3日 | 5日 | RSI |")
        lines.append("|------|------|------|------|------|------|-----|")
        for r in sorted(watches, key=lambda x: x['pct_3d'], reverse=True):
            rsi_s = f"{r['rsi14']:.0f}" if r['rsi14'] is not None else '-'
            lines.append(
                f"| {r['sector']} | {r['ticker']} ({r['name']}) | ${r['price']:.2f} | "
                f"{r['pct_1d']:+.2f}% | {r['pct_3d']:+.2f}% | {r['pct_5d']:+.2f}% | {rsi_s} |"
            )
        lines.append("")

    # 回避
    lines.append(f"## 🚫 回避 ({len(avoids)})")
    lines.append("")
    if avoids:
        lines.append("| 板块 | 标的 | 价格 | 5日 | RSI | 原因 |")
        lines.append("|------|------|------|------|-----|------|")
        for r in sorted(avoids, key=lambda x: x['pct_5d']):
            rsi_s = f"{r['rsi14']:.0f}" if r['rsi14'] is not None else '-'
            lines.append(
                f"| {r['sector']} | {r['ticker']} ({r['name']}) | ${r['price']:.2f} | "
                f"{r['pct_5d']:+.2f}% | {rsi_s} | {'; '.join(r['avoid_reasons'])} |"
            )
        lines.append("")

    # 总结
    lines.append("## 📊 总结")
    lines.append("")
    lines.append(f"- ✅ 入场机会: {len(entries)} 只")
    if entries:
        high = sum(1 for r in entries if r['setup']['conviction'] == 'HIGH')
        med = sum(1 for r in entries if r['setup']['conviction'] == 'MED')
        low = sum(1 for r in entries if r['setup']['conviction'] == 'LOW')
        lines.append(f"  - 高信心: {high} | 中信心: {med} | 低信心: {low}")
        types = Counter(r['setup']['type'] for r in entries)
        for t, c in types.most_common():
            lines.append(f"  - {t}: {c}")
    lines.append(f"- 👀 观察: {len(watches)} 只")
    lines.append(f"- 🚫 回避: {len(avoids)} 只")
    if failed:
        lines.append(f"- ❌ 数据失败: {len(failed)} 只")
    lines.append("")

    out_path.write_text('\n'.join(lines), encoding='utf-8')


def main():
    filepath = Path(__file__).parent / 'AI_Portfolios.xlsx'
    print(f"{'='*90}")
    print(f"  ⚡ AI Portfolio 短线交易策略 (持仓 1-5 日)")
    print(f"  分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*90}\n")

    # 大盘短线背景 (并行抓取)
    print(f"{'='*90}")
    print(f"  🌐 大盘短线状态 (为短线仓位提供方向背景)")
    print(f"{'='*90}")
    indices_data = {}
    with ThreadPoolExecutor(max_workers=len(INDEX_MAP)) as ex:
        futs = {ex.submit(compute_index_short_term, ticker, name): name
                for name, ticker in INDEX_MAP.items()}
        for fut in as_completed(futs):
            indices_data[futs[fut]] = fut.result()
    for name in INDEX_MAP.keys():  # preserve order
        idx = indices_data.get(name)
        if idx is None:
            print(f"  {name:<14} 数据获取失败")
        else:
            print_index_short_term(idx)
    print(f"{'='*90}\n")

    stocks = load_stocks_from_excel(str(filepath))
    total = len(stocks)
    print(f"共发现 {total} 只标的, 并行计算短线信号 (max_workers=15)...\n")

    results = []
    done = 0
    with ThreadPoolExecutor(max_workers=15) as ex:
        futs = {ex.submit(analyze_short_term, ticker, name, sector): (name, ticker, sector)
                for name, ticker, sector in stocks}
        for fut in as_completed(futs):
            done += 1
            try:
                r = fut.result()
            except Exception as e:
                name, ticker, sector = futs[fut]
                r = {
                    'name': name, 'ticker': ticker, 'sector': sector, 'price': 0.0,
                    'action': '❌ 失败', 'setup': None, 'avoid_reasons': [str(e)[:40]],
                    'pct_1d': 0, 'pct_3d': 0, 'pct_5d': 0,
                    'rsi14': None, 'rsi7': None, 'atr': None, 'atr_pct': None, 'vol_ratio': None,
                }
            if r:
                results.append(r)
            if done % 20 == 0 or done == total:
                print(f"  已完成 {done}/{total}", flush=True)
    print()

    entries = [r for r in results if r['action'].startswith('✅')]
    watches = [r for r in results if r['action'].startswith('👀')]
    avoids  = [r for r in results if r['action'].startswith('🚫')]
    failed  = [r for r in results if r['action'].startswith('❌')]

    # 按信心度 + R:R 排序
    conv_rank = {'HIGH': 3, 'MED': 2, 'LOW': 1}
    def entry_key(r):
        s = r['setup']
        stop_pct = (r['price'] - s['stop']) / r['price'] * 100
        t1_pct   = (s['target1'] - r['price']) / r['price'] * 100
        rr = (t1_pct / stop_pct) if stop_pct > 0 else 0
        return (conv_rank.get(s['conviction'], 0), rr)
    entries.sort(key=entry_key, reverse=True)

    # 入场机会
    print(f"{'='*90}")
    print(f"  🎯 短线入场机会 ({len(entries)} 只) — 按信心度 & R:R 排序")
    print(f"{'='*90}\n")
    if not entries:
        print('  今日无明确短线入场信号, 市场震荡或不符合设置条件\n')
    else:
        for r in entries:
            print(format_entry_card(r))
            print()

    # 观察区
    print(f"{'='*90}")
    print(f"  👀 观察区 ({len(watches)} 只) — 信号模糊, 暂不入场, 按 3 日动量排序")
    print(f"{'='*90}")
    watches.sort(key=lambda r: r['pct_3d'], reverse=True)
    for r in watches:
        rsi_s = f"RSI={r['rsi14']:.0f}" if r['rsi14'] is not None else ''
        print(f"  [{r['sector']:<14}] {r['name']:<18} ({r['ticker']:<8}) "
              f"${r['price']:>9.2f}  "
              f"日{r['pct_1d']:+.2f}% / 3日{r['pct_3d']:+.2f}% / 5日{r['pct_5d']:+.2f}%  {rsi_s}")
    print()

    # 回避
    print(f"{'='*90}")
    print(f"  🚫 回避 ({len(avoids)} 只) — 短线不利, 不做多")
    print(f"{'='*90}")
    avoids.sort(key=lambda r: r['pct_5d'])
    for r in avoids:
        rsi_s = f"RSI={r['rsi14']:.0f}" if r['rsi14'] is not None else ''
        print(f"  [{r['sector']:<14}] {r['name']:<18} ({r['ticker']:<8}) "
              f"${r['price']:>9.2f}  5日{r['pct_5d']:+.2f}%  {rsi_s}  "
              f"→ {'; '.join(r['avoid_reasons'])}")
    print()

    # 总结
    print(f"{'='*90}")
    print(f"  📊 短线策略总结")
    print(f"{'='*90}")
    print(f"  ✅ 入场机会: {len(entries)} 只")
    if entries:
        high = sum(1 for r in entries if r['setup']['conviction'] == 'HIGH')
        med  = sum(1 for r in entries if r['setup']['conviction'] == 'MED')
        low  = sum(1 for r in entries if r['setup']['conviction'] == 'LOW')
        print(f"     高信心: {high}  |  中信心: {med}  |  低信心: {low}")
        types = Counter(r['setup']['type'] for r in entries)
        for t, c in types.most_common():
            print(f"     {t}: {c}")
    print(f"  👀 观察: {len(watches)} 只")
    print(f"  🚫 回避: {len(avoids)} 只")
    if failed:
        print(f"  ❌ 数据失败: {len(failed)} 只")

    print(f"\n{'='*90}")
    print(f"  📖 短线策略说明 (持仓 1-5 日)")
    print(f"{'='*90}")
    print(f"  设置类型:")
    print(f"    🚀 动量突破: 突破 20 日高点 + 放量 + RSI 未严重超买 → 跟势做多, 1-3 日")
    print(f"    📉📈 回调买入: 上升趋势中回调至 MA10, 短线超卖, 阳线反弹 → 2-5 日")
    print(f"    📈 趋势跟随: MA5>MA10>MA20 多头排列, MACD 柱放大 → 2-5 日")
    print(f"    ⚡ 超卖反弹: RSI14<32 深度超卖 + 阳线反转 → 1-3 日, 风险高仓位轻\n")
    print(f"  仓位建议:")
    print(f"    HIGH 信心: 标准仓位 (建议单只 2-5%)")
    print(f"    MED  信心: 减半仓位")
    print(f"    LOW  信心: 小仓试探 (超卖反弹、逆势均算)\n")
    print(f"  止损原则:")
    print(f"    严格执行止损位, 短线 = 止损是利润的保障")
    print(f"    单笔最大亏损 ≤ 账户的 1-2%")
    print(f"    目标1达到 → 减半锁利; 目标2 = 展望位, 看势头决定是否留仓\n")
    print(f"  配合大盘:")
    print(f"    大盘空头/偏空 → 只做最强动量突破, 仓位减半")
    print(f"    大盘多头      → 正常执行全部信号")
    print(f"{'='*90}\n")

    # ── Persist a deterministic markdown report so the SKILL doesn't have to scrape stdout ──
    out_path = Path(__file__).parent / f"short_term_report_{datetime.now().strftime('%Y-%m-%d')}.md"
    try:
        write_markdown_report(results, indices_data, entries, watches, avoids, failed, out_path)
        print(f"  ✅ 报告已保存: {out_path.name}")
    except Exception as e:
        print(f"  ⚠️ 报告写入失败: {e}")


if __name__ == '__main__':
    main()
