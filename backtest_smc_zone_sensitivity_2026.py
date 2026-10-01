import warnings, numpy as np; warnings.filterwarnings("ignore")
import sys; sys.path.insert(0, '.')
import backtest_smc_bottom_2026 as m
from backtest_playbooks_2026 import cd1_entry, cd1_exit, cd6_entry, cd6_exit
tickers,_=m.get_universe(); data=m.download_all(tickers)
for t in list(data): data[t]=m.add_swing(m.add_indicators(data[t]))
def zone(lv):
    def f(df,i):
        lo,hi=df["sw_lo"].iloc[i],df["sw_hi"].iloc[i]
        if np.isnan(lo): return False
        return df["Low"].iloc[i-9:i+1].min() <= hi-lv*(hi-lo) and df["Close"].iloc[i] > lo
    return f
print("| 策略 | 交易 | 胜率 | 单笔均值 | 中位数 | PF | 逐年 |\n|---|---|---|---|---|---|---|")
for nm,en,ex in (("打法14",cd1_entry,cd1_exit),("打法15",cd6_entry,cd6_exit)):
    for lv in (0.382,0.5,0.618,0.786,0.886):
        print(m.stats(data, m.filt(en, zone(lv)), ex, f"{nm} · 回撤≥{lv}")[0])
    nosw=lambda df,i: np.isnan(df["sw_lo"].iloc[i])
    print(m.stats(data, m.filt(en, nosw), ex, f"{nm} · 无大升浪(非回撤票)")[0])
