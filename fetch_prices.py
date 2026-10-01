# -*- coding: utf-8 -*-
import yfinance as yf, json, datetime
from resolve_universe import UNIVERSE

syms=[]
meta={}
for theme,items in UNIVERSE.items():
    for orig,tk,yfs,note in items:
        syms.append(yfs)
        meta[yfs]=(theme,orig,tk,note)

data = yf.download(syms, period="6d", interval="1d", group_by="ticker", threads=True, progress=False, auto_adjust=False)

out={}
for yfs in syms:
    try:
        df = data[yfs].dropna()
        if len(df)==0:
            out[yfs]=None; continue
        last = float(df["Close"].iloc[-1])
        prev = float(df["Close"].iloc[-2]) if len(df)>=2 else last
        chg = (last-prev)/prev*100 if prev else 0.0
        wk = float(df["Close"].iloc[0])
        wkchg = (last-wk)/wk*100 if wk else 0.0
        out[yfs]={"last":round(last,4),"prev":round(prev,4),"day_chg_pct":round(chg,2),"wk_chg_pct":round(wkchg,2)}
    except Exception as e:
        out[yfs]={"err":str(e)[:80]}

ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
print("AS_OF", ts)
miss=[s for s in syms if not out.get(s) or "err" in (out.get(s) or {}) or out.get(s) is None]
print("MISSING/ERR:", miss)
json.dump({"as_of":ts,"prices":out,"meta":{k:list(v) for k,v in meta.items()}}, open("prices.json","w"))
print("saved prices.json; got", len([s for s in syms if out.get(s) and 'last' in (out.get(s) or {})]), "of", len(syms))
