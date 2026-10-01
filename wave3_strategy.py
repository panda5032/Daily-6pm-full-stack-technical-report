#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wave3_strategy.py — Wave-3 Launchpad screener.

Wave 3 is the strongest Elliott wave, but it can't be bought directly: by the
time a live Wave 3 is confirmable the move is over. This screen finds the
launchpad instead, by cross-referencing three existing daily reports:

  1. ELLIOTT   elliott_wave_recommendations_<date>.md
       C-wave complete / bounce setup -> action STRONG BUY or BUY
       (the count says the next move is a fresh Wave 1 -> Wave 3 sequence)
  2. WAVE-1 EVIDENCE   right_side_trading_<date>.md
       trend already re-confirmed: 右侧交易 (full right-zone) or 偏右侧 (partial)
  3. WAVE-2 EVIDENCE   chinese_principles_<date>.md + RSI
       orderly pullback holding support: 贴近MA10/MA20 / 回调到位, RSI reset 40-68

  Plus risk flags from long_term_strategy_<date>.md (fundamental AVOID names)
  and the Elliott detail blocks (Fib deviation warnings, RR sanity).

Tiers:
  TIER 1  LAUNCHPAD   Elliott GO + full right-zone + wave-2 evidence
  TIER 2  CONFIRMING  Elliott GO + partial right-zone (or full zone, no W2 proof)
  TIER 3  WATCHLIST   Elliott GO but price still left-zone (don't front-run)

Output: wave3_candidates_<date>.md in this directory (+ compact stdout summary).
Usage:  python wave3_strategy.py [--date YYYY-MM-DD]
        (reuses the newest available reports; it never re-runs the 4 underliers)
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

GO_ACTIONS = ("STRONG BUY", "BUY")


def latest(pattern: str, date: str | None) -> str | None:
    if date:
        p = os.path.join(HERE, pattern.replace("*", date))
        return p if os.path.exists(p) else None
    files = sorted(glob.glob(os.path.join(HERE, pattern)))
    return files[-1] if files else None


def read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def fnum(s: str) -> float | None:
    s = s.replace("**", "").replace(",", "").replace("$", "").strip()
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


# ---------------------------------------------------------------- Elliott ---
def parse_elliott(text: str) -> dict:
    """Sector-table rows -> {tick: {...}}; detail blocks add quality/deviations."""
    out: dict[str, dict] = {}
    for line in text.splitlines():
        if not line.startswith("| **"):
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        # sector rows: 标的 现价 时间框 波浪位置 评分 操作 入场 止损 目标1 目标2 RR 4W 13W 52W
        if len(cells) < 14 or cells[2] not in ("weekly", "daily", "n/a"):
            continue
        m = re.match(r"\*\*([A-Z0-9\.\-]+)\*\*", cells[0])
        if not m:
            continue
        tick = m.group(1)
        action = next((a for a in ("STRONG BUY", "NO_SIGNAL", "HOLD", "SELL", "BUY")
                       if a in cells[5]), "?")
        row = dict(price=fnum(cells[1]), tf=cells[2], wave=cells[3],
                   score=fnum(cells[4]), action=action, entry=fnum(cells[6]),
                   stop=fnum(cells[7]), t1=fnum(cells[8]), t2=fnum(cells[9]),
                   rr=fnum(cells[10]), quality=None, deviations=[])
        prev = out.get(tick)
        if prev is None or (row["score"] or 0) > (prev["score"] or 0):
            out[tick] = row
    cur = None
    for line in text.splitlines():
        m = re.match(r"\*\*([A-Z0-9\.\-]+)\*\* — ", line)
        if m:
            cur = m.group(1) if m.group(1) in out else None
            continue
        if not cur:
            continue
        m = re.search(r"形态质量评分[:：]\s*(\d+)/100", line)
        if m:
            out[cur]["quality"] = int(m.group(1))
        if "偏离项" in line:
            out[cur]["deviations"].append(line.split("偏离项")[-1].strip(" :：").strip())
    return out


# ------------------------------------------------------------- Right-Side ---
def parse_rightside(text: str) -> dict:
    out: dict[str, dict] = {}
    cur = None
    for line in text.splitlines():
        m = re.match(r"### \[[^\]]+\] .*\(([A-Z0-9\.\-]+)\)\s*$", line)
        if m:
            cur = m.group(1)
            out[cur] = dict(rsi=None, score=None, status="?", signals="")
            continue
        if not cur:
            continue
        if line.startswith("- 价格"):
            m = re.search(r"RSI:(\d+)", line)
            if m:
                out[cur]["rsi"] = int(m.group(1))
            m = re.search(r"得分 \*\*(-?[\d\.]+)\*\*", line)
            if m:
                out[cur]["score"] = float(m.group(1))
        elif line.startswith("- 状态"):
            m = re.search(r"\*\*(.+?)\*\*", line)
            if m:
                out[cur]["status"] = m.group(1)
        elif line.startswith("- 信号"):
            out[cur]["signals"] = line
    return out


# ---------------------------------------------------------------- Chinese ---
def parse_chinese(text: str) -> dict:
    out: dict[str, dict] = {}
    cur = None
    for line in text.splitlines():
        m = re.match(r"\*\*([A-Z0-9\.\-]+)\*\* — .*\*\*(STRONG BUY|STRONG SELL|BUY|SELL|HOLD)\*\*", line)
        if m:
            cur = m.group(1)
            out[cur] = dict(action=m.group(2), pullback_ok=False)
            continue
        if cur and line.strip().startswith("-"):
            if "贴近MA10" in line or "贴近MA20" in line or "回调到位" in line:
                out[cur]["pullback_ok"] = True
        elif not line.strip():
            cur = None
    return out


# -------------------------------------------------------------- Long-term ---
def parse_longterm(text: str) -> dict:
    out: dict[str, dict] = {}
    for line in text.splitlines():
        if not line.startswith("| **"):
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        m = re.match(r"\*\*([A-Z0-9\.\-]+)\*\*$", cells[0])
        if not m or len(cells) < 5:
            continue
        rec_cell = cells[-1]
        rec = ("AVOID" if "回避" in rec_cell else "REDUCE" if "减持" in rec_cell
               else "BUY" if "买入" in rec_cell else "ACCUM" if "增持" in rec_cell
               else "HOLD" if "持有" in rec_cell else None)
        if rec is None:
            continue
        score = None
        for c in reversed(cells[:-1]):
            mm = re.match(r"\*\*(\d+)\*\*$", c)
            if mm:
                score = int(mm.group(1))
                break
        out.setdefault(m.group(1), dict(rec=rec, score=score))
    return out


# ------------------------------------------------------------------ Screen ---
def run(date_arg: str | None) -> int:
    paths = {k: latest(p, date_arg) for k, p in dict(
        elliott="elliott_wave_recommendations_*.md",
        rightside="right_side_trading_*.md",
        chinese="chinese_principles_*.md",
        longterm="long_term_strategy_*.md",
    ).items()}
    missing = [k for k, v in paths.items() if v is None]
    if "elliott" in missing or "rightside" in missing:
        print(f"FATAL: required report(s) missing: {missing}. "
              f"Run elliott_wave_strategy.py / stock_analysis.py first.")
        return 2

    ew = parse_elliott(read(paths["elliott"]))
    rs = parse_rightside(read(paths["rightside"]))
    cn = parse_chinese(read(paths["chinese"])) if paths["chinese"] else {}
    lt = parse_longterm(read(paths["longterm"])) if paths["longterm"] else {}

    rows = []
    for tick, e in ew.items():
        if e["action"] not in GO_ACTIONS:
            continue
        r = rs.get(tick, {})
        status = r.get("status", "?")
        rsi = r.get("rsi")
        c = cn.get(tick, {})
        f = lt.get(tick, {})

        w1 = 2 if "右侧交易" in status else 1 if "偏右侧" in status else 0
        w2 = 0
        w2_why = []
        if c.get("pullback_ok"):
            w2 += 1
            w2_why.append("pullback-to-MA held (10-Rules)")
        if rsi is not None and 40 <= rsi <= 68:
            w2 += 1
            w2_why.append(f"RSI {rsi} reset")
        tier = (1 if w1 == 2 and w2 >= 1 else
                2 if w1 >= 1 else
                3)

        flags = []
        if e["deviations"]:
            flags.append("fib-dev: " + "; ".join(e["deviations"])[:90])
        if e["rr"] is not None and e["rr"] < 1:
            flags.append(f"RR {e['rr']} < 1")
        if rsi is not None and rsi > 70:
            flags.append(f"RSI {rsi} hot — buy dips only")
        if f.get("rec") in ("AVOID", "REDUCE"):
            flags.append(f"fundamental {f['rec']} (LT {f.get('score', '—')}/100)")
        if e["t1"] and e["price"] and e["t1"] > 2.5 * e["price"]:
            flags.append("T1 > 2.5x price — sanity-check target")
        if e["stop"] and e["price"] and (e["price"] - e["stop"]) / e["price"] < 0.06:
            flags.append("stop <6% away — high stop-out odds, RR overstated")

        rank = w1 + w2 + (e["quality"] or e["score"] or 0) / 100.0 \
            + (0.3 if c.get("action") in GO_ACTIONS else 0)
        rows.append(dict(tick=tick, tier=tier, rank=rank, e=e, status=status,
                         rsi=rsi, w2_why=w2_why, flags=flags,
                         cn=c.get("action", "—"), lt=f.get("rec", "—")))

    rows.sort(key=lambda x: (x["tier"], -x["rank"]))
    date = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(paths["elliott"]))
    date = date.group(1) if date else dt.date.today().isoformat()
    out_path = os.path.join(HERE, f"wave3_candidates_{date}.md")

    names = {1: "TIER 1 — LAUNCHPAD (Wave 1 done, Wave 2 held — closest to Wave 3)",
             2: "TIER 2 — CONFIRMING (Wave 1 underway, buy the trigger not the hope)",
             3: "TIER 3 — WATCHLIST (count ready, trend not turned — don't front-run)"}
    L = [f"# Wave-3 Launchpad Screen — {date}",
         "",
         "> Method: Elliott says correction complete (STRONG BUY/BUY count) x "
         "Right-Side confirms a fresh Wave-1 trend x 10-Rules/RSI show an orderly "
         "Wave-2 pullback holding. Wave 3 can't be bought directly — this is the seat "
         "before it starts. Stops are invalidation levels: hit = count wrong, exit.",
         "",
         f"Sources: {', '.join(os.path.basename(v) for v in paths.values() if v)}",
         ""]
    for t in (1, 2, 3):
        sub = [x for x in rows if x["tier"] == t]
        L += [f"## {names[t]}  ({len(sub)})", ""]
        if not sub:
            L += ["(none today)", ""]
            continue
        L += ["| Ticker | Elliott | Px | Entry | Stop | T1 | T2 | RR | RSI | Trend | W2 evidence | 10R | LT | Flags |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for x in sub:
            e = x["e"]
            g = lambda v: "—" if v is None else (f"{v:,.2f}" if isinstance(v, float) else v)
            L.append("| **{}** | {} {}/100 ({}) | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                x["tick"], e["action"], int(e["score"] or 0), e["tf"], g(e["price"]),
                g(e["entry"]), g(e["stop"]), g(e["t1"]), g(e["t2"]), g(e["rr"]),
                x["rsi"] if x["rsi"] is not None else "—", x["status"],
                "; ".join(x["w2_why"]) or "—", x["cn"], x["lt"],
                " · ".join(x["flags"]) or "—"))
        L.append("")
    L += ["---",
          "*Tier 1 = actionable on pullbacks; Tier 2 = set entry triggers; "
          "Tier 3 = alerts only. Fundamental AVOID/REDUCE flags mean technical-only "
          "trade — lottery sizing. Generated by wave3_strategy.py (no fresh data pull; "
          "re-run the 4 underlying strategy scripts first for live prices).*"]
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))

    n = {t: sum(1 for x in rows if x["tier"] == t) for t in (1, 2, 3)}
    print(f"Wave-3 screen {date}: {len(rows)} Elliott GO candidates -> "
          f"Tier1 {n[1]} / Tier2 {n[2]} / Tier3 {n[3]}")
    for x in rows:
        if x["tier"] == 1:
            print(f"  T1 {x['tick']:8s} entry {x['e']['entry']} stop {x['e']['stop']} "
                  f"T1 {x['e']['t1']} RR {x['e']['rr']}")
    print(f"Report: {out_path}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD (default: newest reports found)")
    sys.exit(run(ap.parse_args().date))
