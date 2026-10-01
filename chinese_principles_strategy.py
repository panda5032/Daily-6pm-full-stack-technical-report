"""
Chinese Investing Principles Strategy — AI_Portfolios.xlsx
==========================================================
Implements 10 classic Chinese trading principles as a quantitative
scoring model. Each stock gets a composite score and a BUY / HOLD / SELL
recommendation based on the following rules:

 1. 低价股不要进       — Avoid penny stocks (< $5)
 2. 高位出利好不要进   — Avoid stocks up >80% from recent low (distribution risk)
 3. 偏离均线过远不要进 — Avoid stocks far above MA10/MA20; buy near MA support
 4. 跳空三连阳不要进   — Avoid 3 consecutive gap-up bullish candles
 5. 换手率超过40%不要进 — Avoid turnover > 40% (internal divergence)
 6. 持股2到3只最好     — Portfolio-level: sell trend-breakers (< MA10) first
 7. 量价关系           — Volume-price divergence rules
 8. 买入分歧卖出一致   — Buy on divergence, sell on consensus
 9. 成交量(量比)       — Volume ratio signals
10. 量减价平为变盘     — Decreasing volume + flat price = trend change

Output: Markdown report with BUY / HOLD / SELL for every stock.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
import sys
import io

warnings.filterwarnings('ignore')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

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
    'Crypto':            ['BTC-USD', 'ETH-USD', 'XRP-USD', 'SOL-USD', 'ADA-USD',
                          'DOGE-USD', 'MSTR', 'COIN', 'CLSK', 'RIOT', 'MARA',
                          'HUT', 'BMNR', 'SBET', 'FIG', 'CRCL', 'XYZ', 'BULL', 'HIVE',
                          'IBIT', 'ETHA', 'BSOL', 'XRPC'],
    'Finance':           ['SOFI', 'OPEN', 'LMND', 'HOOD', 'PYPL', 'AFRM'],
    'Quantum':           ['RGTI', 'IONQ', 'QUBT', 'QBTS'],
    'Trading':           ['GME', 'LULU', 'CMG', 'UPS', 'ABNB', 'PTON', 'BA', 'NKE'],
    'Rotation':          ['JPM', 'GS', 'BRK-B', 'XOM', 'CVX', 'CAT', 'DE', 'GE', 'COST', 'WMT', 'JNJ', 'XLU'],
    'Commodity':         ['GLD', 'SLV', 'CPER', 'USO'],
}

TICKER_TO_SECTOR = {}
for sector, tickers in SECTORS.items():
    for t in tickers:
        if t not in TICKER_TO_SECTOR:
            TICKER_TO_SECTOR[t] = sector

ALL_TICKERS = list({t for tickers in SECTORS.values() for t in tickers})


def _live_price(ticker: str, fallback: float) -> float:
    """Return the most recent traded price.

    Order of preference (each gracefully falls through on failure):
      1. fast_info.last_price / regularMarketPrice (real-time / 15m delayed quote)
      2. 1-minute intraday history close (today's most recent bar)
      3. Provided fallback (typically last daily close — flagged as stale)
    """
    # Tier 1: fast_info real-time quote
    try:
        fi = yf.Ticker(ticker).fast_info
        p = fi.get('last_price') or fi.get('regularMarketPrice')
        if p and float(p) > 0:
            return float(p)
    except Exception:
        pass
    # Tier 2: 1-minute intraday bar
    try:
        intraday = yf.Ticker(ticker).history(period='1d', interval='1m', auto_adjust=False)
        if not intraday.empty:
            closes = intraday['Close'].dropna()
            if len(closes) > 0 and float(closes.iloc[-1]) > 0:
                return float(closes.iloc[-1])
    except Exception:
        pass
    # Tier 3: caller-provided fallback (stale)
    return fallback


def _get_shares_outstanding(ticker: str) -> float:
    try:
        import logging
        logging.disable(logging.CRITICAL)
        info = yf.Ticker(ticker).info
        logging.disable(logging.NOTSET)
        return float(info.get('sharesOutstanding', 0))
    except Exception:
        return 0.0


def analyze_stock(ticker: str) -> dict | None:
    """Run all 10 principles against a single stock. Returns a result dict."""
    try:
        data = yf.download(ticker, period='6mo', progress=False, auto_adjust=True)
        if data.empty or len(data) < 30:
            return None
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        close = data['Close'].astype(float)
        high = data['High'].astype(float)
        low = data['Low'].astype(float)
        opn = data['Open'].astype(float)
        volume = data['Volume'].astype(float)

        ma5 = close.rolling(5).mean()
        ma10 = close.rolling(10).mean()
        ma20 = close.rolling(20).mean()
        ma50 = close.rolling(50).mean()
        vol_ma5 = volume.rolling(5).mean()
        vol_ma20 = volume.rolling(20).mean()

        price = _live_price(ticker, float(close.iloc[-1]))
        prev_close = float(close.iloc[-2]) if len(close) > 1 else price

        score = 0.0
        flags: list[tuple[str, float, str]] = []

        # ── Rule 1: Low-price stocks ─────────────────────────────────
        is_crypto = ticker.endswith('-USD')
        if not is_crypto and price < 5.0:
            score -= 3
            flags.append(('R1_低价股', -3, f'价格${price:.2f}<$5, 缺乏上涨逻辑'))
        elif not is_crypto and price < 10.0:
            score -= 1
            flags.append(('R1_低价股', -1, f'价格${price:.2f}偏低, 注意风险'))

        # ── Rule 2: High-position distribution risk ──────────────────
        low_60d = float(low.iloc[-60:].min()) if len(low) >= 60 else float(low.min())
        gain_from_low = (price - low_60d) / low_60d * 100 if low_60d > 0 else 0
        if gain_from_low > 80:
            score -= 3
            flags.append(('R2_高位风险', -3,
                          f'60日低点${low_60d:.2f}已涨{gain_from_low:.0f}%, 高位出利好需警惕主力出货'))
        elif gain_from_low > 50:
            score -= 1.5
            flags.append(('R2_高位风险', -1.5,
                          f'60日涨幅{gain_from_low:.0f}%, 追高风险偏大'))

        # ── Rule 3: Deviation from moving averages ───────────────────
        c_ma10 = float(ma10.iloc[-1]) if pd.notna(ma10.iloc[-1]) else None
        c_ma20 = float(ma20.iloc[-1]) if pd.notna(ma20.iloc[-1]) else None

        if c_ma20:
            dev_ma20 = (price - c_ma20) / c_ma20 * 100
            if dev_ma20 > 20:
                score -= 2.5
                flags.append(('R3_偏离均线', -2.5,
                              f'价格偏离MA20达{dev_ma20:.1f}%, 远超安全范围, 等待回调'))
            elif dev_ma20 > 10:
                score -= 1
                flags.append(('R3_偏离均线', -1,
                              f'偏离MA20 {dev_ma20:.1f}%, 短期过热'))
            elif -3 <= dev_ma20 <= 3 and price >= c_ma20:
                score += 2
                flags.append(('R3_均线支撑', +2,
                              f'价格贴近MA20({dev_ma20:+.1f}%), 回调到位, 入场好时机'))

        if c_ma10:
            dev_ma10 = (price - c_ma10) / c_ma10 * 100
            if -2 <= dev_ma10 <= 2 and price >= c_ma10:
                score += 1
                flags.append(('R3_MA10支撑', +1,
                              f'价格贴近MA10({dev_ma10:+.1f}%), 短线支撑位'))

        # ── Rule 4: Three consecutive gap-up bullish candles ─────────
        if len(data) >= 5:
            gap_bull_count = 0
            unfilled_gaps = 0
            for i in range(-3, 0):
                o = float(opn.iloc[i])
                c = float(close.iloc[i])
                prev_c = float(close.iloc[i - 1])
                if o > prev_c and c > o:
                    gap_bull_count += 1
                    if float(low.iloc[i]) > prev_c:
                        unfilled_gaps += 1
            if gap_bull_count >= 3 and unfilled_gaps >= 2:
                score -= 3
                flags.append(('R4_跳空三连阳', -3,
                              '连续3日跳空高开收阳且缺口未补, 主力拉一波就跑概率大'))
            elif gap_bull_count >= 3:
                score -= 1.5
                flags.append(('R4_三连阳', -1.5,
                              '连续3日跳空阳线, 短期过热'))

        # ── Rule 5: Turnover rate > 40% ──────────────────────────────
        shares = _get_shares_outstanding(ticker)
        if shares > 0 and not is_crypto:
            today_vol = float(volume.iloc[-1])
            turnover = today_vol / shares * 100
            if turnover > 40:
                score -= 3
                flags.append(('R5_换手率过高', -3,
                              f'换手率{turnover:.1f}%>40%, 多空严重分歧, 后市下跌概率大'))
            elif turnover > 25:
                score -= 1.5
                flags.append(('R5_换手率偏高', -1.5,
                              f'换手率{turnover:.1f}%, 内部分歧加大'))

        # ── Rule 6: Trend-break detection (sell below MA10) ──────────
        if c_ma10 and price < c_ma10:
            c_ma20_val = c_ma20 if c_ma20 else 0
            if c_ma20_val and price < c_ma20_val:
                score -= 2
                flags.append(('R6_趋势破位', -2,
                              f'价格跌破MA10(${c_ma10:.2f})和MA20(${c_ma20_val:.2f}), 优先卖出'))
            else:
                score -= 1
                flags.append(('R6_跌破MA10', -1,
                              f'价格跌破MA10(${c_ma10:.2f}), 关注是否进一步破位'))

        # ── Rule 7: Volume-price relationship rules ──────────────────
        c_vol = float(volume.iloc[-1])
        c_volma = float(vol_ma20.iloc[-1]) if pd.notna(vol_ma20.iloc[-1]) else c_vol
        vol_ratio = c_vol / c_volma if c_volma > 0 else 1.0

        pct_1d = (price - prev_close) / prev_close * 100 if prev_close > 0 else 0
        pct_5d = 0
        if len(close) >= 6:
            pct_5d = (price - float(close.iloc[-6])) / float(close.iloc[-6]) * 100

        if vol_ratio < 0.7 and pct_1d > 0.5:
            score += 2
            flags.append(('R7_缩量上涨', +2,
                          f'量比{vol_ratio:.2f}x缩量+价格上涨, 还会继续上涨'))
        elif vol_ratio < 0.7 and pct_1d < -0.5:
            score -= 2
            flags.append(('R7_缩量下跌', -2,
                          f'量比{vol_ratio:.2f}x缩量+价格下跌, 还会继续下跌'))
        elif vol_ratio > 2.0 and abs(pct_1d) < 1.0:
            score -= 2
            flags.append(('R7_放量滞涨', -2,
                          f'量比{vol_ratio:.2f}x放量但价格不动, 头部已现'))
        elif vol_ratio < 0.5 and abs(pct_1d) < 0.5 and pct_5d < -5:
            score += 2
            flags.append(('R7_缩量止跌', +2,
                          f'5日跌{pct_5d:.1f}%后缩量企稳, 底部已现'))
        elif vol_ratio > 3.0 and pct_1d > 5:
            score -= 1.5
            flags.append(('R7_巨量急涨', -1.5,
                          f'量比{vol_ratio:.2f}x巨量+涨{pct_1d:.1f}%, 必然回调'))

        # ── Rule 8: Buy divergence, sell consensus ───────────────────
        if len(data) >= 5:
            recent_range = (float(high.iloc[-1]) - float(low.iloc[-1])) / price * 100
            avg_range = float(((high - low) / close * 100).iloc[-20:].mean()) if len(data) >= 20 else recent_range

            in_uptrend = c_ma10 and c_ma20 and c_ma10 > c_ma20 and price > c_ma10
            if in_uptrend and vol_ratio > 1.5 and recent_range > avg_range * 1.5:
                score += 2
                flags.append(('R8_分歧买入', +2,
                              f'强势股出现放量大振幅(量比{vol_ratio:.2f}x,振幅{recent_range:.1f}%), 分歧产生溢价'))
            elif in_uptrend and vol_ratio < 0.6 and recent_range < avg_range * 0.5:
                score -= 1.5
                flags.append(('R8_一致卖出', -1.5,
                              '缩量窄幅上涨, 市场一致看多, 接近卖点'))

        # ── Rule 9: Volume ratio signals ─────────────────────────────
        if c_volma > 0:
            high_20d = float(close.iloc[-20:].max()) if len(close) >= 20 else float(close.max())
            near_high = (price / high_20d) > 0.97

            if vol_ratio < 0.5 and near_high:
                score += 2.5
                flags.append(('R9_缩量新高', +2.5,
                              f'量比{vol_ratio:.2f}x<0.5且接近新高, 主力高度控盘, 看多'))
            elif vol_ratio < 1.0 and pct_1d > 3:
                score += 1.5
                flags.append(('R9_量比<1强势', +1.5,
                              f'量比{vol_ratio:.2f}x<1但涨{pct_1d:.1f}%, 上涨空间大'))

            c_ma50_val = float(ma50.iloc[-1]) if pd.notna(ma50.iloc[-1]) else None
            if c_ma50_val and vol_ratio > 1.5 and price > c_ma20 and len(close) >= 3:
                was_below = float(close.iloc[-3]) < c_ma20
                if was_below:
                    score += 2
                    flags.append(('R9_放量突破', +2,
                                  f'量比{vol_ratio:.2f}x>1.5突破MA20, 不可多得的买入机会'))

        # ── Rule 10: Decreasing volume + flat price = trend change ───
        if len(data) >= 10:
            vol_5d = volume.iloc[-5:].values.astype(float)
            vol_prev5 = volume.iloc[-10:-5].values.astype(float)
            vol_decreasing = float(vol_5d.mean()) < float(vol_prev5.mean()) * 0.7

            price_flat = abs(pct_5d) < 3
            pct_20d = 0
            if len(close) >= 21:
                pct_20d = (price - float(close.iloc[-21])) / float(close.iloc[-21]) * 100
            was_uptrend = pct_20d > 10

            if vol_decreasing and price_flat and was_uptrend:
                score -= 3
                flags.append(('R10_量减价平', -3,
                              f'上涨趋势中成交量减少{(1-float(vol_5d.mean())/float(vol_prev5.mean()))*100:.0f}%且价格走平, '
                              f'主力压盘出货信号, 及时离场'))

        # ── Composite recommendation ─────────────────────────────────
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

        # RSI for display
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        c_rsi = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else None

        # MACD
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9).mean()
        c_macd = float(macd_line.iloc[-1]) if pd.notna(macd_line.iloc[-1]) else None
        c_signal = float(signal_line.iloc[-1]) if pd.notna(signal_line.iloc[-1]) else None

        return {
            'ticker': ticker,
            'sector': TICKER_TO_SECTOR.get(ticker, 'Other'),
            'price': price,
            'pct_1d': pct_1d,
            'pct_5d': pct_5d,
            'gain_from_low': gain_from_low,
            'vol_ratio': vol_ratio,
            'rsi': c_rsi,
            'macd': c_macd,
            'macd_signal': c_signal,
            'ma10': c_ma10,
            'ma20': c_ma20,
            'score': score,
            'action': action,
            'flags': flags,
        }
    except Exception as e:
        return {
            'ticker': ticker,
            'sector': TICKER_TO_SECTOR.get(ticker, 'Other'),
            'price': 0, 'pct_1d': 0, 'pct_5d': 0, 'gain_from_low': 0,
            'vol_ratio': 0, 'rsi': None, 'macd': None, 'macd_signal': None,
            'ma10': None, 'ma20': None,
            'score': 0, 'action': 'ERROR',
            'flags': [('ERROR', 0, str(e))],
        }


def _action_emoji(action: str) -> str:
    return {
        'STRONG BUY': '🟢🟢',
        'BUY': '🟢',
        'HOLD': '🟡',
        'SELL': '🔴',
        'STRONG SELL': '🔴🔴',
        'ERROR': '⚠️',
    }.get(action, '❓')


def write_report(results: list[dict], out_path: Path):
    lines = []
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')
    lines.append(f'# Chinese Principles Strategy Report')
    lines.append(f'**Generated**: {ts}  |  **Stocks analyzed**: {len(results)}')
    lines.append('')
    lines.append('> **Disclaimer**: This is an algorithmic output based on user-defined rules, '
                 'not financial advice. Do your own due diligence.')
    lines.append('')

    # Summary counts
    counts = {}
    for r in results:
        counts[r['action']] = counts.get(r['action'], 0) + 1
    lines.append('## Summary')
    lines.append('')
    lines.append('| Action | Count |')
    lines.append('|--------|-------|')
    for act in ['STRONG BUY', 'BUY', 'HOLD', 'SELL', 'STRONG SELL', 'ERROR']:
        if counts.get(act, 0) > 0:
            lines.append(f'| {_action_emoji(act)} {act} | {counts[act]} |')
    lines.append('')

    # Top BUY picks
    buys = [r for r in results if r['action'] in ('STRONG BUY', 'BUY')]
    buys.sort(key=lambda x: x['score'], reverse=True)
    if buys:
        lines.append('## Top BUY Candidates')
        lines.append('')
        lines.append('| Rank | Ticker | Sector | Price | 5D% | RSI | Vol Ratio | Score | Action | Key Signal |')
        lines.append('|------|--------|--------|-------|-----|-----|-----------|-------|--------|------------|')
        for i, r in enumerate(buys[:15], 1):
            rsi_s = f"{r['rsi']:.0f}" if r['rsi'] else 'N/A'
            top_flag = r['flags'][0][2] if r['flags'] else ''
            if len(top_flag) > 40:
                top_flag = top_flag[:40] + '...'
            lines.append(
                f"| {i} | **{r['ticker']}** | {r['sector']} | ${r['price']:.2f} | "
                f"{r['pct_5d']:+.1f}% | {rsi_s} | {r['vol_ratio']:.2f}x | "
                f"{r['score']:+.1f} | {_action_emoji(r['action'])} {r['action']} | {top_flag} |"
            )
        lines.append('')

    # Top SELL picks
    sells = [r for r in results if r['action'] in ('SELL', 'STRONG SELL')]
    sells.sort(key=lambda x: x['score'])
    if sells:
        lines.append('## Top SELL / Avoid')
        lines.append('')
        lines.append('| Rank | Ticker | Sector | Price | 5D% | Score | Action | Key Warning |')
        lines.append('|------|--------|--------|-------|-----|-------|--------|-------------|')
        for i, r in enumerate(sells[:15], 1):
            top_flag = r['flags'][0][2] if r['flags'] else ''
            if len(top_flag) > 45:
                top_flag = top_flag[:45] + '...'
            lines.append(
                f"| {i} | **{r['ticker']}** | {r['sector']} | ${r['price']:.2f} | "
                f"{r['pct_5d']:+.1f}% | {r['score']:+.1f} | "
                f"{_action_emoji(r['action'])} {r['action']} | {top_flag} |"
            )
        lines.append('')

    # Portfolio management note (Rule 6)
    lines.append('## Portfolio Management (Rule 6)')
    lines.append('')
    lines.append('- Hold 2-3 positions max for focused risk management')
    lines.append('- If holding 5+ stocks with most in loss, reduce position count')
    lines.append('- Sell trend-breakers first (stocks below MA10)')
    below_ma10 = [r for r in results if r['ma10'] and r['price'] < r['ma10'] and r['action'] != 'ERROR']
    below_ma10.sort(key=lambda x: x['score'])
    if below_ma10:
        lines.append('')
        lines.append(f'**Stocks below MA10 ({len(below_ma10)}) — sell priority (worst first):**')
        for r in below_ma10[:10]:
            dev = (r['price'] - r['ma10']) / r['ma10'] * 100
            lines.append(f"- {r['ticker']} (${r['price']:.2f}, {dev:.1f}% below MA10, score {r['score']:+.1f})")
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
            rsi_s = f"RSI:{r['rsi']:.0f}" if r['rsi'] else 'RSI:N/A'
            macd_s = ''
            if r['macd'] is not None and r['macd_signal'] is not None:
                macd_s = 'MACD金叉' if r['macd'] > r['macd_signal'] else 'MACD死叉'
            lines.append(
                f"**{r['ticker']}** — {emoji} **{r['action']}** (score: {r['score']:+.1f})  "
            )
            lines.append(
                f"Price: ${r['price']:.2f} | 1D: {r['pct_1d']:+.1f}% | 5D: {r['pct_5d']:+.1f}% | "
                f"{rsi_s} | Vol: {r['vol_ratio']:.2f}x | {macd_s}"
            )
            if r['flags']:
                for rule, pts, desc in r['flags']:
                    sign = '+' if pts > 0 else ''
                    lines.append(f"- [{rule}] ({sign}{pts:.1f}) {desc}")
            lines.append('')

    # Scoring methodology
    lines.append('---')
    lines.append('## Scoring Methodology')
    lines.append('')
    lines.append('| Score Range | Action | Meaning |')
    lines.append('|-------------|--------|---------|')
    lines.append('| >= +4 | STRONG BUY | Multiple bullish signals aligned |')
    lines.append('| +2 to +4 | BUY | Net positive — good entry conditions |')
    lines.append('| -2 to +2 | HOLD | Mixed signals — wait for clarity |')
    lines.append('| -4 to -2 | SELL | Net negative — reduce or exit |')
    lines.append('| < -4 | STRONG SELL | Multiple red flags — exit immediately |')
    lines.append('')
    lines.append('### The 10 Principles')
    lines.append('1. R1 低价股 — Avoid stocks under $5 (lack upside logic)')
    lines.append('2. R2 高位风险 — Avoid stocks up >80% from 60D low (distribution)')
    lines.append('3. R3 偏离均线 — Avoid overextended stocks; buy near MA support')
    lines.append('4. R4 跳空三连阳 — Avoid 3 consecutive gap-up bullish candles')
    lines.append('5. R5 换手率 — Avoid turnover >40% (internal divergence)')
    lines.append('6. R6 趋势破位 — Sell stocks below MA10/MA20 first')
    lines.append('7. R7 量价关系 — Volume-price divergence rules')
    lines.append('8. R8 分歧/一致 — Buy on divergence, sell on consensus')
    lines.append('9. R9 量比 — Volume ratio <0.5 at highs = bullish control')
    lines.append('10. R10 量减价平 — Decreasing volume + flat price = exit')

    out_path.write_text('\n'.join(lines), encoding='utf-8')
    return out_path


def main():
    print(f"{'=' * 80}")
    print(f"  Chinese Principles Strategy — AI Portfolio Analysis")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'=' * 80}\n")

    total = len(ALL_TICKERS)
    print(f"Analyzing {total} stocks with 10 principles (max_workers=15)...\n")

    results = []
    done = 0
    with ThreadPoolExecutor(max_workers=15) as ex:
        futures = {ex.submit(analyze_stock, t): t for t in ALL_TICKERS}
        for fut in as_completed(futures):
            done += 1
            r = fut.result()
            if r:
                results.append(r)
            if done % 20 == 0 or done == total:
                print(f"  {done}/{total} complete", flush=True)

    results.sort(key=lambda x: x['score'], reverse=True)

    # Console summary
    buys = [r for r in results if r['action'] in ('STRONG BUY', 'BUY')]
    holds = [r for r in results if r['action'] == 'HOLD']
    sells = [r for r in results if r['action'] in ('SELL', 'STRONG SELL')]
    errors = [r for r in results if r['action'] == 'ERROR']

    print(f"\n{'=' * 80}")
    print(f"  Results: {len(buys)} BUY | {len(holds)} HOLD | {len(sells)} SELL | {len(errors)} ERROR")
    print(f"{'=' * 80}")

    if buys:
        print(f"\n  Top BUY candidates:")
        for r in buys[:10]:
            print(f"    {_action_emoji(r['action'])} {r['ticker']:8s} ${r['price']:>8.2f}  "
                  f"score:{r['score']:+5.1f}  5D:{r['pct_5d']:+6.1f}%  vol:{r['vol_ratio']:.2f}x")

    if sells:
        print(f"\n  Top SELL warnings:")
        for r in sells[:10]:
            top_warn = r['flags'][0][2][:50] if r['flags'] else ''
            print(f"    {_action_emoji(r['action'])} {r['ticker']:8s} ${r['price']:>8.2f}  "
                  f"score:{r['score']:+5.1f}  {top_warn}")

    # Write report
    date_str = datetime.now().strftime('%Y-%m-%d')
    out_path = Path(__file__).parent / f'chinese_principles_{date_str}.md'
    write_report(results, out_path)
    print(f"\n  Report saved: {out_path.name}")
    print(f"{'=' * 80}\n")


if __name__ == '__main__':
    main()
