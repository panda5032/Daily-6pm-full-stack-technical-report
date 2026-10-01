"""
Playbook Paper Portfolio — $3M simulated account managed by the six
best-ranked playbooks (8带行/1回踩/13金叉/2突破/14底背离/15金针, per the
2026-08-20 three-year backtest ranking). PAPER ONLY: no real orders ever.

Daily weekday run after close:
  * mark positions to market, check每个 sleeve's exit rules, sell
  * scan the AI_Portfolios universe for fresh entry signals, fill free slots
  * append trades + daily NAV to playbook_portfolio_ledger.json
  * write playbook_portfolio_report_<date>.md (positions, trades, NAV vs SPY/QQQ)

Rounds (see ROUNDS): r1 2026-08-20 → 2026-09-21 (one month), r2 2026-09-22 →
2026-12-21 (three months — the 2026-09-17 ablation showed 21-bar results are
mostly slot-fill noise; 63-bar windows beat QQQ 72% vs 61%). Each round is a
fresh $3M ledger compared with $3M buy-hold SPY and QQQ from its own start
close. r2 also keeps a shadow ledger with the 13金叉 catastrophe stop (arm F)
for an A/B read; the base arm's rules are unchanged.

Signal engine is imported from backtest_playbooks_2026.py so live rules are
byte-identical to the backtested ones. Entries execute at the signal bar's
close (same convention as the backtest).
"""

import json
import math
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

HERE = Path(__file__).parent
TODAY = datetime.now().strftime("%Y-%m-%d")
LEDGER_PATH = HERE / "playbook_portfolio_ledger.json"
START_CASH = 3_000_000.0

# one fresh $3M ledger per round; the round whose window holds the bar trades.
# arms = {label: (ledger file, cfg)} — first arm is the reported one.
ROUNDS = [
    dict(name="r1", start="2026-08-20", end="2026-09-21",
         arms={"基线": ("playbook_portfolio_ledger.json", {})}),
    dict(name="r2", start="2026-09-22", end="2026-12-21",
         arms={"基线": ("playbook_portfolio_r2_ledger.json", {}),
               "F 13金叉灾难止损": ("playbook_portfolio_r2F_ledger.json", dict(stop13=True))}),
]

from backtest_playbooks_2026 import (  # noqa: E402
    get_universe, download_all, add_indicators,
    pb1_entry, pb2_entry, pb8_entry, cd1_entry, cd6_entry)

# sleeve order = same-day priority when one ticker fires in several sleeves
SLEEVES = {
    "13金叉":   dict(slots=12, budget=600_000),
    "8带行":    dict(slots=6,  budget=750_000),
    "1回踩":    dict(slots=6,  budget=750_000),
    "2突破":    dict(slots=4,  budget=450_000),
    "14底背离": dict(slots=4,  budget=300_000),
    "15金针":   dict(slots=2,  budget=150_000),
}
SLOT_SIZE = {k: v["budget"] / v["slots"] for k, v in SLEEVES.items()}


# ────────────────────── entry adapters (i = last bar) ──────────────────────
def entry_13(df, i):
    """Fresh golden cross today."""
    if (df["ma50"].iloc[i] > df["ma200"].iloc[i]
            and df["ma50"].iloc[i - 1] <= df["ma200"].iloc[i - 1]):
        return {}
    return None


ENTRIES = {
    "13金叉":   entry_13,
    "8带行":    pb8_entry,
    "1回踩":    pb1_entry,
    "2突破":    pb2_entry,
    "14底背离": cd1_entry,
    "15金针":   cd6_entry,
}


# ────────────────────── exit rules (mirror the backtest) ──────────────────────
def bars_held(df, entry_date):
    return int((df.index > pd.Timestamp(entry_date)).sum())


def exit_13(df, i, pos):
    if df["ma50"].iloc[i] < df["ma200"].iloc[i]:
        return "死叉离场"
    return None


def exit_8(df, i, pos):
    c, ma = df["Close"].iloc[i], df["ma20"].iloc[i]
    heavy = df["Volume"].iloc[i] >= 1.2 * df["vol20"].iloc[i]
    two = df["Close"].iloc[i - 1] < df["ma20"].iloc[i - 1]
    if c < ma and (heavy or two):
        return "放量/连续收破MA20"
    return None


def exit_1(df, i, pos):
    c = df["Close"].iloc[i]
    if c < pos["stop"]:
        return "破止损"
    if c < df["ma20"].iloc[i] * 0.99:
        return "收破MA20"
    return None


def exit_2(df, i, pos):
    if df["Close"].iloc[i] < df["ma20"].iloc[i]:
        return "收破MA20"
    return None


def exit_14(df, i, pos):
    dead = (df["macd"].iloc[i] < df["macds"].iloc[i]
            and df["macd"].iloc[i - 1] >= df["macds"].iloc[i - 1])
    if dead:
        return "MACD死叉"
    if df["Close"].iloc[i] < pos["stop"]:
        return "破止损"
    if bars_held(df, pos["entry_date"]) >= 40:
        return "40日时间止损"
    return None


def exit_15(df, i, pos):
    c = df["Close"].iloc[i]
    if c < pos["stop"]:
        return "破止损"
    if c >= df["ma20"].iloc[i]:
        return "达标MA20"
    if bars_held(df, pos["entry_date"]) >= 12:
        return "12日时间止损"
    return None


EXITS = {"13金叉": exit_13, "8带行": exit_8, "1回踩": exit_1,
         "2突破": exit_2, "14底背离": exit_14, "15金针": exit_15}


# ────────────────────── ledger ──────────────────────
def load_ledger(path=None):
    path = path or LEDGER_PATH
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def save_ledger(led, path=None):
    (path or LEDGER_PATH).write_text(json.dumps(led, ensure_ascii=False, indent=1),
                                     encoding="utf-8")


def seed_13(data, led, bar_date):
    """First run only: seed the 13金叉 sleeve with the 12 freshest golden
    crosses (state age ascending) that are also above MA50."""
    cands = []
    for t, df in data.items():
        i = len(df) - 1
        if np.isnan(df["ma200"].iloc[i]) or df["ma50"].iloc[i] <= df["ma200"].iloc[i]:
            continue
        if df["Close"].iloc[i] < df["ma50"].iloc[i]:
            continue
        d = (df["ma50"] - df["ma200"]).dropna()
        age = 0
        for v in d.iloc[::-1]:
            if v > 0:
                age += 1
            else:
                break
        cands.append((age, t))
    cands.sort()
    for age, t in cands[:SLEEVES["13金叉"]["slots"]]:
        buy(led, data[t], t, "13金叉", bar_date, {},
            note=f"播种: 金叉{age}日")


def buy(led, df, tkr, sleeve, bar_date, extra, note=""):
    px = float(df["Close"].iloc[-1])
    size = SLOT_SIZE[sleeve]
    frac = px < 10 or tkr.endswith("-USD")   # crypto & penny: fractional shares
    shares = math.floor(size / px * 10000) / 10000 if frac else math.floor(size / px)
    if shares <= 0 or led["cash"] < shares * px:
        return
    cost = shares * px
    led["cash"] -= cost
    pos = dict(ticker=tkr, sleeve=sleeve, shares=shares, entry_price=px,
               entry_date=bar_date, note=note, **{k: v for k, v in extra.items()
                                                  if isinstance(v, (int, float, bool, str))})
    led["positions"].append(pos)
    led["trades"].append(dict(date=bar_date, action="BUY", ticker=tkr,
                              sleeve=sleeve, shares=shares, price=round(px, 4),
                              value=round(cost, 2), reason=note or "入场信号"))


def sell(led, df, pos, bar_date, reason):
    px = float(df["Close"].iloc[-1])
    proceeds = pos["shares"] * px
    led["cash"] += proceeds
    ret = px / pos["entry_price"] - 1
    led["trades"].append(dict(date=bar_date, action="SELL", ticker=pos["ticker"],
                              sleeve=pos["sleeve"], shares=pos["shares"],
                              price=round(px, 4), value=round(proceeds, 2),
                              ret=round(ret, 4), reason=reason))
    led["positions"].remove(pos)


def trade_bar(led, data, bar_date, first_run, stop13=False):
    """One bar of trading: exits → (seed) → entries. `data` must end at bar_date.
    stop13 = arm F: 13金叉 also exits on close < MA200 or -12% from entry."""
    held = {p["ticker"] for p in led["positions"]}
    # 1) exits first (frees slots + cash)
    for pos in list(led["positions"]):
        df = data.get(pos["ticker"])
        if df is None:
            continue
        reason = EXITS[pos["sleeve"]](df, len(df) - 1, pos)
        if not reason and stop13 and pos["sleeve"] == "13金叉":
            c = df["Close"].iloc[-1]
            if c < df["ma200"].iloc[-1] or c / pos["entry_price"] - 1 <= -0.12:
                reason = "13灾难止损"
        if reason:
            sell(led, df, pos, bar_date, reason)
            held.discard(pos["ticker"])
    # 2) seed 13金叉 sleeve on first run
    if first_run:
        seed_13(data, led, bar_date)
        held = {p["ticker"] for p in led["positions"]}
    # 3) fresh entries into free slots, sleeve priority order
    for sleeve, cfg in SLEEVES.items():
        open_n = sum(1 for p in led["positions"] if p["sleeve"] == sleeve)
        free = cfg["slots"] - open_n
        if free <= 0:
            continue
        cands = []
        for t, df in data.items():
            if t in held:
                continue
            try:
                e = ENTRIES[sleeve](df, len(df) - 1)
            except Exception:
                e = None
            if e is not None:
                mom = float(df["ret20"].iloc[-1]) if not np.isnan(df["ret20"].iloc[-1]) else 0.0
                cands.append((t, e, mom))
        # trend sleeves: strongest momentum first; 抄底 sleeves: weakest first
        rev = sleeve in ("13金叉", "8带行", "1回踩", "2突破")
        cands.sort(key=lambda x: x[2], reverse=rev)
        for t, e, _ in cands[:free]:
            buy(led, data[t], t, sleeve, bar_date, e)
            held.add(t)


def run_ledger(path, cfg, data, bar_date, bclose, rnd):
    """Trade every pending bar of round `rnd` on one ledger (catch-up replays
    missed bars one by one). Returns (led, nav, bnav), or None if the round has
    no ledger yet and no bar inside its window."""
    hi = pd.Timestamp(rnd["end"])
    led = load_ledger(path)
    first_run = led is None
    since = (pd.Timestamp(rnd["start"]) - pd.Timedelta(days=1) if first_run
             else pd.Timestamp(led["last_bar"]))
    newer = np.concatenate([df.index[df.index > since].values for df in data.values()])
    cnt = pd.Series(newer).value_counts()
    pending = sorted(str(pd.Timestamp(d).date()) for d, n in cnt.items()
                     if n >= 0.5 * len(data)
                     and pd.Timestamp(d) <= min(pd.Timestamp(bar_date), hi))
    if first_run:
        if not pending:
            return None
        pending = pending[-1:]          # a new round starts at the latest bar, no back-fill
        d0 = pd.Timestamp(pending[0])
        bpx = {b: float(bclose[b][bclose[b].index <= d0].iloc[-1]) for b in ("SPY", "QQQ")}
        led = dict(round=rnd["name"], start_date=pending[0], end_date=rnd["end"],
                   start_cash=START_CASH, cash=START_CASH,
                   positions=[], trades=[], daily_nav=[], last_bar=None,
                   bench={b: dict(start_price=bpx[b], shares=START_CASH / bpx[b])
                          for b in ("SPY", "QQQ")})
        print(f"NEW LEDGER {path.name}: $3,000,000 paper account, start {pending[0]}")

    def view_at(d):
        if d == bar_date:
            return data
        return {t: df[df.index <= pd.Timestamp(d)] for t, df in data.items()
                if (df.index <= pd.Timestamp(d)).sum() >= 220}

    if not pending:
        print(f"{path.name}: already traded this bar — refreshing report only")
        views = [(led["last_bar"], False)]
    else:
        if len(pending) > 1:
            print(f"{path.name}: catch-up, replaying {len(pending)} bars {pending[0]} → {pending[-1]}")
        views = [(d, True) for d in pending]

    for d, do_trade in views:
        view = view_at(d)
        if do_trade:
            trade_bar(led, view, d, first_run and d == pending[0], stop13=cfg.get("stop13", False))
            led["last_bar"] = d
        # ── mark to market ──
        mv = 0.0
        for p in led["positions"]:
            df = view.get(p["ticker"])
            p["last_price"] = round(float(df["Close"].iloc[-1]), 4) if df is not None else p["entry_price"]
            p["unreal"] = round(p["last_price"] / p["entry_price"] - 1, 4)
            mv += p["shares"] * p["last_price"]
        nav = led["cash"] + mv
        bnav = {b: led["bench"][b]["shares"] * float(bclose[b][bclose[b].index <= pd.Timestamp(d)].iloc[-1])
                for b in ("SPY", "QQQ")}
        led["daily_nav"] = [r for r in led["daily_nav"] if r["date"] != d]
        led["daily_nav"].append(dict(date=d, nav=round(nav, 2),
                                     spy=round(bnav["SPY"], 2), qqq=round(bnav["QQQ"], 2)))
    led["daily_nav"].sort(key=lambda r: r["date"])
    save_ledger(led, path)
    return led, nav, bnav


def main():
    tickers, _ = get_universe()
    data = download_all(tickers)
    for t in list(data):
        data[t] = add_indicators(data[t])
    # bar date = the most common latest-bar date across the universe
    dates = pd.Series([df.index[-1] for df in data.values()])
    bar_date = str(dates.mode().iloc[0].date())
    print(f"universe {len(data)} tickers · last bar {bar_date}")

    # benchmark closes (6mo so catch-up bars and round starts can be marked)
    bclose = {}
    for b in ("SPY", "QQQ"):
        d = yf.download(b, period="6mo", interval="1d", auto_adjust=True, progress=False)
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = d.columns.get_level_values(0)
        bclose[b] = d["Close"].dropna()

    # every started round gets its pending bars (an ended round only catches up
    # to its end date); the report covers the latest started round
    started = [r for r in ROUNDS if r["start"] <= bar_date]
    rnd = started[-1]
    res = {}
    for r in started:
        for label, (fname, cfg) in r["arms"].items():
            path = LEDGER_PATH if fname == LEDGER_PATH.name else HERE / fname
            out = run_ledger(path, cfg, data, bar_date, bclose, r)
            if r is rnd and out:
                res[label] = out
    if bar_date > rnd["end"]:
        print(f"round {rnd['name']} ended {rnd['end']} — ledger frozen, report shows its final state")
    led, nav, bnav = next(iter(res.values()))
    rep_date = led["last_bar"]

    # ── report ──
    ret_p = nav / START_CASH - 1
    ret_s = bnav["SPY"] / START_CASH - 1
    ret_q = bnav["QQQ"] / START_CASH - 1
    today_trades = [t for t in led["trades"] if t["date"] == rep_date]
    closed = [t for t in led["trades"] if t["action"] == "SELL"]
    md = [f"# 打法组合模拟盘 日报 — {rep_date}",
          f"第 {rnd['name'][1:]} 轮 · 起始 $3,000,000 @ {led['start_date']} · 纸面账户, 无真实下单 · "
          f"至 {rnd['end']} 与 SPY/QQQ 对比", "",
          f"| | 组合 | SPY | QQQ |", "|---|---|---|---|",
          f"| 净值 | ${nav:,.0f} | ${bnav['SPY']:,.0f} | ${bnav['QQQ']:,.0f} |",
          f"| 收益 | **{ret_p:+.2%}** | {ret_s:+.2%} | {ret_q:+.2%} |",
          f"| 超额 | — | {ret_p - ret_s:+.2%} | {ret_p - ret_q:+.2%} |", "",
          f"现金 ${led['cash']:,.0f} · 持仓 {len(led['positions'])} · "
          f"累计交易 {len(led['trades'])} 笔 (已平 {len(closed)})", ""]
    if today_trades:
        md += ["## 今日交易", "", "| 动作 | 票 | Sleeve | 股数 | 价格 | 金额 | 原因 |", "|---|---|---|---|---|---|---|"]
        for t in today_trades:
            md.append(f"| {t['action']} | {t['ticker']} | {t['sleeve']} | {t['shares']} | "
                      f"${t['price']:,.2f} | ${t['value']:,.0f} | {t.get('reason', '')} |")
        md.append("")
    if led["positions"]:
        md += ["## 当前持仓", "", "| 票 | Sleeve | 入场日 | 入场价 | 现价 | 浮盈 |", "|---|---|---|---|---|---|"]
        for p in sorted(led["positions"], key=lambda x: x["sleeve"]):
            md.append(f"| {p['ticker']} | {p['sleeve']} | {p['entry_date']} | "
                      f"${p['entry_price']:,.2f} | ${p['last_price']:,.2f} | {p['unreal']:+.2%} |")
        md.append("")
    if closed:
        w = [t for t in closed if t.get("ret", 0) > 0]
        md.append(f"已平仓 {len(closed)} 笔 · 胜率 {len(w)/len(closed):.0%} · "
                  f"平均 {np.mean([t['ret'] for t in closed]):+.2%}")
    if len(res) > 1:
        md += ["", "## A/B 影子臂", "", "| 臂 | 净值 | 收益 | 对基线 | 已平 | 今日交易 |", "|---|---|---|---|---|---|"]
        for label, (l2, n2, _) in res.items():
            tt = [f"{t['action']} {t['ticker']}" + (f"({t['reason']})" if t["action"] == "SELL" else "")
                  for t in l2["trades"] if t["date"] == rep_date]
            md.append(f"| {label} | ${n2:,.0f} | {n2 / START_CASH - 1:+.2%} | {(n2 - nav) / START_CASH:+.2%} | "
                      f"{sum(1 for t in l2['trades'] if t['action'] == 'SELL')} | {', '.join(tt) or '—'} |")
    out = HERE / f"playbook_portfolio_report_{rep_date}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    print(f"NAV ${nav:,.0f} ({ret_p:+.2%}) vs SPY {ret_s:+.2%} / QQQ {ret_q:+.2%}")
    print(f"today: {len(today_trades)} trades · report {out.name}")


if __name__ == "__main__":
    main()
