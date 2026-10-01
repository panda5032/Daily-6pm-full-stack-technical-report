"""
长线策略分析 (1 年+ 投资视角)
对 AI_Portfolios.xlsx 中的所有股票、指数、加密货币进行分析
核心评估维度 (巴菲特基本面优先版):
1. 趋势质量 (20 分): 价格 vs MA200 + 周线 MA50
2. 动量强度 (10 分): 12M/6M 回报
3. 基本面 (50 分): 营收增长 + 盈利质量 + 护城河(毛利率) + ROE
                   + FCF收益率(owner earnings) + 估值(P/E+PEG) + 同行比较
4. 风险控制 (20 分): 波动率 + 最大回撤 + 负债 + 流动性
5. 综合评分 → 买入 / 增持 / 持有 / 减持 / 回避
"""
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
import sys
import io
import json
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

warnings.filterwarnings('ignore')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ===== 股票分类 =====
SECTORS = {
    'Hyperscaler (超大规模云)': ['GOOGL', 'AMZN', 'META', 'MSFT', 'AAPL'],
    'Self-Driving (自动驾驶)': ['TSLA', 'PONY', 'UBER', 'GRAB'],
    'Robotics (机器人)': ['SERV', 'PATH', 'ISRG'],
    'Semis (半导体)': ['NVDA', 'AMD', 'AVGO', 'TSM', 'ARM', 'MRVL', 'MU', 'INTC', 'SMCI', 'ANET', 'DELL', 'ASML', 'QCOM',
                      'AMAT', 'LRCX', 'KLAC', 'COHR', 'TXN', 'ADI', 'NXPI', 'MCHP', 'GFS', 'TER', 'SKHY'],
    'AI Infrastructure (AI基建)': ['CRWV', 'ORCL', 'IREN', 'NBIS', 'CIFR', 'APLD', 'CSCO', 'VRT', 'GEV', 'ETN', 'DLR',
                      'VST', 'CEG', 'CIEN', 'PSTG'],
    'Energy (能源)': ['OKLO', 'LAC', 'MP', 'SMR', 'BE', 'ONDS', 'QS', 'EOSE'],
    'Software (软件)': ['PLTR', 'SNOW', 'AI', 'IBM', 'MDB', 'NOW', 'CRM', 'ADBE', 'OKTA', 'SHOP',
                      'SOUN', 'BBAI', 'UPST', 'DUOL', 'RBRK', 'DDOG', 'NFLX', 'ZETA', 'SPOT', 'APP',
                      'RDDT', 'TTD', 'RBLX', 'U', 'INFY', 'ALAB', 'CRDO', 'WOLF', 'SNPS',
                      'CRWD', 'PANW', 'ZS', 'NET', 'TEAM', 'WDAY', 'INTU',
                      'S', 'GTLB', 'ESTC', 'TWLO', 'CFLT', 'HUBS'],
    'Health (医疗)': ['UNH', 'OSCR', 'HIMS', 'RXRX', 'LLY', 'TEM', 'CRSP', 'TMDX'],
    'Space (太空/出行)': ['RKLB', 'FLY', 'JOBY', 'ACHR', 'LUNR', 'ASTS'],
    'China (中概股)': ['BABA', 'BIDU', 'JD', 'XPEV', 'NIO', 'PDD', 'FUTU', 'TCEHY'],
    'Crypto (加密货币及相关)': ['BTC-USD', 'ETH-USD', 'XRP-USD', 'SOL-USD', 'ADA-USD', 'DOGE-USD',
                          'MSTR', 'COIN', 'CLSK', 'RIOT', 'MARA', 'HUT', 'BMNR', 'SBET',
                          'FIG', 'CRCL', 'XYZ', 'BULL', 'HIVE',
                          'IBIT', 'ETHA', 'BSOL', 'XRPC'],
    'Finance (金融科技)': ['SOFI', 'OPEN', 'LMND', 'HOOD', 'PYPL', 'AFRM'],
    'Quantum (量子计算)': ['RGTI', 'IONQ', 'QUBT', 'QBTS'],
    'Consumer/Other (消费/其他)': ['GME', 'LULU', 'CMG', 'UPS', 'ABNB', 'PTON', 'BA', 'NKE'],
    'Rotation (轮动板凳)': ['JPM', 'GS', 'BRK-B', 'XOM', 'CVX', 'CAT', 'DE', 'GE', 'COST', 'WMT', 'JNJ'],  # no XLU/commodity ETFs — fundamentals N/A
}

# ===== 大盘指数 =====
INDICES = {
    'Nasdaq (纳斯达克)': '^IXIC',
    'S&P 500 (标普500)': '^GSPC',
    'Dow Jones (道琼斯)': '^DJI',
    'Russell 2000 (罗素2000)': '^RUT',
    'Hang Seng (恒生指数)': '^HSI',
    '上证综指': '000001.SS',
}


def fetch_data(ticker, period='3y', max_retries=3):
    """获取 3 年的周线数据 + 日线数据 + 基本面信息

    - 最多 max_retries 次重试 (指数退避), 应对 yfinance 临时限流/超时
    - 自动剔除 Yahoo 偶尔在最后插入的全 NaN 占位行 (例如 000001.SS 当天行情未更新)
    """
    last_err = None
    for attempt in range(max_retries):
        try:
            t = yf.Ticker(ticker)
            daily = t.history(period=period, interval='1d', auto_adjust=True)
            # 关键修复: 部分指数 (如 000001.SS) 最后一行常为 NaN, 必须 dropna 否则
            # 后续 close.iloc[-1] 会拿到 NaN, 导致整张报告该标的字段为 "—"
            if not daily.empty:
                daily = daily.dropna(subset=['Close'])
            if daily.empty or len(daily) < 60:
                # 数据太少: 可能是新股或临时空, 重试一次再放弃
                if attempt < max_retries - 1:
                    time.sleep(0.6 * (attempt + 1))
                    continue
                return None

            weekly = t.history(period=period, interval='1wk', auto_adjust=True)
            if not weekly.empty:
                weekly = weekly.dropna(subset=['Close'])

            info = {}
            try:
                info = t.info or {}
            except Exception:
                info = {}

            # Live price: try fast_info → 1m intraday bar → None (caller falls back to last close)
            live_price = None
            try:
                fi = t.fast_info
                p = fi.get('last_price') or fi.get('regularMarketPrice')
                if p and float(p) > 0:
                    live_price = float(p)
            except Exception:
                pass
            if live_price is None:
                try:
                    intraday = t.history(period='1d', interval='1m', auto_adjust=False)
                    if not intraday.empty:
                        closes = intraday['Close'].dropna()
                        if len(closes) > 0 and float(closes.iloc[-1]) > 0:
                            live_price = float(closes.iloc[-1])
                except Exception:
                    pass

            return {'daily': daily, 'weekly': weekly, 'info': info, 'ticker': ticker, 'live_price': live_price}
        except Exception as e:
            last_err = e
            if attempt < max_retries - 1:
                time.sleep(0.6 * (attempt + 1))
                continue
    return None


def compute_metrics(data):
    """计算所有长线评估指标"""
    d = data['daily']
    w = data['weekly']
    info = data['info']
    close = d['Close']
    current_price = data.get('live_price') or float(close.iloc[-1])

    # --- 移动均线 ---
    ma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
    ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

    # --- 周线趋势 ---
    w_close = w['Close']
    w_ma50 = float(w_close.rolling(50).mean().iloc[-1]) if len(w_close) >= 50 else None
    w_ma20 = float(w_close.rolling(20).mean().iloc[-1]) if len(w_close) >= 20 else None

    # --- 回报率 (use live price as numerator so today's intraday move is included) ---
    def ret_over(days):
        if len(close) < days + 1:
            return None
        return float((current_price / close.iloc[-days - 1] - 1) * 100)

    ret_1m = ret_over(21)
    ret_3m = ret_over(63)
    ret_6m = ret_over(126)
    ret_12m = ret_over(252)

    # --- 年化波动率 (日收益) ---
    daily_ret = close.pct_change().dropna()
    vol_annual = float(daily_ret.std() * np.sqrt(252) * 100) if len(daily_ret) > 30 else None

    # --- 最大回撤 (近 1 年) ---
    recent = close.iloc[-252:] if len(close) >= 252 else close
    rolling_max = recent.cummax()
    drawdown = (recent / rolling_max - 1) * 100
    max_dd = float(drawdown.min())

    # --- 周线 RSI ---
    delta = w_close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    w_rsi = float((100 - 100 / (1 + rs)).iloc[-1]) if len(w_close) >= 15 else None

    # --- 周线 MACD ---
    ema12 = w_close.ewm(span=12).mean()
    ema26 = w_close.ewm(span=26).mean()
    macd_line = ema12 - ema26
    macd_signal = macd_line.ewm(span=9).mean()
    macd_hist = float((macd_line - macd_signal).iloc[-1]) if len(w_close) >= 27 else None
    macd_bull = bool(macd_hist is not None and macd_hist > 0)

    # --- 距离 52 周高点 ---
    high_52w = float(close.iloc[-252:].max()) if len(close) >= 252 else float(close.max())
    dist_from_high = (current_price / high_52w - 1) * 100

    # --- 基本面 ---
    pe = info.get('trailingPE') or info.get('forwardPE')
    forward_pe = info.get('forwardPE')
    peg = info.get('pegRatio')
    rev_growth = info.get('revenueGrowth')
    earnings_growth = info.get('earningsGrowth')
    profit_margin = info.get('profitMargins')
    gross_margin = info.get('grossMargins')
    operating_margin = info.get('operatingMargins')
    roe = info.get('returnOnEquity')
    debt_to_equity = info.get('debtToEquity')
    current_ratio = info.get('currentRatio')
    market_cap = info.get('marketCap')
    free_cashflow = info.get('freeCashflow')
    price_to_book = info.get('priceToBook')
    sector = info.get('sector', '')

    # FCF yield = 自由现金流 / 市值 (巴菲特 owner earnings 代理指标)
    fcf_yield = (free_cashflow / market_cap) if (free_cashflow and market_cap and market_cap > 0) else None

    return {
        'ticker': data['ticker'],
        'price': current_price,
        'ma50': ma50,
        'ma200': ma200,
        'w_ma20': w_ma20,
        'w_ma50': w_ma50,
        'above_ma200': bool(ma200 and current_price > ma200),
        'above_ma50': bool(ma50 and current_price > ma50),
        'above_w_ma50': bool(w_ma50 and current_price > w_ma50),
        'ret_1m': ret_1m, 'ret_3m': ret_3m, 'ret_6m': ret_6m, 'ret_12m': ret_12m,
        'vol_annual': vol_annual,
        'max_dd': max_dd,
        'w_rsi': w_rsi,
        'macd_hist': macd_hist,
        'macd_bull': macd_bull,
        'dist_from_high': dist_from_high,
        'pe': pe, 'forward_pe': forward_pe, 'peg': peg,
        'rev_growth': rev_growth,
        'earnings_growth': earnings_growth,
        'profit_margin': profit_margin,
        'gross_margin': gross_margin,
        'operating_margin': operating_margin,
        'roe': roe,
        'debt_to_equity': debt_to_equity,
        'current_ratio': current_ratio,
        'free_cashflow': free_cashflow,
        'fcf_yield': fcf_yield,
        'price_to_book': price_to_book,
        'market_cap': market_cap,
        'sector_info': sector,
    }


def compute_sector_stats(sector_metrics_list):
    """计算板块内各基本面指标中位数，用于同行比较评分。"""
    stats = {}
    for key in ('gross_margin', 'roe', 'profit_margin', 'rev_growth', 'fcf_yield'):
        vals = [m[key] for m in sector_metrics_list
                if m.get(key) is not None and not np.isnan(float(m[key]))]
        stats[key] = float(np.median(vals)) if vals else None
    return stats


def score_stock(m, sector_stats=None):
    """
    长线综合评分 (0-100) — 巴菲特基本面优先版:
    - 趋势质量 (20 分): 价格 vs MA200 + 周线 MA50
    - 动量强度 (10 分): 12M/6M 回报
    - 基本面 (50 分): 营收增长 + 盈利质量 + 护城河(毛利率) + ROE
                      + FCF收益率(owner earnings) + 估值(P/E+PEG) + 同行比较
    - 风险控制 (20 分): 波动率 + 最大回撤 + 负债 + 流动性
    """
    score = 0
    notes = []

    # 1. 趋势质量 (20)
    trend_score = 0
    if m['above_ma200']:
        trend_score += 12
        notes.append("价>MA200")
    elif m['ma200']:
        pct_below = (m['price'] / m['ma200'] - 1) * 100
        if pct_below > -10:
            trend_score += 6
            notes.append("接近MA200")
        else:
            notes.append("MA200下方")
    if m['above_w_ma50']:
        trend_score += 8
    score += trend_score

    # 2. 动量 (10)
    mom_score = 0
    if m['ret_12m'] is not None:
        if m['ret_12m'] > 30:   mom_score += 6
        elif m['ret_12m'] > 10: mom_score += 4
        elif m['ret_12m'] > 0:  mom_score += 2
        elif m['ret_12m'] > -20: mom_score += 1
    if m['ret_6m'] is not None:
        if m['ret_6m'] > 15:   mom_score += 4
        elif m['ret_6m'] > 5:  mom_score += 2
        elif m['ret_6m'] > -10: mom_score += 1
    score += mom_score

    # 3. 基本面 (50) ── Buffett Framework
    fund_score = 0
    is_crypto = '-USD' in m['ticker']
    if is_crypto:
        fund_score = 25 if (m['ret_12m'] or 0) > 0 else 12
    else:
        # A. 营收增长 (8 分) — 顶线成长性
        if m['rev_growth'] is not None:
            rg = m['rev_growth'] * 100
            if rg > 30:   fund_score += 8
            elif rg > 15: fund_score += 6
            elif rg > 5:  fund_score += 4
            elif rg > 0:  fund_score += 2

        # B. 盈利质量 (8 分) — 净利率 + 盈利增速
        #    Buffett: 持续高利润率 = 定价权 + 运营效率
        if m['profit_margin'] is not None:
            pm = m['profit_margin'] * 100
            if pm > 25:   fund_score += 5
            elif pm > 15: fund_score += 3
            elif pm > 5:  fund_score += 1
            elif pm < 0:  fund_score -= 5
        if m['earnings_growth'] is not None:
            eg = m['earnings_growth'] * 100
            if eg > 25:    fund_score += 3
            elif eg > 10:  fund_score += 2
            elif eg > 0:   fund_score += 1
            elif eg < -15: fund_score -= 2

        # C. 护城河 (9 分) — 毛利率是定价权/竞争壁垒最直接代理指标
        #    Buffett: great businesses have consistently high gross margins
        if m['gross_margin'] is not None:
            gm = m['gross_margin'] * 100
            if gm > 65:   fund_score += 9
            elif gm > 50: fund_score += 7
            elif gm > 35: fund_score += 5
            elif gm > 20: fund_score += 3
            elif gm > 10: fund_score += 1

        # D. 资本回报率 ROE (8 分) — Buffett 最核心单项指标
        #    ROE > 15% = management 在有效地为股东复利
        if m['roe'] is not None:
            roe = m['roe'] * 100
            if roe > 30:   fund_score += 8
            elif roe > 20: fund_score += 6
            elif roe > 15: fund_score += 4
            elif roe > 5:  fund_score += 2
            elif roe < 0:  fund_score -= 3

        # E. 自由现金流收益率 (9 分) — Buffett "owner earnings"
        #    FCF yield = FCF / 市值; >5% 相当于 P/FCF < 20，强烈看好
        if m['fcf_yield'] is not None:
            fy = m['fcf_yield'] * 100
            if fy > 8:   fund_score += 9
            elif fy > 5: fund_score += 7
            elif fy > 3: fund_score += 4
            elif fy > 1: fund_score += 2
            elif fy > 0: fund_score += 1
            else:        fund_score -= 3  # 负 FCF = 持续烧钱

        # F. 估值 P/E + PEG (6 分) — Margin of safety，不为好公司付过高价格
        #    三层: PEG (成长调整后 P/E) + Forward P/E
        if m['peg'] is not None and m['peg'] > 0:
            if m['peg'] < 1:   fund_score += 3
            elif m['peg'] < 2: fund_score += 2
            elif m['peg'] < 3: fund_score += 1
        if m['forward_pe'] is not None and m['forward_pe'] > 0:
            fpe = m['forward_pe']
            if fpe < 15:   fund_score += 3
            elif fpe < 25: fund_score += 2
            elif fpe < 40: fund_score += 1

        # G. 同行比较 (4 分) — 相对竞争地位
        if sector_stats:
            keys = ('gross_margin', 'roe', 'profit_margin', 'rev_growth', 'fcf_yield')
            total_compared = sum(1 for k in keys if m.get(k) is not None and sector_stats.get(k) is not None)
            above = sum(1 for k in keys if m.get(k) is not None and sector_stats.get(k) is not None and m[k] > sector_stats[k])
            if total_compared > 0:
                pct = above / total_compared
                if pct >= 0.8:   fund_score += 4; notes.append("同行Top")
                elif pct >= 0.6: fund_score += 2
                elif pct >= 0.4: fund_score += 1

    score += fund_score

    # 4. 风险控制 (20)
    risk_score = 20
    if m['vol_annual'] is not None:
        if m['vol_annual'] > 80:   risk_score -= 10
        elif m['vol_annual'] > 50: risk_score -= 6
        elif m['vol_annual'] > 30: risk_score -= 2
    if m['max_dd'] is not None:
        if m['max_dd'] < -60:   risk_score -= 8
        elif m['max_dd'] < -40: risk_score -= 4
    if m['debt_to_equity'] is not None and m['debt_to_equity'] > 200:
        risk_score -= 3
        notes.append("高负债")
    if m.get('current_ratio') is not None and m['current_ratio'] < 1:
        risk_score -= 2
        notes.append("流动性弱")
    score += max(0, risk_score)

    if m['w_rsi'] is not None and m['w_rsi'] > 78:
        score -= 3
        notes.append("周RSI超买")

    return max(0, min(100, score)), notes


def get_rating(score, m):
    """根据评分和情境给出建议"""
    if score >= 75:
        return "🟢 买入 / 核心持仓", "长线趋势和基本面均强劲, 可作为组合核心配置"
    elif score >= 62:
        return "🟢 增持 / 长线建仓", "长线质地良好, 适合分批建仓"
    elif score >= 48:
        return "🟡 持有 / 观望", "有基础但需更多确认, 持仓可留, 不急于加仓"
    elif score >= 35:
        return "🟠 减持 / 风险警告", "趋势或基本面存疑, 建议降低仓位"
    else:
        return "🔴 回避 / 重新评估", "长线趋势弱, 不适合现阶段建立多头仓位"


def format_pct(v, decimals=1):
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return "—"
    return f"{v:+.{decimals}f}%"


def format_num(v, decimals=2):
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return "—"
    if abs(v) > 1e9:
        return f"${v/1e9:.1f}B"
    if abs(v) > 1e6:
        return f"${v/1e6:.1f}M"
    return f"${v:.{decimals}f}"


def load_previous_snapshot(out_path):
    """找到最近一份 (非今天) 的 sidecar JSON 用于做日间对比。"""
    parent = out_path.parent
    today_stem = out_path.stem
    candidates = sorted(
        [c for c in parent.glob('long_term_strategy_*.json') if c.stem != today_stem],
        key=lambda p: p.stem,
    )
    if not candidates:
        return None, None
    prev = candidates[-1]
    try:
        data = json.loads(prev.read_text(encoding='utf-8'))
        date_str = prev.stem.replace('long_term_strategy_', '')
        return data, date_str
    except Exception:
        return None, None


def save_snapshot(results, out_path, sector_of):
    """保存一份精简的 ticker → score 快照, 供下次运行对比使用。"""
    snapshot = {}
    for ticker, r in results.items():
        snapshot[ticker] = {
            'score': r.get('score'),
            'price': r.get('price'),
            'ret_12m': r.get('ret_12m'),
            'rating': r.get('rating'),
            'above_ma200': r.get('above_ma200'),
            'sector': sector_of.get(ticker),
        }
    json_path = out_path.with_suffix('.json')
    json_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')


def diff_section(results, prev_snapshot, prev_date, sector_of, index_tickers):
    """生成与上一期的对比章节。返回 markdown 行列表。

    展示:
      - 评分变化最大的 5 个上升 / 5 个下降 (≥3 分变动)
      - 新进 Top15 / 跌出 Top15
      - 评级跨档变化 (例如 持有→买入)
    """
    lines = []
    lines.append(f"## 📊 与上期 ({prev_date}) 对比")
    lines.append("")

    # 当前与上期的非指数 ticker 评分
    today_scores = {t: r['score'] for t, r in results.items() if t not in index_tickers}
    prev_scores = {t: v.get('score') for t, v in prev_snapshot.items()
                   if t not in index_tickers and v.get('score') is not None}

    common = [t for t in today_scores if t in prev_scores]
    deltas = sorted(
        [(t, today_scores[t] - prev_scores[t]) for t in common],
        key=lambda x: -x[1],
    )
    risers = [(t, d) for t, d in deltas if d >= 3][:5]
    fallers = [(t, d) for t, d in deltas[::-1] if d <= -3][:5]

    if risers:
        lines.append("### 🔺 评分上升 Top 5")
        lines.append("")
        lines.append("| 标的 | 板块 | 上期分 | 今日分 | 变化 | 12M 回报 |")
        lines.append("|------|------|--------|--------|------|---------|")
        for t, d in risers:
            r = results[t]
            ret12 = format_pct(r.get('ret_12m'), 0)
            lines.append(f"| **{t}** | {sector_of.get(t, '—')} | {prev_scores[t]} | "
                         f"{today_scores[t]} | **+{d}** | {ret12} |")
        lines.append("")

    if fallers:
        lines.append("### 🔻 评分下降 Top 5")
        lines.append("")
        lines.append("| 标的 | 板块 | 上期分 | 今日分 | 变化 | 12M 回报 |")
        lines.append("|------|------|--------|--------|------|---------|")
        for t, d in fallers:
            r = results[t]
            ret12 = format_pct(r.get('ret_12m'), 0)
            lines.append(f"| **{t}** | {sector_of.get(t, '—')} | {prev_scores[t]} | "
                         f"{today_scores[t]} | **{d}** | {ret12} |")
        lines.append("")

    # Top15 进出
    today_top15 = set([t for t, _ in sorted(today_scores.items(), key=lambda x: -x[1])[:15]])
    prev_top15 = set([t for t, _ in sorted(prev_scores.items(), key=lambda x: -x[1])[:15]])
    new_in = today_top15 - prev_top15
    dropped = prev_top15 - today_top15
    if new_in or dropped:
        lines.append("### 🔄 Top 15 买入榜进出")
        lines.append("")
        if new_in:
            entries = sorted(new_in, key=lambda t: -today_scores[t])
            parts = [f"**{t}** ({today_scores[t]}分)" for t in entries]
            lines.append(f"- 🟢 **新进入**: {', '.join(parts)}")
        if dropped:
            entries = sorted(dropped, key=lambda t: -prev_scores[t])
            parts = []
            for t in entries:
                cur = today_scores.get(t, '—')
                parts.append(f"**{t}** ({prev_scores[t]}→{cur})")
            lines.append(f"- 🔴 **跌出榜单**: {', '.join(parts)}")
        lines.append("")

    # 评级跨档变化
    rating_order = {
        "🔴 回避 / 重新评估": 0,
        "🟠 减持 / 风险警告": 1,
        "🟡 持有 / 观望": 2,
        "🟢 增持 / 长线建仓": 3,
        "🟢 买入 / 核心持仓": 4,
    }
    upgrades = []
    downgrades = []
    for t in common:
        cur_rating = results[t].get('rating')
        prev_rating = prev_snapshot.get(t, {}).get('rating')
        if cur_rating and prev_rating and cur_rating != prev_rating:
            cur_lvl = rating_order.get(cur_rating, -1)
            prev_lvl = rating_order.get(prev_rating, -1)
            if cur_lvl > prev_lvl:
                upgrades.append((t, prev_rating, cur_rating))
            elif cur_lvl < prev_lvl:
                downgrades.append((t, prev_rating, cur_rating))

    if upgrades or downgrades:
        lines.append("### 🎚️ 评级跨档变化")
        lines.append("")
        if upgrades:
            parts = [f"**{t}** ({pr.split(' ')[1]}→{cr.split(' ')[1]})"
                     for t, pr, cr in upgrades[:8]]
            lines.append(f"- 升档: {', '.join(parts)}")
        if downgrades:
            parts = [f"**{t}** ({pr.split(' ')[1]}→{cr.split(' ')[1]})"
                     for t, pr, cr in downgrades[:8]]
            lines.append(f"- 降档: {', '.join(parts)}")
        lines.append("")

    if not (risers or fallers or new_in or dropped or upgrades or downgrades):
        lines.append("_本期所有标的评分与评级相对上期无显著变化 (变动 <3 分)。_")
        lines.append("")

    return lines


def compute_one(ticker):
    """第一轮: 只获取数据和计算指标，不打分（打分需要板块中位数）。"""
    data = fetch_data(ticker)
    if data is None:
        return None
    try:
        return compute_metrics(data)
    except Exception:
        return None


def score_one(m, sector_stats=None):
    """第二轮: 带板块参照打分。"""
    score, notes = score_stock(m, sector_stats=sector_stats)
    rating, reason = get_rating(score, m)
    m['score'] = score
    m['notes'] = notes
    m['rating'] = rating
    m['reason'] = reason
    return m


def main():
    print("\n" + "=" * 80)
    print("  📊 长线策略分析 (1 年+ 视角) - AI Portfolio")
    print(f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 80)

    # 汇总所有 ticker
    all_tickers = []
    sector_of = {}
    for sec, ticks in SECTORS.items():
        for t in ticks:
            if t not in sector_of:
                all_tickers.append(t)
                sector_of[t] = sec
    index_tickers = list(INDICES.values())
    index_names = {v: k for k, v in INDICES.items()}

    print(f"\n分析 {len(all_tickers)} 只标的 + {len(index_tickers)} 个指数...")

    # 第一轮: 并行获取数据 + 计算指标
    raw = {}
    with ThreadPoolExecutor(max_workers=20) as ex:
        futures = {ex.submit(compute_one, t): t for t in all_tickers + index_tickers}
        done_count = 0
        total = len(futures)
        for fut in as_completed(futures):
            t = futures[fut]
            r = fut.result()
            if r:
                raw[t] = r
            done_count += 1
            if done_count % 20 == 0:
                print(f"  已完成 {done_count}/{total}")

    print(f"  ✅ 成功获取 {len(raw)}/{total} 只标的数据")

    # 空报告守门: 拉取成功率过低时, 不覆盖当天报告 — 避免出现"全 0 标的"垃圾报告
    MIN_TICKERS = 50
    if len(raw) < MIN_TICKERS:
        print(f"\n❌ 致命: 仅 {len(raw)}/{total} 只标的成功 (< {MIN_TICKERS}), 疑似 yfinance 限流/网络故障")
        print("    → 跳过本次报告生成, 等下一次定时任务重试")
        sys.exit(2)

    # 第二轮: 计算板块中位数，然后带同行参照打分
    sector_stats_map = {}
    for sec, ticks in SECTORS.items():
        members = [raw[t] for t in ticks if t in raw and '-USD' not in t]
        sector_stats_map[sec] = compute_sector_stats(members) if members else {}

    results = {}
    for t, m in raw.items():
        sec = sector_of.get(t)
        stats = sector_stats_map.get(sec)
        results[t] = score_one(m, sector_stats=stats)

    # 保存报告
    out_path = Path(__file__).parent / f"long_term_strategy_{datetime.now().strftime('%Y-%m-%d')}.md"

    # 加载上一期快照, 用于稍后渲染对比章节
    prev_snapshot, prev_date = load_previous_snapshot(out_path)

    lines = []

    def p(s=""):
        lines.append(s)
        print(s)

    p(f"# 长线策略分析报告 (1 年+ 视角)")
    p(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    p(f"**分析范围**: {len(results)} 只标的 (股票 + 指数 + 加密货币)")
    p()
    p("## 📈 一、大盘指数 — 宏观环境判断")
    p()
    p("| 指数 | 现价 | 1M | 3M | 6M | 12M | vs MA200 | 周RSI | 评分 | 建议 |")
    p("|------|------|----|----|----|----|---------|-------|------|------|")
    for name, tk in INDICES.items():
        if tk in results:
            m = results[tk]
            vs_ma200 = f"{(m['price']/m['ma200']-1)*100:+.1f}%" if m['ma200'] else "—"
            rsi_s = f"{m['w_rsi']:.0f}" if m['w_rsi'] else "—"
            p(f"| **{name}** | ${m['price']:.2f} | {format_pct(m['ret_1m'])} | {format_pct(m['ret_3m'])} | "
              f"{format_pct(m['ret_6m'])} | {format_pct(m['ret_12m'])} | {vs_ma200} | "
              f"{rsi_s} | {m['score']} | {m['rating']} |")
    p()

    # 宏观解读
    p("### 🧭 宏观解读")
    ixic = results.get('^IXIC', {})
    gspc = results.get('^GSPC', {})
    rut = results.get('^RUT', {})
    hsi = results.get('^HSI', {})
    macro_notes = []
    if gspc.get('above_ma200') and ixic.get('above_ma200'):
        macro_notes.append("- **美股主趋势: 多头** ✅ 标普与纳指均站稳 200 日均线, 1 年+ 长线配置环境友好")
    else:
        macro_notes.append("- **美股主趋势: 转弱** ⚠️ 主要指数跌破 200 日均线, 长线建仓宜更谨慎, 分批进场")
    if rut.get('ret_12m') is not None and ixic.get('ret_12m') is not None:
        gap = ixic['ret_12m'] - rut['ret_12m']
        if gap > 15:
            macro_notes.append(f"- **大小盘分化: 明显** 纳指领先罗素 2000 约 {gap:.0f} 个百分点 → 资金集中在大市值 AI/科技龙头, 中小盘行情尚未扩散")
        elif gap < -5:
            macro_notes.append(f"- **中小盘反而领先** 罗素 2000 跑赢纳指 → 行情扩散, 有利于小市值成长股")
    if hsi.get('ret_12m') is not None:
        if hsi['ret_12m'] > 10:
            macro_notes.append(f"- **港股/中概: 回暖** 恒指 12M 回报 {hsi['ret_12m']:+.0f}% → 中概股长线仓可逐步恢复")
        elif hsi['ret_12m'] < -10:
            macro_notes.append(f"- **港股/中概: 偏弱** 恒指 12M {hsi['ret_12m']:+.0f}% → 中概股仓位宜控制在组合 5-10% 以内")

    for n in macro_notes:
        p(n)
    p()

    # 与上期对比 (如果有上一期快照)
    if prev_snapshot:
        for line in diff_section(results, prev_snapshot, prev_date, sector_of, set(index_tickers)):
            p(line)
    else:
        p("## 📊 与上期对比")
        p()
        p("_未找到上一期快照, 本期为基准。下次运行起将自动展示日间评分变化。_")
        p()

    # 按板块生成分析
    p("## 🏢 二、各板块长线分析")
    p()

    for sector_name, tickers in SECTORS.items():
        sector_results = [results[t] for t in tickers if t in results]
        if not sector_results:
            continue

        avg_score = np.mean([r['score'] for r in sector_results])
        avg_ret12 = np.mean([r['ret_12m'] for r in sector_results if r['ret_12m'] is not None])

        p(f"### {sector_name}")
        p(f"板块平均评分: **{avg_score:.0f}/100** · 平均 12M 回报: **{avg_ret12:+.1f}%**")
        p()
        p("| 标的 | 价格 | 12M | vs MA200 | 周RSI | 营收增长 | PEG | 评分 | 建议 |")
        p("|------|------|-----|---------|-------|---------|-----|------|------|")

        sector_results.sort(key=lambda x: -x['score'])
        for r in sector_results:
            vs_ma200 = f"{(r['price']/r['ma200']-1)*100:+.0f}%" if r['ma200'] else "—"
            w_rsi_s = f"{r['w_rsi']:.0f}" if r['w_rsi'] else "—"
            rg_s = f"{r['rev_growth']*100:+.0f}%" if r['rev_growth'] is not None else "—"
            peg_s = f"{r['peg']:.2f}" if r['peg'] and r['peg'] > 0 else "—"
            ret12_s = format_pct(r['ret_12m'], 0)
            p(f"| **{r['ticker']}** | ${r['price']:.2f} | {ret12_s} | {vs_ma200} | {w_rsi_s} | {rg_s} | {peg_s} | **{r['score']}** | {r['rating']} |")
        p()

    # Top Buy / Avoid 汇总
    p("## 🎯 三、Top Buy & Top Avoid 精选")
    p()
    all_results = [r for r in results.values() if r['ticker'] not in index_tickers]
    all_results.sort(key=lambda x: -x['score'])

    p("### 🟢 Top 15 长线买入候选 (最高评分)")
    p()
    p("| 排名 | 标的 | 板块 | 评分 | 12M回报 | 关键逻辑 |")
    p("|------|------|------|------|---------|----------|")
    for i, r in enumerate(all_results[:15], 1):
        logic_parts = []
        if r['above_ma200']: logic_parts.append("长期多头")
        if r['rev_growth'] and r['rev_growth'] > 0.20: logic_parts.append(f"营收+{r['rev_growth']*100:.0f}%")
        if r['profit_margin'] and r['profit_margin'] > 0.15: logic_parts.append(f"净利率{r['profit_margin']*100:.0f}%")
        if r['ret_12m'] and r['ret_12m'] > 30: logic_parts.append(f"12M+{r['ret_12m']:.0f}%")
        if r['peg'] and 0 < r['peg'] < 1.5: logic_parts.append(f"PEG{r['peg']:.1f}")
        if not logic_parts: logic_parts.append("技术趋势强劲")
        p(f"| {i} | **{r['ticker']}** | {sector_of.get(r['ticker'], '—')} | {r['score']} | {format_pct(r['ret_12m'], 0)} | {', '.join(logic_parts[:3])} |")
    p()

    p("### 🔴 Top 15 回避/减持 (最低评分)")
    p()
    p("| 排名 | 标的 | 板块 | 评分 | 12M回报 | 最大回撤 | 关键风险 |")
    p("|------|------|------|------|---------|----------|----------|")
    for i, r in enumerate(all_results[-15:][::-1], 1):
        risk_parts = []
        if not r['above_ma200']: risk_parts.append("跌破MA200")
        if r['ret_12m'] and r['ret_12m'] < -20: risk_parts.append(f"大幅下跌")
        if r['profit_margin'] and r['profit_margin'] < 0: risk_parts.append("亏损")
        if r['max_dd'] and r['max_dd'] < -50: risk_parts.append(f"回撤>{abs(r['max_dd']):.0f}%")
        if r['vol_annual'] and r['vol_annual'] > 80: risk_parts.append(f"波动率{r['vol_annual']:.0f}%")
        if not risk_parts: risk_parts.append("综合弱势")
        dd_s = f"{r['max_dd']:.0f}%" if r['max_dd'] else "—"
        p(f"| {i} | **{r['ticker']}** | {sector_of.get(r['ticker'], '—')} | {r['score']} | {format_pct(r['ret_12m'], 0)} | {dd_s} | {', '.join(risk_parts[:3])} |")
    p()

    # 加密货币专栏
    p("## ₿ 四、加密货币长线分析")
    p()
    crypto_tickers = ['BTC-USD', 'ETH-USD', 'XRP-USD', 'SOL-USD', 'ADA-USD', 'DOGE-USD']
    p("| 加密货币 | 现价 | 12M | vs MA200 | 年化波动率 | 最大回撤 | 评分 | 长线建议 |")
    p("|---------|------|-----|---------|-----------|----------|------|----------|")
    for t in crypto_tickers:
        if t in results:
            r = results[t]
            vs_ma200 = f"{(r['price']/r['ma200']-1)*100:+.0f}%" if r['ma200'] else "—"
            vol_s = f"{r['vol_annual']:.0f}%" if r['vol_annual'] else "—"
            dd_s = f"{r['max_dd']:.0f}%" if r['max_dd'] else "—"
            p(f"| **{t}** | ${r['price']:.2f} | {format_pct(r['ret_12m'], 0)} | {vs_ma200} | {vol_s} | {dd_s} | **{r['score']}** | {r['rating']} |")
    p()

    # 资产配置建议
    p("## 💼 五、长线资产配置建议")
    p()
    p("基于上述分析, 针对 1 年+ 投资者的组合配置框架 (假设 100% 风险资产):")
    p()
    p("| 类别 | 建议仓位 | 代表标的 | 理由 |")
    p("|------|---------|----------|------|")
    p("| **AI/半导体龙头** | 25-30% | NVDA, AVGO, TSM, ASML | AI 算力基建 5-10 年超级周期核心 |")
    p("| **超大规模云** | 20-25% | MSFT, GOOGL, META, AMZN | 现金流 + AI 变现双轮驱动, 低 Beta 压舱石 |")
    p("| **AI 应用/软件** | 10-15% | PLTR, NOW, CRWD, SNOW | 企业 AI 渗透率提升, 高毛利订阅模式 |")
    p("| **自动驾驶/具身智能** | 8-12% | TSLA, ISRG | 物理 AI, 长坡厚雪但波动高 |")
    p("| **加密货币** | 5-10% | BTC, ETH | 数字黄金/全球流动性对冲, 单品不超过 5% |")
    p("| **能源/核能** | 5-8% | OKLO, SMR, MP | AI 耗电的长线受益方 |")
    p("| **医疗/机器人** | 5-8% | LLY, ISRG, TMDX | 人口老龄化 + AI 赋能 |")
    p("| **高风险高回报** | 0-5% | 量子/小市值 | IONQ/RGTI 等仅作尾部 Beta, 单品 <1% |")
    p("| **现金/短债** | 5-10% | — | 留子弹应对回调 |")
    p()

    # 关键风险与交易纪律
    p("## ⚠️ 六、长线交易纪律")
    p()
    p("1. **分批建仓**: 一次性 All-in 是长线最大风险, 将目标仓位分 3-4 批, 每批间隔 3-4 周或回调 5-8% 再加")
    p("2. **定期再平衡**: 每季度检查一次板块权重, 单板块超过 35%、单股超过 10% 应减仓")
    p("3. **止损阈值**: 长线并不意味不止损 — 任何标的跌破周线 MA50 且伴随基本面恶化 (连续两季营收负增长) 应减半仓")
    p("4. **不追涨超买**: 周线 RSI > 78 时不新开仓, 已持仓可保留")
    p("5. **现金流策略**: 对现金流股票 (AAPL/GOOGL/META/MSFT) 偏 Buy & Hold, 对高成长无利润股 (量子/小型 AI) 偏波段")
    p("6. **宏观再校准**: 每半年复评一次 — Fed 政策、中美博弈、AI 进展都可能改变配置优先级")
    p()

    p("---")
    p(f"*报告生成: {datetime.now().strftime('%Y-%m-%d %H:%M')} · 数据来源: Yahoo Finance · 本分析仅供参考, 不构成投资建议*")

    # 写文件
    out_path.write_text("\n".join(lines), encoding='utf-8')
    print(f"\n✅ 报告已保存: {out_path}")

    # 写一份精简快照, 供下次运行做日间对比
    save_snapshot(results, out_path, sector_of)
    print(f"   快照已保存: {out_path.with_suffix('.json').name}")


if __name__ == '__main__':
    main()
