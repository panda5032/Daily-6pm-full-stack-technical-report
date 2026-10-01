# -*- coding: utf-8 -*-
"""
三个新 $3M 纸面模拟盘 (2026-09-20 用户要求; 纯记账, 永不真实下单)

  A 打法3 纯轮动     池内 MA50 上方按 20 日动量取前 10, 等权, 每 20 根 bar 整体再平衡;
                     调仓之间不设止损 (= backtest_playbooks_2026.rotation_backtest 原样).
  B 核心七打法       3(选股闸) + 16/2/8(趋势袖) + 13(金叉袖) + 15/14(抄底袖).
                     打法3 作闸门: 趋势袖只接"MA50 上方且 20 日动量排名前 ROT_N"的票.
                     一票全组合只持一仓; 同日优先级 16 > 2 > 8 > 13 > 15 > 14.
  C 长线打法13       长线池 = 金叉在位(MA50>MA200) 且 LT>=75 (long_term_strategy_<date>.json).
                     25 槽 × $120k; 首日把池内全部买入, 之后新合格者有空槽即买.
                     卖出只认保险丝: 死叉 / LT<50 (论点破的机械代理). 极端估值无数据, 未实现.

约定与 playbook_portfolio.py 一致: 信号 bar 收盘价成交、无成本滑点、漏跑自动逐 bar 补跑、
基准 = 同一起始收盘买入持有 SPY/QQQ. 信号函数直接 import 回测模块 (实盘=回测).
文件: paper_new3_{A_rot3,B_core7,C_lt13}_ledger.json · paper_new3_report_<bar>.md
"""
import json, math, re, warnings
from datetime import datetime
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
warnings.filterwarnings("ignore")
from backtest_playbooks_2026 import (get_universe, download_all, add_indicators,
                                     pb2_entry, pb8_entry, cd1_entry, cd6_entry)
from backtest_pb16_2026 import add_pb16_indicators
from backtest_pb16_gate_2026 import i_entry as pb16_entry
from playbook_portfolio import exit_13, exit_8, exit_2, exit_14, exit_15, entry_13

HERE = Path(__file__).parent
START_CASH = 3_000_000.0
ROT_TOP, ROT_EVERY = 10, 20          # A: holdings / rebalance interval (bars)
ROT_N = 40                           # B: 打法3 gate — momentum rank cutoff for trend sleeves
LT_BUY, LT_FUSE, C_SLOTS = 75, 50, 25

B_SLEEVES = {                        # order = same-day priority
    "16纯图":   dict(slots=6, budget=750_000, trend=True),
    "2突破":    dict(slots=4, budget=450_000, trend=True),
    "8带行":    dict(slots=6, budget=750_000, trend=True),
    "13金叉":   dict(slots=9, budget=450_000, trend=False),
    "15金针":   dict(slots=4, budget=300_000, trend=False),
    "14底背离": dict(slots=4, budget=300_000, trend=False),
}


def exit_16(df, i, pos):
    c = df["Close"].iloc[i]
    if c < pos.get("stop", -1):
        return "破形态止损"
    if c < df["ma20"].iloc[i]:
        return "收破MA20"
    return None


B_ENTRIES = {"16纯图": pb16_entry, "2突破": pb2_entry, "8带行": pb8_entry,
             "13金叉": entry_13, "15金针": cd6_entry, "14底背离": cd1_entry}
B_EXITS = {"16纯图": exit_16, "2突破": exit_2, "8带行": exit_8,
           "13金叉": exit_13, "15金针": exit_15, "14底背离": exit_14}


# ────────────────────────── bookkeeping ──────────────────────────
def _shares(size, px, tkr):
    frac = px < 10 or tkr.endswith("-USD")
    return math.floor(size / px * 10000) / 10000 if frac else math.floor(size / px)


def buy(led, df, tkr, sleeve, bar, size, extra=None, note=""):
    px = float(df["Close"].iloc[-1])
    sh = _shares(min(size, led["cash"]), px, tkr)
    if sh <= 0:
        return
    led["cash"] -= sh * px
    pos = dict(ticker=tkr, sleeve=sleeve, shares=sh, entry_price=px, entry_date=bar, note=note,
               **{k: v for k, v in (extra or {}).items() if isinstance(v, (int, float, bool, str))})
    led["positions"].append(pos)
    led["trades"].append(dict(date=bar, action="BUY", ticker=tkr, sleeve=sleeve, shares=sh,
                              price=round(px, 4), value=round(sh * px, 2), reason=note or "入场信号"))


def sell(led, df, pos, bar, reason, shares=None):
    px = float(df["Close"].iloc[-1])
    sh = pos["shares"] if shares is None else shares
    led["cash"] += sh * px
    led["trades"].append(dict(date=bar, action="SELL", ticker=pos["ticker"], sleeve=pos["sleeve"], shares=sh,
                              price=round(px, 4), value=round(sh * px, 2),
                              ret=round(px / pos["entry_price"] - 1, 4), reason=reason))
    if shares is None or sh >= pos["shares"]:
        led["positions"].remove(pos)
    else:
        pos["shares"] = round(pos["shares"] - sh, 4)


def nav_of(led, data):
    mv = 0.0
    for p in led["positions"]:
        df = data.get(p["ticker"])
        p["last_price"] = round(float(df["Close"].iloc[-1]), 4) if df is not None else p.get("last_price", p["entry_price"])
        p["unreal"] = round(p["last_price"] / p["entry_price"] - 1, 4)
        mv += p["shares"] * p["last_price"]
    return led["cash"] + mv


def momentum_rank(data):
    """打法3 eligibility: above MA50, ranked by 20d return (strongest first)."""
    el = []
    for t, df in data.items():
        c, m50, r = df["Close"].iloc[-1], df["ma50"].iloc[-1], df["ret20"].iloc[-1]
        if not (np.isnan(m50) or np.isnan(r)) and c > m50:
            el.append((float(r), t))
    el.sort(reverse=True)
    return [t for _, t in el]


def lt_scores(bar):
    files = sorted(HERE.glob("long_term_strategy_*.json"))
    ok = [f for f in files if re.search(r"(\d{4}-\d{2}-\d{2})", f.name).group(1) <= bar] or files
    if not ok:
        return {}, None
    d = json.loads(ok[-1].read_text(encoding="utf-8"))
    return {t: v.get("score") for t, v in d.items() if isinstance(v, dict)}, ok[-1].name


# ────────────────────────── strategies (one bar each) ──────────────────────────
def trade_A(led, data, bar, first):
    led["bars"] = led.get("bars", 0) + 1
    if not first and (led["bars"] - 1) % ROT_EVERY != 0:
        return
    top = momentum_rank(data)[:ROT_TOP]
    nav = nav_of(led, data)
    target = nav / max(len(top), 1)
    for pos in list(led["positions"]):                      # drop names that fell out
        if pos["ticker"] not in top and pos["ticker"] in data:
            sell(led, data[pos["ticker"]], pos, bar, "轮动调出")
    for pos in list(led["positions"]):                      # trim stayers above target
        if pos["ticker"] in data:
            px = float(data[pos["ticker"]]["Close"].iloc[-1])
            over = pos["shares"] * px - target
            if over > 0.02 * target:
                sell(led, data[pos["ticker"]], pos, bar, "再平衡减持", shares=_shares(over, px, pos["ticker"]))
    held = {p["ticker"]: p for p in led["positions"]}
    for rk, t in enumerate(top, 1):
        px = float(data[t]["Close"].iloc[-1])
        have = held[t]["shares"] * px if t in held else 0.0
        if target - have > 0.02 * target:
            if t in held:                                   # top up a stayer → merge into the lot
                sh = _shares(min(target - have, led["cash"]), px, t)
                if sh > 0:
                    p = held[t]
                    p["entry_price"] = (p["entry_price"] * p["shares"] + px * sh) / (p["shares"] + sh)
                    p["shares"] = round(p["shares"] + sh, 4)
                    led["cash"] -= sh * px
                    led["trades"].append(dict(date=bar, action="BUY", ticker=t, sleeve="3轮动", shares=sh,
                                              price=round(px, 4), value=round(sh * px, 2), reason="再平衡增持"))
            else:
                buy(led, data[t], t, "3轮动", bar, target, note=f"动量第{rk}名 (20日 {data[t]['ret20'].iloc[-1]:+.1%})")
    led["next_rebalance_in"] = ROT_EVERY


def trade_B(led, data, bar, first):
    held = {p["ticker"] for p in led["positions"]}
    for pos in list(led["positions"]):
        df = data.get(pos["ticker"])
        if df is None:
            continue
        reason = B_EXITS[pos["sleeve"]](df, len(df) - 1, pos)
        if reason:
            sell(led, df, pos, bar, reason)
            held.discard(pos["ticker"])
    rot = momentum_rank(data)
    rot_set, rot_pos = set(rot[:ROT_N]), {t: k for k, t in enumerate(rot)}
    led["rot_list"] = rot[:ROT_N]
    for sleeve, cfg in B_SLEEVES.items():
        free = cfg["slots"] - sum(1 for p in led["positions"] if p["sleeve"] == sleeve)
        if free <= 0:
            continue
        size = cfg["budget"] / cfg["slots"]
        cands = []
        if sleeve == "13金叉" and first:                     # seed with the freshest golden crosses above MA50
            for t, df in data.items():
                if t in held or np.isnan(df["ma200"].iloc[-1]) or df["ma50"].iloc[-1] <= df["ma200"].iloc[-1] \
                        or df["Close"].iloc[-1] < df["ma50"].iloc[-1]:
                    continue
                d = (df["ma50"] - df["ma200"]).dropna().values[::-1]
                age = int(np.argmax(d <= 0)) if (d <= 0).any() else len(d)
                cands.append((age, t, {}, f"播种: 金叉{age}日"))
            cands.sort()
        else:
            for t, df in data.items():
                if t in held or (cfg["trend"] and t not in rot_set):
                    continue
                try:
                    e = B_ENTRIES[sleeve](df, len(df) - 1)
                except Exception:
                    e = None
                if e is not None:
                    mom = float(df["ret20"].iloc[-1]) if not np.isnan(df["ret20"].iloc[-1]) else 0.0
                    key = -mom if sleeve in ("16纯图", "2突破", "8带行", "13金叉") else mom
                    note = f"打法3名单第{rot_pos[t] + 1}名" if cfg["trend"] else ""
                    cands.append((key, t, e, note))
            cands.sort(key=lambda x: x[0])
        for _, t, e, note in cands[:free]:
            buy(led, data[t], t, sleeve, bar, size, e, note)
            held.add(t)


def trade_C(led, data, bar, first):
    lt, src = lt_scores(bar)
    led["lt_source"] = src
    for pos in list(led["positions"]):
        df = data.get(pos["ticker"])
        if df is None:
            continue
        s = lt.get(pos["ticker"])
        if df["ma50"].iloc[-1] < df["ma200"].iloc[-1]:
            sell(led, df, pos, bar, "保险丝1: 死叉")
        elif s is not None and s < LT_FUSE:
            sell(led, df, pos, bar, f"保险丝2: LT {s}<{LT_FUSE} 论点破代理")
    held = {p["ticker"] for p in led["positions"]}
    cands = []
    for t, df in data.items():
        s = lt.get(t)
        if t in held or s is None or s < LT_BUY or np.isnan(df["ma200"].iloc[-1]):
            continue
        if df["ma50"].iloc[-1] > df["ma200"].iloc[-1]:
            d = (df["ma50"] - df["ma200"]).dropna().values[::-1]
            age = int(np.argmax(d <= 0)) if (d <= 0).any() else len(d)
            cands.append((-s, age, t))
    cands.sort()
    for ns, age, t in cands[:C_SLOTS - len(led["positions"])]:
        buy(led, data[t], t, "13长线", bar, START_CASH / C_SLOTS, note=f"LT {-ns} · 金叉{age}日")


BOOKS = {"A 打法3 纯轮动": ("paper_new3_A_rot3_ledger.json", trade_A),
         "B 核心七打法 3+16/2/8+13+15/14": ("paper_new3_B_core7_ledger.json", trade_B),
         "C 长线 打法13 (LT≥75)": ("paper_new3_C_lt13_ledger.json", trade_C)}


def run_book(path, fn, data, bar_date, bclose):
    led = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    first = led is None
    since = pd.Timestamp(bar_date) - pd.Timedelta(days=1) if first else pd.Timestamp(led["last_bar"])
    newer = np.concatenate([df.index[df.index > since].values for df in data.values()])
    cnt = pd.Series(newer).value_counts()
    pending = sorted(str(pd.Timestamp(d).date()) for d, n in cnt.items()
                     if n >= 0.5 * len(data) and pd.Timestamp(d) <= pd.Timestamp(bar_date))
    if first:
        pending = pending[-1:] or [bar_date]
        d0 = pd.Timestamp(pending[0])
        led = dict(start_date=pending[0], start_cash=START_CASH, cash=START_CASH, positions=[], trades=[],
                   daily_nav=[], last_bar=None,
                   bench={b: dict(start_price=float(bclose[b][bclose[b].index <= d0].iloc[-1]),
                                  shares=START_CASH / float(bclose[b][bclose[b].index <= d0].iloc[-1])) for b in ("SPY", "QQQ")})
        print(f"NEW LEDGER {path.name}: $3,000,000 paper, start {pending[0]}")
    for d in (pending or [led["last_bar"]]):
        view = data if d == bar_date else {t: df[df.index <= pd.Timestamp(d)] for t, df in data.items()
                                           if (df.index <= pd.Timestamp(d)).sum() >= 220}
        if pending:
            fn(led, view, d, first and d == pending[0])
            led["last_bar"] = d
        nav = nav_of(led, view)
        bn = {b: led["bench"][b]["shares"] * float(bclose[b][bclose[b].index <= pd.Timestamp(d)].iloc[-1]) for b in ("SPY", "QQQ")}
        led["daily_nav"] = [r for r in led["daily_nav"] if r["date"] != d] + \
                           [dict(date=d, nav=round(nav, 2), spy=round(bn["SPY"], 2), qqq=round(bn["QQQ"], 2))]
    led["daily_nav"].sort(key=lambda r: r["date"])
    path.write_text(json.dumps(led, ensure_ascii=False, indent=1), encoding="utf-8")
    return led, nav, bn


def main():
    tickers, _ = get_universe()
    data = download_all(tickers)
    for t in list(data):
        data[t] = add_pb16_indicators(add_indicators(data[t]))
    bar_date = str(pd.Series([df.index[-1] for df in data.values()]).mode().iloc[0].date())
    print(f"universe {len(data)} tickers · last bar {bar_date}")
    bclose = {}
    for b in ("SPY", "QQQ"):
        d = yf.download(b, period="2y", interval="1d", auto_adjust=True, progress=False)
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = d.columns.get_level_values(0)
        bclose[b] = d["Close"].dropna()

    res = {name: run_book(HERE / f, fn, data, bar_date, bclose) for name, (f, fn) in BOOKS.items()}
    rep = next(iter(res.values()))[0]["last_bar"]
    md = [f"# 三个新模拟盘 日报 — {rep}", "各 $3,000,000 纸面账户 · 信号bar收盘成交 · 无成本 · 永不真实下单", "",
          "| 模拟盘 | 起始日 | 净值 | 收益 | vs SPY | vs QQQ | 现金 | 持仓 | 已平(胜率) |", "|---|---|---|---|---|---|---|---|---|"]
    for name, (led, nav, bn) in res.items():
        closed = [t for t in led["trades"] if t["action"] == "SELL" and "再平衡" not in t["reason"]]
        wr = f"{len(closed)} ({np.mean([t['ret'] > 0 for t in closed]):.0%})" if closed else "0"
        r = nav / START_CASH - 1
        md.append(f"| {name} | {led['start_date']} | ${nav:,.0f} | **{r:+.2%}** | {r - (bn['SPY'] / START_CASH - 1):+.2%} | "
                  f"{r - (bn['QQQ'] / START_CASH - 1):+.2%} | ${led['cash']:,.0f} | {len(led['positions'])} | {wr} |")
    bn = next(iter(res.values()))[2]
    md += ["", f"基准(自各盘起始收盘): SPY {bn['SPY'] / START_CASH - 1:+.2%} · QQQ {bn['QQQ'] / START_CASH - 1:+.2%}", ""]
    for name, (led, nav, _) in res.items():
        md += [f"## {name}", ""]
        if name.startswith("A"):
            left = ROT_EVERY - ((led.get("bars", 1) - 1) % ROT_EVERY)
            md += [f"下次整体再平衡: {left} 根 bar 后 (每 {ROT_EVERY} 根)", ""]
        if name.startswith("B"):
            md += [f"今日打法3名单(前{ROT_N}): {', '.join(led.get('rot_list', [])[:ROT_N])}", ""]
        if name.startswith("C"):
            md += [f"LT 评分来源: {led.get('lt_source')}", ""]
        tt = [t for t in led["trades"] if t["date"] == led["last_bar"]]
        if tt:
            md += ["**今日交易**", "", "| 动作 | 票 | 袖 | 股数 | 价格 | 金额 | 原因 |", "|---|---|---|---|---|---|---|"]
            md += [f"| {t['action']} | {t['ticker']} | {t['sleeve']} | {t['shares']} | ${t['price']:,.2f} | ${t['value']:,.0f} | {t.get('reason', '')} |" for t in tt]
            md.append("")
        if led["positions"]:
            md += ["**持仓**", "", "| 票 | 袖 | 入场日 | 入场价 | 现价 | 浮盈 | 市值 |", "|---|---|---|---|---|---|---|"]
            md += [f"| {p['ticker']} | {p['sleeve']} | {p['entry_date']} | ${p['entry_price']:,.2f} | ${p['last_price']:,.2f} | "
                   f"{p['unreal']:+.2%} | ${p['shares'] * p['last_price']:,.0f} |" for p in sorted(led["positions"], key=lambda x: (x["sleeve"], x["ticker"]))]
            md.append("")
    out = HERE / f"paper_new3_report_{rep}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md[:9]))
    print(f"report → {out.name}")


if __name__ == "__main__":
    main()
