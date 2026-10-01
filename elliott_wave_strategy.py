"""
Elliott Wave 投资策略 - AI_Portfolios.xlsx 全标的扫描
====================================================
对 AI_Portfolios.xlsx 中的所有股票/指数/加密货币进行 Elliott Wave 分析:

核心算法:
1. ZigZag 摆动点识别 (自适应阈值, 周线优先, 日线辅助)
2. Elliott Wave 5+3 形态匹配 (Impulse 1-2-3-4-5 + Corrective A-B-C)
3. Elliott Wave 三大铁律校验:
   - Rule 1: Wave 2 不能回撤超过 Wave 1 起点
   - Rule 2: Wave 3 不能是 1/3/5 中最短的浪
   - Rule 3: Wave 4 不能进入 Wave 1 的价格区间 (除楔形外)
4. Fibonacci 比例验证 (Wave 2: 0.5/0.618, Wave 3: 1.618/2.618, Wave 4: 0.382, Wave 5: 1.0/1.618)
5. 当前波浪定位 + 入场/止损/目标位生成
6. 综合评级: STRONG BUY / BUY / HOLD / REDUCE / SELL / AVOID

输出:
- Markdown 报告 (按板块分组, 含每个标的的波浪计数 + 交易建议)
- Excel 汇总 (一行一个标的, 含分数 + 操作 + 三个目标位)
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
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ===== 股票分类 + 名称→Ticker 映射 (与 long_term_strategy.py 对齐) =====
SECTORS = {
    'Hyperscaler (超大规模云)':       ['GOOGL', 'AMZN', 'META', 'MSFT', 'AAPL'],
    'Self-Driving (自动驾驶)':        ['TSLA', 'GOOGL', 'PONY', 'UBER', 'GRAB'],
    'Robotics (机器人)':              ['SERV', 'PATH', 'ISRG'],
    'Semis (半导体)':                 ['NVDA', 'AMD', 'AVGO', 'TSM', 'ARM', 'MRVL', 'MU', 'INTC', 'SMCI', 'ANET', 'DELL', 'ASML', 'QCOM',
                                       'AMAT', 'LRCX', 'KLAC', 'COHR', 'TXN', 'ADI', 'NXPI', 'MCHP', 'GFS', 'TER', 'SKHY'],
    'AI Infrastructure (AI 基建)':    ['CRWV', 'ORCL', 'IREN', 'NBIS', 'CIFR', 'APLD', 'CSCO', 'VRT', 'GEV', 'ETN', 'DLR',
                                       'VST', 'CEG', 'CIEN', 'PSTG'],
    'Energy (能源)':                  ['OKLO', 'LAC', 'MP', 'SMR', 'BE', 'ONDS', 'QS', 'EOSE'],
    'Software (软件)':                ['PLTR', 'SNOW', 'AI', 'IBM', 'MDB', 'NOW', 'CRM', 'ADBE', 'OKTA', 'SHOP',
                                       'SOUN', 'BBAI', 'UPST', 'DUOL', 'RBRK', 'DDOG', 'NFLX', 'ZETA', 'SPOT', 'APP',
                                       'RDDT', 'TTD', 'RBLX', 'U', 'INFY', 'ALAB', 'CRDO', 'WOLF', 'SNPS',
                                       'CRWD', 'PANW', 'ZS', 'NET', 'TEAM', 'WDAY', 'INTU',
                                       'S', 'GTLB', 'ESTC', 'TWLO', 'CFLT', 'HUBS'],
    'Health (医疗)':                  ['UNH', 'OSCR', 'HIMS', 'RXRX', 'LLY', 'TEM', 'CRSP', 'TMDX'],
    'Space (太空/出行)':              ['RKLB', 'FLY', 'JOBY', 'ACHR', 'LUNR', 'ASTS'],
    'China (中概股)':                 ['BABA', 'BIDU', 'JD', 'XPEV', 'NIO', 'PDD', 'FUTU', 'TCEHY'],
    'Crypto (加密货币及相关)':        ['BTC-USD', 'ETH-USD', 'XRP-USD', 'SOL-USD', 'ADA-USD', 'DOGE-USD',
                                       'MSTR', 'COIN', 'CLSK', 'RIOT', 'MARA', 'HUT', 'BMNR', 'SBET',
                                       'FIG', 'CRCL', 'XYZ', 'BULL', 'HIVE', 'HOOD'],
    'Finance (金融科技)':             ['SOFI', 'OPEN', 'LMND', 'HOOD', 'PYPL', 'AFRM', 'BULL'],
    'Quantum (量子计算)':             ['RGTI', 'IONQ', 'QUBT', 'QBTS'],
    'Trading/Consumer (交易热门)':    ['GME', 'LULU', 'CMG', 'UPS', 'ABNB', 'PTON', 'BA', 'NKE'],
    'Rotation (轮动板凳)':            ['JPM', 'GS', 'BRK-B', 'XOM', 'CVX', 'CAT', 'DE', 'GE', 'COST', 'WMT', 'JNJ', 'XLU'],
    'Commodity (商品)':               ['GLD', 'SLV', 'CPER', 'USO'],
}

INDICES = {
    'Nasdaq':       '^IXIC',
    'S&P 500':      '^GSPC',
    'Dow Jones':    '^DJI',
    'Hang Seng':    '^HSI',
    'Shanghai SSE': '000001.SS',
}


# ============================================================
# 1. 数据获取
# ============================================================
def fetch_data(ticker):
    """拉 5 年周线 + 2 年日线 (波浪分析以周线为主, 日线确认入场)"""
    try:
        t = yf.Ticker(ticker)
        weekly = t.history(period='5y', interval='1wk', auto_adjust=True)
        daily = t.history(period='2y', interval='1d', auto_adjust=True)
        if weekly.empty or len(weekly) < 50:
            return None
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
        return {'ticker': ticker, 'weekly': weekly, 'daily': daily, 'live_price': live_price}
    except Exception:
        return None


# ============================================================
# 2. ZigZag 摆动点识别 (Elliott Wave 的基础)
# ============================================================
def zigzag_pivots(prices, threshold_pct):
    """
    返回 [(idx, price, kind)]，kind: 'H' = 高点, 'L' = 低点
    threshold_pct: 反向波动达到此比例才确认拐点 (例如 0.08 = 8%)
    """
    if len(prices) < 3:
        return []

    pivots = []
    last_idx = 0
    last_price = prices[0]
    direction = 0  # 1 = 上, -1 = 下, 0 = 待定

    for i in range(1, len(prices)):
        p = prices[i]
        if direction == 0:
            change = (p - last_price) / last_price
            if change >= threshold_pct:
                pivots.append((last_idx, last_price, 'L'))
                direction = 1
                last_idx, last_price = i, p
            elif change <= -threshold_pct:
                pivots.append((last_idx, last_price, 'H'))
                direction = -1
                last_idx, last_price = i, p
        elif direction == 1:
            if p >= last_price:
                last_idx, last_price = i, p
            elif (last_price - p) / last_price >= threshold_pct:
                pivots.append((last_idx, last_price, 'H'))
                direction = -1
                last_idx, last_price = i, p
        else:  # direction == -1
            if p <= last_price:
                last_idx, last_price = i, p
            elif (p - last_price) / last_price >= threshold_pct:
                pivots.append((last_idx, last_price, 'L'))
                direction = 1
                last_idx, last_price = i, p

    pivots.append((last_idx, last_price, 'H' if direction == 1 else 'L'))
    return pivots


def adaptive_pivots(prices):
    """自适应阈值: 高波动用大阈值, 低波动用小阈值, 目标得到 8-15 个拐点"""
    log_ret = np.diff(np.log(prices + 1e-9))
    vol = np.std(log_ret) * np.sqrt(52)  # 年化波动率
    base = max(0.04, min(0.20, vol * 0.45))  # 4%-20% 区间

    for thr in [base, base * 0.75, base * 1.3, base * 0.5, base * 1.6]:
        pivots = zigzag_pivots(prices, thr)
        if 8 <= len(pivots) <= 18:
            return pivots, thr

    return zigzag_pivots(prices, base), base


# ============================================================
# 3. Elliott Wave 形态识别 + 校验
# ============================================================
def validate_impulse(p0, p1, p2, p3, p4, p5, direction='up'):
    """
    校验 5 浪推动结构 (impulse). 返回 (是否合规, 评分 0-100, 失分项)
    direction = 'up' 时 p0/p2/p4 是低点, p1/p3/p5 是高点; 'down' 反之
    """
    issues = []
    score = 100

    if direction == 'up':
        w1 = p1 - p0   # 浪 1 (上)
        w2 = p1 - p2   # 浪 2 (回撤)
        w3 = p3 - p2   # 浪 3 (上)
        w4 = p3 - p4   # 浪 4 (回撤)
        w5 = p5 - p4   # 浪 5 (上)
    else:
        w1 = p0 - p1
        w2 = p2 - p1
        w3 = p2 - p3
        w4 = p4 - p3
        w5 = p4 - p5

    if min(w1, w2, w3, w4, w5) <= 0:
        return False, 0, ['方向不一致']

    # Rule 1: Wave 2 retrace < 100% of Wave 1
    r2 = w2 / w1
    if r2 >= 1.0:
        return False, 0, ['Rule1 违反: Wave2 回撤 >= 100%']
    if not (0.382 <= r2 <= 0.786):
        score -= 10
        issues.append(f'W2 回撤 {r2:.0%} 偏离理想 38.2-78.6%')

    # Rule 2: Wave 3 not the shortest
    if w3 < w1 and w3 < w5:
        return False, 0, ['Rule2 违反: Wave3 是最短浪']
    r3 = w3 / w1
    if r3 < 1.0:
        score -= 15
        issues.append(f'W3 仅为 W1 的 {r3:.1f}x (理想 >1.618x)')
    elif r3 < 1.618:
        score -= 5

    # Rule 3: Wave 4 doesn't overlap Wave 1
    if direction == 'up':
        if p4 <= p1:
            return False, 0, ['Rule3 违反: Wave4 进入 Wave1 区间']
    else:
        if p4 >= p1:
            return False, 0, ['Rule3 违反: Wave4 进入 Wave1 区间']

    # Wave 4 retrace
    r4 = w4 / w3
    if not (0.236 <= r4 <= 0.5):
        score -= 8
        issues.append(f'W4 回撤 {r4:.0%} 偏离理想 23.6-50%')

    # Wave 5 vs Wave 1 (typical equality or 0.618)
    r5 = w5 / w1
    if r5 < 0.382:
        score -= 10
        issues.append(f'W5 仅 W1 的 {r5:.1f}x (偏弱)')

    # Alternation: W2 vs W4 should differ (one sharp, one sideways)
    if abs(r2 - r4) < 0.1:
        score -= 5
        issues.append('W2/W4 缺乏交替性')

    return True, score, issues


def detect_wave_count(pivots, current_price):
    """
    识别当前波浪计数. 返回字典:
      {direction, wave_label, wave_score, pivots_used, fib_targets, issues}
    扫描最近 6-8 个拐点, 寻找最优 5 浪结构
    """
    if len(pivots) < 6:
        return None

    best = None

    # 扫描所有可能的窗口: 推动浪起点可能在任意拐点, 终点 + 修正可贴近末尾
    # n_total = 推动 + 修正部分长度: 6 (无修正) / 7 (A) / 8 (A+B)
    # start = 推动浪起点在 pivots 中的位置, 越靠近末尾结构越新鲜
    max_lookback = min(len(pivots), 14)
    for n_total in [6, 7, 8]:
        # 优先尝试更新鲜的窗口 (右端贴近 pivots[-1])
        for end in range(len(pivots), max(len(pivots) - 4, n_total) - 1, -1):
            start = end - n_total
            if start < 0 or end - start != n_total:
                continue
            if len(pivots) - end > max_lookback - n_total:
                continue
            seg = pivots[start:end]
            p0, p1, p2, p3, p4, p5 = [seg[i][1] for i in range(6)]
            k0, k1, k2, k3, k4, k5 = [seg[i][2] for i in range(6)]

            # 上行推动: L H L H L H
            if (k0, k1, k2, k3, k4, k5) == ('L', 'H', 'L', 'H', 'L', 'H'):
                valid, score, issues = validate_impulse(p0, p1, p2, p3, p4, p5, 'up')
                if valid:
                    # 越新鲜越好: 加 freshness 奖励
                    freshness_bonus = max(0, 10 - (len(pivots) - end) * 3)
                    eff = score + freshness_bonus
                    if best is None or eff > best['wave_score']:
                        cand = _build_count(seg, n_total, 'up', score, issues, current_price)
                        cand['_eff'] = eff
                        best = cand

            elif (k0, k1, k2, k3, k4, k5) == ('H', 'L', 'H', 'L', 'H', 'L'):
                valid, score, issues = validate_impulse(p0, p1, p2, p3, p4, p5, 'down')
                if valid:
                    freshness_bonus = max(0, 10 - (len(pivots) - end) * 3)
                    eff = score + freshness_bonus
                    if best is None or eff > best['wave_score']:
                        cand = _build_count(seg, n_total, 'down', score, issues, current_price)
                        cand['_eff'] = eff
                        best = cand

    return best


def _build_count(seg, n, direction, score, issues, current_price):
    """构造波浪计数结果, 推断当前位置 + 计算 Fibonacci 目标"""
    p_prices = [s[1] for s in seg]
    p0, p1, p2, p3, p4, p5 = p_prices[:6]
    # 修正浪 A/B/C 对应 seg[6], seg[7], seg[8] (若存在)
    pa = p_prices[6] if len(p_prices) > 6 else None
    pb = p_prices[7] if len(p_prices) > 7 else None

    # 当前波浪定位:
    #   n == 6: 5 浪刚结束, 当前在 ABC 修正中 (位置由价格判断)
    #   n == 7: 第 7 个拐点 = A 浪结束, 当前在 B 浪
    #   n == 8: 第 8 个拐点 = B 浪结束, 当前在 C 浪
    if direction == 'up':
        w1 = p1 - p0
        w3_target_min = p2 + 1.618 * w1
        w3_target_typ = p2 + 2.618 * w1
        w5_target_min = p4 + w1                 # equality
        w5_target_typ = p4 + 1.618 * w1         # extended
        # ABC 目标 (浪 5 后的修正)
        abc_target_618 = p5 - 0.618 * (p5 - p0)
        abc_target_500 = p5 - 0.500 * (p5 - p0)
    else:
        w1 = p0 - p1
        w3_target_min = p2 - 1.618 * w1
        w3_target_typ = p2 - 2.618 * w1
        w5_target_min = p4 - w1
        w5_target_typ = p4 - 1.618 * w1
        abc_target_618 = p5 + 0.618 * (p0 - p5)
        abc_target_500 = p5 + 0.500 * (p0 - p5)

    # 推断当前位置
    if n == 6:
        # 5 浪已完成, 看价格是否回撤至 W4 区间或 ABC 38.2/61.8
        if direction == 'up':
            if current_price < p5 * 0.95:
                position = 'CORRECTION_AB'  # 修正进行中
            else:
                position = 'WAVE_5_END'
        else:
            if current_price > p5 * 1.05:
                position = 'CORRECTION_AB'
            else:
                position = 'WAVE_5_END'
    elif n == 7:
        position = 'CORRECTION_B'  # A 完成, B 反弹中
    elif n == 8:
        position = 'CORRECTION_C'  # B 完成, C 进行中, 临近新一轮浪 1 起点
    else:
        position = 'UNKNOWN'

    return {
        'direction':   direction,
        'wave_score':  score,
        'position':    position,
        'pivots':      seg,
        'p0_p5':       (p0, p1, p2, p3, p4, p5),
        'pa':          pa,
        'pb':          pb,
        'fib_targets': {
            'wave_3_min':    w3_target_min,
            'wave_3_typ':    w3_target_typ,
            'wave_5_min':    w5_target_min,
            'wave_5_typ':    w5_target_typ,
            'abc_50_target': abc_target_500,
            'abc_618_target': abc_target_618,
        },
        'issues':      issues,
    }


# ============================================================
# 4. 交易建议生成
# ============================================================
def generate_recommendation(count, current_price, direction):
    """
    根据当前波浪位置 + 方向生成: action, entry, stop, targets, rationale
    """
    if count is None:
        return {
            'action':    'NO_SIGNAL',
            'rating':    50,
            'entry':     None,
            'stop':      None,
            'target1':   None,
            'target2':   None,
            'rationale': '无法识别清晰的 Elliott Wave 结构, 等待形态明朗',
            'wave_label': 'UNCLEAR',
        }

    p0, p1, p2, p3, p4, p5 = count['p0_p5']
    pa = count.get('pa')
    pb = count.get('pb')
    wave_dir = count['direction']
    pos = count['position']
    fib = count['fib_targets']
    score = count['wave_score']

    # 最近的摆动低/高 (用于止损)
    pivots = count['pivots']
    recent_lows  = [pp[1] for pp in pivots if pp[2] == 'L']
    recent_highs = [pp[1] for pp in pivots if pp[2] == 'H']
    last_low  = recent_lows[-1]  if recent_lows  else p0
    last_high = recent_highs[-1] if recent_highs else p5

    entry = current_price

    if wave_dir == 'up':
        if pos == 'WAVE_5_END':
            # 浪 5 已完成 → 准备做空 / 减仓
            stop = p5 * 1.03
            target1 = fib['abc_50_target']
            target2 = fib['abc_618_target']
            if target1 >= current_price:
                action, rating = 'HOLD', 55
                rationale = '5 浪结构判定中, 价格仍在高位震荡.'
            else:
                if score >= 75:
                    action, rating = 'SELL / TAKE PROFIT', 25
                else:
                    action, rating = 'REDUCE', 40
                rationale = (f"5 浪推动已完成 (顶={p5:.2f}), 进入 ABC 修正. "
                             f"下方目标 {target1:.2f}-{target2:.2f}.")

        elif pos == 'CORRECTION_AB':
            stop = current_price * 1.06
            target1 = fib['abc_50_target']
            target2 = fib['abc_618_target']
            if target1 >= current_price:
                action, rating = 'HOLD', 55
                rationale = '回撤刚开始, 等待修正深度展开.'
            else:
                action, rating = 'HOLD / WAIT', 50
                rationale = (f"修正 A/B 进行中, 顶部 {p5:.2f}. "
                             f"等待回撤至 {target1:.2f}-{target2:.2f} 后进场新一轮浪 1.")

        elif pos == 'CORRECTION_B':
            # B 浪反弹中, C 浪即将下跌
            stop = max(pb or last_high, current_price) * 1.03
            target1 = pa if pa else fib['abc_50_target']
            target2 = fib['abc_618_target']
            action, rating = 'AVOID', 30
            rationale = (f"B 浪反弹中, C 浪下跌即将启动. "
                         f"下方支撑 {target1:.2f}-{target2:.2f}.")

        elif pos == 'CORRECTION_C':
            # C 浪进行中, 接近底部 = 黄金买点
            # 止损放在最近一个低点稍下方 (而非 p0)
            stop = min(last_low, current_price) * 0.95
            target1 = max(p5, current_price * 1.10)
            target2 = max(p5 * 1.15, current_price * 1.25)
            if score >= 70:
                action, rating = 'STRONG BUY', 90
            else:
                action, rating = 'BUY', 75
            rationale = (f"C 浪修正接近完成, 新一轮浪 1 即将启动. "
                         f"目标 1: 重测前高 {target1:.2f}; 目标 2: 突破至 {target2:.2f}.")

        else:
            stop = current_price * 0.92
            target1 = fib['wave_5_min']
            target2 = fib['wave_5_typ']
            action, rating = 'HOLD', 55
            rationale = '波浪结构待确认'

    else:  # wave_dir == 'down'
        if pos == 'WAVE_5_END':
            # 下跌 5 浪结束 = 大底, 反弹机会
            stop = p5 * 0.95
            target1 = fib['abc_50_target']
            target2 = fib['abc_618_target']
            if target1 <= current_price:
                action, rating = 'HOLD', 55
                rationale = '价格仍在底部区, 反弹力度待观察.'
            else:
                if score >= 75:
                    action, rating = 'STRONG BUY', 90
                else:
                    action, rating = 'BUY', 75
                rationale = (f"下跌 5 浪已完成 (底={p5:.2f}), ABC 反弹启动. "
                             f"目标 {target1:.2f}-{target2:.2f}.")

        elif pos == 'CORRECTION_AB':
            stop = p5 * 0.94
            target1 = fib['abc_50_target']
            target2 = fib['abc_618_target']
            if target1 <= current_price:
                action, rating = 'HOLD', 55
                rationale = 'A/B 反弹刚启动, 等待延伸.'
            else:
                action, rating = 'BUY', 70
                rationale = (f"下跌结束, 反弹 A/B 进行中, 上方目标 {target1:.2f}-{target2:.2f}.")

        elif pos == 'CORRECTION_B':
            stop = (pb or last_high) * 1.05
            target1 = fib['abc_50_target']
            target2 = fib['abc_618_target']
            action, rating = 'HOLD', 50
            rationale = '反弹中继 B 浪进行中, 等待 C 浪冲高后评估转折.'

        elif pos == 'CORRECTION_C':
            # 反弹 C 浪 = 高位, 准备转空 (DOWN 趋势中继)
            upper_ref = max(pa or last_high, current_price)
            stop = upper_ref * 1.05            # 止损放在反弹高点上方
            target1 = p5                        # 下方目标: 回测前低
            target2 = p5 * 0.92                 # 突破前低
            action, rating = 'SELL', 25
            rationale = (f"反弹 C 浪进行中, 接近反弹高点, 准备做空. "
                         f"下方目标 {target1:.2f}-{target2:.2f}.")

        else:
            stop = current_price * 1.08
            target1 = fib['wave_5_min']
            target2 = fib['wave_5_typ']
            action, rating = 'HOLD', 45
            rationale = '下跌结构待确认'

    # ====== Risk-reward 后置过滤 ======
    risk = abs(entry - stop)
    reward = abs(target1 - entry) if target1 else 0
    rr_post = reward / risk if risk > 0 else 0

    # 强买入但 RR < 1.0 → 降级 (说明止损过远或目标过近)
    if action in ('STRONG BUY', 'BUY') and rr_post < 1.0:
        action = 'HOLD'
        rating = max(50, rating - 30)
        rationale += f" [RR={rr_post:.2f} 偏低, 降级至观望]"
    if action in ('SELL / TAKE PROFIT', 'SELL') and rr_post < 1.0:
        action = 'HOLD'
        rating = min(55, rating + 25)
        rationale += f" [RR={rr_post:.2f} 偏低, 降级至观望]"

    return {
        'action':     action,
        'rating':     rating,
        'entry':      entry,
        'stop':       stop,
        'target1':    target1,
        'target2':    target2,
        'rationale':  rationale,
        'wave_label': f"{wave_dir.upper()}-{pos}",
    }


# ============================================================
# 5. 单标的全流程分析
# ============================================================
def analyze_ticker(ticker):
    data = fetch_data(ticker)
    if data is None:
        return {'ticker': ticker, 'error': '数据获取失败'}

    weekly = data['weekly']
    closes = weekly['Close'].values

    pivots, thr = adaptive_pivots(closes)
    if len(pivots) < 6:
        return {'ticker': ticker, 'error': f'拐点不足 ({len(pivots)})'}

    current = data.get('live_price') or float(closes[-1])
    count = detect_wave_count(pivots, current)

    # 若周线无法识别, 回退到日线
    if count is None and not data['daily'].empty:
        d_closes = data['daily']['Close'].values
        d_pivots, _ = adaptive_pivots(d_closes)
        if len(d_pivots) >= 6:
            count = detect_wave_count(d_pivots, current)
            if count:
                count['timeframe'] = 'daily'
    else:
        if count:
            count['timeframe'] = 'weekly'

    rec = generate_recommendation(count, current, None)

    # 计算 RR (风险回报比)
    rr = None
    if rec['entry'] and rec['stop'] and rec['target1']:
        risk = abs(rec['entry'] - rec['stop'])
        reward = abs(rec['target1'] - rec['entry'])
        rr = round(reward / risk, 2) if risk > 0 else None

    # 周回报 (use live `current` as numerator so today's intraday move is included)
    ret_4w = (current / closes[-5] - 1) if len(closes) >= 5 else None
    ret_13w = (current / closes[-14] - 1) if len(closes) >= 14 else None
    ret_52w = (current / closes[-53] - 1) if len(closes) >= 53 else None

    return {
        'ticker':       ticker,
        'current':      current,
        'pivots_count': len(pivots),
        'zigzag_thr':   thr,
        'wave':         count,
        'rec':          rec,
        'risk_reward':  rr,
        'ret_4w':       ret_4w,
        'ret_13w':      ret_13w,
        'ret_52w':      ret_52w,
        'timeframe':    (count or {}).get('timeframe', 'n/a'),
    }


# ============================================================
# 6. 批量扫描 + 报告生成
# ============================================================
def fmt(x, pct=False, decimals=2):
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return '-'
    if pct:
        return f"{x*100:+.1f}%"
    return f"{x:,.{decimals}f}"


def action_emoji(action):
    return {
        'STRONG BUY':         '🟢🟢',
        'BUY':                '🟢',
        'HOLD':               '🟡',
        'HOLD / WAIT':        '🟡',
        'REDUCE':             '🟠',
        'SELL':               '🔴',
        'SELL / TAKE PROFIT': '🔴',
        'AVOID':              '⛔',
        'NO_SIGNAL':          '❓',
    }.get(action, '·')


def build_report(results_by_sector, indices_results, run_date):
    lines = []
    lines.append(f"# Elliott Wave 投资策略报告 - {run_date}\n")
    lines.append("> **方法**: ZigZag 摆动点 → 5 浪推动 + ABC 修正校验 → Fibonacci 目标位 → 操作建议\n")
    lines.append("> **三大铁律**: ① 浪 2 不破浪 1 起点  ② 浪 3 非最短  ③ 浪 4 不入浪 1 区间\n")
    lines.append("> **数据**: yfinance 周线 5 年 + 日线 2 年 (周线优先, 日线确认)\n")

    # ========== 大盘指数 ==========
    lines.append("\n## 📊 大盘指数波浪结构\n")
    lines.append("| 指数 | 现价 | 波浪位置 | 评分 | 操作 | 入场 | 止损 | 目标 1 | 目标 2 | RR | 4W | 13W | 52W |")
    lines.append("|------|------|----------|------|------|------|------|--------|--------|----|----|-----|-----|")
    for name, r in indices_results.items():
        if 'error' in r:
            lines.append(f"| {name} | - | - | - | ❌ {r['error']} | - | - | - | - | - | - | - | - |")
            continue
        rec = r['rec']
        lines.append(
            f"| **{name}** | {fmt(r['current'])} | {rec['wave_label']} | {rec['rating']} | "
            f"{action_emoji(rec['action'])} {rec['action']} | "
            f"{fmt(rec['entry'])} | {fmt(rec['stop'])} | {fmt(rec['target1'])} | {fmt(rec['target2'])} | "
            f"{fmt(r['risk_reward'])} | {fmt(r['ret_4w'], pct=True)} | "
            f"{fmt(r['ret_13w'], pct=True)} | {fmt(r['ret_52w'], pct=True)} |"
        )

    # ========== 板块明细 ==========
    for sector, results in results_by_sector.items():
        lines.append(f"\n## 🏷️ {sector}\n")
        # Top picks first
        valid = [r for r in results if 'error' not in r]
        valid.sort(key=lambda x: x['rec']['rating'], reverse=True)

        lines.append("| 标的 | 现价 | 时间框 | 波浪位置 | 评分 | 操作 | 入场 | 止损 | 目标 1 | 目标 2 | RR | 4W | 13W | 52W |")
        lines.append("|------|------|--------|----------|------|------|------|------|--------|--------|----|----|-----|-----|")
        for r in valid:
            rec = r['rec']
            lines.append(
                f"| **{r['ticker']}** | {fmt(r['current'])} | {r['timeframe']} | {rec['wave_label']} | "
                f"{rec['rating']} | {action_emoji(rec['action'])} {rec['action']} | "
                f"{fmt(rec['entry'])} | {fmt(rec['stop'])} | {fmt(rec['target1'])} | {fmt(rec['target2'])} | "
                f"{fmt(r['risk_reward'])} | {fmt(r['ret_4w'], pct=True)} | "
                f"{fmt(r['ret_13w'], pct=True)} | {fmt(r['ret_52w'], pct=True)} |"
            )

        # 失败标的
        errs = [r for r in results if 'error' in r]
        if errs:
            errlist = ', '.join(f"{r['ticker']} ({r['error']})" for r in errs)
            lines.append(f"\n*跳过*: {errlist}")

        # 详细分析 (前 3 名)
        lines.append("\n### 🔍 重点标的详解\n")
        for r in valid[:3]:
            rec = r['rec']
            wave = r['wave']
            lines.append(f"\n**{r['ticker']}** — {rec['action']} (评分 {rec['rating']}/100)")
            lines.append(f"- 现价 ${fmt(r['current'])} | 时间框: {r['timeframe']} | 波浪计数: {rec['wave_label']}")
            if wave:
                p0, p1, p2, p3, p4, p5 = wave['p0_p5']
                lines.append(f"- 5 浪关键点 (推断): "
                             f"P0=${fmt(p0)} → P1=${fmt(p1)} → P2=${fmt(p2)} → P3=${fmt(p3)} → P4=${fmt(p4)} → P5=${fmt(p5)}")
                lines.append(f"- 形态质量评分: {wave['wave_score']}/100")
                if wave['issues']:
                    lines.append(f"- ⚠️ 偏离项: {'; '.join(wave['issues'])}")
            lines.append(f"- 操作: 入场 ${fmt(rec['entry'])} | 止损 ${fmt(rec['stop'])} | "
                         f"目标 1 ${fmt(rec['target1'])} | 目标 2 ${fmt(rec['target2'])} | RR={fmt(r['risk_reward'])}")
            lines.append(f"- 逻辑: {rec['rationale']}")

    # ========== 总览 Top 10 ==========
    all_valid = []
    for results in results_by_sector.values():
        all_valid.extend([r for r in results if 'error' not in r])

    lines.append("\n## 🏆 全市场 Top 15 买入候选 (评分 ≥ 70)\n")
    top = sorted(all_valid, key=lambda x: x['rec']['rating'], reverse=True)[:15]
    lines.append("| 排名 | 标的 | 现价 | 操作 | 评分 | 波浪位置 | 入场 | 止损 | 目标 1 | RR |")
    lines.append("|------|------|------|------|------|----------|------|------|--------|----|")
    for i, r in enumerate(top, 1):
        rec = r['rec']
        if rec['rating'] < 70:
            break
        lines.append(
            f"| {i} | **{r['ticker']}** | {fmt(r['current'])} | "
            f"{action_emoji(rec['action'])} {rec['action']} | {rec['rating']} | "
            f"{rec['wave_label']} | {fmt(rec['entry'])} | {fmt(rec['stop'])} | "
            f"{fmt(rec['target1'])} | {fmt(r['risk_reward'])} |"
        )

    # ========== 卖出 / 回避列表 ==========
    bottom = sorted(all_valid, key=lambda x: x['rec']['rating'])[:10]
    lines.append("\n## 🚨 减仓 / 卖出预警 (评分 ≤ 40)\n")
    lines.append("| 标的 | 现价 | 操作 | 评分 | 波浪位置 | 逻辑 |")
    lines.append("|------|------|------|------|----------|------|")
    for r in bottom:
        rec = r['rec']
        if rec['rating'] > 40:
            break
        lines.append(
            f"| **{r['ticker']}** | {fmt(r['current'])} | {action_emoji(rec['action'])} {rec['action']} | "
            f"{rec['rating']} | {rec['wave_label']} | {rec['rationale']} |"
        )

    # ========== 全部标的总表 (按评分排序) ==========
    # ticker -> 板块 映射 (取首次出现的板块)
    sector_of = {}
    for sector, results in results_by_sector.items():
        sec_short = sector.split(' (')[0]
        for r in results:
            sector_of.setdefault(r['ticker'], sec_short)

    all_sorted = sorted(all_valid, key=lambda x: x['rec']['rating'], reverse=True)
    lines.append(f"\n## 📋 全部标的扫描结果 ({len(all_sorted)} 只, 按评分排序)\n")

    # 评级分布
    band = {'strong': 0, 'bullish': 0, 'neutral': 0, 'bearish': 0}
    for r in all_sorted:
        rt = r['rec']['rating']
        if rt >= 70: band['strong'] += 1
        elif rt >= 55: band['bullish'] += 1
        elif rt >= 40: band['neutral'] += 1
        else: band['bearish'] += 1
    n = len(all_sorted) or 1
    lines.append("| 评级带 | 数量 | 占比 |")
    lines.append("|------|------|------|")
    lines.append(f"| 🟢 强势买入 (≥70) | {band['strong']} | {band['strong']/n*100:.0f}% |")
    lines.append(f"| 🔵 偏多 (55-69) | {band['bullish']} | {band['bullish']/n*100:.0f}% |")
    lines.append(f"| 🟡 中性 (40-54) | {band['neutral']} | {band['neutral']/n*100:.0f}% |")
    lines.append(f"| 🔴 偏空/回避 (<40) | {band['bearish']} | {band['bearish']/n*100:.0f}% |")
    lines.append("")

    lines.append("| 排名 | 标的 | 板块 | 现价 | 时间框 | 波浪位置 | 评分 | 操作 | 入场 | 止损 | 目标 1 | 目标 2 | RR | 52W |")
    lines.append("|------|------|------|------|--------|----------|------|------|------|------|--------|--------|----|-----|")
    for idx, r in enumerate(all_sorted, 1):
        rec = r['rec']
        lines.append(
            f"| {idx} | **{r['ticker']}** | {sector_of.get(r['ticker'], '—')} | {fmt(r['current'])} | "
            f"{r['timeframe']} | {rec['wave_label']} | {rec['rating']} | "
            f"{action_emoji(rec['action'])} {rec['action']} | "
            f"{fmt(rec['entry'])} | {fmt(rec['stop'])} | {fmt(rec['target1'])} | {fmt(rec['target2'])} | "
            f"{fmt(r['risk_reward'])} | {fmt(r['ret_52w'], pct=True)} |"
        )

    # ========== 策略说明 ==========
    lines.append("\n## 📚 Elliott Wave 策略框架\n")
    lines.append("""
### 波浪计数图示

```
推动浪 (Impulse, 与主趋势同向):
              5
        3   ╱
       ╱╲ ╱
      ╱  4
   1 ╱
   ╱╲
  ╱  2
 ╱
0

修正浪 (Corrective, ABC):
   ╲   B
    ╲ ╱╲
     A  ╲
         ╲
          C
```

### 各波浪位置的标准操作

| 波浪 | 子状态 | 操作 | 仓位 |
|------|--------|------|------|
| 上行 W1 | 起步 | 谨慎做多 | 试探仓 30% |
| 上行 W2 | 修正 38.2-78.6% | **加仓多头** | 加至 70% |
| 上行 W3 | 主升 (1.618-2.618×W1) | **持有 / 趋势跟随** | 满仓 |
| 上行 W4 | 修正 23.6-50% | 持有, 不破 W1 顶部 | 70% |
| 上行 W5 | 终结浪 | **逐步减仓** | 降至 30% |
| ABC 修正 A/B | 反弹中 | 观望或做空 B 浪 | 0-20% |
| ABC 修正 C | 末跌 | **抄底进场** 新一轮 W1 | 30-50% |

### Fibonacci 关键比例

- 浪 2 回撤: **38.2% / 50% / 61.8%** (浅修正常见 38.2%, 深修正 78.6%)
- 浪 3 延伸: **1.618× / 2.618× 浪 1** (强势可达 4.236×)
- 浪 4 回撤: **23.6% / 38.2%** (与浪 2 形成交替)
- 浪 5 等长: **= 浪 1** 或 **0.618× (浪 1+3)**
- ABC 修正深度: **38.2% / 50% / 61.8%** 浪 1-5 整体涨幅

### 三大铁律 (违反则计数失效)

1. **浪 2 不能回撤超过浪 1 的起点** (100%)
2. **浪 3 不能是 1/3/5 中最短的浪** (通常是最长)
3. **浪 4 不能进入浪 1 的价格区间** (除楔形 ending diagonal 外)

### 风险提示

- Elliott Wave 主观性较强, 同一行情可有多种计数, 本算法选取**评分最高的合规计数**
- 评分 ≥ 75 视为高置信度结构, < 60 视为参考
- 进场前请用 RSI/MACD/成交量 二次确认拐点反转
- 仓位与止损比例严格执行, 单笔风险不超过总资金 2%
- 加密货币波动率显著高于股票, 止损宽幅放大 1.5×
""")

    return '\n'.join(lines)


def build_excel_summary(results_by_sector, indices_results, out_path):
    """生成扁平 Excel 表格 (一行一标的)"""
    rows = []
    for name, r in indices_results.items():
        rows.append(_flatten(r, sector='Index', name=name))
    for sector, results in results_by_sector.items():
        for r in results:
            rows.append(_flatten(r, sector=sector, name=r.get('ticker', '?')))

    df = pd.DataFrame(rows)

    # 排序: 按评分降序
    df_sorted = df.sort_values(['Rating'], ascending=False, na_position='last')

    with pd.ExcelWriter(out_path, engine='openpyxl') as writer:
        df_sorted.to_excel(writer, sheet_name='All', index=False)
        # 各板块单 sheet
        for sector in df['Sector'].unique():
            sub = df[df['Sector'] == sector].sort_values('Rating', ascending=False)
            raw = sector.split('(')[0].strip()
            for ch in r'/\?*[]:':
                raw = raw.replace(ch, '-')
            sheet_name = raw[:28]
            sub.to_excel(writer, sheet_name=sheet_name, index=False)

        # 高亮: 评分 >= 70 绿; <= 40 红
        from openpyxl.styles import PatternFill, Font
        green = PatternFill('solid', start_color='C8E6C9')
        red = PatternFill('solid', start_color='FFCDD2')
        bold = Font(bold=True)

        for sheet_name in writer.sheets:
            ws = writer.sheets[sheet_name]
            for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
                for cell in row:
                    if cell.column_letter in ('E',):  # Rating col
                        try:
                            v = float(cell.value)
                            if v >= 70:
                                for c in row: c.fill = green
                            elif v <= 40:
                                for c in row: c.fill = red
                        except (TypeError, ValueError):
                            pass
            # Header bold
            for c in ws[1]:
                c.font = bold
            # Auto width
            for col in ws.columns:
                max_len = max(len(str(c.value or '')) for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(28, max_len + 2)


def _flatten(r, sector, name):
    if 'error' in r:
        return {
            'Sector': sector, 'Ticker': name, 'Current': None, 'Action': 'ERROR',
            'Rating': None, 'WaveLabel': r['error'], 'Entry': None, 'Stop': None,
            'Target1': None, 'Target2': None, 'RiskReward': None,
            'Ret4W': None, 'Ret13W': None, 'Ret52W': None, 'Rationale': r['error'],
        }
    rec = r['rec']
    return {
        'Sector':     sector,
        'Ticker':     name,
        'Current':    round(r['current'], 2),
        'Action':     rec['action'],
        'Rating':     rec['rating'],
        'WaveLabel':  rec['wave_label'],
        'Entry':      round(rec['entry'], 2)   if rec['entry']   else None,
        'Stop':       round(rec['stop'], 2)    if rec['stop']    else None,
        'Target1':    round(rec['target1'], 2) if rec['target1'] else None,
        'Target2':    round(rec['target2'], 2) if rec['target2'] else None,
        'RiskReward': r['risk_reward'],
        'Ret4W':      round(r['ret_4w']*100, 2)  if r['ret_4w']  is not None else None,
        'Ret13W':     round(r['ret_13w']*100, 2) if r['ret_13w'] is not None else None,
        'Ret52W':     round(r['ret_52w']*100, 2) if r['ret_52w'] is not None else None,
        'Timeframe':  r['timeframe'],
        'Rationale':  rec['rationale'],
    }


# ============================================================
# 7. 主入口
# ============================================================
def main():
    base = Path(__file__).parent
    run_date = datetime.now().strftime('%Y-%m-%d')

    # 收集所有去重后的 ticker
    all_tickers = set()
    for tickers in SECTORS.values():
        all_tickers.update(tickers)
    all_tickers.update(INDICES.values())

    print(f"[*] 共扫描 {len(all_tickers)} 个标的 (含指数)")
    print(f"[*] 并发拉取数据 + 波浪分析 ...")

    cache = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(analyze_ticker, t): t for t in all_tickers}
        for i, fut in enumerate(as_completed(futures), 1):
            t = futures[fut]
            try:
                cache[t] = fut.result()
            except Exception as e:
                cache[t] = {'ticker': t, 'error': str(e)[:50]}
            if i % 10 == 0:
                print(f"    {i}/{len(all_tickers)} ...")

    print(f"[*] 数据采集完成, 生成报告 ...")

    # 按板块组织结果
    results_by_sector = {}
    for sector, tickers in SECTORS.items():
        results_by_sector[sector] = [cache[t] for t in tickers if t in cache]

    indices_results = {name: cache[tk] for name, tk in INDICES.items() if tk in cache}

    # 生成 Markdown
    md = build_report(results_by_sector, indices_results, run_date)
    md_path = base / f'elliott_wave_recommendations_{run_date}.md'
    md_path.write_text(md, encoding='utf-8')
    print(f"[✓] 报告已生成: {md_path.name}")

    # 生成 Excel
    xlsx_path = base / f'elliott_wave_recommendations_{run_date}.xlsx'
    build_excel_summary(results_by_sector, indices_results, xlsx_path)
    print(f"[✓] Excel 已生成: {xlsx_path.name}")


if __name__ == '__main__':
    main()
