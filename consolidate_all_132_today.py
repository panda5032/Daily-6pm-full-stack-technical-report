"""Consolidate per-ticker signals from 4 trading-routine reports (dated 2026-04-27).

Outputs `all_132_consolidated_2026-04-28.md` covering ALL 132 stocks with a PM verdict.
"""

from __future__ import annotations

import io
import re
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Optional

# Force UTF-8 stdout on Windows so verification prints don't blow up on emojis.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE = Path(r"C:\Users\panda\OneDrive\Desktop\Claude\StockInvesting")
RIGHT_SIDE = BASE / "right_side_trading_2026-05-19.md"
SHORT_TERM = BASE / "short_term_report_2026-05-19.md"
LONG_TERM = BASE / "long_term_strategy_2026-05-19.md"
ELLIOTT = BASE / "elliott_wave_recommendations_2026-05-19.md"
OUTPUT = BASE / "all_132_consolidated_2026-05-19.md"

# ----- index symbols to filter out (we only want stocks/crypto in the universe) -----
INDEX_SYMBOLS = {
    "Nasdaq", "S&P 500", "Dow Jones", "Russell 2000", "Hang Seng",
    "A股上证", "Shanghai SSE", "上证综指",
}

NUM_RE = r"[-+]?\d[\d,\.]*"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ============================================================
# 1) Right Side Trading (per-ticker block format)
# ============================================================
def parse_right_side(text: str) -> dict:
    """Parse the '全部标的' section. Each block looks like:

        ### [Sector] Display Name (TICKER)
        - 价格 **$266.92** · 日 -1.53% · 5日 +0.28% · RSI:64 · 得分 **13.0**
        - 状态: **右侧交易 ✅**
        - ...
        - 入场: ✅ 适合入场 — ...
        - 止损: MA20 $262.30...
    """
    out = {}
    # Capture each ### block until next ### or EOF
    blocks = re.split(r"\n(?=### \[)", text)
    for blk in blocks:
        m = re.match(r"### \[([^\]]+)\]\s+(.+?)\s+\(([^)]+)\)", blk)
        if not m:
            continue
        sector, _name, ticker = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        rec = {"sector": sector}

        m_price = re.search(r"价格\s+\*\*\$([\d,\.]+)\*\*", blk)
        if m_price:
            rec["price"] = float(m_price.group(1).replace(",", ""))

        m_5d = re.search(r"5日\s+([-+]?[\d\.]+)%", blk)
        if m_5d:
            rec["d5"] = float(m_5d.group(1))

        m_rsi = re.search(r"RSI:(\d+)", blk)
        if m_rsi:
            rec["rsi"] = int(m_rsi.group(1))

        m_score = re.search(r"得分\s+\*\*([-+]?[\d\.]+)\*\*", blk)
        if m_score:
            rec["score"] = float(m_score.group(1))

        m_status = re.search(r"状态:\s+\*\*([^*]+)\*\*", blk)
        if m_status:
            rec["status"] = m_status.group(1).strip()

        m_entry = re.search(r"入场:\s+(.+)", blk)
        if m_entry:
            rec["entry"] = m_entry.group(1).strip()

        m_stop = re.search(r"止损:\s+MA20\s+\$?([\d,\.]+)", blk)
        if m_stop:
            rec["ma20_stop"] = float(m_stop.group(1).replace(",", ""))

        out[ticker] = rec
    return out


# ============================================================
# 2) Day Trading / Short Term
# ============================================================
def parse_short_term(text: str) -> dict:
    """Three sections:
        ## 🎯 短线入场机会  → 入场 (HIGH/MED/LOW)
        ## 👀 观察区        → WATCH
        ## 🚫 回避          → AVOID
    """
    out = {}

    # --- Entries section: split by major ## headers ---
    sections = re.split(r"\n## ", text)
    for sec in sections:
        if sec.startswith("🎯") or "短线入场机会" in sec.split("\n", 1)[0]:
            for line in sec.splitlines():
                # | **HIGH** | 📉📈 回调买入 | **SOFI** (Sofi) | Finance | $18.72 | $18.71 - $18.81 | $18.12 (-3.2%) | $20.05 (+7.1%) | $21.37 | 2.2 | 72 | -4.00% |
                m = re.match(
                    r"\|\s*\*\*(HIGH|MED|LOW)\*\*\s*\|\s*([^|]+?)\s*\|\s*\*\*([A-Z0-9\-]+)\*\*\s*\([^)]+\)\s*\|\s*([^|]+?)\s*\|\s*\$([\d,\.]+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*\$?([\d,\.]+)\s*\|\s*([\d\.]+)\s*\|",
                    line,
                )
                if m:
                    ticker = m.group(3)
                    out[ticker] = {
                        "kind": "ENTRY",
                        "tier": m.group(1),
                        "setup": m.group(2).strip(),
                        "sector": m.group(4).strip(),
                        "price": float(m.group(5).replace(",", "")),
                        "entry_zone": m.group(6).strip(),
                        "stop": m.group(7).strip(),
                        "t1": m.group(8).strip(),
                        "t2": m.group(9).replace(",", "").strip(),
                        "rr": m.group(10),
                    }
        elif sec.startswith("👀") or "观察区" in sec.split("\n", 1)[0]:
            for line in sec.splitlines():
                # | Semis | INTC (Intel) | $83.34 | +0.97% | +27.69% | +26.85% | 87 |
                m = re.match(
                    r"\|\s*([^|]+?)\s*\|\s*([A-Z0-9\-]+)\s+\([^)]+\)\s*\|\s*\$([\d,\.]+)\s*\|\s*([-+][\d\.]+)%\s*\|\s*([-+][\d\.]+)%\s*\|\s*([-+][\d\.]+)%\s*\|\s*(\d+)\s*\|",
                    line,
                )
                if m:
                    ticker = m.group(2)
                    if ticker in out:
                        continue
                    out[ticker] = {
                        "kind": "WATCH",
                        "sector": m.group(1).strip(),
                        "price": float(m.group(3).replace(",", "")),
                        "d5": float(m.group(6)),
                        "rsi": int(m.group(7)),
                    }
        elif sec.startswith("🚫") or "回避" in sec.split("\n", 1)[0]:
            for line in sec.splitlines():
                # | Space | FLY (FLY) | $33.39 | -21.97% | 46 | MACD 零轴下方; 5 日跌幅 -20.7% |
                m = re.match(
                    r"\|\s*([^|]+?)\s*\|\s*([A-Z0-9\-]+)\s+\([^)]+\)\s*\|\s*\$([\d,\.]+)\s*\|\s*([-+][\d\.]+)%\s*\|\s*(\d+)\s*\|\s*(.+?)\s*\|",
                    line,
                )
                if m:
                    ticker = m.group(2)
                    out[ticker] = {
                        "kind": "AVOID",
                        "sector": m.group(1).strip(),
                        "price": float(m.group(3).replace(",", "")),
                        "d5": float(m.group(4)),
                        "rsi": int(m.group(5)),
                        "reason": m.group(6).strip(),
                    }
    return out


# ============================================================
# 3) Long Term
# ============================================================
def parse_long_term(text: str) -> dict:
    """Sector tables of the form:

        ### Hyperscaler (超大规模云)
        ...
        | **GOOGL** | $349.06 | +120% | +26% | 56 | +18% | 2.36 | **84** | 🟢 买入 / 核心持仓 |

    Also handles crypto table which has slightly different columns; we still
    match the leading **TICKER** | $price | 12M | ...| **score** | 建议.
    """
    out = {}
    current_sector = None
    sector_re = re.compile(r"^### ([^(]+?)\s*\(")

    # Match data rows. Two formats:
    #  - 9 cells: ticker | price | 12M | vsMA200 | RSI | revGrowth | PEG | score | rec
    #  - 8 cells (crypto): ticker | price | 12M | vsMA200 | volatility | maxDD | score | rec
    row_re = re.compile(
        r"\|\s*\*\*([A-Z0-9\-\.]+)\*\*\s*\|\s*\$?([\d,\.]+)\s*\|\s*([^|]*?)\s*\|.*?\|\s*\*\*(\d+)\*\*\s*\|\s*([^|]+?)\s*\|"
    )

    in_section_two = False
    for line in text.splitlines():
        if line.startswith("## 🏢 二、各板块长线分析"):
            in_section_two = True
            continue
        if line.startswith("## 🎯 三") or line.startswith("## 💼"):
            in_section_two = False
        if not in_section_two and "## ₿ 四" in line:
            in_section_two = True  # crypto table also useful
            continue

        sm = sector_re.match(line)
        if sm:
            current_sector = sm.group(1).strip()
            continue

        if not in_section_two:
            continue

        m = row_re.match(line)
        if not m:
            continue

        ticker = m.group(1)
        if ticker in INDEX_SYMBOLS:
            continue

        try:
            price = float(m.group(2).replace(",", ""))
        except ValueError:
            price = None
        twelvem = m.group(3).strip()
        score = int(m.group(4))
        rec = m.group(5).strip()

        # Skip header markers like **指数** that slipped through (none expected)
        out[ticker] = {
            "sector_lt": current_sector,
            "lt_price": price,
            "lt_12m": twelvem,
            "lt_score": score,
            "lt_rec": rec,
        }
    return out


# ============================================================
# 4) Elliott Wave
# ============================================================
def parse_elliott(text: str) -> dict:
    """Elliott wave per-sector tables. Row schema:

        | **TICKER** | price | 时间框 | 波浪位置 | 评分 | 操作 | 入场 | 止损 | 目标 1 | 目标 2 | RR | 4W | 13W | 52W |
    """
    out = {}
    for line in text.splitlines():
        if not line.startswith("| **"):
            continue
        # split by '|'
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if len(parts) < 14:
            continue
        m = re.match(r"\*\*([A-Z0-9\-\.\&\s]+)\*\*", parts[0])
        if not m:
            continue
        ticker = m.group(1).strip()
        if ticker in INDEX_SYMBOLS:
            continue
        # Skip markdown alignment rows
        if set(parts[0]) <= set("-: *"):
            continue

        price_raw = parts[1]
        try:
            price = float(price_raw.replace(",", ""))
        except ValueError:
            price = None
        timeframe = parts[2]
        wave_pos = parts[3]
        score_raw = parts[4]
        try:
            score = int(score_raw)
        except ValueError:
            continue  # this means it's a header row
        action_raw = parts[5]
        # Normalize action
        action = "NO_SIGNAL"
        if "STRONG BUY" in action_raw:
            action = "STRONG BUY"
        elif "BUY" in action_raw:
            action = "BUY"
        elif "HOLD" in action_raw:
            action = "HOLD"
        elif "SELL" in action_raw or "TAKE PROFIT" in action_raw:
            action = "SELL"
        elif "AVOID" in action_raw:
            action = "AVOID"
        elif "NO_SIGNAL" in action_raw:
            action = "NO_SIGNAL"

        rec = {
            "ew_price": price,
            "ew_timeframe": timeframe,
            "ew_wave": wave_pos,
            "ew_score": score,
            "ew_action": action,
            "ew_entry": parts[6],
            "ew_stop": parts[7],
            "ew_t1": parts[8],
            "ew_t2": parts[9],
            "ew_rr": parts[10],
        }
        # Some tickers (e.g. GOOGL) appear in multiple sector tables; keep the
        # one with the highest score.
        if ticker in out and out[ticker]["ew_score"] >= score:
            continue
        out[ticker] = rec
    return out


# ============================================================
# Consolidation rules (PM verdict)
# ============================================================
def derive_pm_verdict(rec: dict) -> tuple[str, str]:
    """Return (verdict, rationale). Rationale is a short string."""
    rs = rec.get("rs", {})
    dt = rec.get("dt", {})
    lt = rec.get("lt", {})
    ew = rec.get("ew", {})

    rs_score = rs.get("score")
    rs_entry = rs.get("entry", "")
    dt_kind = dt.get("kind")
    dt_tier = dt.get("tier")
    lt_score = lt.get("lt_score")
    lt_rec = lt.get("lt_rec", "")
    ew_action = ew.get("ew_action")
    ew_score = ew.get("ew_score")

    # Boolean primary signals
    is_dt_high = dt_kind == "ENTRY" and dt_tier == "HIGH"
    is_dt_avoid = dt_kind == "AVOID"
    is_rs_strong = (
        rs_score is not None and rs_score >= 12 and "✅" in rs_entry
    )
    is_rs_buyable_10_12 = (
        rs_score is not None and 10 <= rs_score < 12 and "✅" in rs_entry
    )
    is_value_top = lt_score is not None and lt_score >= 75 and "🟢" in lt_rec
    is_value_mid = lt_score is not None and 65 <= lt_score < 75
    is_value_avoid = "🔴" in lt_rec
    is_ew_strong = ew_action == "STRONG BUY" and (ew_score or 0) >= 90
    is_ew_buy = ew_action == "BUY" and (ew_score or 0) >= 70
    is_ew_sell = ew_action in {"SELL", "AVOID"}

    # Count primary STRONG-BUY conditions
    primary = sum([is_dt_high, is_rs_strong, is_value_top, is_ew_strong])

    # CONFLICT detection (Value 🟢 vs EW SELL)
    conflict = is_value_top and is_ew_sell
    # also a softer conflict: value mid + EW sell
    conflict_soft = (lt_score and lt_score >= 65 and "🟢" in lt_rec) and is_ew_sell

    # AVOID
    if is_dt_avoid:
        return "AVOID", f"Day-trade AVOID: {dt.get('reason','')}"
    if is_value_avoid and not (is_dt_high or is_rs_strong or is_ew_strong):
        return "AVOID", f"Value 🔴 ({lt_score}) and no offsetting trade signal"
    if is_ew_sell and not (is_value_top or is_dt_high or is_rs_strong):
        return "AVOID", f"EW {ew_action} ({ew_score}) without offsetting signal"

    # CONFLICT
    if conflict or conflict_soft:
        return (
            "CONFLICT",
            f"Value 🟢 score {lt_score} but EW {ew_action} ({ew_score}) — "
            f"long-term thesis intact, near-term wave count negative.",
        )

    # STRONG BUY (>=2 primaries)
    if primary >= 2:
        bullets = []
        if is_dt_high:
            bullets.append("DT HIGH")
        if is_rs_strong:
            bullets.append(f"RS✅ score {rs_score}")
        if is_value_top:
            bullets.append(f"Value {lt_score} 🟢")
        if is_ew_strong:
            bullets.append(f"EW STRONG BUY {ew_score}")
        return "STRONG BUY", "Multi-signal alignment: " + " + ".join(bullets)

    # TRADE-ONLY
    if (is_ew_strong or is_dt_high) and (lt_score is not None and lt_score < 50):
        return (
            "TRADE-ONLY",
            f"Strong near-term signal but Value score {lt_score} (<50) — trade, do not invest",
        )

    # BUY (single primary OR specific looser conditions)
    if primary == 1:
        return "BUY", "One strong signal; size accordingly"
    if is_rs_buyable_10_12:
        return "BUY", f"Right-side ✅ with score {rs_score} (10-12)"
    if is_ew_buy:
        return "BUY", f"EW BUY ({ew_score})"
    if is_value_mid and "🟢" in lt_rec:
        return "BUY", f"Value 🟢 with score {lt_score} (65-74)"

    # HOLD/WATCH default
    return (
        "HOLD/WATCH",
        "Mixed/neutral signals across timeframes",
    )


# ============================================================
# Build master record
# ============================================================
def build_master() -> "OrderedDict[str, dict]":
    rs = parse_right_side(read(RIGHT_SIDE))
    dt = parse_short_term(read(SHORT_TERM))
    lt = parse_long_term(read(LONG_TERM))
    ew = parse_elliott(read(ELLIOTT))

    # Universe = union of tickers, but indexes filtered out.
    universe = set()
    for src in (rs, dt, lt, ew):
        for t in src:
            if t in INDEX_SYMBOLS:
                continue
            universe.add(t)

    master: "OrderedDict[str, dict]" = OrderedDict()
    for ticker in sorted(universe):
        rec = {
            "ticker": ticker,
            "rs": rs.get(ticker, {}),
            "dt": dt.get(ticker, {}),
            "lt": lt.get(ticker, {}),
            "ew": ew.get(ticker, {}),
        }
        # Sector preference: long-term > right-side > day-trade
        rec["sector"] = (
            rec["lt"].get("sector_lt")
            or rec["rs"].get("sector")
            or rec["dt"].get("sector")
            or "—"
        )
        rec["price"] = (
            rec["rs"].get("price")
            or rec["dt"].get("price")
            or rec["lt"].get("lt_price")
            or rec["ew"].get("ew_price")
        )
        verdict, rationale = derive_pm_verdict(rec)
        rec["verdict"] = verdict
        rec["rationale"] = rationale
        master[ticker] = rec
    return master


# ============================================================
# Output rendering
# ============================================================
VERDICT_ORDER = ["STRONG BUY", "BUY", "TRADE-ONLY", "CONFLICT", "HOLD/WATCH", "AVOID"]


def fmt_price(p) -> str:
    if p is None:
        return "—"
    if p >= 1000:
        return f"${p:,.2f}"
    if p >= 1:
        return f"${p:.2f}"
    return f"${p:.4f}"


def dt_brief(rec: dict) -> str:
    d = rec["dt"]
    if not d:
        return "—"
    if d["kind"] == "ENTRY":
        return f"{d['tier']} {d.get('setup','')}"
    if d["kind"] == "WATCH":
        return "WATCH"
    if d["kind"] == "AVOID":
        return "AVOID"
    return "—"


def rs_brief(rec: dict) -> str:
    r = rec["rs"]
    if not r:
        return "—"
    score = r.get("score")
    entry = r.get("entry", "")
    icon = "—"
    for sym in ("✅", "⏳", "🔵", "⚠️", "🚫"):
        if sym in entry:
            icon = sym
            break
    return f"{icon} {score}" if score is not None else icon


def value_brief(rec: dict) -> str:
    l = rec["lt"]
    if not l:
        return "—"
    rec_str = l.get("lt_rec", "")
    icon = "—"
    for sym in ("🟢", "🟡", "🟠", "🔴"):
        if sym in rec_str:
            icon = sym
            break
    return f"{icon} {l.get('lt_score','—')}"


def ew_brief(rec: dict) -> str:
    e = rec["ew"]
    if not e:
        return "—"
    action = e.get("ew_action", "—")
    score = e.get("ew_score", "—")
    return f"{action} ({score})"


def render(master) -> str:
    lines = []
    lines.append("# 全部 132 只标的 整合 PM 视角 (2026-05-19)")
    lines.append("")
    lines.append(
        f"基于 4 份策略报告 (2026-05-19): Right-Side Trading · Day Trading · "
        f"Long-Term Value · Elliott Wave."
    )
    lines.append("")
    lines.append(f"**总数**: {len(master)} 只")
    lines.append("")

    # Verdict counts
    counts = {v: 0 for v in VERDICT_ORDER}
    for rec in master.values():
        counts[rec["verdict"]] = counts.get(rec["verdict"], 0) + 1
    lines.append("## 📊 PM 判定汇总")
    lines.append("")
    lines.append("| 判定 | 数量 |")
    lines.append("|------|------|")
    for v in VERDICT_ORDER:
        lines.append(f"| **{v}** | {counts.get(v, 0)} |")
    lines.append("")

    # Master table
    lines.append("## 📋 主表 (全部标的)")
    lines.append("")
    lines.append("| Ticker | Sector | Price | DT | RS | Value | EW | PM Verdict |")
    lines.append("|--------|--------|-------|----|----|-------|----|------------|")
    # Sort by verdict, then ticker
    verdict_index = {v: i for i, v in enumerate(VERDICT_ORDER)}
    sorted_recs = sorted(
        master.values(), key=lambda r: (verdict_index.get(r["verdict"], 99), r["ticker"])
    )
    for rec in sorted_recs:
        lines.append(
            "| **{tkr}** | {sec} | {pr} | {dt} | {rs} | {vl} | {ew} | **{pm}** |".format(
                tkr=rec["ticker"],
                sec=rec["sector"],
                pr=fmt_price(rec["price"]),
                dt=dt_brief(rec),
                rs=rs_brief(rec),
                vl=value_brief(rec),
                ew=ew_brief(rec),
                pm=rec["verdict"],
            )
        )
    lines.append("")

    # Sectioned blocks
    for verdict in VERDICT_ORDER:
        bucket = [r for r in master.values() if r["verdict"] == verdict]
        if not bucket:
            continue
        bucket.sort(key=lambda r: r["ticker"])
        lines.append(f"## {verdict} ({len(bucket)})")
        lines.append("")
        lines.append(
            "| Ticker | Sector | Price | DT | RS | Value | EW | Entry / Stop / Targets | Rationale |"
        )
        lines.append(
            "|--------|--------|-------|----|----|-------|----|------------------------|-----------|"
        )
        for rec in bucket:
            entry_block = build_entry_block(rec)
            rationale = rec["rationale"]
            lines.append(
                "| **{t}** | {s} | {p} | {dt} | {rs} | {v} | {ew} | {eb} | {rt} |".format(
                    t=rec["ticker"],
                    s=rec["sector"],
                    p=fmt_price(rec["price"]),
                    dt=dt_brief(rec),
                    rs=rs_brief(rec),
                    v=value_brief(rec),
                    ew=ew_brief(rec),
                    eb=entry_block,
                    rt=rationale,
                )
            )
        lines.append("")

        # Per-ticker rationale paragraphs for STRONG BUY and CONFLICT
        if verdict in {"STRONG BUY", "CONFLICT"}:
            lines.append(f"### {verdict} — 逐票逻辑")
            lines.append("")
            for rec in bucket:
                lines.append(f"- **{rec['ticker']}** — {build_long_rationale(rec)}")
            lines.append("")

    return "\n".join(lines) + "\n"


def build_entry_block(rec: dict) -> str:
    """Build a compact entry/stop/target string from the most actionable source."""
    dt = rec["dt"]
    if dt and dt.get("kind") == "ENTRY":
        return (
            f"DT entry {dt.get('entry_zone','—')} · stop {dt.get('stop','—')} · "
            f"T1 {dt.get('t1','—')} · T2 {dt.get('t2','—')} · RR {dt.get('rr','—')}"
        )
    ew = rec["ew"]
    if ew and ew.get("ew_action") in {"STRONG BUY", "BUY"}:
        return (
            f"EW entry {ew.get('ew_entry','—')} · stop {ew.get('ew_stop','—')} · "
            f"T1 {ew.get('ew_t1','—')} · T2 {ew.get('ew_t2','—')} · RR {ew.get('ew_rr','—')}"
        )
    rs = rec["rs"]
    if rs and rs.get("ma20_stop"):
        return f"RS stop MA20 ${rs['ma20_stop']:.2f}"
    return "—"


def build_long_rationale(rec: dict) -> str:
    """1-2 sentence rationale combining all 4 lenses for STRONG BUY/CONFLICT."""
    ticker = rec["ticker"]
    pieces = []
    rs = rec["rs"]
    if rs:
        pieces.append(f"RS 得分 {rs.get('score','—')} 状态 {rs.get('status','—')} 入场 {rs.get('entry','—')}")
    dt = rec["dt"]
    if dt and dt.get("kind") == "ENTRY":
        pieces.append(f"DT {dt.get('tier')} {dt.get('setup','')} entry {dt.get('entry_zone','')}")
    elif dt:
        pieces.append(f"DT {dt.get('kind')}")
    lt = rec["lt"]
    if lt:
        pieces.append(f"Value {lt.get('lt_score','—')} {lt.get('lt_rec','—')} (12M {lt.get('lt_12m','—')})")
    ew = rec["ew"]
    if ew:
        pieces.append(
            f"EW {ew.get('ew_action','—')} {ew.get('ew_score','—')} ({ew.get('ew_wave','—')})"
        )
    base = f"{ticker}: " + " | ".join(pieces) + "."
    base += f" 判定理由: {rec['rationale']}"
    return base


# ============================================================
# Verification helpers
# ============================================================
def verify(master) -> None:
    print(f"Total tickers consolidated: {len(master)}")
    missing = [t for t, r in master.items() if not r["verdict"]]
    print(f"Empty PM verdicts: {len(missing)}")
    if missing:
        print("First missing:", missing[:5])

    # Print first 3 (alphabetical)
    print("\n--- First 3 rows (alphabetical) ---")
    for ticker in list(master.keys())[:3]:
        r = master[ticker]
        print(
            f"{ticker} | sector={r['sector']} | price={r['price']} | "
            f"DT={dt_brief(r)} | RS={rs_brief(r)} | Value={value_brief(r)} | "
            f"EW={ew_brief(r)} | PM={r['verdict']}"
        )

    # Coverage breakdown
    rs_cov = sum(1 for r in master.values() if r["rs"])
    dt_cov = sum(1 for r in master.values() if r["dt"])
    lt_cov = sum(1 for r in master.values() if r["lt"])
    ew_cov = sum(1 for r in master.values() if r["ew"])
    print(
        f"\nCoverage: RS={rs_cov}, DT={dt_cov}, LT={lt_cov}, EW={ew_cov}"
    )

    conflicts = [t for t, r in master.items() if r["verdict"] == "CONFLICT"]
    print(f"\nCONFLICT tickers ({len(conflicts)}): {conflicts}")


def main():
    master = build_master()
    text = render(master)
    OUTPUT.write_text(text, encoding="utf-8")
    print(f"Wrote: {OUTPUT}")
    verify(master)


if __name__ == "__main__":
    main()
