# -*- coding: utf-8 -*-
"""Crypto derivatives positioning read for 打法12c (BTC → 高贝塔温度计).

Free, US-reachable sources only (Binance/Bybit/Coinglass/Farside are geo-blocked or keyed):
  OKX public API   — funding rate (current + 8h history), OI & volume history (1D),
                     long/short account ratio, taker buy/sell ratio, recent liquidation orders
  Deribit public   — DVOL (BTC/ETH implied-vol index) daily history

Outputs crypto_derivs_<date>.json / .md.  Reads no keys.  Run: python crypto_derivs.py
"""
import requests, json, sys, time, io
from datetime import datetime, timedelta, timezone
import statistics as st

COINS = ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE"]
OKX = "https://www.okx.com"
HDR = {"User-Agent": "Mozilla/5.0"}
DATE = datetime.now().strftime("%Y-%m-%d")


def get(url, params=None, tries=3):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=HDR, timeout=15)
            if r.status_code == 200:
                j = r.json()
                if isinstance(j, dict) and j.get("code") not in (None, "0", 0):
                    raise RuntimeError(j.get("msg"))
                return j
            raise RuntimeError(f"HTTP {r.status_code}")
        except Exception as e:
            if i == tries - 1:
                print(f"  [warn] {url.split('/api/')[-1][:60]} {params}: {e}", file=sys.stderr)
                return None
            time.sleep(1.5)


def okx_coin(c):
    inst = f"{c}-USDT-SWAP"
    out = {"inst": inst}
    j = get(f"{OKX}/api/v5/public/funding-rate", {"instId": inst})
    if j and j.get("data"):
        d = j["data"][0]
        out["funding_now"] = float(d["fundingRate"]) * 100          # % per 8h
        out["funding_next"] = float(d.get("nextFundingRate") or 0) * 100 if d.get("nextFundingRate") else None
    j = get(f"{OKX}/api/v5/public/funding-rate-history", {"instId": inst, "limit": 90})
    if j and j.get("data"):
        hist = [float(x["realizedRate"]) * 100 for x in j["data"]]   # newest first, 8h each
        out["funding_hist_8h"] = hist
        out["funding_avg_7d"] = round(st.mean(hist[:21]), 4) if len(hist) >= 21 else None
        out["funding_avg_30d"] = round(st.mean(hist[:90]), 4) if len(hist) >= 30 else None
        out["funding_neg_streak_8h"] = next((i for i, v in enumerate(hist) if v >= 0), len(hist))
        out["funding_pos_streak_8h"] = next((i for i, v in enumerate(hist) if v < 0), len(hist))
        if len(hist) >= 30:
            out["funding_pct_90"] = round(100 * sum(1 for v in hist if v < hist[0]) / len(hist), 0)
    j = get(f"{OKX}/api/v5/rubik/stat/contracts/open-interest-volume", {"ccy": c, "period": "1D"})
    if j and j.get("data"):
        rows = sorted(j["data"], key=lambda r: int(r[0]))   # ts, oi(USD), vol(USD)
        oi = [float(r[1]) for r in rows]; vol = [float(r[2]) for r in rows]
        out["oi_usd"] = oi[-1]
        out["oi_chg_1d"] = round((oi[-1] / oi[-2] - 1) * 100, 1) if len(oi) > 1 else None
        out["oi_chg_7d"] = round((oi[-1] / oi[-8] - 1) * 100, 1) if len(oi) > 7 else None
        out["oi_chg_30d"] = round((oi[-1] / oi[-31] - 1) * 100, 1) if len(oi) > 30 else None
        out["oi_pct_rank"] = round(100 * sum(1 for v in oi if v < oi[-1]) / len(oi), 0)
        out["vol_usd"] = vol[-1]
        out["vol_vs_20d"] = round(vol[-1] / st.mean(vol[-21:-1]), 2) if len(vol) > 21 and st.mean(vol[-21:-1]) > 0 else None
        out["oi_hist_30"] = [round(v / 1e9, 2) for v in oi[-30:]]
    j = get(f"{OKX}/api/v5/rubik/stat/contracts/long-short-account-ratio", {"ccy": c, "period": "1D"})
    if j and j.get("data"):
        rows = sorted(j["data"], key=lambda r: int(r[0]))
        ls = [float(r[1]) for r in rows]
        out["ls_ratio"] = ls[-1]
        out["ls_ratio_7d_ago"] = ls[-8] if len(ls) > 7 else None
        out["ls_hist_14"] = ls[-14:]
    j = get(f"{OKX}/api/v5/rubik/stat/taker-volume", {"ccy": c, "instType": "CONTRACTS", "period": "1D"})
    if j and j.get("data"):
        rows = sorted(j["data"], key=lambda r: int(r[0]))
        b, s = float(rows[-1][1]), float(rows[-1][2])
        out["taker_buy_sell"] = round(b / s, 2) if s else None
    # recent liquidations (OKX returns most recent ~100 filled liquidation orders for the underlying)
    j = get(f"{OKX}/api/v5/public/liquidation-orders", {"instType": "SWAP", "uly": f"{c}-USDT", "state": "filled", "limit": 100})
    if j and j.get("data"):
        det = []
        for blk in j["data"]:
            det += blk.get("details", [])
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).timestamp() * 1000
        recent = [d for d in det if float(d.get("ts", 0)) >= cutoff]
        shorts = sum(1 for d in recent if d.get("posSide") == "short")
        longs = sum(1 for d in recent if d.get("posSide") == "long")
        out["liq_24h_sample"] = {"n": len(recent), "short": shorts, "long": longs,
                                 "note": "OKX 最近≤100笔样本, 非全市场金额"}
    return out


def deribit_dvol(c):
    end = int(time.time() * 1000); start = end - 120 * 86400 * 1000
    j = get("https://www.deribit.com/api/v2/public/get_volatility_index_data",
            {"currency": c, "resolution": "1D", "start_timestamp": start, "end_timestamp": end})
    if not j or not j.get("result", {}).get("data"):
        return None
    rows = j["result"]["data"]   # [ts, open, high, low, close]
    closes = [r[4] for r in rows]
    cur = closes[-1]
    return {"dvol": round(cur, 1), "dvol_7d_ago": round(closes[-8], 1) if len(closes) > 7 else None,
            "dvol_30d_ago": round(closes[-31], 1) if len(closes) > 30 else None,
            "dvol_pct_120d": round(100 * sum(1 for v in closes if v < cur) / len(closes), 0),
            "dvol_120d_hi": round(max(closes), 1), "dvol_120d_lo": round(min(closes), 1)}


def read_12c(btc):
    """Turn BTC positioning into the 打法12c gauge wording."""
    if not btc:
        return "数据缺失", []
    why = []
    f7 = btc.get("funding_avg_7d"); fn = btc.get("funding_now")
    oi7 = btc.get("oi_chg_7d"); ls = btc.get("ls_ratio"); dv = (btc.get("deribit") or {}).get("dvol")
    score = 0
    if fn is not None:
        if fn > 0.03: score -= 1; why.append(f"资金费率 {fn:+.3f}%/8h 偏烫(>0.03)")
        elif fn < 0: score += 1; why.append(f"资金费率 {fn:+.3f}%/8h 为负(空头付费)")
        else: why.append(f"资金费率 {fn:+.3f}%/8h 温和")
    if oi7 is not None:
        if oi7 > 5: score += 1; why.append(f"OI 7日 {oi7:+.1f}% 随价回升")
        elif oi7 < -5: score -= 1; why.append(f"OI 7日 {oi7:+.1f}% 萎缩(平仓驱动)")
        else: why.append(f"OI 7日 {oi7:+.1f}% 持平")
    if ls is not None:
        if ls > 1.5: score -= 1; why.append(f"多空账户比 {ls:.2f} 散户多头拥挤")
        elif ls < 0.9: score += 1; why.append(f"多空账户比 {ls:.2f} 散户偏空")
        else: why.append(f"多空账户比 {ls:.2f} 中性")
    if dv is not None:
        why.append(f"DVOL {dv:.0f} (120日分位 {(btc.get('deribit') or {}).get('dvol_pct_120d')})")
    label = "健康(趋势型)" if score >= 1 else ("拥挤(轧空尾声/过热风险)" if score <= -1 else "中性")
    return label, why


def main():
    res = {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "source": "OKX public + Deribit DVOL", "coins": {}}
    for c in COINS:
        print(f"  {c} ...", file=sys.stderr)
        d = okx_coin(c)
        if c in ("BTC", "ETH"):
            d["deribit"] = deribit_dvol(c)
        res["coins"][c] = d
        time.sleep(0.3)
    lab, why = read_12c(res["coins"].get("BTC"))
    res["gauge_12c"] = {"label": lab, "why": why}
    io.open(f"crypto_derivs_{DATE}.json", "w", encoding="utf-8").write(json.dumps(res, indent=1, ensure_ascii=False))

    L = [f"# 🪙 Crypto Derivatives Positioning — {res['generated']}", "",
         f"来源: OKX 公共 API (USDT 永续) + Deribit DVOL · 免费无 key · 强平为 OKX 最近样本非全市场", "",
         f"**打法12c 仓位读数 (BTC): {lab}** — " + "; ".join(why), "",
         "| 币 | 费率 now %/8h | 7日均 | 30日均 | 费率90期分位 | OI $B | OI 1d | OI 7d | OI 30d | OI分位 | 成交/20d | 多空账户比(7d前) | 吃单买/卖 | 强平24h样本(空/多) | DVOL(分位) |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for c, d in res["coins"].items():
        f = lambda v, fmt="{:+.3f}": (fmt.format(v) if isinstance(v, (int, float)) else "—")
        liq = d.get("liq_24h_sample") or {}
        dv = d.get("deribit") or {}
        L.append(f"| {c} | {f(d.get('funding_now'))} | {f(d.get('funding_avg_7d'),'{:+.4f}')} | {f(d.get('funding_avg_30d'),'{:+.4f}')} | {f(d.get('funding_pct_90'),'{:.0f}')} | "
                 f"{f((d.get('oi_usd') or 0)/1e9,'{:.2f}')} | {f(d.get('oi_chg_1d'),'{:+.1f}%')} | {f(d.get('oi_chg_7d'),'{:+.1f}%')} | {f(d.get('oi_chg_30d'),'{:+.1f}%')} | {f(d.get('oi_pct_rank'),'{:.0f}')} | "
                 f"{f(d.get('vol_vs_20d'),'{:.2f}x')} | {f(d.get('ls_ratio'),'{:.2f}')}({f(d.get('ls_ratio_7d_ago'),'{:.2f}')}) | {f(d.get('taker_buy_sell'),'{:.2f}')} | "
                 f"{liq.get('short','—')}/{liq.get('long','—')} (n={liq.get('n','—')}) | {f(dv.get('dvol'),'{:.0f}')}({f(dv.get('dvol_pct_120d'),'{:.0f}')}) |")
    L += ["", "读法: 费率>0.03%/8h=多头拥挤; 价涨+OI升+费率温和=趋势型; 价涨+OI降=纯轧空; 多空账户比>1.5 散户追多; DVOL 分位高=期权贵/事件溢价。", ""]
    io.open(f"crypto_derivs_{DATE}.md", "w", encoding="utf-8").write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
