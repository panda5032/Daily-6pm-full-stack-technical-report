"""
Tesla Stock Agent — research engine.

Job: keep searching TSLA's own history for the best SHORT-TERM entry/exit method, promote only
what survives out-of-sample, and turn the current champion into tomorrow's buy/sell levels.

  python tsla_agent.py --research   walk-forward search over the rule families (≈1-3 min), update state
  python tsla_agent.py --today      tomorrow's buy/sell points from the current champion (fast, default)
  python tsla_agent.py --both

Method families (each with a small parameter grid; every rule is long-only, 1 position at a time):
  F1 突破      N-day-high breakout, optional MA50 filter, exit close<MA_k or ATR stop
  F2 带行      fresh %B ≥ p in uptrend, exit close<MA20 (with/without volume confirm)
  F3 回踩      pullback to MA10/20 + close > prior high, exit MA_k −1% or stop
  F4 RSI2回归  RSI(2) < x above MA50/200, exit close>MA5 or RSI(2)>y or 5 bars
  F5 缺口延续  gap-up ≥ g% closing strong, hold n bars, stop gap-day low
  F6 金针      lower-wick pin bar scaled K×ATR, target MA20, 12-bar time stop
  F7 财报PEAD  beat-pop then pullback to MA5 within w bars

Walk-forward: train 24 months → validate 6 months, rolling 6 months, 2016 → today. Per family the
train-best parameters (PF, n ≥ 12) are frozen and scored on the validation slice; all validation
trades are pooled = out-of-sample record. Fills: signal at close → next open, 0.1% slippage/side.
Promotion (same bar as the playbook system): OOS n ≥ 30 and PF ≥ 2.0 and PF without top-10% ≥ 1.2.

State: tsla_agent_state.json (champion, leaderboard, run history) · tsla_agent_<date>.md · tsla_agent_signals.jsonl
Research only — not financial advice, no live orders.
"""
import argparse
import itertools
import json
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

HERE = Path(__file__).parent
TODAY = datetime.now().strftime("%Y-%m-%d")
STATE = HERE / "tsla_agent_state.json"
SIGLOG = HERE / "tsla_agent_signals.jsonl"
SLIP = 0.001
TRAIN_M, VAL_M, STEP_M = 24, 6, 6
WF_START = "2016-01-01"


# ────────────────────────── data ──────────────────────────
def load():
    t = yf.Ticker("TSLA")
    df = t.history(start="2010-06-29", interval="1d", auto_adjust=True)
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
    try:
        ed = t.get_earnings_dates(limit=80)
        earn = sorted({pd.Timestamp(x).tz_localize(None).normalize() for x in ed.index})
    except Exception:
        earn = []
    df["earn_react"] = False
    for d in earn:                      # AMC report → reaction is the next session
        j = int(np.searchsorted(df.index, d, side="right"))
        if j < len(df):
            df.iloc[j, df.columns.get_loc("earn_react")] = True
    return df


def arrays(df):
    return {k: df[k].values.astype(float) if k != "earn_react" else df[k].values
            for k in df.columns}


# ────────────────────────── rule families ──────────────────────────
# entry(A, i) -> dict|None ; exit(A, i, pos) -> bool.  A = column arrays. i = signal bar.
def F1(N, ma50, k, s):
    def entry(A, i):
        if np.isnan(A[f"hi{N}"][i]) or A["Close"][i] <= A[f"hi{N}"][i]:
            return None
        if ma50 and A["Close"][i] < A["ma50"][i]:
            return None
        return {"stop": A["Close"][i] - s * A["atr"][i]}
    def exit_(A, i, pos):
        return A["Close"][i] < A[f"ma{k}"][i] or A["Close"][i] < pos["stop"]
    return entry, exit_


def F2(p, rvol):
    def entry(A, i):
        if (A["pctb"][i] >= p and A["pctb"][i - 1] < p
                and A["Close"][i] > A["ma20"][i] > A["ma50"][i]):
            return {}
        return None
    def exit_(A, i, pos):
        below = A["Close"][i] < A["ma20"][i]
        if rvol <= 1.0:
            return below
        return below and (A["Volume"][i] >= rvol * A["vol20"][i] or A["Close"][i - 1] < A["ma20"][i - 1])
    return entry, exit_


def F3(m, tol, k):
    def entry(A, i):
        if not (A["Close"][i] > A["ma50"][i] and A["ma50"][i] > A["ma50"][i - 10]):
            return None
        near = any(abs(A["Close"][j] / A[f"ma{m}"][j] - 1) <= tol and A["Close"][j] < A["Close"][j - 5]
                   for j in (i - 2, i - 1, i))
        if near and A["Close"][i] > A["High"][i - 1]:
            return {"stop": A["Low"][i] - 0.5 * A["atr"][i]}
        return None
    def exit_(A, i, pos):
        return A["Close"][i] < pos["stop"] or A["Close"][i] < A[f"ma{k}"][i] * 0.99
    return entry, exit_


def F4(x, mafilt, y):
    def entry(A, i):
        if A["rsi2"][i] < x and A["Close"][i] > A[f"ma{mafilt}"][i]:
            return {}
        return None
    def exit_(A, i, pos):
        return (A["Close"][i] > A["ma5"][i] or A["rsi2"][i] > y or i - pos["sig_i"] >= 5)
    return entry, exit_


def F5(g, n):
    def entry(A, i):
        gap = A["Open"][i] / A["Close"][i - 1] - 1
        rng = (A["High"][i] - A["Low"][i]) or 1e-9
        if gap >= g and (A["Close"][i] - A["Low"][i]) / rng >= 0.6 and A["Close"][i] > A["Open"][i]:
            return {"stop": A["Low"][i]}
        return None
    def exit_(A, i, pos):
        return A["Close"][i] < pos["stop"] or i - pos["sig_i"] >= n
    return entry, exit_


def F6(K):
    def entry(A, i):
        o, h, l, c = A["Open"][i], A["High"][i], A["Low"][i], A["Close"][i]
        body, wick, rng = abs(c - o), min(o, c) - l, (h - l) or 1e-9
        weak = c < A["ma20"][i] or c / A["Close"][i - 5] - 1 <= -0.05
        if wick >= 2 * body and wick >= K * A["atr"][i] and (c - l) / rng >= 0.5 and weak:
            return {"stop": l - 0.25 * A["atr"][i]}
        return None
    def exit_(A, i, pos):
        return (A["Close"][i] < pos["stop"] or A["Close"][i] >= A["ma20"][i]
                or i - pos["sig_i"] >= 12)
    return entry, exit_


def F7(w, g):
    def entry(A, i):
        for k in range(1, w + 1):
            j = i - k
            if j >= 1 and A["earn_react"][j]:
                rng = (A["High"][j] - A["Low"][j]) or 1e-9
                pop = A["Open"][j] / A["Close"][j - 1] - 1 >= g and (A["Close"][j] - A["Low"][j]) / rng >= 0.5
                if pop and A["Close"][i] <= A["ma5"][i] * 1.01 and A["Close"][i] > A["Low"][j]:
                    return {"stop": A["Low"][j]}
        return None
    def exit_(A, i, pos):
        return (A["Close"][i] < pos["stop"] or A["Close"][i] < A["ma20"][i]
                or i - pos["sig_i"] >= 20)
    return entry, exit_


FAMILIES = {
    "F1 突破":     (F1, dict(N=[10, 20, 30, 55], ma50=[True, False], k=[10, 20], s=[2.0, 3.0])),
    "F2 带行":     (F2, dict(p=[0.8, 0.9], rvol=[1.0, 1.3])),
    "F3 回踩":     (F3, dict(m=[10, 20], tol=[0.02, 0.035], k=[10, 20])),
    "F4 RSI2回归": (F4, dict(x=[5, 10, 15], mafilt=[50, 200], y=[65, 85])),
    "F5 缺口延续": (F5, dict(g=[0.03, 0.05], n=[3, 5, 10])),
    "F6 金针":     (F6, dict(K=[0.4, 0.6, 0.8])),
    "F7 财报PEAD": (F7, dict(w=[3, 5], g=[0.03])),
}
MIN_N = {"F2 带行": 6, "F7 财报PEAD": 3}          # low-frequency families; others need 12
PB_MAP = {"F1 突破": "打法2/16", "F2 带行": "打法8", "F3 回踩": "打法1", "F4 RSI2回归": "新候选(未在打法体系)",
          "F5 缺口延续": "新候选(未在打法体系)", "F6 金针": "打法15", "F7 财报PEAD": "打法6"}


def grid(params):
    keys = list(params)
    for vals in itertools.product(*[params[k] for k in keys]):
        yield dict(zip(keys, vals))


# ────────────────────────── engine ──────────────────────────
def run(A, n_bars, entry, exit_, i0, i1):
    """Entries signalled in [i0, i1); positions may run past i1 (closed at the true exit, or
    marked at the last bar). Returns trades [(sig_i, entry_i, exit_i, ret)]."""
    o, c = A["Open"], A["Close"]
    trades, pos, i = [], None, max(i0, 210)
    while i < n_bars - 1:
        if pos is None:
            if i >= i1:
                break
            e = entry(A, i)
            if e is not None:
                pos = {"sig_i": i, "entry_i": i + 1, "entry": o[i + 1] * (1 + SLIP), **e}
        elif exit_(A, i, pos):
            trades.append((pos["sig_i"], pos["entry_i"], i + 1, o[i + 1] * (1 - SLIP) / pos["entry"] - 1, False))
            pos = None
        i += 1
    if pos is not None:
        trades.append((pos["sig_i"], pos["entry_i"], n_bars - 1, c[-1] / pos["entry"] - 1, True))
    return trades


def stats(rets):
    r = np.asarray(rets, float)
    if len(r) == 0:
        return {"n": 0, "pf": 0.0, "avg": 0.0, "win": 0.0, "mdd": 0.0, "pf_ex": 0.0, "tail": 0.0}
    w, lo = r[r > 0], r[r <= 0]
    pf = float(w.sum() / abs(lo.sum())) if lo.sum() != 0 else (99.0 if w.sum() > 0 else 0.0)
    eq = np.cumprod(1 + r)
    mdd = float((eq / np.maximum.accumulate(eq) - 1).min())
    k = max(1, int(np.ceil(len(r) * 0.1)))
    rest = np.sort(r)[:-k]
    rw, rl = rest[rest > 0], rest[rest <= 0]
    pf_ex = float(rw.sum() / abs(rl.sum())) if rl.sum() != 0 else (99.0 if rw.sum() > 0 else 0.0)
    tail = float(np.sort(r)[-k:].clip(0).sum() / w.sum()) if w.sum() > 0 else 0.0
    return {"n": int(len(r)), "pf": round(pf, 2), "avg": round(float(r.mean()), 4),
            "win": round(float((r > 0).mean()), 3), "mdd": round(mdd, 3), "pf_ex": round(pf_ex, 2),
            "tail": round(tail, 2)}


TIER = {"晋升": 2, "影子期": 1, "影子期(样本不足)": 1}


def rank_key(s):
    """Champion = highest verdict tier first, then score (a 影子期 family never outranks a 晋升 one)."""
    return (TIER.get(s["verdict"], 0), s["score"])


def verdict(s):
    if s["n"] < 30:
        return "影子期(样本不足)" if s["pf"] >= 1.5 else "弱"
    if s["pf"] >= 2.0 and s["pf_ex"] >= 1.2:
        return "晋升"
    return "影子期" if s["pf"] >= 1.5 else "只当修正器"


# ────────────────────────── walk-forward research ──────────────────────────
def research(df):
    A, idx, n = arrays(df), df.index, len(df)
    folds = []
    t = pd.Timestamp(WF_START)
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
                tr = run(A, n, *fn(**p), a, b)
                s = stats([x[3] for x in tr])
                key = (s["pf"] if s["n"] >= MIN_N.get(fam, 12) else -1, s["n"])
                if best_key is None or key > best_key:
                    best, best_key = p, key
            if best_key[0] < 0:
                chosen.append(None)
                continue
            va = run(A, n, *fn(**best), b, c_)
            rets = [x[3] for x in va]
            oos += [(str(idx[x[1]].date()), str(idx[x[2]].date()), round(x[3], 4), best) for x in va]
            chosen.append(best)
            fold_pos += 1 if sum(rets) > 0 else 0
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
    ranked = sorted(board.values(), key=rank_key, reverse=True)
    return ranked, len(folds)


# ────────────────────────── today's levels ──────────────────────────
def today_levels(df, fam, p):
    A, n, i = arrays(df), len(df), len(df) - 1
    fn = FAMILIES[fam][0]
    entry, exit_ = fn(**p)
    # current simulated position under the champion (entries from 2024)
    tr = run(A, n, entry, exit_, int(np.searchsorted(df.index, pd.Timestamp("2024-01-01"))), n - 1)
    open_pos = tr[-1] if tr and tr[-1][4] else None
    sig = entry(A, i)
    c, atr = A["Close"][i], A["atr"][i]
    out = {"family": fam, "params": p, "close": round(c, 2), "atr": round(atr, 2),
           "signal_now": sig is not None, "stop_if_entered": round(sig["stop"], 2) if sig and "stop" in sig else None}
    if fam == "F1 突破":
        lvl = A[f"hi{p['N']}"][i]
        out["buy_trigger"] = f"收盘 > {lvl:.2f}（{p['N']}日高）" + ("，且在 MA50 上方" if p["ma50"] else "")
        if out["stop_if_entered"] is None and not np.isnan(lvl):
            out["stop_if_entered"] = round(lvl - p["s"] * atr, 2)
        mk = A["ma%d" % p["k"]][i]
        out["sell_rule"] = f"收盘 < MA{p['k']} {mk:.2f} 或 跌破 入场−{p['s']}×ATR"
    elif fam == "F2 带行":
        out["buy_trigger"] = f"%B 首次 ≥ {p['p']}（今 {A['pctb'][i]:.2f}），且 价>MA20>MA50"
        out["sell_rule"] = f"收盘 < MA20 {A['ma20'][i]:.2f}" + (f"（RVOL≥{p['rvol']} 或连续两日）" if p["rvol"] > 1 else "")
    elif fam == "F3 回踩":
        mm = A["ma%d" % p["m"]][i]
        out["buy_trigger"] = f"回踩 MA{p['m']} {mm:.2f}±{p['tol']:.1%} 后收盘过前一日高"
        out["sell_rule"] = f"收盘 < MA{p['k']}×0.99 或 企稳bar低点−0.5ATR"
    elif fam == "F4 RSI2回归":
        mf = A["ma%d" % p["mafilt"]][i]
        out["buy_trigger"] = f"RSI(2) < {p['x']}（今 {A['rsi2'][i]:.0f}）且 价 > MA{p['mafilt']} {mf:.2f}"
        out["sell_rule"] = f"收盘 > MA5 {A['ma5'][i]:.2f} 或 RSI(2) > {p['y']} 或 5 日"
    elif fam == "F5 缺口延续":
        out["buy_trigger"] = f"高开 ≥ {p['g']:.0%} 且收在振幅上 40% 的阳线"
        out["sell_rule"] = f"持 {p['n']} 日，跌破缺口日低点离场"
    elif fam == "F6 金针":
        out["buy_trigger"] = f"下影 ≥ 2×实体 且 ≥ {p['K']}×ATR（= ${p['K'] * atr:.2f}），弱势中"
        out["sell_rule"] = f"到 MA20 {A['ma20'][i]:.2f} 或 12 日 或 影线低点下方"
    elif fam == "F7 财报PEAD":
        out["buy_trigger"] = f"财报日高开 ≥ {p['g']:.0%} 收上半区后 {p['w']} 日内回踩 MA5"
        out["sell_rule"] = "收盘 < MA20 或 缺口日低点 或 20 日"
    elif fam == "F8 MA20站回":
        out["buy_trigger"] = (f"MA20 下方 ≥ {p['below']} 根后收盘站回上行的 MA20 {A['ma20'][i]:.2f}"
                              f"（今 {'上方' if c > A['ma20'][i] else '下方'}）")
        out["sell_rule"] = f"收盘 < MA{p['k']} {A['ma%d' % p['k']][i]:.2f} 或 站回日低点−1×ATR"
    elif fam == "F9 暴跌反转":
        d5 = A["Close"][i] / A["Close"][i - 5] - 1
        out["buy_trigger"] = f"5 根跌幅 ≥ {p['drop']:.0%}（今 {d5:+.1%}）后收盘过前一根高点"
        out["sell_rule"] = f"到 MA20 {A['ma20'][i]:.2f} 或 5 根低点下方 或 {p['hold']} 根"
    out["position"] = ({"entered": str(df.index[open_pos[1]].date()), "unrealized": round(float(open_pos[3]), 4)}
                       if open_pos else None)
    return out


# ────────────────────────── main ──────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--research", action="store_true")
    ap.add_argument("--today", action="store_true")
    ap.add_argument("--both", action="store_true")
    a = ap.parse_args()
    do_r = a.research or a.both
    do_t = a.today or a.both or not a.research
    df = load()
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"runs": [], "champion": None}
    intraday = False
    try:
        from zoneinfo import ZoneInfo
        et = datetime.now(ZoneInfo("America/New_York"))
        intraday = et.weekday() < 5 and (et.hour, et.minute) >= (9, 30) and et.hour < 16
    except Exception:
        pass
    md = [f"# Tesla Stock Agent — {TODAY}" + ("（盘中快照，今日 bar 未完成，价位以收盘为准）" if intraday else ""),
          f"data 2010-06-29 → {df.index[-1].date()} · {len(df)} bars · 次日开盘成交 · 滑点 {SLIP:.1%}/边", ""]
    if do_r:
        print("research: walk-forward", WF_START, "→ today")
        ranked, nf = research(df)
        champ = ranked[0]
        prev = state.get("champion")
        state["champion"] = {k: champ[k] for k in ("family", "playbook", "mode_params", "n", "pf", "win", "avg",
                                                   "mdd", "pf_ex", "tail", "consistency", "param_stability", "score", "verdict")}
        state["leaderboard"] = [{k: s[k] for k in state["champion"]} for s in ranked]
        state["runs"].append({"date": TODAY, "folds": nf, "champion": champ["family"], "score": champ["score"],
                              "changed": (prev or {}).get("family") != champ["family"]})
        (HERE / f"tsla_agent_oos_{TODAY}.json").write_text(
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
        md += ["## 明日买点 / 卖点（按当前冠军 + 前三名）", ""]
        for s in state["leaderboard"][:3]:
            lv = today_levels(df, s["family"], s["mode_params"])
            tag = "冠军" if s["family"] == champ["family"] else "候补"
            md += [f"**{tag} · {s['family']}**（{s['playbook']}，OOS PF {s['pf']}，n {s['n']}，{s['verdict']}）",
                   f"- 今收 {lv['close']} · ATR {lv['atr']}",
                   f"- 买点：{lv['buy_trigger']}" + ("  ← **今日已触发，明日开盘执行**" if lv["signal_now"] else "（未触发）"),
                   f"- 卖点：{lv['sell_rule']}",
                   f"- 若进场止损：{lv['stop_if_entered']}" if lv["stop_if_entered"] else "- 止损：按规则",
                   f"- 模拟持仓：{lv['position']}" if lv["position"] else "- 模拟持仓：空仓", ""]
            with SIGLOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"date": TODAY, "bar": str(df.index[-1].date()), **{k: v for k, v in lv.items()}},
                                   ensure_ascii=False, default=str) + "\n")
    elif do_t:
        md.append("尚无冠军 — 先跑 `--research`。")
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (HERE / f"tsla_agent_{TODAY}.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
