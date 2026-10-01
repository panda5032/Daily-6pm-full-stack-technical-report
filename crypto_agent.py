"""
Crypto Asset Agents — BTC / ETH / XRP short-term method research, same engine as the Tesla agent.

  python crypto_agent.py --asset BTC --research|--today|--both
  python crypto_agent.py --asset ETH ...      python crypto_agent.py --asset XRP ...

Differences from tsla_agent.py:
  * 24/7 market: daily bars are UTC 00:00 (yfinance). Signal at bar close → fill at next bar open.
  * No earnings → F7 PEAD dropped. Families: F1 突破 · F2 带行 · F3 回踩 · F4 RSI2回归 · F5 缺口延续
    (gap = open vs prior close, rare in crypto but kept) · F6 金针 · F8 MA20 站回 (crypto-specific: close back
    above a rising MA20 after ≥5 bars below, exit close<MA10) · F9 暴跌反转 (5-bar drop ≥ 12% then a close
    above the prior bar's high, 8-bar time stop).
  * Walk-forward start: BTC 2017-01, ETH/XRP 2020-01 (24-month train needs data from 2017-11).
  * Gates cross-checked by the agent (not the script): 12c BTC gauge (crypto_derivs_<date>.md), M顶闸 in
    trade_plans_<date>.json, BTC below MA20 → ETH/XRP tightened.

State: <key>_agent_state.json · <key>_agent_<date>.md · <key>_agent_oos_<date>.json · <key>_agent_signals.jsonl
Research only — not financial advice, no live orders.
"""
import argparse
import json
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")
from tsla_agent import (F1, F2, F3, F4, F5, F6, MIN_N, SLIP, TRAIN_M, VAL_M, STEP_M,  # noqa: E402
                        arrays, grid, rank_key, run, stats, verdict)
import tsla_agent  # noqa: E402  (today_levels reads tsla_agent.FAMILIES — extended below)

HERE = Path(__file__).parent
TODAY = datetime.now().strftime("%Y-%m-%d")
ASSETS = {
    "BTC": {"ticker": "BTC-USD", "wf_start": "2017-01-01", "name": "Bitcoin"},
    "ETH": {"ticker": "ETH-USD", "wf_start": "2020-01-01", "name": "Ethereum"},
    "XRP": {"ticker": "XRP-USD", "wf_start": "2020-01-01", "name": "XRP"},
}


# ────────────────────────── crypto-specific families ──────────────────────────
def F8(k, below):
    """MA20 reclaim: ≥`below` bars under MA20, today closes above MA20 and above the prior bar's high
    (a rising-MA20 filter contradicts the setup — MA20 falls while price sits under it); exit close<MA_k."""
    def entry(A, i):
        c, m = A["Close"], A["ma20"]
        if c[i] > m[i] and c[i] > A["High"][i - 1] and all(c[j] < m[j] for j in range(i - below, i)):
            return {"stop": A["Low"][i] - 1.0 * A["atr"][i]}
        return None
    def exit_(A, i, pos):
        return A["Close"][i] < A[f"ma{k}"][i] or A["Close"][i] < pos["stop"]
    return entry, exit_


def F9(drop, hold):
    """Crash reversal: 5-bar drop ≥ drop, today closes above prior bar high; stop = 5-bar low; hold ≤ `hold`."""
    def entry(A, i):
        if A["Close"][i - 1] / A["Close"][i - 6] - 1 <= -drop and A["Close"][i] > A["High"][i - 1]:
            return {"stop": float(A["Low"][i - 5:i + 1].min())}
        return None
    def exit_(A, i, pos):
        return (A["Close"][i] < pos["stop"] or A["Close"][i] >= A["ma20"][i]
                or i - pos["sig_i"] >= hold)
    return entry, exit_


FAMILIES = {
    "F1 突破":     (F1, dict(N=[10, 20, 30, 55], ma50=[True, False], k=[10, 20], s=[2.0, 3.0])),
    "F2 带行":     (F2, dict(p=[0.8, 0.9], rvol=[1.0, 1.3])),
    "F3 回踩":     (F3, dict(m=[10, 20], tol=[0.02, 0.035], k=[10, 20])),
    "F4 RSI2回归": (F4, dict(x=[5, 10, 15], mafilt=[50, 200], y=[65, 85])),
    "F5 缺口延续": (F5, dict(g=[0.03, 0.05], n=[3, 5, 10])),
    "F6 金针":     (F6, dict(K=[0.4, 0.6, 0.8])),
    "F8 MA20站回": (F8, dict(k=[10, 20], below=[5, 10])),
    "F9 暴跌反转": (F9, dict(drop=[0.12, 0.18], hold=[8, 15])),
}
MIN_N_C = {**MIN_N, "F5 缺口延续": 4, "F8 MA20站回": 6, "F9 暴跌反转": 4}   # rare families need a lower train bar
PB_MAP = {"F1 突破": "打法2/16", "F2 带行": "打法8", "F3 回踩": "打法1", "F4 RSI2回归": "新候选",
          "F5 缺口延续": "新候选", "F6 金针": "打法15", "F8 MA20站回": "新候选(币圈)", "F9 暴跌反转": "打法7变体"}
# let tsla_agent.today_levels resolve the crypto families too
tsla_agent.FAMILIES.update({k: v for k, v in FAMILIES.items() if k not in tsla_agent.FAMILIES})


def load(ticker):
    df = yf.Ticker(ticker).history(period="max", interval="1d", auto_adjust=True)
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"]).copy()
    df.index = df.index.tz_localize(None)
    c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]
    for n in (5, 10, 20, 50, 200):
        df[f"ma{n}"] = c.rolling(n).mean()
    sd = c.rolling(20).std()
    df["bb_up"], df["bb_lo"] = df["ma20"] + 2 * sd, df["ma20"] - 2 * sd
    df["pctb"] = (c - df["bb_lo"]) / (df["bb_up"] - df["bb_lo"])
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()
    for p in (2, 14):
        d = c.diff()
        g = d.where(d > 0, 0).rolling(p).mean()
        s = (-d.where(d < 0, 0)).rolling(p).mean()
        df[f"rsi{p}"] = 100 - 100 / (1 + g / s.replace(0, np.nan))
    df["vol20"] = v.rolling(20).mean()
    for n in (10, 20, 30, 55):
        df[f"hi{n}"] = h.rolling(n).max().shift(1)
    df["earn_react"] = False
    return df


def research(df, wf_start):
    A, idx, n = arrays(df), df.index, len(df)
    folds, t = [], pd.Timestamp(wf_start)
    while t + pd.DateOffset(months=1) < idx[-1]:
        tr0, tr1, va1 = t - pd.DateOffset(months=TRAIN_M), t, t + pd.DateOffset(months=VAL_M)
        folds.append(tuple(int(np.searchsorted(idx, x)) for x in (tr0, tr1, va1)))
        t += pd.DateOffset(months=STEP_M)
    board = {}
    for fam, (fn, params) in FAMILIES.items():
        oos, chosen, fold_pos = [], [], 0
        for (a, b, c_) in folds:
            best, best_key = None, None
            for p in grid(params):
                s = stats([x[3] for x in run(A, n, *fn(**p), a, b)])
                key = (s["pf"] if s["n"] >= MIN_N_C.get(fam, 12) else -1, s["n"])
                if best_key is None or key > best_key:
                    best, best_key = p, key
            if best_key[0] < 0:
                chosen.append(None)
                continue
            va = run(A, n, *fn(**best), b, c_)
            oos += [(str(idx[x[1]].date()), str(idx[x[2]].date()), round(x[3], 4), best) for x in va]
            chosen.append(best)
            fold_pos += 1 if sum(x[3] for x in va) > 0 else 0
        s = stats([x[2] for x in oos])
        used = [c for c in chosen if c]
        consist = fold_pos / max(1, len(used))
        mode = max(used, key=lambda p: sum(1 for q in used if q == p)) if used else None
        s.update({"family": fam, "playbook": PB_MAP[fam], "consistency": round(consist, 2),
                  "mode_params": mode, "param_stability": round(sum(1 for q in used if q == mode) / max(1, len(used)), 2),
                  "score": round(s["pf"] * min(1.0, s["n"] / 40) * (0.5 + 0.5 * consist), 3),
                  "verdict": verdict(s), "oos_trades": oos})
        board[fam] = s
        print(f"  {fam:12s} OOS n={s['n']:3d} PF={s['pf']:.2f} win={s['win']:.0%} pf_ex={s['pf_ex']:.2f} "
              f"consist={consist:.0%} score={s['score']:.2f} params={mode}")
    return sorted(board.values(), key=rank_key, reverse=True), len(folds)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asset", required=True, choices=list(ASSETS))
    ap.add_argument("--research", action="store_true")
    ap.add_argument("--today", action="store_true")
    ap.add_argument("--both", action="store_true")
    a = ap.parse_args()
    cfg, key = ASSETS[a.asset], a.asset.lower()
    do_r, do_t = a.research or a.both, a.today or a.both or not a.research
    state_p = HERE / f"{key}_agent_state.json"
    df = load(cfg["ticker"])
    state = json.loads(state_p.read_text(encoding="utf-8")) if state_p.exists() else {"runs": [], "champion": None}
    utc = datetime.utcnow()
    md = [f"# {cfg['name']} Agent — {TODAY}（日线为 UTC 00:00 收盘；最新 bar {df.index[-1].date()}"
          + ("，当日 bar 未完成" if df.index[-1].date() == utc.date() else "") + "）",
          f"data {df.index[0].date()} → {df.index[-1].date()} · {len(df)} bars · 次 bar 开盘成交 · 滑点 {SLIP:.1%}/边", ""]
    if do_r:
        print(f"research {a.asset}: walk-forward {cfg['wf_start']} → today")
        ranked, nf = research(df, cfg["wf_start"])
        champ, prev = ranked[0], state.get("champion")
        keys = ("family", "playbook", "mode_params", "n", "pf", "win", "avg", "mdd", "pf_ex", "tail",
                "consistency", "param_stability", "score", "verdict")
        state["champion"] = {k: champ[k] for k in keys}
        state["leaderboard"] = [{k: s[k] for k in keys} for s in ranked]
        state["runs"].append({"date": TODAY, "folds": nf, "champion": champ["family"], "score": champ["score"],
                              "changed": (prev or {}).get("family") != champ["family"]})
        (HERE / f"{key}_agent_oos_{TODAY}.json").write_text(
            json.dumps({s["family"]: s["oos_trades"] for s in ranked}, ensure_ascii=False, indent=0), encoding="utf-8")
        md += [f"## Walk-forward 榜单（{nf} 折，训练 {TRAIN_M} 月 → 验证 {VAL_M} 月，只记验证段）", "",
               "| 名次 | 家族 | 对应打法 | OOS n | 胜率 | PF | 单笔均值 | 最大回撤 | 去顶10% PF | 折内一致性 | 参数稳定 | 众数参数 | 判定 |",
               "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r, s in enumerate(ranked, 1):
            md.append(f"| {r} | {s['family']} | {s['playbook']} | {s['n']} | {s['win']:.0%} | {s['pf']:.2f} | {s['avg']:+.2%} | "
                      f"{s['mdd']:.1%} | {s['pf_ex']:.2f} | {s['consistency']:.0%} | {s['param_stability']:.0%} | "
                      f"`{s['mode_params']}` | {s['verdict']} |")
        md.append("")
    champ = state.get("champion")
    if do_t and champ:
        md += ["## 下一 bar 买点 / 卖点（按当前冠军 + 前三名）", ""]
        for s in state["leaderboard"][:3]:
            lv = tsla_agent.today_levels(df, s["family"], s["mode_params"])
            tag = "冠军" if s["family"] == champ["family"] else "候补"
            md += [f"**{tag} · {s['family']}**（{s['playbook']}，OOS PF {s['pf']}，n {s['n']}，{s['verdict']}）",
                   f"- 最新收 {lv['close']} · ATR {lv['atr']}",
                   f"- 买点：{lv.get('buy_trigger', '见规则')}" + ("  ← **已触发，下一 bar 开盘执行**" if lv["signal_now"] else "（未触发）"),
                   f"- 卖点：{lv.get('sell_rule', '见规则')}",
                   f"- 若进场止损：{lv['stop_if_entered']}" if lv["stop_if_entered"] else "- 止损：按规则",
                   f"- 模拟持仓：{lv['position']}" if lv["position"] else "- 模拟持仓：空仓", ""]
            with (HERE / f"{key}_agent_signals.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"date": TODAY, "bar": str(df.index[-1].date()), **lv}, ensure_ascii=False, default=str) + "\n")
    elif do_t:
        md.append("尚无冠军 — 先跑 `--research`。")
    state_p.write_text(json.dumps(state, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (HERE / f"{key}_agent_{TODAY}.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
