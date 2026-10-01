import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
import sys
import io
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
warnings.filterwarnings('ignore')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

ALERTS_LOG = Path(__file__).parent / 'alerts.log'


def print_recent_tv_alerts(hours=12):
    """Print TradingView webhook alerts received in the last N hours."""
    if not ALERTS_LOG.exists():
        return
    cutoff = datetime.now() - timedelta(hours=hours)
    alerts = []
    with ALERTS_LOG.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                a = json.loads(line)
                ts = datetime.fromisoformat(a.get('received_at', ''))
                if ts >= cutoff:
                    alerts.append((ts, a))
            except Exception:
                continue
    if not alerts:
        return
    print(f"\n{'='*80}")
    print(f"  🔔 TradingView 实时警报 (最近 {hours} 小时, {len(alerts)} 条)")
    print(f"{'='*80}")
    for ts, a in alerts:
        ticker = a.get('ticker', '?')
        price = a.get('price', '?')
        action = a.get('action', '')
        note = a.get('note', '')
        price_str = f"${price:.2f}" if isinstance(price, (int, float)) else f"${price}"
        action_str = f"[{action.upper()}]" if action else ''
        print(f"  {ts.strftime('%m-%d %H:%M')}  {ticker:<8} {price_str:<10} {action_str} {note}")
    print(f"{'='*80}\n")

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
    # Crypto-related stocks
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

# Indices
INDEX_MAP = {
    'Nasdaq':       '^IXIC',
    'S&P 500':      '^GSPC',
    'Dow Jones':    '^DJI',
    'Russell 2000': '^RUT',
    'Hang Seng':    '^HSI',
    'A股上证':       '000001.SS',
}


def compute_indicators(df):
    """Compute technical indicators for trend analysis."""
    close = df['Close']
    df['MA5'] = close.rolling(5).mean()
    df['MA10'] = close.rolling(10).mean()
    df['MA20'] = close.rolling(20).mean()
    df['MA50'] = close.rolling(50).mean()
    df['MA200'] = close.rolling(200).mean()

    # MACD
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    df['MACD'] = ema12 - ema26
    df['Signal'] = df['MACD'].ewm(span=9).mean()
    df['MACD_Hist'] = df['MACD'] - df['Signal']

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df['RSI'] = 100 - (100 / (1 + rs))

    return df


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


def analyze_index(ticker, name):
    """Analyze a market index and return a summary dict."""
    try:
        data = yf.download(ticker, period='1y', progress=False, auto_adjust=True)
        if data.empty or len(data) < 50:
            return None
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        data = compute_indicators(data)
        latest = data.iloc[-1]
        prev   = data.iloc[-2] if len(data) > 1 else latest
        price  = _get_live_price(ticker, float(latest['Close']))

        pct_1d = (price - float(prev['Close'])) / float(prev['Close']) * 100 if float(prev['Close']) != 0 else 0
        pct_5d = (price - float(data['Close'].iloc[-5]))  / float(data['Close'].iloc[-5])  * 100 if len(data) >= 5  else 0
        pct_20d= (price - float(data['Close'].iloc[-20])) / float(data['Close'].iloc[-20]) * 100 if len(data) >= 20 else 0

        rsi  = float(latest['RSI'])   if pd.notna(latest.get('RSI'))    else np.nan
        ma20 = float(latest['MA20'])  if pd.notna(latest.get('MA20'))   else np.nan
        ma50 = float(latest['MA50'])  if pd.notna(latest.get('MA50'))   else np.nan
        ma200= float(latest['MA200']) if pd.notna(latest.get('MA200'))  else np.nan
        macd = float(latest['MACD'])  if pd.notna(latest.get('MACD'))   else np.nan
        sig  = float(latest['Signal'])if pd.notna(latest.get('Signal')) else np.nan

        # Simple trend verdict
        above = []
        below = []
        for label, val in [('MA20', ma20), ('MA50', ma50), ('MA200', ma200)]:
            if pd.notna(val):
                (above if price > val else below).append(label)

        if len(above) == 3:
            trend = '多头 📈'
        elif len(above) >= 2:
            trend = '偏多 ↗️'
        elif len(below) >= 2:
            trend = '偏空 ↘️'
        else:
            trend = '震荡 ➡️'

        macd_str = ''
        if pd.notna(macd) and pd.notna(sig):
            macd_str = 'MACD金叉✅' if macd > sig else 'MACD死叉❌'

        rsi_str = f'RSI {rsi:.0f}' if pd.notna(rsi) else 'RSI N/A'

        return {
            'name': name, 'ticker': ticker, 'price': price,
            'pct_1d': pct_1d, 'pct_5d': pct_5d, 'pct_20d': pct_20d,
            'trend': trend, 'macd_str': macd_str, 'rsi_str': rsi_str,
            'above': above, 'below': below,
            'ma20': ma20, 'ma50': ma50, 'ma200': ma200,
        }
    except Exception:
        return None


def print_index_overview():
    """Fetch (in parallel) and print a market overview for all indices.
    Returns dict[name -> idx_data] so the caller can re-use it for the markdown report."""
    print(f"\n{'='*80}")
    print(f"  🌐 大盘指数概览")
    print(f"{'='*80}")

    indices_data = {}
    with ThreadPoolExecutor(max_workers=len(INDEX_MAP)) as ex:
        futures = {ex.submit(analyze_index, ticker, name): name for name, ticker in INDEX_MAP.items()}
        for fut in as_completed(futures):
            indices_data[futures[fut]] = fut.result()

    for name, _ in INDEX_MAP.items():  # preserve original order
        idx = indices_data.get(name)
        if idx is None:
            print(f"  {name:<14} 数据获取失败")
            continue

        price_str = f"${idx['price']:,.2f}" if idx['price'] > 10 else f"${idx['price']:.4f}"
        above_str = '/'.join(idx['above']) if idx['above'] else '—'
        below_str = '/'.join(idx['below']) if idx['below'] else '—'
        ma_detail = f"站上 {above_str}" if idx['above'] else ''
        if idx['below']:
            ma_detail += f"  跌破 {'/'.join(idx['below'])}" if ma_detail else f"跌破 {below_str}"

        print(f"  {name:<14} {price_str:<12} "
              f"日 {idx['pct_1d']:+.2f}%  5日 {idx['pct_5d']:+.2f}%  20日 {idx['pct_20d']:+.2f}%  "
              f"{idx['rsi_str']}  {idx['macd_str']}")
        print(f"  {'':14} 趋势: {idx['trend']}  均线: {ma_detail}")
        print()
    print(f"{'='*80}\n")
    return indices_data


def analyze_stock(ticker, name, sector):
    """Analyze if a stock is left-side or right-side trading."""
    try:
        data = yf.download(ticker, period='1y', progress=False, auto_adjust=True)
        if data.empty or len(data) < 50:
            return None

        # Flatten MultiIndex columns if present
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        data = compute_indicators(data)
        latest = data.iloc[-1]
        prev = data.iloc[-2] if len(data) > 1 else latest
        price = _get_live_price(ticker, float(latest['Close']))

        signals = {}
        reasons = []
        score = 0  # positive = right-side, negative = left-side

        # 1. Price vs Moving Averages
        if pd.notna(latest['MA20']):
            if price > latest['MA20']:
                score += 1
                signals['above_MA20'] = True
            else:
                score -= 1
                signals['above_MA20'] = False

        if pd.notna(latest['MA50']):
            if price > latest['MA50']:
                score += 1.5
                signals['above_MA50'] = True
            else:
                score -= 1.5
                signals['above_MA50'] = False

        if pd.notna(latest['MA200']):
            if price > latest['MA200']:
                score += 2
                signals['above_MA200'] = True
            else:
                score -= 2
                signals['above_MA200'] = False

        # 2. MA alignment (bullish: MA5 > MA10 > MA20 > MA50)
        if all(pd.notna(latest[m]) for m in ['MA5', 'MA10', 'MA20', 'MA50']):
            if latest['MA5'] > latest['MA10'] > latest['MA20'] > latest['MA50']:
                score += 2
                signals['ma_bullish_align'] = True
                reasons.append('均线多头排列 (MA5>MA10>MA20>MA50)')
            elif latest['MA5'] < latest['MA10'] < latest['MA20'] < latest['MA50']:
                score -= 2
                signals['ma_bearish_align'] = True
                reasons.append('均线空头排列')

        # 3. Golden Cross / Death Cross (MA50 vs MA200)
        if pd.notna(latest['MA50']) and pd.notna(latest['MA200']):
            if latest['MA50'] > latest['MA200']:
                score += 1.5
                signals['golden_cross'] = True
            else:
                score -= 1.5
                signals['golden_cross'] = False

        # 4. MACD
        if pd.notna(latest['MACD']) and pd.notna(latest['Signal']):
            if latest['MACD'] > latest['Signal'] and latest['MACD'] > 0:
                score += 1.5
                signals['macd_bullish'] = True
                reasons.append('MACD金叉且在零轴上方')
            elif latest['MACD'] > latest['Signal'] and latest['MACD'] < 0:
                score += 0.5
                signals['macd_cross_up'] = True
            elif latest['MACD'] < latest['Signal']:
                score -= 1
                signals['macd_bearish'] = True

        # 5. MACD Histogram trend
        if len(data) >= 5:
            recent_hist = data['MACD_Hist'].iloc[-5:]
            if recent_hist.is_monotonic_increasing:
                score += 1
                reasons.append('MACD柱状图连续放大')
            elif recent_hist.is_monotonic_decreasing:
                score -= 1

        # 6. RSI
        if pd.notna(latest['RSI']):
            if 50 < latest['RSI'] < 70:
                score += 1
                signals['rsi_healthy'] = True
            elif latest['RSI'] >= 70:
                score += 0.5
                signals['rsi_overbought'] = True
                reasons.append(f'RSI超买({latest["RSI"]:.0f})')
            elif latest['RSI'] < 30:
                score -= 0.5
                signals['rsi_oversold'] = True

        # 7. Recent price trend (20-day)
        if len(data) >= 20:
            price_20d_ago = data['Close'].iloc[-20]
            pct_20d = (price - price_20d_ago) / price_20d_ago * 100
            if pct_20d > 5:
                score += 1.5
                reasons.append(f'近20日涨幅 {pct_20d:.1f}%')
            elif pct_20d < -5:
                score -= 1.5

        # 8. Higher highs and higher lows (trend confirmation)
        if len(data) >= 20:
            recent = data.iloc[-20:]
            highs = recent['Close'].rolling(5).max()
            lows = recent['Close'].rolling(5).min()
            if len(highs.dropna()) >= 3:
                h_vals = highs.dropna()
                l_vals = lows.dropna()
                if h_vals.iloc[-1] > h_vals.iloc[-5] and l_vals.iloc[-1] > l_vals.iloc[-5]:
                    score += 1
                    reasons.append('近期高点和低点持续抬升')

        # Build reason strings
        right_reasons = []
        if signals.get('above_MA20'):
            right_reasons.append('价格在MA20上方')
        if signals.get('above_MA50'):
            right_reasons.append('价格在MA50上方')
        if signals.get('above_MA200'):
            right_reasons.append('价格在MA200上方')
        if signals.get('golden_cross'):
            right_reasons.append('MA50在MA200上方(金叉)')

        all_reasons = right_reasons + reasons

        # Classify
        if score >= 3:
            side = '右侧交易 ✅'
        elif score >= 0:
            side = '偏右侧 ➡️'
        elif score >= -3:
            side = '偏左侧 ⬅️'
        else:
            side = '左侧交易 ❌'

        # Price changes
        pct_1d = ((price - prev['Close']) / prev['Close'] * 100) if prev['Close'] != 0 else 0
        pct_5d = 0
        if len(data) >= 5:
            pct_5d = (price - data['Close'].iloc[-5]) / data['Close'].iloc[-5] * 100

        # ── Entry Timing ──────────────────────────────────────────────
        rsi_val = latest.get('RSI', np.nan)
        ma20_val = latest.get('MA20', np.nan)
        ma50_val = latest.get('MA50', np.nan)
        ma10_val = latest.get('MA10', np.nan)

        # Determine 5-day gain for overextension check
        pct_20d_gain = 0
        if len(data) >= 20:
            p20 = data['Close'].iloc[-20]
            pct_20d_gain = (price - p20) / p20 * 100 if p20 != 0 else 0

        # Check if price recently crossed above MA20 (within last 3 bars)
        crossed_ma20_recently = False
        if pd.notna(ma20_val) and len(data) >= 4:
            for i in range(1, 4):
                if data['Close'].iloc[-i-1] < data['MA20'].iloc[-i-1] and data['Close'].iloc[-i] >= data['MA20'].iloc[-i]:
                    crossed_ma20_recently = True
                    break

        entry_signal = ''
        entry_note = []

        if score >= 3:  # Right-side confirmed
            if pd.notna(rsi_val) and rsi_val > 80:
                entry_signal = '⏳ 等待回调'
                entry_note.append(f'RSI超买({rsi_val:.0f})，等待回调至MA20附近再入')
            elif pct_5d > 25:
                entry_signal = '⏳ 等待回调'
                entry_note.append(f'5日已涨{pct_5d:.1f}%，短期过热，等待回调至MA10/MA20')
            elif pct_5d > 15 and pd.notna(rsi_val) and rsi_val > 70:
                entry_signal = '⚠️ 谨慎追入'
                entry_note.append(f'5日涨{pct_5d:.1f}%且RSI({rsi_val:.0f})偏高，建议分批轻仓')
            elif crossed_ma20_recently:
                entry_signal = '✅ 较佳入场'
                entry_note.append('价格刚突破MA20，右侧起点附近，可考虑建仓')
            elif pd.notna(rsi_val) and 50 <= rsi_val <= 70:
                entry_signal = '✅ 适合入场'
                entry_note.append(f'RSI({rsi_val:.0f})健康，趋势确认，可分批建仓')
            else:
                entry_signal = '🔵 可以关注'
                entry_note.append('趋势向上但需结合大盘判断入场点')
        elif 0 <= score < 3:  # Lean right
            entry_signal = '👀 持续观察'
            entry_note.append('偏右侧但信号不够强，等待更多确认信号再入场')
        else:
            entry_signal = '🚫 暂不入场'
            entry_note.append('左侧区间，趋势未确认')

        # ── Stop-Loss Levels ──────────────────────────────────────────
        stop_levels = []
        stop_primary = None
        stop_secondary = None

        if pd.notna(ma20_val) and price > ma20_val:
            stop_primary = ma20_val
            stop_levels.append(f'MA20 ${ma20_val:.2f}（主止损，跌破离场）')
        if pd.notna(ma50_val) and price > ma50_val:
            stop_secondary = ma50_val
            stop_levels.append(f'MA50 ${ma50_val:.2f}（次级支撑）')

        # Tight stop for very overextended stocks (use MA10)
        if pct_5d > 20 and pd.notna(ma10_val) and price > ma10_val:
            stop_levels.insert(0, f'MA10 ${ma10_val:.2f}（短线止损，5日涨幅过大时收紧）')

        # Stop-loss as % from current price
        stop_pct_str = ''
        if stop_primary is not None:
            stop_pct = (price - stop_primary) / price * 100
            stop_pct_str = f'（距当前价 -{stop_pct:.1f}%）'

        return {
            'name': name,
            'ticker': ticker,
            'sector': sector,
            'price': price,
            'pct_1d': pct_1d,
            'pct_5d': pct_5d,
            'side': side,
            'score': score,
            'reasons': all_reasons,
            'rsi': latest.get('RSI', None),
            'macd': latest.get('MACD', None),
            'entry_signal': entry_signal,
            'entry_note': entry_note,
            'stop_levels': stop_levels,
            'stop_pct_str': stop_pct_str,
            'ma20': ma20_val,
            'ma50': ma50_val,
            'ma10': ma10_val,
        }
    except Exception as e:
        return {'name': name, 'ticker': ticker, 'sector': sector, 'side': f'数据获取失败: {e}',
                'score': 0, 'reasons': [], 'price': 0, 'pct_1d': 0, 'pct_5d': 0, 'rsi': None, 'macd': None,
                'entry_signal': '', 'entry_note': [], 'stop_levels': [], 'stop_pct_str': '',
                'ma20': None, 'ma50': None, 'ma10': None}


def load_stocks_from_excel(filepath):
    """Load all stocks from the Excel file."""
    df = pd.read_excel(filepath, sheet_name='AI')
    stocks = []
    skip_cols = ['Index']
    for col in df.columns:
        if col in skip_cols:
            continue
        for val in df[col].dropna():
            val = str(val).strip()
            if val and val != 'nan':
                ticker = TICKER_MAP.get(val, val.upper())
                stocks.append((val, ticker, col))
    # Remove duplicates by ticker
    seen = set()
    unique = []
    for name, ticker, sector in stocks:
        if ticker not in seen:
            seen.add(ticker)
            unique.append((name, ticker, sector))
    return unique


def write_markdown_report(results, indices_data, out_path):
    """Write a deterministic markdown report so callers don't need to scrape stdout."""
    lines = []
    lines.append(f"# Right-Side Trading 策略分析报告 (持仓 2 周–3 个月)")
    lines.append("")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**分析范围**: {len(results)} 只标的")
    lines.append("")

    # 大盘
    lines.append("## 🌐 大盘指数")
    lines.append("")
    lines.append("| 指数 | 现价 | 1日 | 5日 | 20日 | RSI | 趋势 | MACD |")
    lines.append("|------|------|------|------|------|-----|------|------|")
    for name, _ in INDEX_MAP.items():
        idx = indices_data.get(name) if indices_data else None
        if idx is None:
            lines.append(f"| {name} | - | - | - | - | - | 数据获取失败 | - |")
            continue
        price_str = f"${idx['price']:,.2f}" if idx['price'] > 10 else f"${idx['price']:.4f}"
        rsi_clean = idx['rsi_str'].replace('RSI ', '') if idx.get('rsi_str') else 'N/A'
        lines.append(
            f"| **{name}** | {price_str} | {idx['pct_1d']:+.2f}% | {idx['pct_5d']:+.2f}% | "
            f"{idx['pct_20d']:+.2f}% | {rsi_clean} | {idx['trend']} | {idx['macd_str']} |"
        )
    lines.append("")

    # 分类统计
    counts = {
        '右侧交易 (趋势确认)': sum(1 for r in results if '右侧交易' in r['side']),
        '偏右侧': sum(1 for r in results if '偏右侧' in r['side']),
        '偏左侧': sum(1 for r in results if '偏左侧' in r['side']),
        '左侧交易 (趋势未明)': sum(1 for r in results if '左侧交易' in r['side']),
        '数据获取失败': sum(1 for r in results if '失败' in r['side']),
    }
    lines.append("## 📊 分类统计")
    lines.append("")
    lines.append("| 分类 | 数量 |")
    lines.append("|------|------|")
    for k, v in counts.items():
        lines.append(f"| {k} | {v} |")
    lines.append("")

    # Top 右侧 (Top 15)
    strong_right = [r for r in results if '右侧交易' in r['side']]
    strong_right.sort(key=lambda x: x['score'], reverse=True)
    lines.append("## 🏆 最强右侧交易候选 (Top 15)")
    lines.append("")
    lines.append("| 排名 | 标的 | 板块 | 现价 | 5日 | RSI | 得分 | 入场建议 | 主止损(MA20) |")
    lines.append("|------|------|------|------|------|-----|------|----------|--------------|")
    for i, r in enumerate(strong_right[:15], 1):
        rsi_str = f"{r['rsi']:.0f}" if pd.notna(r.get('rsi')) else "N/A"
        ma20_str = f"${r['ma20']:.2f}" if pd.notna(r.get('ma20')) else "—"
        lines.append(
            f"| {i} | **{r['ticker']}** ({r['name']}) | {r['sector']} | ${r['price']:.2f} | "
            f"{r['pct_5d']:+.2f}% | {rsi_str} | {r['score']:.1f} | {r['entry_signal']} | {ma20_str} |"
        )
    lines.append("")

    # 全部标的
    lines.append("## 📋 全部标的 (按得分排序)")
    lines.append("")
    for r in results:
        rsi_str = f"RSI:{r['rsi']:.0f}" if pd.notna(r.get('rsi')) else "RSI:N/A"
        lines.append(f"### [{r['sector']}] {r['name']} ({r['ticker']})")
        lines.append(
            f"- 价格 **${r['price']:.2f}** · 日 {r['pct_1d']:+.2f}% · 5日 {r['pct_5d']:+.2f}% "
            f"· {rsi_str} · 得分 **{r['score']:.1f}**"
        )
        lines.append(f"- 状态: **{r['side']}**")
        if r['reasons'] and '右侧' in r['side']:
            lines.append(f"- 信号: {'; '.join(r['reasons'])}")
        if r.get('entry_signal'):
            lines.append(f"- 入场: {r['entry_signal']} — {'; '.join(r['entry_note'])}")
        if r.get('stop_levels'):
            lines.append(f"- 止损: {' | '.join(r['stop_levels'])}{r.get('stop_pct_str', '')}")
        if '左侧' in r['side']:
            ma20 = r.get('ma20')
            ma50 = r.get('ma50')
            watch_levels = []
            if pd.notna(ma20) and r['price'] < ma20:
                watch_levels.append(f'MA20 ${ma20:.2f}')
            if pd.notna(ma50) and r['price'] < ma50:
                watch_levels.append(f'MA50 ${ma50:.2f}')
            if watch_levels:
                lines.append(f"- 转机: 收复 {' → '.join(watch_levels)} 并站稳后再考虑入场")
        lines.append("")

    out_path.write_text('\n'.join(lines), encoding='utf-8')


def main():
    filepath = Path(__file__).parent / 'AI_Portfolios.xlsx'
    print(f"{'='*80}")
    print(f"  AI Portfolio 左侧/右侧交易分析")
    print(f"  分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*80}\n")

    print_recent_tv_alerts(hours=12)
    indices_data = print_index_overview()

    stocks = load_stocks_from_excel(str(filepath))
    total = len(stocks)
    print(f"共发现 {total} 只股票/资产，并行下载中 (max_workers=15)...\n")

    results = []
    done = 0
    with ThreadPoolExecutor(max_workers=15) as ex:
        futures = {
            ex.submit(analyze_stock, ticker, name, sector): (name, ticker, sector)
            for name, ticker, sector in stocks
        }
        for fut in as_completed(futures):
            done += 1
            try:
                result = fut.result()
            except Exception as e:
                name, ticker, sector = futures[fut]
                result = {
                    'name': name, 'ticker': ticker, 'sector': sector,
                    'side': f'数据获取失败: {e}', 'score': 0, 'reasons': [],
                    'price': 0, 'pct_1d': 0, 'pct_5d': 0, 'rsi': None, 'macd': None,
                    'entry_signal': '', 'entry_note': [], 'stop_levels': [],
                    'stop_pct_str': '', 'ma20': None, 'ma50': None, 'ma10': None,
                }
            if result:
                results.append(result)
            if done % 20 == 0 or done == total:
                print(f"  已完成 {done}/{total}", flush=True)
    print()

    # Sort by score descending
    results.sort(key=lambda x: x['score'], reverse=True)

    right_side = [r for r in results if '右侧' in r['side']]
    left_side  = [r for r in results if '左侧' in r['side']]

    print(f"\n{'='*80}")
    print(f"  📋 全部股票交易建议 ({len(results)} 只) — 按得分排序")
    print(f"{'='*80}\n")

    for r in results:
        rsi_str = f"RSI:{r['rsi']:.0f}" if pd.notna(r.get('rsi')) else "RSI:N/A"
        print(f"  [{r['sector']}] {r['name']} ({r['ticker']})")
        print(f"    价格: ${r['price']:.2f}  |  日涨跌: {r['pct_1d']:+.2f}%  |  5日: {r['pct_5d']:+.2f}%  |  {rsi_str}  |  得分: {r['score']:.1f}")
        print(f"    状态: {r['side']}")

        # Trend reasons (right-side only, keep output concise for left-side)
        if r['reasons'] and '右侧' in r['side']:
            print(f"    信号: {'; '.join(r['reasons'])}")

        # Entry timing — shown for all stocks
        if r.get('entry_signal'):
            print(f"    入场: {r['entry_signal']}  —  {'; '.join(r['entry_note'])}")

        # Stop-loss — shown when price is above any MA (right-side stocks)
        if r.get('stop_levels'):
            print(f"    止损: {' | '.join(r['stop_levels'])}{r.get('stop_pct_str', '')}")

        # Watch levels — shown for left-side stocks (what to recover to flip right)
        if '左侧' in r['side']:
            ma20 = r.get('ma20')
            ma50 = r.get('ma50')
            watch_levels = []
            if pd.notna(ma20) and r['price'] < ma20:
                watch_levels.append(f'MA20 ${ma20:.2f}')
            if pd.notna(ma50) and r['price'] < ma50:
                watch_levels.append(f'MA50 ${ma50:.2f}')
            if watch_levels:
                print(f"    转机: 收复 {' → '.join(watch_levels)} 并站稳后再考虑入场")

        print()

    # Summary
    print(f"\n{'='*80}")
    print(f"  📊 分析总结")
    print(f"{'='*80}")
    print(f"  右侧交易 (趋势确认): {len([r for r in results if '右侧交易' in r['side']])} 只")
    print(f"  偏右侧:              {len([r for r in results if '偏右侧' in r['side']])} 只")
    print(f"  偏左侧:              {len([r for r in results if '偏左侧' in r['side']])} 只")
    print(f"  左侧交易 (趋势未明): {len([r for r in results if '左侧交易' in r['side']])} 只")
    print(f"  数据获取失败:         {len([r for r in results if '失败' in r['side']])} 只")

    # Top right-side picks
    strong_right = [r for r in results if '右侧交易' in r['side']]
    if strong_right:
        print(f"\n  🏆 最强右侧交易 Top 5:")
        for r in strong_right[:5]:
            print(f"    {r['name']} ({r['ticker']}) - 得分:{r['score']:.1f} | {'; '.join(r['reasons'][:3])}")

    print(f"\n{'='*80}")
    print(f"  判断标准说明:")
    print(f"  右侧交易: 价格站上MA20/MA50/MA200, MACD金叉, 均线多头排列, 趋势向上")
    print(f"  左侧交易: 价格在均线下方, 趋势未反转, MACD在零轴下方")
    print(f"  综合得分 ≥3 为右侧交易, 0~3 偏右侧, -3~0 偏左侧, <-3 为左侧交易")
    print(f"")
    print(f"  入场时机说明:")
    print(f"  ✅ 适合/较佳入场: RSI 50-70, 趋势确认, 涨幅未过热")
    print(f"  ⚠️ 谨慎追入:      5日涨幅>15%且RSI>70，建议分批轻仓")
    print(f"  ⏳ 等待回调:      RSI>80或5日涨幅>25%，短期过热，等回调至MA10/MA20")
    print(f"  👀 持续观察:      偏右侧信号不足，继续跟踪")
    print(f"  🚫 暂不入场:      左侧区间，等趋势反转信号")
    print(f"")
    print(f"  止损位说明:")
    print(f"  主止损(MA20): 日线收盘价跌破MA20则止损离场（右侧交易标准线）")
    print(f"  次级支撑(MA50): 长线持有者可用MA50作为更宽的止损")
    print(f"  短线止损(MA10): 5日涨幅>20%的过热股，用MA10收紧止损保护利润")
    print(f"{'='*80}\n")

    # ── Persist a deterministic markdown report so callers don't have to scrape stdout ──
    out_path = Path(__file__).parent / f"right_side_trading_{datetime.now().strftime('%Y-%m-%d')}.md"
    try:
        write_markdown_report(results, indices_data, out_path)
        print(f"  ✅ 报告已保存: {out_path.name}")
    except Exception as e:
        print(f"  ⚠️ 报告写入失败: {e}")


if __name__ == '__main__':
    main()
