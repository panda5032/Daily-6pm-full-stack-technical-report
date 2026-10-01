"""Daily Quant System — AI_Portfolios.xlsx 全标的每日量化分析流水线.

每天收盘后运行一次:
  1. ENSURE  — 检查当天 6 份策略报告是否存在, 缺失的补跑对应脚本
               (right_side / short_term / long_term / macd_volume / chinese_principles / elliott)
  2. PARSE   — 解析 6 份报告的全部标的信号, 归一化到 [-1, +1]
  3. SCORE   — 加权合成综合评分 → BUY / HOLD / SELL, 附大盘风险开关 (regime gate)
  4. LEDGER  — 模拟盘账本 (paper trading): 信号开平仓、止损、逐日盯市, 追踪策略真实绩效
  5. REPORT  — 输出 quant_daily_YYYY-MM-DD.md

只产生信号与模拟盘记录, 不会执行任何真实交易。

用法:
  python daily_quant_system.py                # 用当天已有报告; 缺失的补跑
  python daily_quant_system.py --no-run      # 只消费已有报告, 从不跑脚本
  python daily_quant_system.py --date 2026-07-29
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
# 报告可能落在两个互为 junction 的目录, 都试一遍
BASES = [HERE, Path(r"C:\Users\panda\OneDrive\Desktop\Claude\StockInvesting")]

INDEX_TICKERS = {"QQQ", "SPY", "DIA", "IWM", "^HSI", "000001.SS"}

# (key, 报告文件前缀, 生成脚本, 权重)
STRATEGIES = [
    ("right_side", "right_side_trading_{d}.md", "stock_analysis.py", 0.20),
    ("short_term", "short_term_report_{d}.md", "short_term_strategy.py", 0.15),
    ("long_term", "long_term_strategy_{d}.md", "long_term_strategy.py", 0.15),
    ("macd", "technical_macd_volume_{d}.md", "technical_macd_volume_strategy.py", 0.20),
    ("principles", "chinese_principles_{d}.md", "chinese_principles_strategy.py", 0.15),
    ("elliott", "elliott_wave_recommendations_{d}.md", "elliott_wave_strategy.py", 0.15),
]

BUY_TH, SELL_TH = 0.40, -0.40          # 综合评分阈值
POS_NOTIONAL = 10_000.0                # 每笔模拟仓位名义金额
MAX_POSITIONS = 12
HARD_STOP = -0.08                      # 入场价 -8% 止损 (按收盘检查)
TRAIL_STOP = -0.12                     # 峰值回撤 -12% 离场

LEDGER = HERE / "paper_ledger.csv"     # 当前持仓
TRADELOG = HERE / "paper_trades_log.csv"  # 已平仓交易


def find_report(fname: str) -> Path | None:
    for b in BASES:
        p = b / fname
        if p.exists():
            return p
    return None


def ensure_reports(d: str, allow_run: bool) -> dict[str, Path]:
    out = {}
    for key, pat, script, _w in STRATEGIES:
        p = find_report(pat.format(d=d))
        if p is None and allow_run:
            print(f"[ensure] {key}: 缺少当日报告, 运行 {script} ...")
            try:
                subprocess.run([sys.executable, str(HERE / script)], cwd=HERE,
                               timeout=1800, check=False)
            except Exception as e:
                print(f"[ensure] {script} 运行失败: {e}")
            p = find_report(pat.format(d=d))
        if p is None:
            print(f"[warn] {key}: 无当日报告, 本策略今日缺席")
        else:
            out[key] = p
    return out


# ─────────────────────── 各报告解析器 → {ticker: (norm_score, price)} ──────────


def _f(x: str) -> float | None:
    try:
        return float(x.replace(",", "").replace("$", "").replace("*", "").strip())
    except Exception:
        return None


def parse_right_side(t: str):
    out = {}
    for blk in re.split(r"\n(?=### \[)", t):
        m = re.match(r"### \[([^\]]+)\]\s+.+?\(([^)]+)\)", blk)
        if not m:
            continue
        ticker = m.group(2).strip()
        score = _f((re.search(r"得分\s+\*\*([-+]?[\d\.]+)\*\*", blk) or [None, ""])[1] or "")
        price_m = re.search(r"价格\s+\*\*\$([\d,\.]+)\*\*", blk)
        right = "右侧交易" in blk
        if score is None:
            continue
        # 得分范围约 [-10, +15]; 右侧确认加成
        norm = max(-1.0, min(1.0, score / 12.0)) * (1.0 if right else 0.8)
        out[ticker] = (norm, _f(price_m.group(1)) if price_m else None)
    return out


def parse_short_term(t: str):
    """三个分区的表格 ticker 均为 `**TICKER** (Name)` 或 `TICKER (Name)` 形式."""
    out = {}
    section = None
    for line in t.splitlines():
        h = re.match(r"^## .*?(入场机会|观察区|回避)", line)
        if h:
            section = h.group(1)
            continue
        if not section or not line.startswith("|") or "---" in line:
            continue
        m = re.search(r"\*?\*?([A-Z][A-Z0-9\.\-]{0,14})\*?\*?\s*\(", line)
        if not m:
            continue
        if section == "入场机会":
            conf = re.search(r"\*\*(HIGH|MED|LOW)\*\*", line)
            val = {"HIGH": 1.0, "MED": 0.8, "LOW": 0.5}.get(conf.group(1) if conf else "MED", 0.8)
        else:
            val = 0.0 if section == "观察区" else -0.8
        px = re.search(r"\$\s*([\d,\.]+)", line)
        out[m.group(1)] = (val, _f(px.group(1)) if px else None)
    return out


def parse_long_term(t: str):
    out = {}
    for m in re.finditer(
        r"^\|\s*\*\*([A-Z0-9\.\-]+)\*\*\s*\|\s*\$?([\d,\.]+)\s*\|.*\*\*(\d+)\*\*\s*\|", t, re.M
    ):
        ticker, price, score = m.group(1), _f(m.group(2)), float(m.group(3))
        out[ticker] = (max(-1.0, min(1.0, (score - 50.0) / 35.0)), price)
    return out


ACTION_MAP = {
    "STRONG BUY": 1.0, "BUY": 0.6, "ACCUMULATE": 0.6, "HOLD": 0.0,
    "WATCH": 0.0, "NO_SIGNAL": None, "AVOID": -0.6, "SELL": -0.6,
    "STRONG SELL": -1.0, "EXIT": -1.0,
}


def _action_score(cell: str):
    cell = re.sub(r"[^A-Z_ ]", "", cell.upper()).strip()
    for k in ("STRONG BUY", "STRONG SELL", "NO_SIGNAL", "ACCUMULATE",
              "BUY", "SELL", "HOLD", "WATCH", "AVOID", "EXIT"):
        if k in cell:
            return ACTION_MAP[k]
    return None


def parse_table_generic(t: str, ticker_col: int, price_col: int, action_col: int):
    """解析 `| a | b | ... |` 表格行; 列号以竖线切分后计 (0=首个非空列)."""
    out = {}
    for line in t.splitlines():
        if not line.startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) <= max(ticker_col, price_col, action_col):
            continue
        ticker = cells[ticker_col].replace("*", "").strip()
        if not re.fullmatch(r"[A-Z][A-Z0-9\.\-]{0,14}", ticker):
            continue
        sc = _action_score(cells[action_col])
        if sc is None:
            continue
        prev = out.get(ticker)
        if prev is None:  # 同一 ticker 取首次出现 (通常是排名表)
            out[ticker] = (sc, _f(cells[price_col]))
    return out


def parse_macd(t: str):
    # | # | Ticker | Sector | Price | 5D% | 20D% | RSI | Pattern | Volume | MACD | Total | Action | ...
    return parse_table_generic(t, 1, 3, 11) or parse_table_generic(t, 1, 3, 10)


def parse_principles(t: str):
    # | Rank | Ticker | Sector | Price | 5D% | RSI | Vol Ratio | Score | Action | ...
    return parse_table_generic(t, 1, 3, 8) or parse_table_generic(t, 1, 3, 6)


def parse_elliott(t: str):
    # | **TICKER** | price | pos | wave | score | action | entry | stop | ...
    out = {}
    for line in t.splitlines():
        m = re.match(r"^\|\s*\*\*([A-Z0-9\.\-]+)\*\*\s*\|\s*([\d,\.]+)\s*\|", line)
        if not m:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 6:
            continue
        sc = _action_score(cells[5]) if len(cells) > 5 else None
        if sc is None:
            continue
        out[m.group(1)] = (sc, _f(m.group(2)))
    return out


PARSERS = {
    "right_side": parse_right_side,
    "short_term": parse_short_term,
    "long_term": parse_long_term,
    "macd": parse_macd,
    "principles": parse_principles,
    "elliott": parse_elliott,
}


# ─────────────────────────────── 合成 + 大盘开关 ───────────────────────────────


def market_regime(reports: dict[str, Path]) -> tuple[str, float]:
    """从 long_term 大盘表读 SPX 评分: <45 risk-off, 45-55 neutral, >55 risk-on."""
    p = reports.get("long_term")
    if p:
        t = p.read_text(encoding="utf-8")
        m = re.search(r"S&P 500[^|]*\|[^\n]*\|\s*(\d+)\s*\|\s*[^|]*\|$",
                      t, re.M) or re.search(r"S&P 500.*?\|\s*(\d+)\s*\|[^|]*减?持?[^|]*\|", t)
        if m:
            s = float(m.group(1))
            if s <= 45:
                return ("RISK_OFF", 0.5)
            if s > 55:
                return ("RISK_ON", 1.0)
            return ("NEUTRAL", 0.75)
    return ("UNKNOWN", 0.75)


def composite(reports: dict[str, Path]):
    per = {}
    for key, _pat, _s, w in STRATEGIES:
        if key not in reports:
            continue
        parsed = PARSERS[key](reports[key].read_text(encoding="utf-8"))
        for tk, (sc, px) in parsed.items():
            if tk in INDEX_TICKERS:
                continue
            rec = per.setdefault(tk, {"scores": {}, "px": None})
            rec["scores"][key] = (sc, w)
            if px:
                rec["px"] = px  # 后解析的覆盖; 各报告同为当日收盘价
    rows = []
    for tk, rec in per.items():
        tot_w = sum(w for _s, w in rec["scores"].values())
        if tot_w < 0.45 or rec["px"] is None:   # 覆盖不足 3 个策略的不给信号
            continue
        comp = sum(s * w for s, w in rec["scores"].values()) / tot_w
        n_bull = sum(1 for s, _ in rec["scores"].values() if s >= 0.5)
        n_bear = sum(1 for s, _ in rec["scores"].values() if s <= -0.5)
        rows.append({"ticker": tk, "comp": round(comp, 3), "px": rec["px"],
                     "n": len(rec["scores"]), "bull": n_bull, "bear": n_bear,
                     "detail": {k: s for k, (s, _w) in rec["scores"].items()}})
    rows.sort(key=lambda r: r["comp"], reverse=True)
    return rows


REGIME_BUY_TH = {"RISK_ON": 0.40, "NEUTRAL": 0.45, "UNKNOWN": 0.45, "RISK_OFF": 0.60}


def verdict(row, regime_mult: float, regime: str = "UNKNOWN") -> str:
    c = row["comp"]
    if c >= REGIME_BUY_TH.get(regime, 0.45) and row["bull"] >= 2 and row["bear"] == 0:
        return "BUY"
    if c <= SELL_TH or row["bear"] >= 3:
        return "SELL"
    return "HOLD"


# ─────────────────────────────── 模拟盘账本 ───────────────────────────────


def load_csv(p: Path) -> list[dict]:
    if not p.exists():
        return []
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_csv(p: Path, rows: list[dict], fields: list[str]):
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


LEDGER_FIELDS = ["ticker", "entry_date", "entry_px", "shares", "peak_px", "last_px", "unreal_pnl"]
LOG_FIELDS = ["ticker", "entry_date", "entry_px", "exit_date", "exit_px", "shares", "pnl", "reason"]


def update_ledger(d: str, rows: list[dict], regime_mult: float, regime: str):
    sig = {r["ticker"]: r for r in rows}
    pos = load_csv(LEDGER)
    log = load_csv(TRADELOG)
    closed, opened = [], []

    kept = []
    for p in pos:
        tk = p["ticker"]
        r = sig.get(tk)
        px = r["px"] if r else float(p["last_px"])
        entry, peak = float(p["entry_px"]), max(float(p["peak_px"]), px)
        ret, dd = px / entry - 1, px / peak - 1
        reason = None
        if r and verdict(r, regime_mult, regime) == "SELL":
            reason = "signal_flip"
        elif ret <= HARD_STOP:
            reason = "hard_stop"
        elif dd <= TRAIL_STOP:
            reason = "trail_stop"
        if reason:
            pnl = (px - entry) * float(p["shares"])
            log.append({"ticker": tk, "entry_date": p["entry_date"], "entry_px": entry,
                        "exit_date": d, "exit_px": px, "shares": p["shares"],
                        "pnl": round(pnl, 2), "reason": reason})
            closed.append((tk, reason, round(pnl, 2)))
        else:
            p.update({"peak_px": round(peak, 4), "last_px": round(px, 4),
                      "unreal_pnl": round((px - entry) * float(p["shares"]), 2)})
            kept.append(p)

    held = {p["ticker"] for p in kept}
    for r in rows:
        if len(kept) >= MAX_POSITIONS:
            break
        if r["ticker"] in held or verdict(r, regime_mult, regime) != "BUY":
            continue
        shares = round(POS_NOTIONAL * regime_mult / r["px"], 4)
        kept.append({"ticker": r["ticker"], "entry_date": d, "entry_px": r["px"],
                     "shares": shares, "peak_px": r["px"], "last_px": r["px"], "unreal_pnl": 0.0})
        opened.append((r["ticker"], r["px"], r["comp"]))

    save_csv(LEDGER, kept, LEDGER_FIELDS)
    save_csv(TRADELOG, log, LOG_FIELDS)
    real = sum(float(x["pnl"]) for x in log)
    unreal = sum(float(x["unreal_pnl"]) for x in kept)
    return kept, opened, closed, real, unreal


# ─────────────────────────────── 报告输出 ───────────────────────────────


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--no-run", action="store_true", help="缺报告也不补跑脚本")
    a = ap.parse_args()
    d = a.date

    reports = ensure_reports(d, allow_run=not a.no_run)
    if len(reports) < 3:
        print("可用报告不足 3 份, 放弃出信号 (fail-safe)。")
        return 1

    regime, mult = market_regime(reports)
    rows = composite(reports)
    verd = {r["ticker"]: verdict(r, mult, regime) for r in rows}
    kept, opened, closed, real, unreal = update_ledger(d, rows, mult, regime)

    buys = [r for r in rows if verd[r["ticker"]] == "BUY"]
    sells = [r for r in rows if verd[r["ticker"]] == "SELL"]

    out = [f"# 每日量化系统报告 — {d}",
           f"\n生成: {datetime.now():%Y-%m-%d %H:%M} · 策略覆盖: {len(reports)}/6"
           f" ({', '.join(reports)}) · 标的: {len(rows)}",
           f"\n**大盘状态: {regime}** (仓位系数 {mult:.2f}) · "
           f"阈值 BUY≥{REGIME_BUY_TH.get(regime, 0.45)} / SELL≤{SELL_TH}",
           "\n## 🟢 BUY 信号\n",
           "| Ticker | 综合分 | 收盘价 | 多/空票 | 明细 |", "|---|---|---|---|---|"]
    for r in buys:
        det = " ".join(f"{k}:{v:+.1f}" for k, v in r["detail"].items())
        out.append(f"| **{r['ticker']}** | {r['comp']:+.2f} | ${r['px']:,.2f} "
                   f"| {r['bull']}/{r['bear']} | {det} |")
    if not buys:
        out.append("| — | | | | 今日无 BUY 信号 |")
    out += ["\n## 🔴 SELL / 回避信号\n",
            "| Ticker | 综合分 | 收盘价 | 多/空票 |", "|---|---|---|---|"]
    for r in sells[:25]:
        out.append(f"| {r['ticker']} | {r['comp']:+.2f} | ${r['px']:,.2f} | {r['bull']}/{r['bear']} |")
    out += ["\n## 📒 模拟盘账本\n",
            f"- 今日开仓: {', '.join(f'{t} @${p:,.2f} (分{c:+.2f})' for t, p, c in opened) or '无'}",
            f"- 今日平仓: {', '.join(f'{t} [{r}] PnL ${p:,.2f}' for t, r, p in closed) or '无'}",
            f"- 持仓 {len(kept)}/{MAX_POSITIONS} · 浮动盈亏 ${unreal:,.2f} · 累计已实现 ${real:,.2f}",
            "\n| 持仓 | 入场日 | 入场价 | 现价 | 浮盈 |", "|---|---|---|---|---|"]
    for p in kept:
        out.append(f"| {p['ticker']} | {p['entry_date']} | ${float(p['entry_px']):,.2f} "
                   f"| ${float(p['last_px']):,.2f} | ${float(p['unreal_pnl']):,.2f} |")
    out += ["\n## 全部标的综合排名 (Top 30)\n",
            "| # | Ticker | 综合分 | 信号 | 覆盖 |", "|---|---|---|---|---|"]
    for i, r in enumerate(rows[:30], 1):
        out.append(f"| {i} | {r['ticker']} | {r['comp']:+.2f} | {verd[r['ticker']]} | {r['n']}/6 |")
    out.append("\n> ⚠️ 仅为量化信号与模拟盘记录, 不构成投资建议; 实盘下单请自行确认。")

    dest = HERE / f"quant_daily_{d}.md"
    dest.write_text("\n".join(out), encoding="utf-8")
    print(f"\n报告已写入 {dest}")
    print(f"BUY {len(buys)} | SELL {len(sells)} | 大盘 {regime} | "
          f"持仓 {len(kept)} | 浮盈 ${unreal:,.2f} | 已实现 ${real:,.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
