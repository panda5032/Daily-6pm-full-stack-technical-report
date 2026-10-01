import yfinance as yf
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

tickers = ['NVO', 'SOFI']

for ticker in tickers:
    print(f'\n{"="*70}')
    print(f'  {ticker} 详细技术分析')
    print(f'{"="*70}')

    df = yf.download(ticker, period='1y', interval='1d', progress=False, auto_adjust=True)
    if df.empty:
        print('  数据获取失败')
        continue

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    close  = df['Close'].astype(float)
    volume = df['Volume'].astype(float)
    high_s = df['High'].astype(float)
    low_s  = df['Low'].astype(float)
    open_s = df['Open'].astype(float)

    ma5   = close.rolling(5).mean()
    ma10  = close.rolling(10).mean()
    ma20  = close.rolling(20).mean()
    ma50  = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()

    ema12  = close.ewm(span=12, adjust=False).mean()
    ema26  = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    hist   = macd_line - signal_line

    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rsi   = 100 - (100 / (1 + gain / loss))

    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_up  = bb_mid + 2 * bb_std
    bb_lo  = bb_mid - 2 * bb_std

    tr    = pd.concat([high_s - low_s,
                       (high_s - close.shift()).abs(),
                       (low_s  - close.shift()).abs()], axis=1).max(axis=1)
    atr    = tr.rolling(14).mean()
    vol_ma = volume.rolling(20).mean()

    # OBV
    obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()

    def last(s):
        return float(s.dropna().iloc[-1])

    def nth(s, n):
        clean = s.dropna()
        return float(clean.iloc[-n]) if len(clean) >= n else float(clean.iloc[0])

    px    = last(close)
    px1   = nth(close, 2)
    px5   = nth(close, 6)
    px20  = nth(close, 21)
    px60  = nth(close, 61)
    px252 = float(close.dropna().iloc[0])

    c_ma5   = last(ma5)
    c_ma10  = last(ma10)
    c_ma20  = last(ma20)
    c_ma50  = last(ma50)
    c_ma200 = last(ma200)
    c_macd  = last(macd_line)
    c_sig   = last(signal_line)
    c_hist  = last(hist)
    c_hist1 = nth(hist, 2)
    c_hist2 = nth(hist, 3)
    c_rsi   = last(rsi)
    c_rsi1  = nth(rsi, 2)
    c_bb_up = last(bb_up)
    c_bb_lo = last(bb_lo)
    c_bb_mid= last(bb_mid)
    c_atr   = last(atr)
    c_vol   = last(volume)
    c_volma = last(vol_ma)
    c_obv   = last(obv)
    c_obv1  = nth(obv, 6)

    high_52w = float(close.max())
    low_52w  = float(close.min())

    last5_close = [float(close.dropna().iloc[-i]) for i in range(1, 6)]
    last5_open  = [float(open_s.dropna().iloc[-i]) for i in range(1, 6)]
    last5_vol   = [float(volume.dropna().iloc[-i]) for i in range(1, 6)]

    chg1d  = (px - px1)  / px1  * 100
    chg5d  = (px - px5)  / px5  * 100
    chg20d = (px - px20) / px20 * 100
    chg60d = (px - px60) / px60 * 100
    chg1y  = (px - px252)/ px252* 100

    vol_ratio  = c_vol / c_volma if c_volma > 0 else 1
    volatility = float(close.pct_change().rolling(20).std().dropna().iloc[-1]) * np.sqrt(252) * 100
    obv_trend  = '量能净流入(看多)' if c_obv > c_obv1 else '量能净流出(看空)'

    print(f'  价格: ${px:.2f}  日{chg1d:+.2f}%  5日{chg5d:+.2f}%  20日{chg20d:+.2f}%  60日{chg60d:+.2f}%  年{chg1y:+.2f}%')
    print(f'  52周高: ${high_52w:.2f} ({(px-high_52w)/high_52w*100:.1f}%)   52周低: ${low_52w:.2f} (+{(px-low_52w)/low_52w*100:.1f}%)')

    print(f'\n  【均线系统】')
    for ref, name in [(c_ma5,'MA5'),(c_ma10,'MA10'),(c_ma20,'MA20'),(c_ma50,'MA50'),(c_ma200,'MA200')]:
        s = 'UP✅' if px > ref else 'DN❌'
        d = (px - ref) / ref * 100
        print(f'    {name:5s}  ${ref:8.2f}    {s}  ({d:+.1f}%)')

    cross = 'MA50>MA200 金叉📈' if c_ma50 > c_ma200 else 'MA50<MA200 死叉📉'
    if px > c_ma5 > c_ma10 > c_ma20 > c_ma50 > c_ma200:
        align = '完全多头排列 🚀'
    elif px > c_ma5 and px > c_ma10 and px > c_ma20 and px > c_ma50:
        align = '主要多头排列'
    elif px < c_ma10 and px < c_ma20 and px < c_ma50:
        align = '完全空头排列 📉'
    else:
        align = '混排待定'
    print(f'    {cross}  |  {align}')

    print(f'\n  【MACD】')
    macd_st = 'MACD金叉✅' if c_macd > c_sig else 'MACD死叉❌'
    zero_st = '零轴上方📈' if c_macd > 0 else '零轴下方📉'
    hist_dir = '放大' if abs(c_hist) > abs(c_hist1) else '收缩'
    cont3 = ' 连续放大3日✅' if abs(c_hist) > abs(c_hist1) > abs(c_hist2) else ''
    print(f'    MACD:{c_macd:.4f}  Signal:{c_sig:.4f}  Hist:{c_hist:.4f}')
    print(f'    {macd_st} | {zero_st} | 柱状图{hist_dir}{cont3}')

    print(f'\n  【RSI】')
    if   c_rsi >= 80: rsi_st = '严重超买⚠️⚠️'
    elif c_rsi >= 70: rsi_st = '超买⚠️'
    elif c_rsi <= 20: rsi_st = '严重超卖🔥🔥'
    elif c_rsi <= 30: rsi_st = '超卖🔥'
    elif 45 <= c_rsi <= 62: rsi_st = '健康中性✅'
    elif c_rsi > 62: rsi_st = '偏强✅'
    else: rsi_st = '偏弱'
    rsi_chg = c_rsi - c_rsi1
    print(f'    RSI(14): {c_rsi:.1f}  {rsi_st}  (较昨日 {rsi_chg:+.1f})')

    print(f'\n  【布林带】')
    bb_pos = (px - c_bb_lo) / (c_bb_up - c_bb_lo) * 100 if c_bb_up != c_bb_lo else 50
    bb_w   = (c_bb_up - c_bb_lo) / c_bb_mid * 100
    if   bb_pos >= 95: bb_st = '突破上轨(极度过热)'
    elif bb_pos >= 70: bb_st = '上半区偏强'
    elif bb_pos <= 5:  bb_st = '触及下轨(超卖)'
    elif bb_pos <= 30: bb_st = '下半区偏弱'
    else:              bb_st = '中部震荡'
    print(f'    上轨:${c_bb_up:.2f}  中轨:${c_bb_mid:.2f}  下轨:${c_bb_lo:.2f}')
    print(f'    位置:{bb_pos:.0f}%  {bb_st}  带宽:{bb_w:.1f}%')

    print(f'\n  【成交量 & OBV】')
    if   vol_ratio >= 2.0: vol_st = '大幅放量✅ (>2x)'
    elif vol_ratio >= 1.3: vol_st = '温和放量(>1.3x)'
    elif vol_ratio <= 0.3: vol_st = '极度缩量❌(<0.3x)'
    elif vol_ratio <= 0.6: vol_st = '缩量'
    else:                  vol_st = '正常量能'
    print(f'    今日量:{c_vol/1e6:.1f}M  20日均量:{c_volma/1e6:.1f}M  量比:{vol_ratio:.2f}x  {vol_st}')
    print(f'    OBV趋势: {obv_trend}')

    print(f'\n  【波动率与风险】')
    if   volatility > 100: risk = '极高风险'
    elif volatility > 60:  risk = '高风险'
    elif volatility > 35:  risk = '中高风险'
    elif volatility > 20:  risk = '中等风险'
    else:                  risk = '低中风险'
    print(f'    ATR(14):${c_atr:.2f} ({c_atr/px*100:.1f}%/日)  年化波动率:{volatility:.1f}%  {risk}')

    print(f'\n  【支撑与压力】')
    levels = sorted([
        (c_ma20, 'MA20'), (c_ma50, 'MA50'), (c_ma200, 'MA200'),
        (c_bb_up, '布林上轨'), (c_bb_lo, '布林下轨'),
        (high_52w, '52周高'), (low_52w, '52周低')
    ], key=lambda x: x[0])
    print(f'    当前价: ${px:.2f}')
    supports = [(v, n) for v, n in levels if v < px]
    resists  = [(v, n) for v, n in levels if v > px]
    for v, n in reversed(supports[-3:]):
        print(f'    支撑  ${v:.2f} ({n:8s})  距当前 {(v-px)/px*100:.1f}%')
    for v, n in resists[:3]:
        print(f'    压力  ${v:.2f} ({n:8s})  距当前 +{(v-px)/px*100:.1f}%')

    print(f'\n  【近5日K线】')
    days = ['今日', '昨日', '前2日', '前3日', '前4日']
    for i in range(5):
        c_ = last5_close[i]
        o_ = last5_open[i]
        chg_ = (c_ - o_) / o_ * 100
        candle = '阳线🟢' if c_ > o_ else '阴线🔴'
        vr_ = last5_vol[i] / c_volma
        print(f'    {days[i]}: ${c_:.2f}  {chg_:+.2f}%  {candle}  量比{vr_:.2f}x')
