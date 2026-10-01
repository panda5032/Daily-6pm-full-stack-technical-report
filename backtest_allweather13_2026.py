# -*- coding: utf-8 -*-
"""
全天候合并打法回测 2026-08-28: 金叉底仓 × 短线叠加
  纯13:   金叉期间满仓持有, 死叉空仓 (基准)
  合并版: 金叉期间 2/3 底仓; 金叉内回踩企稳(打法1式) 加 1/3, 破MA20撤加仓;
          死叉期间 1/3 仓做打法7恐慌反转 (下轨+RSI<32 后反包, 中轨/止损/15根出)
  逐日复利: equity *= 1 + w(t)*ret(t); 入场信号收盘确认, 次日起计权重。
输出: 各年每票复利均值/中位数 + 平均最大回撤, 对比纯13。
"""
import json, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
from backtest_playbooks_2026 import get_universe, download_all, WINDOWS

def build_weights(df):
    c = df["Close"]; h = df["High"]; l = df["Low"]
    ma20 = c.rolling(20).mean(); ma50 = c.rolling(50).mean(); ma200 = c.rolling(200).mean()
    sd = c.rolling(20).std(); bb_lo = ma20 - 2 * sd
    delta = c.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    gold = (ma50 > ma200).values
    n = len(df)
    w13 = np.zeros(n)   # pure 13 weight
    wm = np.zeros(n)    # merged weight
    add_on = False; pb7_on = False; pb7_stop = 0.0; pb7_i = 0
    cv, ma20v, rsiv, bbv = c.values, ma20.values, rsi.values, bb_lo.values
    hv, lv = h.values, l.values
    for i in range(210, n - 1):
        g = gold[i]
        w13[i + 1] = 1.0 if g else 0.0
        if g:
            pb7_on = False
            base = 2 / 3
            # add leg: pullback to MA20 (±3.5%) after down-5d, stabilization close>prior high
            if not add_on:
                near = abs(cv[i] / ma20v[i] - 1) <= 0.035 and cv[i] < cv[i - 5]
                if near and cv[i] > hv[i - 1]:
                    add_on = True
            else:
                if cv[i] < ma20v[i] * 0.99:
                    add_on = False
            wm[i + 1] = base + (1 / 3 if add_on else 0.0)
        else:
            add_on = False
            if not pb7_on:
                cap = any(cv[j] < bbv[j] and rsiv[j] < 32 for j in range(i - 5, i))
                if cap and cv[i] > hv[i - 1]:
                    pb7_on = True; pb7_stop = float(np.min(lv[i - 5:i + 1])); pb7_i = i
            else:
                if cv[i] >= ma20v[i] or cv[i] < pb7_stop or i - pb7_i >= 15:
                    pb7_on = False
            wm[i + 1] = 1 / 3 if pb7_on else 0.0
    return w13, wm

def main():
    tickers, _ = get_universe()
    data = download_all(tickers)
    print(f"data ok {len(data)}")
    W = {}
    for t, df in data.items():
        if len(df) < 260: continue
        W[t] = (df, *build_weights(df))
    for label, start, end in WINDOWS:
        r13, rm, dd13, ddm = [], [], [], []
        for t, (df, w13, wm) in W.items():
            idx = df.index
            s_i = int(np.searchsorted(idx, pd.Timestamp(start)))
            e_i = len(df) if end is None else int(np.searchsorted(idx, pd.Timestamp(end)))
            if e_i - s_i < 20: continue
            ret = df["Close"].pct_change().values
            def equity(w):
                eq = np.cumprod(1 + w[s_i:e_i] * np.nan_to_num(ret[s_i:e_i]))
                mdd = float(np.min(eq / np.maximum.accumulate(eq)) - 1)
                return float(eq[-1] - 1), mdd
            a, d1 = equity(w13); b, d2 = equity(wm)
            r13.append(a); rm.append(b); dd13.append(d1); ddm.append(d2)
        print(f"\n== {label} ==  (tickers {len(r13)})")
        print(f"纯13 满仓 : mean {np.mean(r13):+.2%} median {np.median(r13):+.2%} avgMaxDD {np.mean(dd13):+.1%}")
        print(f"合并全天候: mean {np.mean(rm):+.2%} median {np.median(rm):+.2%} avgMaxDD {np.mean(ddm):+.1%}")

if __name__ == "__main__":
    main()
