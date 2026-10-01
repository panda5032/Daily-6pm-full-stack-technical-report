import yfinance as yf
import pandas as pd
import numpy as np

def detailed_analysis(ticker, name):
    print('\n' + '='*60)
    print('  ' + name + ' (' + ticker + ') 详细分析')
    print('='*60)

    df = yf.download(ticker, period='1y', interval='1d', progress=False, auto_adjust=True)
    if df.empty:
        print('数据获取失败')
        return

    for n in [5,10,20,50,100,200]:
        df['MA'+str(n)] = df['Close'].rolling(n).mean()

    ema12 = df['Close'].ewm(span=12).mean()
    ema26 = df['Close'].ewm(span=26).mean()
    df['MACD'] = ema12 - ema26
    df['Signal'] = df['MACD'].ewm(span=9).mean()
    df['Hist'] = df['MACD'] - df['Signal']

    delta = df['Close'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    df['BB_mid'] = df['Close'].rolling(20).mean()
    df['BB_std'] = df['Close'].rolling(20).std()
    df['BB_upper'] = df['BB_mid'] + 2*df['BB_std']
    df['BB_lower'] = df['BB_mid'] - 2*df['BB_std']

    df['H_L'] = df['High'] - df['Low']
    df['H_PC'] = abs(df['High'] - df['Close'].shift(1))
    df['L_PC'] = abs(df['Low'] - df['Close'].shift(1))
    df['TR'] = df[['H_L','H_PC','L_PC']].max(axis=1)
    df['ATR14'] = df['TR'].rolling(14).mean()
    df['Vol_MA20'] = df['Volume'].rolling(20).mean()

    # flatten multi-level columns if needed
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]

    last = df.iloc[-1]
    prev = df.iloc[-2]

    price = float(last['Close'])
    vol = float(last['Volume'])
    vol_ma = float(last['Vol_MA20'])
    atr = float(last['ATR14'])

    print('\n[价格信息]')
    print('  当前价:  $' + str(round(price,2)))
    print('  今日: 开 $' + str(round(float(last['Open']),2)) + '  高 $' + str(round(float(last['High']),2)) + '  低 $' + str(round(float(last['Low']),2)))
    print('  成交量: ' + str(round(vol/1e6,1)) + 'M  (均量 ' + str(round(vol_ma/1e6,1)) + 'M,  量比 ' + str(round(vol/vol_ma,2)) + 'x)')
    print('  ATR14: $' + str(round(atr,2)) + '  (日均波动 ' + str(round(atr/price*100,1)) + '%)')

    p1 = (price/float(df.iloc[-2]['Close'])-1)*100
    p5 = (price/float(df.iloc[-6]['Close'])-1)*100
    p10 = (price/float(df.iloc[-11]['Close'])-1)*100
    p20 = (price/float(df.iloc[-21]['Close'])-1)*100
    p60 = (price/float(df.iloc[-61]['Close'])-1)*100
    p252 = (price/float(df.iloc[0]['Close'])-1)*100
    print('\n[涨跌幅]')
    print('  日: ' + str(round(p1,2)) + '%   5日: ' + str(round(p5,2)) + '%   10日: ' + str(round(p10,2)) + '%')
    print('  20日: ' + str(round(p20,2)) + '%   60日: ' + str(round(p60,2)) + '%   一年: ' + str(round(p252,2)) + '%')

    high52 = float(df['High'].tail(252).max())
    low52 = float(df['Low'].tail(252).min())
    from_high = (price/high52-1)*100
    from_low = (price/low52-1)*100
    print('\n[52周高低]')
    print('  52周高: $' + str(round(high52,2)) + '  (距高点 ' + str(round(from_high,1)) + '%)')
    print('  52周低: $' + str(round(low52,2)) + '  (距低点 +' + str(round(from_low,1)) + '%)')

    print('\n[均线系统]')
    for n in [5,10,20,50,100,200]:
        ma = float(last['MA'+str(n)])
        diff = (price/ma-1)*100
        cross = '价格上方 +' if price > ma else '价格下方 '
        print('  MA' + str(n).ljust(3) + ': $' + str(round(ma,2)).ljust(10) + cross + str(round(diff,1)) + '%')

    ma5=float(last['MA5']); ma10=float(last['MA10']); ma20=float(last['MA20'])
    ma50=float(last['MA50']); ma100=float(last['MA100']); ma200=float(last['MA200'])
    print('\n  均线多头排列检查:')
    print('  MA5(' + str(round(ma5,0)) + ') > MA10(' + str(round(ma10,0)) + ')? ' + ('YES' if ma5>ma10 else 'NO'))
    print('  MA10(' + str(round(ma10,0)) + ') > MA20(' + str(round(ma20,0)) + ')? ' + ('YES' if ma10>ma20 else 'NO'))
    print('  MA20(' + str(round(ma20,0)) + ') > MA50(' + str(round(ma50,0)) + ')? ' + ('YES' if ma20>ma50 else 'NO'))
    print('  MA50(' + str(round(ma50,0)) + ') > MA200(' + str(round(ma200,0)) + ')? ' + ('YES' if ma50>ma200 else 'NO'))

    macd = float(last['MACD']); sig = float(last['Signal']); hist = float(last['Hist'])
    prev_hist = float(prev['Hist'])
    print('\n[MACD (12/26/9)]')
    print('  MACD线: ' + str(round(macd,3)))
    print('  信号线: ' + str(round(sig,3)))
    print('  柱状图: ' + str(round(hist,3)) + '  (前日 ' + str(round(prev_hist,3)) + ')')
    macd_cross = '金叉(MACD>Signal)' if macd > sig else '死叉(MACD<Signal)'
    zero_pos = '零轴上方(多头)' if macd > 0 else '零轴下方(空头)'
    print('  交叉:   ' + macd_cross)
    print('  零轴:   ' + zero_pos)
    expand = '放大' if abs(hist) > abs(prev_hist) else '收窄'
    direction = '(上行动能增强)' if hist > 0 else '(下行动能增强)'
    no_direction = '(上行动能减弱)' if hist > 0 else '(下行动能减弱)'
    if abs(hist) > abs(prev_hist):
        print('  动能:   柱状图' + expand + direction)
    else:
        print('  动能:   柱状图' + expand + no_direction)

    rsi = float(last['RSI'])
    rsi_5ago = float(df.iloc[-5]['RSI'])
    print('\n[RSI (14)]')
    print('  当前: ' + str(round(rsi,1)) + '  (5日前: ' + str(round(rsi_5ago,1)) + ', 变化: ' + str(round(rsi-rsi_5ago,1)) + ')')
    if rsi > 80:
        rsi_status = '严重超买 -- 高风险追高区'
    elif rsi > 70:
        rsi_status = '超买区 -- 注意短线回调风险'
    elif rsi > 50:
        rsi_status = '多头区间 -- 健康'
    elif rsi > 30:
        rsi_status = '空头区间 -- 趋势偏弱'
    else:
        rsi_status = '严重超卖 -- 可能反弹'
    print('  状态:  ' + rsi_status)

    bb_upper = float(last['BB_upper']); bb_mid = float(last['BB_mid']); bb_lower = float(last['BB_lower'])
    bb_width = (bb_upper - bb_lower)/bb_mid*100
    bb_pos = (price - bb_lower)/(bb_upper - bb_lower)*100
    print('\n[布林带 (20,2)]')
    print('  上轨: $' + str(round(bb_upper,2)) + '  中轨: $' + str(round(bb_mid,2)) + '  下轨: $' + str(round(bb_lower,2)))
    print('  带宽: ' + str(round(bb_width,1)) + '%  价格位置: ' + str(round(bb_pos,0)) + '% (0%=下轨 100%=上轨)')

    print('\n[关键支撑阻力]')
    h60 = float(df['High'].tail(60).max())
    l60 = float(df['Low'].tail(60).min())
    print('  近60日最高: $' + str(round(h60,2)))
    print('  近60日最低: $' + str(round(l60,2)))
    print('  上方阻力:   MA50 $' + str(round(ma50,2)) + ' | 布林上轨 $' + str(round(bb_upper,2)) + ' | 52周高 $' + str(round(high52,2)))
    print('  下方支撑:   MA20 $' + str(round(ma20,2)) + ' | 布林中轨 $' + str(round(bb_mid,2)) + ' | 布林下轨 $' + str(round(bb_lower,2)) + ' | MA200 $' + str(round(ma200,2)))

    print('\n[止损参考]')
    print('  短线止损MA10: $' + str(round(ma10,2)) + '  (距现价 ' + str(round((ma10/price-1)*100,1)) + '%)')
    print('  主止损 MA20:  $' + str(round(ma20,2)) + '  (距现价 ' + str(round((ma20/price-1)*100,1)) + '%)')
    print('  宽止损 MA50:  $' + str(round(ma50,2)) + '  (距现价 ' + str(round((ma50/price-1)*100,1)) + '%)')
    print('  ATR止损2x:    $' + str(round(price - 2*atr,2)) + '  (距现价 ' + str(round(-2*atr/price*100,1)) + '%)')

    print('\n[近5日K线]')
    recent = df.tail(5)
    for idx, row in recent.iterrows():
        o=float(row['Open']); h=float(row['High']); l=float(row['Low']); c=float(row['Close'])
        v=float(row['Volume'])
        chg = (c/o-1)*100
        candle = '阳线' if c>o else '阴线'
        print('  ' + str(idx.date()) + '  开$' + str(round(o,2)) + ' 高$' + str(round(h,2)) + ' 低$' + str(round(l,2)) + ' 收$' + str(round(c,2)) + '  ' + candle + ' ' + str(round(chg,2)) + '%  量' + str(round(v/1e6,1)) + 'M')

detailed_analysis('TSLA', 'Tesla')
detailed_analysis('ETH-USD', 'Ethereum')
