"""
Portfolio-level ablation of the 打法组合模拟盘 engine (playbook_portfolio.py).

Replays the live engine's slot/sleeve logic bar-by-bar over 2024-01 → today and
tests the improvement ideas raised after the 2026-08-20→09-21 experiment lagged
SPY/QQQ:

  A  大盘闸     trend sleeves only open new positions while QQQ > MA20 / MA50
  B  波动定仓   slot $ scaled by stop distance (6% distance = full slot, cap 1.5x)
  C  排序       rank candidates by least-extended (ATR above MA20) / lowest ret20
                instead of highest ret20
  D  分批建仓   max 3 new (non-seed) entries per day
  E  行业上限   max 3 open positions per sector
  F  13金叉止损 close < MA200 or -12% from entry
  H  核心+卫星  50% QQQ buy&hold + 50% engine (computed post hoc)

Two test beds:
  1. continuous run 2024-01-02 → last bar (return / maxDD / Sharpe / trade PF)
  2. fresh-start "one-month experiments": start from cash every 5 bars, run
     21 (and 63) bars, compare with SPY/QQQ buy&hold over the same bars —
     this mirrors the live experiment incl. the day-one cohort effect.

Entries/exits fill at the signal bar's close, no costs — same as the live paper
engine, so variants are comparable with each other, not with a real account.

Usage:  python backtest_portfolio_ablation.py [--cache path.pkl] [--refresh]
"""
import argparse
import math
import pickle
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
TODAY = datetime.now().strftime("%Y-%m-%d")

from backtest_playbooks_2026 import (  # noqa: E402
    get_universe, download_all, add_indicators, DATA_START,
    pb1_entry, pb2_entry, pb8_entry, cd1_entry, cd6_entry)
from playbook_portfolio import SLEEVES, SLOT_SIZE, entry_13  # noqa: E402

BT_START = "2024-01-02"
TREND = ("13金叉", "8带行", "1回踩", "2突破")
ENTRIES = {"13金叉": entry_13, "8带行": pb8_entry, "1回踩": pb1_entry,
           "2突破": pb2_entry, "14底背离": cd1_entry, "15金针": cd6_entry}


# ────────────────────────── data prep ──────────────────────────
def load_data(cache, refresh):
    if cache and Path(cache).exists() and not refresh:
        return pickle.load(open(cache, "rb"))
    tickers, sector_of = get_universe()
    data = download_all(tickers)
    for b in ("SPY", "QQQ"):
        d = yf.download(b, start=DATA_START, interval="1d", auto_adjust=True, progress=False)
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = d.columns.get_level_values(0)
        data["_" + b] = d[["Open", "High", "Low", "Close", "Volume"]].dropna()
    if cache:
        pickle.dump((data, sector_of), open(cache, "wb"))
    return data, sector_of


def prep(data, cal):
    """Per ticker: indicators + entry signals on the native calendar, then
    aligned to the NYSE calendar `cal` as numpy arrays."""
    out = {}
    for t, raw in data.items():
        if t.startswith("_"):
            continue
        df = add_indicators(raw.copy())
        n = len(df)
        sig = {s: np.zeros(n, bool) for s in ENTRIES}
        stop = {s: np.full(n, np.nan) for s in ENTRIES}
        for i in range(210, n):
            for s, fn in ENTRIES.items():
                try:
                    e = fn(df, i)
                except Exception:
                    e = None
                if e is not None:
                    sig[s][i] = True
                    stop[s][i] = e.get("stop", np.nan)
        for s in ENTRIES:
            df["sig_" + s] = sig[s]
            df["stop_" + s] = stop[s]
        df["two"] = (df["Close"] < df["ma20"]).shift(1).fillna(False)
        df["dead"] = ((df["macd"] < df["macds"])
                      & (df["macd"].shift(1) >= df["macds"].shift(1)))
        up = (df["ma50"] > df["ma200"]).astype(int)
        df["gc_age"] = up.groupby((up == 0).cumsum()).cumsum()      # bars since golden cross
        a = df.reindex(cal)
        arr = {c: a[c].to_numpy(dtype=float) for c in
               ("Close", "ma20", "ma50", "ma200", "Volume", "vol20", "macd",
                "macds", "atr", "ret20", "gc_age")}
        arr["Cff"] = a["Close"].ffill().to_numpy(dtype=float)
        for c in ["two", "dead"] + ["sig_" + s for s in ENTRIES]:
            arr[c] = a[c].fillna(False).to_numpy(dtype=bool)
        for s in ENTRIES:
            arr["stop_" + s] = a["stop_" + s].to_numpy(dtype=float)
        out[t] = arr
    return out


# ────────────────────────── simulator ──────────────────────────
def exit_reason(A, k, pos, cfg):
    c, ma20 = A["Close"][k], A["ma20"][k]
    if np.isnan(c):
        return None
    s = pos["sleeve"]
    if s == "13金叉":
        if A["ma50"][k] < A["ma200"][k]:
            return "死叉"
        if cfg.get("stop13") and (c < A["ma200"][k] or c / pos["px"] - 1 <= -0.12):
            return "13灾难止损"
    elif s == "8带行":
        if c < ma20 and (A["Volume"][k] >= 1.2 * A["vol20"][k] or A["two"][k]):
            return "破MA20"
    elif s == "1回踩":
        if c < pos["stop"]:
            return "破止损"
        if c < ma20 * 0.99:
            return "破MA20"
    elif s == "2突破":
        if c < ma20:
            return "破MA20"
    elif s == "14底背离":
        if A["dead"][k] or c < pos["stop"] or k - pos["k"] >= 40:
            return "离场14"
    elif s == "15金针":
        if c < pos["stop"] or c >= ma20 or k - pos["k"] >= 12:
            return "离场15"
    return None


def simulate(P, sector_of, gate, k0, k1, cfg):
    """Run the engine from calendar bar k0 (all cash) through k1 inclusive.
    Returns (nav array, closed-trade list, avg exposure)."""
    cash = 3_000_000.0
    pos, trades, nav, expo = [], [], [], []
    for k in range(k0, k1 + 1):
        # 1) exits
        for p in list(pos):
            A = P[p["t"]]
            r = exit_reason(A, k, p, cfg)
            if r:
                px = A["Close"][k]
                cash += p["sh"] * px
                trades.append(dict(sleeve=p["sleeve"], ret=px / p["px"] - 1,
                                   pnl=p["sh"] * (px - p["px"]), days=k - p["k"]))
                pos.remove(p)
        held = {p["t"] for p in pos}
        new_today = 0

        def buy(t, sleeve, seed=False):
            nonlocal cash, new_today
            A = P[t]
            px = A["Close"][k]
            size = SLOT_SIZE[sleeve]
            st = A["stop_" + sleeve][k]
            if cfg.get("volsize"):
                atrp = A["atr"][k] / px
                dist = (px - st) / px if not np.isnan(st) else 2 * atrp
                dist = max(dist, atrp, 0.01)
                size = min(1.5 * size, size * 0.06 / dist)
            sh = size / px
            if sh * px > cash:
                return False
            cash -= sh * px
            pos.append(dict(t=t, sleeve=sleeve, sh=sh, px=px, k=k, stop=st))
            held.add(t)
            if not seed:
                new_today += 1
            return True

        # 2) seed 13金叉 on the first bar (freshest golden crosses above MA50)
        if k == k0:
            c = [(A["gc_age"][k], t) for t, A in P.items()
                 if A["gc_age"][k] > 0 and A["Close"][k] >= A["ma50"][k]]
            for _, t in sorted(c)[:SLEEVES["13金叉"]["slots"]]:
                buy(t, "13金叉", seed=True)

        # 3) fresh entries, sleeve priority order
        gate_ok = True if not cfg.get("gate") else bool(gate[cfg["gate"]][k])
        for sleeve, sc in SLEEVES.items():
            if sleeve in TREND and not gate_ok:
                continue
            free = sc["slots"] - sum(1 for p in pos if p["sleeve"] == sleeve)
            if free <= 0:
                continue
            cands = []
            for t, A in P.items():
                if t in held or not A["sig_" + sleeve][k]:
                    continue
                mom = A["ret20"][k] if not np.isnan(A["ret20"][k]) else 0.0
                ext = (A["Close"][k] - A["ma20"][k]) / A["atr"][k] if A["atr"][k] > 0 else 0.0
                cands.append((t, mom, ext))
            rank = cfg.get("rank", "mom")
            if sleeve in TREND:
                if rank == "mom":
                    cands.sort(key=lambda x: -x[1])
                elif rank == "ext":
                    cands.sort(key=lambda x: x[2])
                else:                                   # lowmom
                    cands.sort(key=lambda x: x[1])
            else:
                cands.sort(key=lambda x: x[1])          # 抄底: weakest first
            for t, _, _ in cands:
                if free <= 0:
                    break
                if cfg.get("maxnew") and new_today >= cfg["maxnew"]:
                    break
                if cfg.get("seccap"):
                    sec = sector_of.get(t)
                    if sum(1 for p in pos if sector_of.get(p["t"]) == sec) >= cfg["seccap"]:
                        continue
                if buy(t, sleeve):
                    free -= 1
        mv = sum(p["sh"] * P[p["t"]]["Cff"][k] for p in pos)
        nav.append(cash + mv)
        expo.append(mv / (cash + mv))
    # mark open trades for PF purposes
    for p in pos:
        px = P[p["t"]]["Cff"][k1]
        trades.append(dict(sleeve=p["sleeve"], ret=px / p["px"] - 1,
                           pnl=p["sh"] * (px - p["px"]), days=k1 - p["k"], open=True))
    return np.array(nav), trades, float(np.mean(expo))


# ────────────────────────── metrics ──────────────────────────
def stats(nav):
    r = np.diff(nav) / nav[:-1]
    dd = (nav / np.maximum.accumulate(nav) - 1).min()
    sharpe = r.mean() / r.std() * math.sqrt(252) if r.std() > 0 else 0.0
    return nav[-1] / 3e6 - 1, dd, sharpe, r.std() * math.sqrt(252)


def pf(trades):
    w = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    l = -sum(t["pnl"] for t in trades if t["pnl"] < 0)
    return w / l if l else float("inf")


VARIANTS = {
    "0 基线(现引擎)":      {},
    "A20 大盘闸QQQ>MA20":  dict(gate="ma20"),
    "A50 大盘闸QQQ>MA50":  dict(gate="ma50"),
    "B 波动定仓":          dict(volsize=True),
    "C1 排序:最不乖离":    dict(rank="ext"),
    "C2 排序:低动量":      dict(rank="lowmom"),
    "D 每日≤3新仓":        dict(maxnew=3),
    "E 行业≤3":            dict(seccap=3),
    "F 13金叉灾难止损":    dict(stop13=True),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=None)
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()

    data, sector_of = load_data(a.cache, a.refresh)
    spy, qqq = data["_SPY"], data["_QQQ"]
    cal = spy.index
    P = prep(data, cal)
    qc = qqq["Close"].reindex(cal).ffill()
    gate = {"ma20": (qc > qc.rolling(20).mean()).to_numpy(),
            "ma50": (qc > qc.rolling(50).mean()).to_numpy()}
    spx, qqx = spy["Close"].to_numpy(float), qc.to_numpy(float)
    k0 = int(np.searchsorted(cal, pd.Timestamp(BT_START)))
    kN = len(cal) - 1
    print(f"universe {len(P)} · calendar {cal[k0].date()} → {cal[kN].date()} ({kN - k0 + 1} bars)")

    def run_all(variants):
        rows_c, rows_f = [], []
        for name, cfg in variants.items():
            nav, tr, ex = simulate(P, sector_of, gate, k0, kN, cfg)
            tot, dd, sh, vol = stats(nav)
            closed = [t for t in tr if not t.get("open")]
            rows_c.append(dict(变体=name, 总收益=tot, 最大回撤=dd, Sharpe=sh, 年化波动=vol,
                               PF=pf(tr), 胜率=np.mean([t["ret"] > 0 for t in closed]),
                               笔数=len(closed), 平均仓位=ex, _nav=nav))
            for H in (21, 63):
                ex_s, ex_q, rets = [], [], []
                for s in range(k0, kN - H + 1, 5):
                    n2, _, _ = simulate(P, sector_of, gate, s, s + H, cfg)
                    r = n2[-1] / 3e6 - 1
                    rets.append(r)
                    ex_s.append(r - (spx[s + H] / spx[s] - 1))
                    ex_q.append(r - (qqx[s + H] / qqx[s] - 1))
                ex_s, ex_q = np.array(ex_s), np.array(ex_q)
                rows_f.append(dict(变体=name, 窗口=H, 次数=len(rets), 平均收益=np.mean(rets),
                                   赢SPY=np.mean(ex_s > 0), 赢QQQ=np.mean(ex_q > 0),
                                   平均超额QQQ=ex_q.mean(), 中位超额QQQ=np.median(ex_q),
                                   最差超额QQQ=ex_q.min(), 最差收益=np.min(rets)))
            print(f"  done {name}")
        return rows_c, rows_f

    rows_c, rows_f = run_all(VARIANTS)

    # combos: stack the singles that improved fresh-start 21-bar mean excess AND
    # did not hurt continuous Sharpe vs baseline
    base_c = rows_c[0]
    base_f = next(r for r in rows_f if r["变体"].startswith("0") and r["窗口"] == 21)
    keep = {}
    for name, cfg in list(VARIANTS.items())[1:]:
        rc = next(r for r in rows_c if r["变体"] == name)
        rf = next(r for r in rows_f if r["变体"] == name and r["窗口"] == 21)
        if rf["平均超额QQQ"] > base_f["平均超额QQQ"] and rc["Sharpe"] >= base_c["Sharpe"] - 0.05:
            fam = name[0]
            if fam not in keep or rf["平均超额QQQ"] > keep[fam][1]:
                keep[fam] = (name, rf["平均超额QQQ"], cfg)
    combo = {}
    for fam, (name, _, cfg) in keep.items():
        combo.update(cfg)
    allcfg = dict(gate="ma50", volsize=True, rank="ext", maxnew=3, seccap=3, stop13=True)
    extra = {"ALL 全部叠加(A50+B+C1+D+E+F)": allcfg}
    if combo:
        extra["BEST 入选项叠加(" + "+".join(sorted(keep)) + ")"] = combo
    rc2, rf2 = run_all(extra)
    rows_c += rc2
    rows_f += rf2

    # H core+satellite on baseline and on BEST
    bench_nav_q = 3e6 * qqx[k0:kN + 1] / qqx[k0]
    bench_nav_s = 3e6 * spx[k0:kN + 1] / spx[k0]
    for r in [rows_c[0], rows_c[-1]]:
        hv = 0.5 * r["_nav"] + 0.5 * bench_nav_q
        tot, dd, sh, vol = stats(hv)
        rows_c.append(dict(变体="H 50%QQQ+50%[" + r["变体"].split()[0] + "]", 总收益=tot, 最大回撤=dd,
                           Sharpe=sh, 年化波动=vol, PF=np.nan, 胜率=np.nan, 笔数=0,
                           平均仓位=np.nan, _nav=hv))
    for nm, bn in (("SPY 买入持有", bench_nav_s), ("QQQ 买入持有", bench_nav_q)):
        tot, dd, sh, vol = stats(bn)
        rows_c.append(dict(变体=nm, 总收益=tot, 最大回撤=dd, Sharpe=sh, 年化波动=vol,
                           PF=np.nan, 胜率=np.nan, 笔数=0, 平均仓位=1.0, _nav=bn))

    # ── report ──
    pct = lambda x: "—" if pd.isna(x) else f"{x * 100:+.1f}%"
    L = [f"# 打法组合 A–F 消融回测 — {TODAY}",
         f"回放 playbook_portfolio.py 的槽位/sleeve 逻辑 · {cal[k0].date()} → {cal[kN].date()} · "
         f"universe {len(P)} · 收盘成交、无成本(与纸面引擎一致)", "",
         "## 1. 连续运行(全样本)", "",
         "| 变体 | 总收益 | 最大回撤 | Sharpe | 年化波动 | PF | 胜率 | 笔数 | 平均仓位 |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in rows_c:
        L.append(f"| {r['变体']} | {pct(r['总收益'])} | {pct(r['最大回撤'])} | {r['Sharpe']:.2f} | "
                 f"{pct(r['年化波动'])} | {'—' if pd.isna(r['PF']) else f'{r['PF']:.2f}'} | "
                 f"{'—' if pd.isna(r['胜率']) else f'{r['胜率'] * 100:.0f}%'} | {r['笔数'] or '—'} | "
                 f"{'—' if pd.isna(r['平均仓位']) else f'{r['平均仓位'] * 100:.0f}%'} |")
    for H in (21, 63):
        L += ["", f"## 2. 空仓起步实验 · {H} 根K线(每 5 根起一次)", "",
              "| 变体 | 次数 | 平均收益 | 赢SPY | 赢QQQ | 平均超额QQQ | 中位超额QQQ | 最差超额QQQ | 最差收益 |",
              "|---|---|---|---|---|---|---|---|---|"]
        for r in rows_f:
            if r["窗口"] != H:
                continue
            L.append(f"| {r['变体']} | {r['次数']} | {pct(r['平均收益'])} | {r['赢SPY'] * 100:.0f}% | "
                     f"{r['赢QQQ'] * 100:.0f}% | {pct(r['平均超额QQQ'])} | {pct(r['中位超额QQQ'])} | "
                     f"{pct(r['最差超额QQQ'])} | {pct(r['最差收益'])} |")
    L += ["", "*纸面打法研究,不构成投资建议。*"]
    out = HERE / f"playbook_portfolio_ablation_{TODAY}.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    print(f"\nreport → {out.name}")


if __name__ == "__main__":
    main()
