# -*- coding: utf-8 -*-
"""Market internals + short-interest block for the 5:22pm full-stack report (六指数定调 a 节 / 逼空识别).

Free yfinance only:
  risk gauges : ^VIX, ^VIX3M (term ratio), ^VIX9D, HYG/IEF (credit), DX-Y.NYB, ^TNX 10Y, ^TYX 30Y, ^IRX 3M,
                RSP/SPY (equal-weight breadth), IWM/SPY, QQQ/SPY, GLD, USO
  breadth     : AI_Portfolios universe % above MA20/50/200, 20d new highs/lows, advancers/decliners (today)
  short int.  : yfinance .info shortPercentOfFloat / shortRatio / sharesShort vs prior month (FINRA bi-monthly)
                cached in short_interest_cache.json (refreshed when >3 days old) — 150 slow .info calls

Outputs market_internals_<date>.json / .md.  Run: python market_internals.py  [--no-short]
"""
import yfinance as yf, pandas as pd, numpy as np
import json, sys, io, time, os
from datetime import datetime
sys.path.insert(0, ".")
from stock_analysis import load_stocks_from_excel

DATE = datetime.now().strftime("%Y-%m-%d")
GAUGES = {"VIX": "^VIX", "VIX3M": "^VIX3M", "VIX9D": "^VIX9D", "HYG": "HYG", "IEF": "IEF", "LQD": "LQD",
          "DXY": "DX-Y.NYB", "US10Y": "^TNX", "US30Y": "^TYX", "US3M": "^IRX", "RSP": "RSP", "SPY": "SPY",
          "IWM": "IWM", "QQQ": "QQQ", "GLD": "GLD", "USO": "USO", "TLT": "TLT", "VVIX": "^VVIX", "SKEW": "^SKEW"}


def pct(a, b):
    try: return round((a / b - 1) * 100, 2)
    except Exception: return None


def gauges():
    raw = yf.download(list(GAUGES.values()), period="1y", interval="1d", auto_adjust=True,
                      group_by="ticker", progress=False, threads=True)
    C = {}
    for k, t in GAUGES.items():
        try:
            s = raw[t]["Close"].dropna()
            if len(s) > 30: C[k] = s
        except Exception: pass
    for k, t in GAUGES.items():          # single-ticker fallback (^VIX3M/^VIX9D often drop out of bulk download)
        if k not in C:
            try:
                s = yf.Ticker(t).history(period="1y", interval="1d", auto_adjust=True)["Close"].dropna()
                if len(s) >= 1: C[k] = s      # ^VIX3M/^VIX6M/^VIX9D: yfinance serves spot only (1 bar) — keep for ratios
            except Exception: pass
    g = {}
    def last(k): return float(C[k].iloc[-1]) if k in C else None
    def chg(k, n): return pct(float(C[k].iloc[-1]), float(C[k].iloc[-1 - n])) if k in C and len(C[k]) > n else None
    def pctile(s, n=126): s = s.iloc[-n:]; return round(100 * float((s < s.iloc[-1]).mean()), 0)
    for k in C:
        if len(C[k]) < 30:
            g[k] = {"last": round(last(k), 2), "d1": None, "d5": None, "d20": None, "pct6m": None, "ma50_dev": None, "ma200_dev": None}
            continue
        g[k] = {"last": round(last(k), 2), "d1": chg(k, 1), "d5": chg(k, 5), "d20": chg(k, 20),
                "pct6m": pctile(C[k]), "ma50_dev": pct(last(k), float(C[k].rolling(50).mean().iloc[-1])),
                "ma200_dev": pct(last(k), float(C[k].rolling(200).mean().iloc[-1])) if len(C[k]) >= 200 else None}
    ratios = {}
    def ratio(a, b, name):
        if a in C and b in C and (len(C[a]) < 30 or len(C[b]) < 30):
            ratios[name] = {"last": round(float(C[a].iloc[-1] / C[b].iloc[-1]), 4), "d5": None, "d20": None, "pct6m": None, "vs_ma20": None}
            return
        if a in C and b in C:
            r = (C[a] / C[b]).dropna()
            ratios[name] = {"last": round(float(r.iloc[-1]), 4), "d5": pct(float(r.iloc[-1]), float(r.iloc[-6])),
                            "d20": pct(float(r.iloc[-1]), float(r.iloc[-21])), "pct6m": pctile(r),
                            "vs_ma20": pct(float(r.iloc[-1]), float(r.rolling(20).mean().iloc[-1]))}
    ratio("VIX", "VIX3M", "VIX/VIX3M")      # >1 = backwardation = stress
    ratio("HYG", "IEF", "HYG/IEF")          # falling = credit stress
    ratio("RSP", "SPY", "RSP/SPY")          # falling = narrow leadership
    ratio("IWM", "SPY", "IWM/SPY")
    ratio("QQQ", "SPY", "QQQ/SPY")
    if "US10Y" in C and "US3M" in C:
        ratios["10Y-3M(bp)"] = {"last": round((last("US10Y") - last("US3M")) * 100, 0)}
    if "US30Y" in C and "US10Y" in C:
        ratios["30Y-10Y(bp)"] = {"last": round((last("US30Y") - last("US10Y")) * 100, 0)}
    return g, ratios


def breadth():
    tks = [t for _, t, _ in load_stocks_from_excel("AI_Portfolios.xlsx") if t not in ("SKHY", "PEPE-USD", "GOLD", "SILVER", "COPPER", "OIL(USO)")]
    tks = list(dict.fromkeys(tks))
    raw = yf.download(tks, period="1y", interval="1d", auto_adjust=True, group_by="ticker", progress=False, threads=True)
    n = 0; a20 = a50 = a200 = 0; nh = nl = 0; adv = dec = 0; above_ma50_prev = 0
    rows = {}
    for t in tks:
        try:
            s = raw[t]["Close"].dropna()
            h = raw[t]["High"].dropna(); l = raw[t]["Low"].dropna()
            if len(s) < 60: continue
            n += 1
            c = float(s.iloc[-1]); m20 = s.rolling(20).mean().iloc[-1]; m50 = s.rolling(50).mean().iloc[-1]
            m200 = s.rolling(200).mean().iloc[-1] if len(s) >= 200 else np.nan
            a20 += c > m20; a50 += c > m50; a200 += (c > m200) if not np.isnan(m200) else 0
            above_ma50_prev += float(s.iloc[-6]) > s.rolling(50).mean().iloc[-6]
            nh += c >= float(h.iloc[-21:-1].max()); nl += c <= float(l.iloc[-21:-1].min())
            adv += c > float(s.iloc[-2]); dec += c < float(s.iloc[-2])
            rows[t] = {"above20": bool(c > m20), "above50": bool(c > m50), "above200": (bool(c > m200) if not np.isnan(m200) else None)}
        except Exception:
            pass
    return {"n": n, "pct_above_ma20": round(100 * a20 / n, 0), "pct_above_ma50": round(100 * a50 / n, 0),
            "pct_above_ma200": round(100 * a200 / n, 0), "pct_above_ma50_5d_ago": round(100 * above_ma50_prev / n, 0),
            "new_20d_highs": nh, "new_20d_lows": nl, "advancers": adv, "decliners": dec}, tks


def short_interest(tks, refresh_days=3):
    cache_f = "short_interest_cache.json"
    cache = {}
    if os.path.exists(cache_f):
        try: cache = json.load(io.open(cache_f, encoding="utf-8"))
        except Exception: cache = {}
    stamp = cache.get("_stamp")
    if stamp and (datetime.now() - datetime.strptime(stamp, "%Y-%m-%d")).days < refresh_days and len(cache) > 50:
        print(f"  short-interest cache from {stamp} reused", file=sys.stderr)
        return cache
    out = {"_stamp": DATE}
    for i, t in enumerate(tks):
        if t.endswith("-USD"): continue
        try:
            inf = yf.Ticker(t).info
            out[t] = {"spf": inf.get("shortPercentOfFloat"), "short_ratio": inf.get("shortRatio"),
                      "shares_short": inf.get("sharesShort"), "shares_short_prior": inf.get("sharesShortPriorMonth"),
                      "date": inf.get("dateShortInterest"), "float": inf.get("floatShares")}
            if out[t]["shares_short"] and out[t]["shares_short_prior"]:
                out[t]["chg_vs_prior"] = round((out[t]["shares_short"] / out[t]["shares_short_prior"] - 1) * 100, 1)
        except Exception as e:
            out[t] = {"error": str(e)[:60]}
        time.sleep(0.35)
        if i % 25 == 0: print(f"  short-interest {i}/{len(tks)}", file=sys.stderr)
    io.open(cache_f, "w", encoding="utf-8").write(json.dumps(out, indent=0))
    return out


def regime(g, r, b):
    why = []; score = 0
    v = g.get("VIX", {}).get("last"); vr = r.get("VIX/VIX3M", {}).get("last")
    if v is not None:
        if v < 15: score += 1; why.append(f"VIX {v:.1f} 低位")
        elif v > 25: score -= 1; why.append(f"VIX {v:.1f} 高位")
        else: why.append(f"VIX {v:.1f}")
    if vr is not None:
        if vr > 1.0: score -= 1; why.append(f"VIX/VIX3M {vr:.2f} 倒挂(近端恐慌)")
        elif vr < 0.9: score += 1; why.append(f"VIX/VIX3M {vr:.2f} 正常陡峭")
        else: why.append(f"VIX/VIX3M {vr:.2f}")
    hy = r.get("HYG/IEF", {})
    if hy.get("d20") is not None:
        if hy["d20"] < -1.5: score -= 1; why.append(f"HYG/IEF 20日 {hy['d20']:+.1f}% 信用利差走阔")
        elif hy["d20"] > 0.5: score += 1; why.append(f"HYG/IEF 20日 {hy['d20']:+.1f}% 信用改善")
        else: why.append(f"HYG/IEF 20日 {hy['d20']:+.1f}%")
    if b.get("pct_above_ma50") is not None:
        p = b["pct_above_ma50"]
        if p >= 60: score += 1; why.append(f"池内 {p:.0f}% 在MA50上方(宽)")
        elif p <= 40: score -= 1; why.append(f"池内仅 {p:.0f}% 在MA50上方(窄)")
        else: why.append(f"池内 {p:.0f}% 在MA50上方")
    y30 = g.get("US30Y", {}).get("last")
    if y30 is not None and y30 >= 5.0: score -= 1; why.append(f"30Y {y30:.2f}% 长端压力")
    label = "风险偏好开" if score >= 2 else ("风险偏好收紧" if score <= -2 else "中性")
    return label, why


def main():
    no_short = "--no-short" in sys.argv
    print("  gauges ...", file=sys.stderr); g, r = gauges()
    print("  breadth ...", file=sys.stderr); b, tks = breadth()
    si = {} if no_short else short_interest(tks)
    lab, why = regime(g, r, b)
    res = {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "gauges": g, "ratios": r, "breadth": b,
           "regime": {"label": lab, "why": why}, "short_interest": si}
    io.open(f"market_internals_{DATE}.json", "w", encoding="utf-8").write(json.dumps(res, indent=1, ensure_ascii=False, default=str))

    f = lambda v, fmt="{:.2f}": (fmt.format(v) if isinstance(v, (int, float)) else "—")
    L = [f"# 📐 Market Internals — {res['generated']}", "", f"**风险偏好读数: {lab}** — " + "; ".join(why), "",
         "## 风险仪表", "| 指标 | 最新 | 1D | 5D | 20D | 6月分位 | vs MA50 | vs MA200 |", "|---|---|---|---|---|---|---|---|"]
    for k in ["VIX", "VIX9D", "VIX3M", "VVIX", "SKEW", "US10Y", "US30Y", "US3M", "DXY", "HYG", "IEF", "LQD", "TLT", "GLD", "USO", "RSP", "IWM", "QQQ", "SPY"]:
        if k in g:
            x = g[k]; L.append(f"| {k} | {f(x['last'])} | {f(x['d1'],'{:+.2f}%')} | {f(x['d5'],'{:+.2f}%')} | {f(x['d20'],'{:+.2f}%')} | {f(x['pct6m'],'{:.0f}')} | {f(x['ma50_dev'],'{:+.1f}%')} | {f(x['ma200_dev'],'{:+.1f}%')} |")
    L += ["", "## 比值 / 利差", "| 比值 | 最新 | 5D | 20D | 6月分位 | vs MA20 | 含义 |", "|---|---|---|---|---|---|---|"]
    meaning = {"VIX/VIX3M": ">1 倒挂=近端恐慌", "HYG/IEF": "↓=信用利差走阔", "RSP/SPY": "↓=龙头独涨(窄)", "IWM/SPY": "↑=小票风险偏好", "QQQ/SPY": "↑=成长领涨", "10Y-3M(bp)": "期限利差", "30Y-10Y(bp)": "长端溢价"}
    for k, x in r.items():
        L.append(f"| {k} | {f(x.get('last'),'{:.3f}')} | {f(x.get('d5'),'{:+.2f}%')} | {f(x.get('d20'),'{:+.2f}%')} | {f(x.get('pct6m'),'{:.0f}')} | {f(x.get('vs_ma20'),'{:+.2f}%')} | {meaning.get(k,'')} |")
    L += ["", "## 池内广度 (AI_Portfolios)", f"- 样本 {b['n']} | MA20 上方 **{b['pct_above_ma20']:.0f}%** · MA50 上方 **{b['pct_above_ma50']:.0f}%**（5日前 {b['pct_above_ma50_5d_ago']:.0f}%）· MA200 上方 **{b['pct_above_ma200']:.0f}%**",
          f"- 今日 20日新高 {b['new_20d_highs']} / 新低 {b['new_20d_lows']} · 上涨 {b['advancers']} / 下跌 {b['decliners']}", ""]
    if si:
        rows = [(t, d) for t, d in si.items() if not t.startswith("_") and isinstance(d, dict) and d.get("spf")]
        rows.sort(key=lambda z: -(z[1]["spf"] or 0))
        dts = rows[0][1].get('date') if rows else None
        try: dts = datetime.utcfromtimestamp(int(dts)).strftime('%Y-%m-%d')
        except Exception: pass
        L += ["## 空头持仓 (FINRA 半月, yfinance)", f"数据日期: {dts or '—'} · 缓存 {si.get('_stamp')}", "",
              "| 股票 | 空头/流通% | 回补天数 | 环比上期 | 逼空提示 |", "|---|---|---|---|---|"]
        for t, d in rows[:40]:
            spf = (d["spf"] or 0) * 100; dtc = d.get("short_ratio"); chg = d.get("chg_vs_prior")
            tag = "🔥高空头(>20%)" if spf > 20 else ("⚠️偏高(10-20%)" if spf > 10 else "")
            if dtc and dtc > 5: tag += " 回补慢(>5天)"
            L.append(f"| {t} | {spf:.1f}% | {f(dtc,'{:.1f}')} | {f(chg,'{:+.1f}%')} | {tag} |")
        L.append("")
    L.append("读法: VIX/VIX3M>1 + HYG/IEF 走阔 + 广度<40% = 任何个股买入信号降一级; 空头>20% 且放量突破 = 逼空燃料(打法2/16 加分, 但第一次回撤更凶).")
    io.open(f"market_internals_{DATE}.md", "w", encoding="utf-8").write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
