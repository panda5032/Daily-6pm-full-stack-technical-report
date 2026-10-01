"""
Technical Patterns + Volume + MACD Strategy — AI_Portfolios.xlsx
================================================================
Reads tickers directly from AI_Portfolios.xlsx and runs a composite
quantitative scoring model combining four pillars:

  1. TECHNICAL PATTERNS   — Head & Shoulders, Double Top/Bottom,
                            Triangles, Cup & Handle, Flag/Pennant,
                            Breakouts, Support/Resistance, MA crosses
  2. VOLUME ANALYSIS      — OBV trend, Volume MA, Accumulation/
                            Distribution, Volume spikes, Money Flow
  3. MACD ANALYSIS        — Golden/Death crosses, Histogram momentum,
                            Bullish/Bearish divergences, Zero-line tests
  4. BOLLINGER BANDS      — Squeeze (volatility compression), band
                            breakouts confirmed/rejected by volume+MACD,
                            band riding, midline reclaim/loss, oversold
                            lower-band bounce with RSI

Output: chinese_principles-style markdown report with BUY / HOLD /
        SELL for every stock, plus a per-pillar breakdown.

Disclaimer: algorithmic technical analysis only — not financial advice.
"""

import yfinance as yf
import pandas as pd
import numpy as np
import openpyxl
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
import sys
import io

warnings.filterwarnings('ignore')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

HERE = Path(__file__).parent
EXCEL_PATH = HERE / 'AI_Portfolios.xlsx'

# ── Company name / shorthand → ticker symbol mapping ──────────────────
NAME_TO_TICKER = {
    # Hyperscaler
    'alphabet': 'GOOGL', 'amazon': 'AMZN', 'meta': 'META',
    'microsoft': 'MSFT', 'apple': 'AAPL',
    # Self-Driving
    'tesla': 'TSLA', 'uber': 'UBER',
    # Robotics
    'intuitive surgical': 'ISRG',
    # Semis
    'nvdia': 'NVDA', 'nvidia': 'NVDA', 'broadcom': 'AVGO',
    'taiwan semis': 'TSM', 'arms': 'ARM', 'marvel': 'MRVL',
    'micron': 'MU', 'intel': 'INTC',
    # AI Infrastructure
    'coreweave': 'CRWV', 'oracle': 'ORCL', 'iren': 'IREN',
    # Energy
    'okolo': 'OKLO',
    # Software
    'palantir': 'PLTR', 'snowflake': 'SNOW', 'c3 ai': 'AI',
    'mongodb': 'MDB', 'servicenow': 'NOW', 'salesforce': 'CRM',
    'soundhound': 'SOUN', 'duolingo': 'DUOL', 'rubrik': 'RBRK',
    'netflix': 'NFLX', 'spotify': 'SPOT', 'applovin': 'APP',
    'wolfspeed': 'WOLF', 'crowdstrike': 'CRWD', 'palo alto': 'PANW',
    'zscaler': 'ZS',
    # Health
    'united health': 'UNH', 'oscar': 'OSCR',
    # Space
    'rocketlab': 'RKLB',
    # China
    'tencent': 'TCEHY',
    # Crypto
    'bitcoin': 'BTC-USD', 'ethereum': 'ETH-USD', 'ripple': 'XRP-USD',
    'solana': 'SOL-USD', 'cardana': 'ADA-USD', 'cardano': 'ADA-USD',
    'doge': 'DOGE-USD', 'pepe': 'PEPE-USD', 'bullish': 'BULL',
    # Finance
    'sofi': 'SOFI', 'paypal': 'PYPL',
    # Trading
    'airbnb': 'ABNB', 'peloton': 'PTON', 'boeing': 'BA', 'nike': 'NKE',
    # Commodity (ETF proxies — 2026-08-24 fix: these xlsx rows were silently skipped)
    'gold': 'GLD', 'silver': 'SLV', 'copper': 'CPER', 'oil(uso)': 'USO',
}


from intraday_volume import rvol_now, low_volume_threshold


def _resolve_ticker(name: str) -> str:
    """Map a name from the Excel to a yfinance ticker."""
    if not name:
        return ''
    s = str(name).strip()
    if not s:
        return ''
    key = s.lower()
    if key in NAME_TO_TICKER:
        return NAME_TO_TICKER[key]
    # already-uppercase looks like a ticker
    if s.isupper() and len(s) <= 6:
        return s
    return s.upper()


def load_portfolio() -> dict[str, list[str]]:
    """Read AI_Portfolios.xlsx and return {sector: [tickers...]}."""
    wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)
    ws = wb['AI']
    sectors: dict[str, list[str]] = {}
    # 2026-08-24 fix: was range(2, 16), which silently dropped column P (Commodity)
    # and anything added after it (Q=Rotation). Scan to the sheet's real width.
    for col_idx in range(2, ws.max_column + 1):
        sector = ws.cell(row=1, column=col_idx).value
        if not sector:
            continue
        tickers: list[str] = []
        seen: set[str] = set()
        for row_idx in range(2, 80):
            v = ws.cell(row=row_idx, column=col_idx).value
            if not v or not str(v).strip():
                continue
            t = _resolve_ticker(v)
            if t and t not in seen:
                seen.add(t)
                tickers.append(t)
        if tickers:
            sectors[str(sector).strip()] = tickers
    return sectors


# ────────────────────────── Indicator helpers ─────────────────────────
def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _macd(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal = macd_line.ewm(span=9, adjust=False).mean()
    hist = macd_line - signal
    return macd_line, signal, hist


def _obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    sign = np.sign(close.diff().fillna(0))
    return (sign * volume).cumsum()


def _bollinger(close: pd.Series, period: int = 20, std_dev: float = 2.0
               ) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    return mid, mid + std_dev * std, mid - std_dev * std


def _live_price(ticker: str, fallback: float) -> float:
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
            c = intra['Close'].dropna()
            if len(c) > 0 and float(c.iloc[-1]) > 0:
                return float(c.iloc[-1])
    except Exception:
        pass
    return fallback


# ─────────────────────── Pattern detectors ────────────────────────────
def _detect_double_bottom(low: pd.Series, close: pd.Series, live_price: float | None = None) -> tuple[bool, str]:
    """Pattern uses historical lows; current-position check uses live_price when provided."""
    if len(low) < 40:
        return False, ''
    win = low.iloc[-40:]
    sorted_lows = win.nsmallest(5)
    if len(sorted_lows) < 2:
        return False, ''
    l1, l2 = sorted_lows.iloc[0], sorted_lows.iloc[1]
    spread = abs(l1 - l2) / l1 * 100 if l1 > 0 else 100
    idx1 = win.tolist().index(l1)
    idx2 = win.tolist().index(l2)
    bars_apart = abs(idx1 - idx2)
    last_close = float(live_price) if live_price and live_price > 0 else float(close.iloc[-1])
    above = last_close > float(l1) * 1.05
    if spread < 4 and bars_apart >= 8 and above:
        return True, f'双底成立 (低点1=${l1:.2f}, 低点2=${l2:.2f}, 间隔{bars_apart}日)'
    return False, ''


def _detect_double_top(high: pd.Series, close: pd.Series, live_price: float | None = None) -> tuple[bool, str]:
    """Pattern uses historical highs; current-position check uses live_price when provided."""
    if len(high) < 40:
        return False, ''
    win = high.iloc[-40:]
    sorted_highs = win.nlargest(5)
    if len(sorted_highs) < 2:
        return False, ''
    h1, h2 = sorted_highs.iloc[0], sorted_highs.iloc[1]
    spread = abs(h1 - h2) / h1 * 100 if h1 > 0 else 100
    idx1 = win.tolist().index(h1)
    idx2 = win.tolist().index(h2)
    bars_apart = abs(idx1 - idx2)
    last_close = float(live_price) if live_price and live_price > 0 else float(close.iloc[-1])
    below = last_close < float(h1) * 0.95
    if spread < 4 and bars_apart >= 8 and below:
        return True, f'双顶成立 (高点1=${h1:.2f}, 高点2=${h2:.2f}, 间隔{bars_apart}日)'
    return False, ''


def _detect_breakout(close: pd.Series, high: pd.Series, volume: pd.Series, live_price: float | None = None) -> tuple[str, str]:
    """Return (kind, desc) where kind in {'bull','bear',''}.

    Prior 20-day high/low uses historical bars; today's breakout check uses live_price when provided
    so an intraday breakout above the prior high isn't missed during market hours.
    """
    if len(close) < 25:
        return '', ''
    last = float(live_price) if live_price and live_price > 0 else float(close.iloc[-1])
    prior_high = float(high.iloc[-21:-1].max())
    prior_low = float(close.iloc[-21:-1].min())
    vol_today = float(volume.iloc[-1])
    vol_avg = float(volume.iloc[-20:].mean())
    vol_surge = vol_today > vol_avg * 1.5 if vol_avg > 0 else False
    if last > prior_high * 1.01 and vol_surge:
        return 'bull', f'放量突破20日新高(${prior_high:.2f}), 量能{vol_today/vol_avg:.1f}x均量'
    if last > prior_high * 1.01:
        return 'bull_weak', f'突破20日新高(${prior_high:.2f}) 但量能不足({vol_today/vol_avg:.1f}x)'
    if last < prior_low * 0.99 and vol_surge:
        return 'bear', f'放量跌破20日新低(${prior_low:.2f}), 量能{vol_today/vol_avg:.1f}x均量'
    return '', ''


def _detect_ma_cross(close: pd.Series, ma50: pd.Series, ma200: pd.Series) -> tuple[str, str]:
    if len(close) < 205 or pd.isna(ma200.iloc[-1]) or pd.isna(ma50.iloc[-1]):
        return '', ''
    cur = float(ma50.iloc[-1]) - float(ma200.iloc[-1])
    prev = float(ma50.iloc[-5]) - float(ma200.iloc[-5])
    if prev < 0 and cur > 0:
        return 'golden', '金叉成立: MA50上穿MA200 (长线买入信号)'
    if prev > 0 and cur < 0:
        return 'death', '死叉成立: MA50下穿MA200 (长线卖出信号)'
    return '', ''


def _detect_cup_handle(close: pd.Series, live_price: float | None = None) -> tuple[bool, str]:
    """Lightweight cup-and-handle: U-shape over ~3-6mo with shallow handle.

    Cup/handle structure uses historical bars; final breakout check uses live_price when provided
    so intraday breaks above the right rim are caught during market hours.
    """
    if len(close) < 80:
        return False, ''
    seg = close.iloc[-80:]
    left = float(seg.iloc[:20].max())
    bottom = float(seg.iloc[20:60].min())
    right = float(seg.iloc[55:75].max())
    handle = float(seg.iloc[-10:].min())
    last = float(live_price) if live_price and live_price > 0 else float(seg.iloc[-1])
    rims_match = abs(left - right) / left * 100 < 8 if left > 0 else False
    cup_depth = (left - bottom) / left * 100 if left > 0 else 0
    handle_pull = (right - handle) / right * 100 if right > 0 else 0
    breakout = last > right * 1.005
    if rims_match and 12 < cup_depth < 50 and 0 < handle_pull < 15 and breakout:
        return True, f'杯柄形态突破 (杯深{cup_depth:.0f}%, 柄回撤{handle_pull:.1f}%)'
    return False, ''


def _detect_macd_divergence(close: pd.Series, macd_line: pd.Series) -> tuple[str, str]:
    if len(close) < 30:
        return '', ''
    c = close.iloc[-30:]
    m = macd_line.iloc[-30:]
    p_lo1 = float(c.iloc[:15].min())
    p_lo2 = float(c.iloc[15:].min())
    m_lo1 = float(m.iloc[:15].min())
    m_lo2 = float(m.iloc[15:].min())
    p_hi1 = float(c.iloc[:15].max())
    p_hi2 = float(c.iloc[15:].max())
    m_hi1 = float(m.iloc[:15].max())
    m_hi2 = float(m.iloc[15:].max())
    if p_lo2 < p_lo1 * 0.98 and m_lo2 > m_lo1:
        return 'bull_div', '价格创新低但MACD抬高 — 底背离, 反弹概率大'
    if p_hi2 > p_hi1 * 1.02 and m_hi2 < m_hi1:
        return 'bear_div', '价格创新高但MACD走低 — 顶背离, 调整概率大'
    return '', ''


# ───────────────────────── Main analyzer ──────────────────────────────
def analyze_stock(ticker: str, sector: str) -> dict | None:
    try:
        data = yf.download(ticker, period='1y', progress=False, auto_adjust=True)
        if data.empty or len(data) < 50:
            return None
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        close = data['Close'].astype(float)
        high = data['High'].astype(float)
        low = data['Low'].astype(float)
        volume = data['Volume'].astype(float)

        ma20 = close.rolling(20).mean()
        ma50 = close.rolling(50).mean()
        ma200 = close.rolling(200).mean()
        vol_ma20 = volume.rolling(20).mean()
        vol_ma50 = volume.rolling(50).mean()

        macd_line, signal_line, hist = _macd(close)
        obv = _obv(close, volume)
        rsi = _rsi(close)
        bb_mid, bb_up, bb_lo = _bollinger(close)

        price = _live_price(ticker, float(close.iloc[-1]))
        prev_close = float(close.iloc[-2])
        pct_1d = (price - prev_close) / prev_close * 100 if prev_close > 0 else 0
        pct_5d = (price - float(close.iloc[-6])) / float(close.iloc[-6]) * 100 if len(close) >= 6 else 0
        pct_20d = (price - float(close.iloc[-21])) / float(close.iloc[-21]) * 100 if len(close) >= 21 else 0

        c_ma20 = float(ma20.iloc[-1]) if pd.notna(ma20.iloc[-1]) else None
        c_ma50 = float(ma50.iloc[-1]) if pd.notna(ma50.iloc[-1]) else None
        c_ma200 = float(ma200.iloc[-1]) if pd.notna(ma200.iloc[-1]) else None

        c_macd = float(macd_line.iloc[-1])
        c_sig = float(signal_line.iloc[-1])
        c_hist = float(hist.iloc[-1])
        prev_hist = float(hist.iloc[-2]) if len(hist) >= 2 else c_hist
        c_rsi = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else None

        c_bb_mid = float(bb_mid.iloc[-1]) if pd.notna(bb_mid.iloc[-1]) else None
        c_bb_up = float(bb_up.iloc[-1]) if pd.notna(bb_up.iloc[-1]) else None
        c_bb_lo = float(bb_lo.iloc[-1]) if pd.notna(bb_lo.iloc[-1]) else None
        bb_pctb = None
        bb_bandwidth = None
        bb_squeeze = False
        if c_bb_up is not None and c_bb_lo is not None and c_bb_up > c_bb_lo:
            bb_pctb = (price - c_bb_lo) / (c_bb_up - c_bb_lo)
            if c_bb_mid:
                bb_bandwidth = (c_bb_up - c_bb_lo) / c_bb_mid * 100

        # ── Scoring ──────────────────────────────────────────────────
        score = 0.0
        pattern_score = 0.0
        volume_score = 0.0
        macd_score = 0.0
        bb_score = 0.0
        flags: list[tuple[str, float, str]] = []

        # =============== PILLAR 1: TECHNICAL PATTERNS ================
        # Double bottom / double top — pass live `price` so pattern confirmation uses real-time, not yesterday's close
        is_db, db_msg = _detect_double_bottom(low, close, live_price=price)
        if is_db:
            pattern_score += 3
            flags.append(('PAT_双底', +3, db_msg))
        is_dt, dt_msg = _detect_double_top(high, close, live_price=price)
        if is_dt:
            pattern_score -= 3
            flags.append(('PAT_双顶', -3, dt_msg))

        # Breakouts — live `price` allows intraday breakout detection
        bk_kind, bk_msg = _detect_breakout(close, high, volume, live_price=price)
        if bk_kind == 'bull':
            pattern_score += 3
            flags.append(('PAT_放量突破', +3, bk_msg))
        elif bk_kind == 'bull_weak':
            pattern_score += 1
            flags.append(('PAT_弱势突破', +1, bk_msg))
        elif bk_kind == 'bear':
            pattern_score -= 3
            flags.append(('PAT_放量破位', -3, bk_msg))

        # MA cross
        cross, cross_msg = _detect_ma_cross(close, ma50, ma200)
        if cross == 'golden':
            pattern_score += 2.5
            flags.append(('PAT_金叉', +2.5, cross_msg))
        elif cross == 'death':
            pattern_score -= 2.5
            flags.append(('PAT_死叉', -2.5, cross_msg))

        # Cup & handle
        is_cup, cup_msg = _detect_cup_handle(close, live_price=price)
        if is_cup:
            pattern_score += 2.5
            flags.append(('PAT_杯柄突破', +2.5, cup_msg))

        # MA stack (price vs MA20/MA50/MA200)
        if c_ma50 and c_ma200 and c_ma20:
            if price > c_ma20 > c_ma50 > c_ma200:
                pattern_score += 2
                flags.append(('PAT_多头排列', +2, '价>MA20>MA50>MA200, 长短期均线多头排列'))
            elif price < c_ma20 < c_ma50 < c_ma200:
                pattern_score -= 2
                flags.append(('PAT_空头排列', -2, '价<MA20<MA50<MA200, 均线空头排列'))

        # Support / resistance touch
        if c_ma50 and abs(price - c_ma50) / c_ma50 * 100 < 1.5 and price > c_ma50:
            pattern_score += 1
            flags.append(('PAT_MA50支撑', +1,
                          f'价格回踩MA50(${c_ma50:.2f})企稳, 支撑成立'))

        # =============== PILLAR 2: VOLUME ANALYSIS ===================
        c_vol = float(volume.iloc[-1])
        c_volma20 = float(vol_ma20.iloc[-1]) if pd.notna(vol_ma20.iloc[-1]) else c_vol
        # 盘中部分bar归一化为全日等效量 (见 intraday_volume.py); 未归一化时
        # 每只票的量比都被系统性压低, BB_缩量假突破嫌疑 会无差别扣分
        _rv, vol_est = rvol_now(volume, ticker=ticker)   # index 取自 volume 自身
        vol_unusable = _rv is None
        vol_ratio = _rv if _rv is not None else (c_vol / c_volma20 if c_volma20 > 0 else 1.0)

        # OBV trend
        if len(obv) >= 20:
            obv_5 = float(obv.iloc[-5:].mean())
            obv_20 = float(obv.iloc[-20:].mean())
            if obv_5 > obv_20 and pct_20d > 0:
                volume_score += 2
                flags.append(('VOL_OBV上行', +2,
                              'OBV 5日均值高于20日均值, 价升量升, 资金流入'))
            elif obv_5 < obv_20 and pct_20d > 0:
                volume_score -= 2
                flags.append(('VOL_OBV背离', -2,
                              'OBV走低但价格上涨, 量价背离, 上涨缺乏资金支持'))
            elif obv_5 > obv_20 and pct_20d < 0:
                volume_score += 1
                flags.append(('VOL_OBV底背离', +1,
                              '价格下跌但OBV走高, 资金悄悄入场'))

        # Volume spike + price action
        if vol_ratio > 2.0 and pct_1d > 3:
            volume_score += 1.5
            flags.append(('VOL_放量上涨', +1.5,
                          f'量比{vol_ratio:.1f}x + 涨{pct_1d:+.1f}%, 资金强势入场'))
        elif vol_ratio > 2.0 and pct_1d < -3:
            volume_score -= 2
            flags.append(('VOL_放量下跌', -2,
                          f'量比{vol_ratio:.1f}x + 跌{pct_1d:+.1f}%, 抛压沉重'))
        elif vol_ratio > 2.0 and abs(pct_1d) < 1:
            volume_score -= 1.5
            flags.append(('VOL_放量滞涨', -1.5,
                          f'量比{vol_ratio:.1f}x但价格不动, 主力派发可能'))

        # Volume MA trend
        if pd.notna(vol_ma50.iloc[-1]):
            v_ma50 = float(vol_ma50.iloc[-1])
            if c_volma20 > v_ma50 * 1.2:
                volume_score += 1
                flags.append(('VOL_持续放量', +1,
                              f'20日均量较50日均量放大{(c_volma20/v_ma50-1)*100:.0f}%, 关注度上升'))
            elif c_volma20 < v_ma50 * 0.7:
                volume_score -= 0.5
                flags.append(('VOL_萎缩', -0.5,
                              f'20日均量较50日均量萎缩{(1-c_volma20/v_ma50)*100:.0f}%, 关注度下降'))

        # Accumulation/distribution proxy (close in upper/lower 1/3 of day's range w/ volume)
        if len(close) >= 5:
            hl5 = (high.iloc[-5:] - low.iloc[-5:])
            hl5 = hl5.replace(0, np.nan)
            cl_pos = ((close.iloc[-5:] - low.iloc[-5:]) / hl5).mean()
            vol_5 = float(volume.iloc[-5:].mean())
            if pd.notna(cl_pos):
                if float(cl_pos) > 0.7 and vol_5 > c_volma20 * 1.1:
                    volume_score += 1.5
                    flags.append(('VOL_吸筹', +1.5,
                                  f'5日收盘均位于K线上1/3({cl_pos:.0%}) + 放量, 多头吸筹'))
                elif float(cl_pos) < 0.3 and vol_5 > c_volma20 * 1.1:
                    volume_score -= 1.5
                    flags.append(('VOL_派发', -1.5,
                                  f'5日收盘均位于K线下1/3({cl_pos:.0%}) + 放量, 主力派发'))

        # =============== PILLAR 3: MACD ANALYSIS =====================
        # MACD position
        if c_macd > c_sig and prev_hist <= 0 < c_hist:
            macd_score += 3
            flags.append(('MACD_金叉', +3,
                          f'MACD({c_macd:.3f})上穿信号线({c_sig:.3f}), 柱状图翻红, 买入信号'))
        elif c_macd < c_sig and prev_hist >= 0 > c_hist:
            macd_score -= 3
            flags.append(('MACD_死叉', -3,
                          f'MACD({c_macd:.3f})下穿信号线({c_sig:.3f}), 柱状图翻绿, 卖出信号'))
        elif c_macd > c_sig:
            macd_score += 1
            flags.append(('MACD_多头', +1,
                          f'MACD({c_macd:.3f})>信号线({c_sig:.3f}), 多头持续'))
        elif c_macd < c_sig:
            macd_score -= 1
            flags.append(('MACD_空头', -1,
                          f'MACD({c_macd:.3f})<信号线({c_sig:.3f}), 空头持续'))

        # Histogram momentum
        if len(hist) >= 4:
            h_seq = [float(hist.iloc[-i]) for i in range(4, 0, -1)]
            if all(h_seq[i] < h_seq[i + 1] for i in range(3)) and h_seq[-1] > 0:
                macd_score += 1.5
                flags.append(('MACD_柱状放大', +1.5,
                              '柱状图连续3日放大且为正, 多头动能加速'))
            elif all(h_seq[i] > h_seq[i + 1] for i in range(3)) and h_seq[-1] < 0:
                macd_score -= 1.5
                flags.append(('MACD_柱状放大空', -1.5,
                              '柱状图连续3日下行且为负, 空头动能加速'))

        # Zero-line position
        if c_macd > 0 and c_sig > 0:
            macd_score += 1
            flags.append(('MACD_零轴上方', +1, 'MACD与信号线均在零轴上方, 多头主导'))
        elif c_macd < 0 and c_sig < 0:
            macd_score -= 1
            flags.append(('MACD_零轴下方', -1, 'MACD与信号线均在零轴下方, 空头主导'))

        # Divergences
        div_kind, div_msg = _detect_macd_divergence(close, macd_line)
        if div_kind == 'bull_div':
            macd_score += 2.5
            flags.append(('MACD_底背离', +2.5, div_msg))
        elif div_kind == 'bear_div':
            macd_score -= 2.5
            flags.append(('MACD_顶背离', -2.5, div_msg))

        # =============== PILLAR 4: BOLLINGER BANDS ===================
        # Each signal is only awarded when confirmed by momentum (RSI/MACD)
        # and/or volume, per the BB playbook: squeeze → breakout w/ volume,
        # band riding in trends, midline reclaim/loss, lower-band bounce.
        macd_bull = c_macd > c_sig
        macd_bear = c_macd < c_sig
        if c_bb_mid is not None and c_bb_up is not None and c_bb_lo is not None:
            # Squeeze: bandwidth in the tightest 15% of the past ~6 months.
            # Direction from OBV + MACD (who is accumulating into the squeeze).
            bw_series = ((bb_up - bb_lo) / bb_mid * 100).dropna()
            if len(bw_series) >= 60 and bb_bandwidth is not None:
                bw_pctile = float((bw_series.iloc[-120:] < bb_bandwidth).mean())
                if bw_pctile <= 0.15:
                    bb_squeeze = True
                    obv_up = len(obv) >= 20 and float(obv.iloc[-5:].mean()) > float(obv.iloc[-20:].mean())
                    if obv_up and macd_bull:
                        bb_score += 1.5
                        flags.append(('BB_挤压蓄势(多)', +1.5,
                                      f'带宽{bb_bandwidth:.1f}%处于6个月最窄15%分位 + OBV上行 + MACD多头, 变盘临近偏向上'))
                    elif (not obv_up) and macd_bear:
                        bb_score -= 1
                        flags.append(('BB_挤压蓄势(空)', -1,
                                      f'带宽{bb_bandwidth:.1f}%极度收窄 + OBV走低 + MACD空头, 变盘临近偏向下'))
                    else:
                        flags.append(('BB_挤压蓄势', 0,
                                      f'带宽{bb_bandwidth:.1f}%极度收窄, 大波动临近但方向未定, 等突破表态'))

            # Upper-band breakout: true only with volume + MACD momentum.
            if price > c_bb_up:
                if vol_ratio >= 1.5 and macd_bull:
                    bb_score += 2.5
                    flags.append(('BB_放量突破上轨', +2.5,
                                  f'收破上轨${c_bb_up:.2f} + 量比{vol_ratio:.1f}x + MACD多头, 真突破确认'))
                elif (not vol_unusable) and vol_ratio < low_volume_threshold(1.0, vol_est):
                    bb_score -= 1
                    flags.append(('BB_缩量假突破嫌疑', -1,
                                  f'价格越过上轨${c_bb_up:.2f}但量比仅{vol_ratio:.1f}x, 无量冲高谨防回落'))
                else:
                    bb_score += 1
                    flags.append(('BB_突破上轨', +1,
                                  f'收破上轨${c_bb_up:.2f}, 量能{vol_ratio:.1f}x一般, 待放量确认'))

            # Lower-band breakdown with volume = real distribution.
            elif price < c_bb_lo:
                if vol_ratio >= 1.5 and macd_bear:
                    bb_score -= 2.5
                    flags.append(('BB_放量跌破下轨', -2.5,
                                  f'跌破下轨${c_bb_lo:.2f} + 量比{vol_ratio:.1f}x + MACD空头, 恐慌抛售确认'))
                elif c_rsi is not None and c_rsi < 30:
                    bb_score += 1.5
                    flags.append(('BB_下轨超卖', +1.5,
                                  f'触及下轨${c_bb_lo:.2f} + RSI超卖({c_rsi:.0f}), 均值回归反弹候选'))

            # Band riding: >=4 of last 5 closes hugging the upper band (%B>0.8)
            # in an uptrend — strength, not a sell; overheat warning via RSI.
            elif bb_pctb is not None and bb_pctb > 0.8:
                recent_pctb = ((close.iloc[-5:] - bb_lo.iloc[-5:]) /
                               (bb_up.iloc[-5:] - bb_lo.iloc[-5:])).dropna()
                riding = len(recent_pctb) >= 4 and (recent_pctb > 0.75).sum() >= 4
                if riding and macd_bull:
                    if c_rsi is not None and c_rsi >= 83:
                        flags.append(('BB_贴上轨+超买', 0,
                                      f'%B={bb_pctb:.2f}沿上轨强势运行但RSI({c_rsi:.0f})过热, 强势但勿追高'))
                    else:
                        bb_score += 1.5
                        flags.append(('BB_沿上轨强势', +1.5,
                                      f'%B={bb_pctb:.2f}连续贴上轨运行 + MACD多头, 趋势强劲(跌破中轨前持有)'))

            # Midline reclaim / loss with volume confirmation.
            prev_c = float(close.iloc[-2])
            prev_mid = float(bb_mid.iloc[-2]) if pd.notna(bb_mid.iloc[-2]) else None
            if prev_mid is not None:
                if prev_c < prev_mid and price > c_bb_mid and vol_ratio >= 1.2:
                    bb_score += 1.5
                    flags.append(('BB_放量收复中轨', +1.5,
                                  f'放量({vol_ratio:.1f}x)收复中轨${c_bb_mid:.2f}, 反弹升级信号'))
                elif prev_c > prev_mid and price < c_bb_mid and vol_ratio >= 1.2:
                    bb_score -= 1.5
                    flags.append(('BB_放量跌破中轨', -1.5,
                                  f'放量({vol_ratio:.1f}x)跌破中轨${c_bb_mid:.2f}, 趋势转弱警告'))

        # ── Composite ────────────────────────────────────────────────
        score = pattern_score + volume_score + macd_score + bb_score

        if score >= 7:
            action = 'STRONG BUY'
        elif score >= 3:
            action = 'BUY'
        elif score >= -3:
            action = 'HOLD'
        elif score >= -7:
            action = 'SELL'
        else:
            action = 'STRONG SELL'

        return {
            'ticker': ticker,
            'sector': sector,
            'price': price,
            'pct_1d': pct_1d,
            'pct_5d': pct_5d,
            'pct_20d': pct_20d,
            'rsi': c_rsi,
            'vol_ratio': vol_ratio,
            'macd': c_macd,
            'macd_signal': c_sig,
            'macd_hist': c_hist,
            'ma20': c_ma20,
            'ma50': c_ma50,
            'ma200': c_ma200,
            'bb_upper': c_bb_up,
            'bb_mid': c_bb_mid,
            'bb_lower': c_bb_lo,
            'bb_pctb': bb_pctb,
            'bb_bandwidth': bb_bandwidth,
            'bb_squeeze': bb_squeeze,
            'pattern_score': pattern_score,
            'volume_score': volume_score,
            'macd_score': macd_score,
            'bb_score': bb_score,
            'score': score,
            'action': action,
            'flags': flags,
        }
    except Exception as e:
        return {
            'ticker': ticker, 'sector': sector,
            'price': 0, 'pct_1d': 0, 'pct_5d': 0, 'pct_20d': 0,
            'rsi': None, 'vol_ratio': 0,
            'macd': None, 'macd_signal': None, 'macd_hist': None,
            'ma20': None, 'ma50': None, 'ma200': None,
            'bb_upper': None, 'bb_mid': None, 'bb_lower': None,
            'bb_pctb': None, 'bb_bandwidth': None, 'bb_squeeze': False,
            'pattern_score': 0, 'volume_score': 0, 'macd_score': 0,
            'bb_score': 0,
            'score': 0, 'action': 'ERROR',
            'flags': [('ERROR', 0, str(e)[:80])],
        }


def _emoji(action: str) -> str:
    return {
        'STRONG BUY': '🟢🟢', 'BUY': '🟢',
        'HOLD': '🟡',
        'SELL': '🔴', 'STRONG SELL': '🔴🔴',
        'ERROR': '⚠️',
    }.get(action, '❓')


def write_report(results: list[dict], sectors: dict[str, list[str]], out_path: Path):
    lines = []
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')
    lines.append('# Technical / Volume / MACD Strategy Report')
    lines.append(f'**Generated**: {ts}  |  **Stocks analyzed**: {len(results)}')
    lines.append('')
    lines.append('> **Disclaimer**: Algorithmic technical analysis based on '
                 'pattern detection, volume metrics, and MACD signals. Not '
                 'financial advice. Do your own due diligence.')
    lines.append('')

    counts: dict[str, int] = {}
    for r in results:
        counts[r['action']] = counts.get(r['action'], 0) + 1
    lines.append('## Summary')
    lines.append('')
    lines.append('| Action | Count |')
    lines.append('|--------|-------|')
    for act in ['STRONG BUY', 'BUY', 'HOLD', 'SELL', 'STRONG SELL', 'ERROR']:
        if counts.get(act, 0) > 0:
            lines.append(f'| {_emoji(act)} {act} | {counts[act]} |')
    lines.append('')

    # Top BUY
    buys = [r for r in results if r['action'] in ('STRONG BUY', 'BUY')]
    buys.sort(key=lambda x: x['score'], reverse=True)
    if buys:
        lines.append('## Top BUY Candidates')
        lines.append('')
        lines.append('| # | Ticker | Sector | Price | 5D% | 20D% | RSI | %B | Pattern | Volume | MACD | BB | Total | Action | Top Signal |')
        lines.append('|---|--------|--------|-------|-----|------|-----|----|---------|--------|------|----|-------|--------|------------|')
        for i, r in enumerate(buys[:20], 1):
            rsi_s = f"{r['rsi']:.0f}" if r['rsi'] else 'N/A'
            pctb_s = f"{r['bb_pctb']:.2f}" if r.get('bb_pctb') is not None else '—'
            top_flag = r['flags'][0][2] if r['flags'] else ''
            if len(top_flag) > 38:
                top_flag = top_flag[:38] + '…'
            lines.append(
                f"| {i} | **{r['ticker']}** | {r['sector']} | ${r['price']:.2f} | "
                f"{r['pct_5d']:+.1f}% | {r['pct_20d']:+.1f}% | {rsi_s} | {pctb_s} | "
                f"{r['pattern_score']:+.1f} | {r['volume_score']:+.1f} | {r['macd_score']:+.1f} | {r['bb_score']:+.1f} | "
                f"**{r['score']:+.1f}** | {_emoji(r['action'])} {r['action']} | {top_flag} |"
            )
        lines.append('')

    # Top SELL
    sells = [r for r in results if r['action'] in ('SELL', 'STRONG SELL')]
    sells.sort(key=lambda x: x['score'])
    if sells:
        lines.append('## Top SELL / Avoid')
        lines.append('')
        lines.append('| # | Ticker | Sector | Price | 5D% | 20D% | %B | Pattern | Volume | MACD | BB | Total | Action | Top Warning |')
        lines.append('|---|--------|--------|-------|-----|------|----|---------|--------|------|----|-------|--------|-------------|')
        for i, r in enumerate(sells[:20], 1):
            pctb_s = f"{r['bb_pctb']:.2f}" if r.get('bb_pctb') is not None else '—'
            top_flag = r['flags'][0][2] if r['flags'] else ''
            if len(top_flag) > 42:
                top_flag = top_flag[:42] + '…'
            lines.append(
                f"| {i} | **{r['ticker']}** | {r['sector']} | ${r['price']:.2f} | "
                f"{r['pct_5d']:+.1f}% | {r['pct_20d']:+.1f}% | {pctb_s} | "
                f"{r['pattern_score']:+.1f} | {r['volume_score']:+.1f} | {r['macd_score']:+.1f} | {r['bb_score']:+.1f} | "
                f"**{r['score']:+.1f}** | {_emoji(r['action'])} {r['action']} | {top_flag} |"
            )
        lines.append('')

    # Detailed by sector
    lines.append('## Detailed Analysis by Sector')
    lines.append('')
    for sector in sectors:
        sec_res = [r for r in results if r['sector'] == sector]
        if not sec_res:
            continue
        sec_res.sort(key=lambda x: x['score'], reverse=True)
        lines.append(f'### {sector}')
        lines.append('')
        for r in sec_res:
            emoji = _emoji(r['action'])
            rsi_s = f"RSI:{r['rsi']:.0f}" if r['rsi'] else 'RSI:N/A'
            macd_state = ''
            if r['macd'] is not None and r['macd_signal'] is not None:
                macd_state = f"MACD:{'金叉' if r['macd'] > r['macd_signal'] else '死叉'}"
            lines.append(
                f"**{r['ticker']}** — {emoji} **{r['action']}** "
                f"(总分: {r['score']:+.1f} | 形态: {r['pattern_score']:+.1f} | "
                f"量能: {r['volume_score']:+.1f} | MACD: {r['macd_score']:+.1f} | "
                f"BB: {r['bb_score']:+.1f})  "
            )
            bb_state = ''
            if r.get('bb_pctb') is not None:
                bb_state = f" | BB %B:{r['bb_pctb']:.2f} 带宽:{r['bb_bandwidth']:.1f}%"
                if r.get('bb_squeeze'):
                    bb_state += ' 🎯挤压'
            lines.append(
                f"Price: ${r['price']:.2f} | 1D: {r['pct_1d']:+.1f}% | "
                f"5D: {r['pct_5d']:+.1f}% | 20D: {r['pct_20d']:+.1f}% | "
                f"{rsi_s} | Vol: {r['vol_ratio']:.2f}x | {macd_state}{bb_state}"
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
    lines.append('Four pillars combine into one composite score:')
    lines.append('')
    lines.append('| Score | Action | Meaning |')
    lines.append('|-------|--------|---------|')
    lines.append('| ≥ +7 | STRONG BUY | Patterns + Volume + MACD + BB all strongly aligned bullish |')
    lines.append('| +3 to +7 | BUY | Net bullish across pillars |')
    lines.append('| -3 to +3 | HOLD | Mixed / wait for confirmation |')
    lines.append('| -7 to -3 | SELL | Net bearish across pillars |')
    lines.append('| < -7 | STRONG SELL | Multiple bearish confirmations |')
    lines.append('')
    lines.append('### Pillar 1 — Technical Patterns')
    lines.append('- Double Bottom / Double Top')
    lines.append('- 20-day breakout (with volume confirmation)')
    lines.append('- MA50 / MA200 Golden / Death Cross')
    lines.append('- Cup & Handle')
    lines.append('- Bullish / Bearish MA stacking (price>MA20>MA50>MA200)')
    lines.append('- Support touch at MA50')
    lines.append('')
    lines.append('### Pillar 2 — Volume Analysis')
    lines.append('- OBV (On-Balance Volume) trend & price-OBV divergence')
    lines.append('- Volume ratio vs 20-day average + price action')
    lines.append('- 20-day vs 50-day average volume (interest rising / fading)')
    lines.append('- Accumulation / Distribution (close position within daily range)')
    lines.append('')
    lines.append('### Pillar 3 — MACD Analysis')
    lines.append('- Golden Cross / Death Cross (MACD vs Signal)')
    lines.append('- Histogram momentum (3-day acceleration)')
    lines.append('- Zero-line position (above = bull, below = bear)')
    lines.append('- Bullish / Bearish divergence vs price')
    lines.append('')
    lines.append('### Pillar 4 — Bollinger Bands (20, 2σ) × RSI/MACD × Volume')
    lines.append('- Squeeze: bandwidth in tightest 15% of ~6 months — direction'
                 ' resolved by OBV + MACD (bull/bear/neutral)')
    lines.append('- Upper-band breakout: TRUE only with ≥1.5x volume + MACD bull;'
                 ' low-volume pokes above the band are flagged as suspect')
    lines.append('- Lower-band breakdown with ≥1.5x volume + MACD bear = distribution;'
                 ' lower-band touch with RSI<30 = mean-reversion bounce candidate')
    lines.append('- Band riding: %B>0.75 for 4 of 5 days + MACD bull = strong trend'
                 ' (hold until midline break); RSI≥83 downgrades to overheat warning')
    lines.append('- Midline (20SMA) reclaim / loss on ≥1.2x volume')
    lines.append('- %B = position within bands (0=lower, 1=upper); 带宽 = band width % of midline')

    out_path.write_text('\n'.join(lines), encoding='utf-8')
    return out_path


def main():
    print('=' * 80)
    print('  Technical / Volume / MACD Strategy — AI Portfolio')
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print('=' * 80)

    sectors = load_portfolio()
    all_tickers = [(t, sec) for sec, ts in sectors.items() for t in ts]
    print(f"\nLoaded {len(all_tickers)} tickers across {len(sectors)} sectors\n")

    results = []
    done = 0
    total = len(all_tickers)
    with ThreadPoolExecutor(max_workers=15) as ex:
        futures = {ex.submit(analyze_stock, t, sec): (t, sec) for t, sec in all_tickers}
        for fut in as_completed(futures):
            done += 1
            r = fut.result()
            if r:
                results.append(r)
            if done % 20 == 0 or done == total:
                print(f"  {done}/{total} complete", flush=True)

    results.sort(key=lambda x: x['score'], reverse=True)
    buys = [r for r in results if r['action'] in ('STRONG BUY', 'BUY')]
    holds = [r for r in results if r['action'] == 'HOLD']
    sells = [r for r in results if r['action'] in ('SELL', 'STRONG SELL')]
    errors = [r for r in results if r['action'] == 'ERROR']

    print('\n' + '=' * 80)
    print(f"  Results: {len(buys)} BUY | {len(holds)} HOLD | {len(sells)} SELL | {len(errors)} ERROR")
    print('=' * 80)

    if buys:
        print('\n  Top BUY:')
        for r in buys[:10]:
            print(f"    {_emoji(r['action'])} {r['ticker']:8s} ${r['price']:>9.2f}  "
                  f"P:{r['pattern_score']:+4.1f} V:{r['volume_score']:+4.1f} M:{r['macd_score']:+4.1f} "
                  f"B:{r['bb_score']:+4.1f}  = {r['score']:+5.1f}")

    if sells:
        print('\n  Top SELL:')
        for r in sells[:10]:
            top = r['flags'][0][2][:48] if r['flags'] else ''
            print(f"    {_emoji(r['action'])} {r['ticker']:8s} ${r['price']:>9.2f}  "
                  f"= {r['score']:+5.1f}  {top}")

    date_str = datetime.now().strftime('%Y-%m-%d')
    out_path = HERE / f'technical_macd_volume_{date_str}.md'
    write_report(results, sectors, out_path)
    print(f"\n  Report saved: {out_path.name}")
    print('=' * 80 + '\n')


if __name__ == '__main__':
    main()
