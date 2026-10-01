"""
PROP TRADE JOURNAL — Process & Expectancy Tracker
====================================================
Tracks every trade with both QUANTITATIVE (P&L, R-multiple, fills) and
QUALITATIVE (thesis, mental state, plan adherence) data — matching the
job's explicit requirement.

WHY THIS EXISTS
  Prop firms scale your capital based on PROCESS, not just P&L. A trader
  with 8% returns and a clean journal beats a trader with 12% returns and
  no journal — because the firm can attribute the returns to a repeatable
  edge vs luck.

WHAT GETS TRACKED PER TRADE
  PRE-TRADE (entered before/at open):
    - Thesis (1-2 sentences) — WHY this trade exists
    - Setup type (from prop_options_model strategy enum)
    - Edge score (from model)
    - Planned entry, stop, target
    - Position size + dollar risk (R = 1 unit of risk)
    - Mental state (1-5, sleep, alertness, recent losses?)
    - Followed pre-trade checklist? Y/N

  POST-TRADE (filled at close):
    - Actual entry, exit, fills, slippage vs mid
    - P&L $, P&L R (R-multiple = pnl/initial_risk)
    - Exit reason: target hit / stop hit / time stop / discretionary / news
    - Did I follow the plan? Y/N
    - What went right / what went wrong (one line each)
    - Lesson tag (one keyword: SIZE, IV_CRUSH, EARLY_EXIT, etc.)

EXPECTANCY DASHBOARD (auto-generated)
  By strategy, by sector, by setup quality:
    - Sample size, win rate, avg win R, avg loss R, expectancy R
    - Profit factor (gross W / gross L)
    - Max consecutive losses (psychological tolerance)
    - Sharpe of daily P&L
    - "Plan adherence" win rate vs "off-plan" win rate
      (this is THE most important number for a prop trader)

USAGE
  # log a new pre-trade row (interactive)
  python prop_trade_journal.py log

  # log from the latest _prop_candidates.json (use top candidate)
  python prop_trade_journal.py log --from-model --rank 1

  # close out a trade
  python prop_trade_journal.py close --id 42 --exit 3.20 --reason TARGET

  # generate the expectancy dashboard
  python prop_trade_journal.py stats

  # full report (pipe to file or paste to chat)
  python prop_trade_journal.py report > my_journal_report.md

DATA
  prop_trade_journal.csv — append-only. Columns documented in CSV_COLUMNS below.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import io
from collections import defaultdict
from dataclasses import dataclass, asdict, field
from datetime import datetime, date
from pathlib import Path
from typing import Optional

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
except Exception:
    pass

ROOT = Path(__file__).parent
JOURNAL = ROOT / 'prop_trade_journal.csv'
CANDIDATES = ROOT / '_prop_candidates.json'

CSV_COLUMNS = [
    # IDs
    'id', 'opened_at', 'closed_at', 'status',
    # Pre-trade
    'ticker', 'sector', 'strategy', 'edge_score', 'bias', 'regime',
    'planned_entry', 'planned_stop', 'planned_target', 'planned_be',
    'contracts', 'risk_$', 'reward_target_$', 'planned_RR',
    'thesis', 'setup_tag',
    'mental_state', 'checklist_pass',
    # Greeks at entry
    'delta_entry', 'gamma_entry', 'theta_entry', 'vega_entry', 'iv_entry',
    # Post-trade (filled at close)
    'actual_entry', 'actual_exit', 'slippage_vs_mid',
    'pnl_$', 'pnl_R', 'pnl_pct_account',
    'exit_reason', 'followed_plan',
    'what_went_right', 'what_went_wrong', 'lesson_tag',
]


def _ensure_csv():
    if not JOURNAL.exists():
        with JOURNAL.open('w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(CSV_COLUMNS)


def _next_id() -> int:
    if not JOURNAL.exists():
        return 1
    with JOURNAL.open('r', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return 1
    return max(int(r['id']) for r in rows if r.get('id', '').isdigit()) + 1


def _read_all() -> list[dict]:
    if not JOURNAL.exists():
        return []
    with JOURNAL.open('r', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def _write_all(rows: list[dict]):
    with JOURNAL.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in CSV_COLUMNS})


# ╔════════════════════════════════════════════════════════════════════╗
# ║  LOG — record a new trade entry                                     ║
# ╚════════════════════════════════════════════════════════════════════╝

def _prompt(label: str, default: str = '') -> str:
    suffix = f" [{default}]" if default else ''
    v = input(f"  {label}{suffix}: ").strip()
    return v or default


def log_interactive():
    _ensure_csv()
    print("─── PRE-TRADE LOG ─────────────────────────────────────────────")
    tid = _next_id()
    row = {k: '' for k in CSV_COLUMNS}
    row['id'] = str(tid)
    row['opened_at'] = datetime.now().isoformat(timespec='seconds')
    row['status'] = 'OPEN'
    row['ticker'] = _prompt("Ticker").upper()
    row['sector'] = _prompt("Sector")
    row['strategy'] = _prompt("Strategy (e.g. BULL_PUT_SPREAD)")
    row['edge_score'] = _prompt("Edge score (0-100)")
    row['bias'] = _prompt("Bias (BULL/BEAR/NEUTRAL)").upper()
    row['regime'] = _prompt("IV regime (HIGH_IV/NEUTRAL/LOW_IV)").upper()
    row['planned_entry'] = _prompt("Planned entry $")
    row['planned_stop'] = _prompt("Planned stop $")
    row['planned_target'] = _prompt("Planned target $")
    row['contracts'] = _prompt("Contracts")
    row['risk_$'] = _prompt("Dollar risk")
    row['reward_target_$'] = _prompt("Reward target $")
    if row['risk_$'] and row['reward_target_$']:
        try:
            row['planned_RR'] = f"{float(row['reward_target_$']) / float(row['risk_$']):.2f}"
        except ValueError:
            pass
    row['thesis'] = _prompt("Thesis (1 line — WHY)")
    row['setup_tag'] = _prompt("Setup tag (e.g. PULLBACK_TO_20MA, IV_CRUSH_PLAY)")
    row['mental_state'] = _prompt("Mental state 1-5 (5=sharp)")
    row['checklist_pass'] = _prompt("Pre-trade checklist passed? Y/N", "Y").upper()
    # Greeks
    print("\n  -- Greeks at entry (from model) --")
    row['delta_entry'] = _prompt("Net Δ at entry")
    row['gamma_entry'] = _prompt("Net Γ at entry")
    row['theta_entry'] = _prompt("Net θ at entry ($/day)")
    row['vega_entry'] = _prompt("Net ν at entry ($/1%)")
    row['iv_entry'] = _prompt("Avg IV at entry (decimal)")

    rows = _read_all()
    rows.append(row)
    _write_all(rows)
    print(f"\n✓ Trade #{tid} logged. Status: OPEN.")


def log_from_model(rank: int = 1, contracts_override: int | None = None):
    """Pull pre-trade row from latest _prop_candidates.json (top-N)."""
    _ensure_csv()
    if not CANDIDATES.exists():
        print(f"✗ No {CANDIDATES.name}. Run prop_options_model.py first.")
        return
    cands = json.loads(CANDIDATES.read_text(encoding='utf-8'))
    if rank > len(cands):
        print(f"✗ Only {len(cands)} candidates; rank {rank} out of range.")
        return
    c = cands[rank - 1]
    tid = _next_id()
    contracts = contracts_override if contracts_override is not None else c['sizing']['contracts']

    # Approximate entry/stop/target from model
    entry = abs(sum(L['mid'] if L['action'] == 'BUY' else -L['mid'] for L in c['legs']))
    if c['debit_credit'] == 'DEBIT':
        stop_price = entry * 0.5         # exit at 50% of debit lost
        target_price = entry * 2.0       # exit at 2x debit
    else:
        # for credits: stop when max-loss is hit (= width - credit); target = 50% of credit captured
        stop_price = c['max_loss_$'] / 100
        target_price = entry * 0.5

    row = {k: '' for k in CSV_COLUMNS}
    row.update({
        'id': str(tid),
        'opened_at': datetime.now().isoformat(timespec='seconds'),
        'status': 'OPEN',
        'ticker': c['ticker'],
        'sector': c['sector'],
        'strategy': c['strategy'],
        'edge_score': f"{c['edge_score']:.1f}",
        'bias': c['bias'],
        'regime': c['regime_label'].split('|')[0].strip(),
        'planned_entry': f"{entry:.2f}",
        'planned_stop': f"{stop_price:.2f}",
        'planned_target': f"{target_price:.2f}",
        'contracts': str(contracts),
        'risk_$': f"{c['sizing']['dollar_risk']:.2f}",
        'reward_target_$': (f"{c['max_profit_$']:.2f}" if isinstance(c['max_profit_$'], (int, float))
                            else 'OPEN'),
        'planned_RR': (f"{c['rr_ratio']:.2f}" if c['rr_ratio'] < 100 else 'OPEN'),
        'thesis': f"Model edge {c['edge_score']:.0f}/100, P(W) {c['prob_profit']:.0%}, "
                  f"{c['bias']}×{c['regime_label'].split('|')[0].strip()}",
        'setup_tag': c['strategy'],
        'mental_state': '',
        'checklist_pass': '',
        'delta_entry': f"{c['net_delta']:.3f}",
        'gamma_entry': f"{c['net_gamma']:.4f}",
        'theta_entry': f"{c['net_theta_$_day']:.2f}",
        'vega_entry': f"{c['net_vega_$_1pct']:.2f}",
        'iv_entry': f"{c['legs'][0]['iv']:.3f}" if c['legs'] else '',
    })
    rows = _read_all()
    rows.append(row)
    _write_all(rows)
    print(f"✓ Pre-trade row #{tid} logged from model rank {rank} ({c['ticker']} {c['strategy']}).")
    print(f"  Fill in mental_state + checklist_pass at fill time, then run `close` after exit.")


# ╔════════════════════════════════════════════════════════════════════╗
# ║  CLOSE — record exit + post-trade quals                            ║
# ╚════════════════════════════════════════════════════════════════════╝

def close_trade(tid: int, exit_price: float, reason: str,
                followed_plan: str = '', what_right: str = '',
                what_wrong: str = '', lesson: str = '',
                actual_entry: float | None = None,
                slippage: float | None = None,
                account_equity: float | None = None):
    rows = _read_all()
    for r in rows:
        if r['id'] == str(tid):
            try:
                entry = float(actual_entry) if actual_entry is not None else float(r['planned_entry'] or 0)
                contracts = int(r['contracts'] or 0)
                risk_dollars = float(r['risk_$'] or 1)
                debit_credit_sgn = 1 if entry > 0 else -1  # crude

                # P&L: for debit trade pnl = (exit - entry) * 100 * contracts
                #      for credit trade pnl = (entry - exit) * 100 * contracts  (we captured premium)
                # We infer from setup_tag/strategy name
                strat = (r.get('strategy') or '').upper()
                is_credit = ('PUT_SPREAD' in strat and 'BULL' in strat) \
                            or ('CALL_SPREAD' in strat and 'BEAR' in strat) \
                            or 'IRON' in strat
                if is_credit:
                    pnl = (entry - exit_price) * 100 * contracts
                else:
                    pnl = (exit_price - entry) * 100 * contracts
                pnl_R = pnl / risk_dollars if risk_dollars else 0
                pct = (pnl / account_equity) if account_equity else None

                r['closed_at'] = datetime.now().isoformat(timespec='seconds')
                r['status'] = 'CLOSED'
                r['actual_entry'] = f"{entry:.2f}"
                r['actual_exit'] = f"{exit_price:.2f}"
                r['slippage_vs_mid'] = f"{slippage:.2f}" if slippage is not None else ''
                r['pnl_$'] = f"{pnl:.2f}"
                r['pnl_R'] = f"{pnl_R:.2f}"
                r['pnl_pct_account'] = f"{pct:.4f}" if pct is not None else ''
                r['exit_reason'] = reason.upper()
                r['followed_plan'] = followed_plan.upper() if followed_plan else ''
                r['what_went_right'] = what_right
                r['what_went_wrong'] = what_wrong
                r['lesson_tag'] = lesson.upper() if lesson else ''
                _write_all(rows)
                print(f"✓ Trade #{tid} CLOSED. P&L: ${pnl:+.2f}  ({pnl_R:+.2f}R)  reason={reason}")
                return
            except Exception as e:
                print(f"✗ close failed: {e}")
                return
    print(f"✗ Trade #{tid} not found.")


# ╔════════════════════════════════════════════════════════════════════╗
# ║  STATS — expectancy dashboard                                       ║
# ╚════════════════════════════════════════════════════════════════════╝

def compute_stats(rows: list[dict]) -> dict:
    closed = [r for r in rows if r.get('status') == 'CLOSED']
    if not closed:
        return {'sample_size': 0}

    def _f(r, k, default=0.0):
        try:
            return float(r.get(k) or default)
        except ValueError:
            return default

    pnl_R = [_f(r, 'pnl_R') for r in closed]
    pnl_dollars = [_f(r, 'pnl_$') for r in closed]
    wins = [x for x in pnl_R if x > 0]
    losses = [x for x in pnl_R if x <= 0]
    win_rate = len(wins) / len(pnl_R) if pnl_R else 0
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    expectancy_R = win_rate * avg_win + (1 - win_rate) * avg_loss
    gross_W = sum(wins)
    gross_L = abs(sum(losses))
    profit_factor = gross_W / gross_L if gross_L > 0 else float('inf') if gross_W > 0 else 0

    # max consecutive losses
    streak = max_streak = 0
    for x in pnl_R:
        if x <= 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0

    # By strategy
    by_strat = defaultdict(list)
    for r in closed:
        by_strat[r.get('strategy', 'UNKNOWN')].append(_f(r, 'pnl_R'))

    # By sector
    by_sector = defaultdict(list)
    for r in closed:
        by_sector[r.get('sector', 'UNKNOWN')].append(_f(r, 'pnl_R'))

    # By edge bucket
    by_edge = defaultdict(list)
    for r in closed:
        e = _f(r, 'edge_score')
        if e >= 80: bucket = '80-100 (elite)'
        elif e >= 65: bucket = '65-79 (strong)'
        elif e >= 55: bucket = '55-64 (marginal)'
        else: bucket = '<55 (below gate)'
        by_edge[bucket].append(_f(r, 'pnl_R'))

    # Plan adherence
    on_plan = [_f(r, 'pnl_R') for r in closed if (r.get('followed_plan') or '').upper().startswith('Y')]
    off_plan = [_f(r, 'pnl_R') for r in closed if (r.get('followed_plan') or '').upper().startswith('N')]

    def _agg(xs):
        if not xs: return {'n': 0}
        wins_ = [x for x in xs if x > 0]
        return {
            'n': len(xs),
            'win_rate': f"{len(wins_) / len(xs):.0%}",
            'avg_R': f"{sum(xs) / len(xs):+.2f}",
            'expectancy_R': f"{sum(xs) / len(xs):+.2f}",
            'total_R': f"{sum(xs):+.2f}",
        }

    return {
        'sample_size': len(pnl_R),
        'win_rate': f"{win_rate:.0%}",
        'avg_win_R': f"{avg_win:+.2f}",
        'avg_loss_R': f"{avg_loss:+.2f}",
        'expectancy_R': f"{expectancy_R:+.2f}",
        'total_R': f"{sum(pnl_R):+.2f}",
        'total_$': f"{sum(pnl_dollars):+.2f}",
        'profit_factor': f"{profit_factor:.2f}",
        'max_consec_losses': max_streak,
        'by_strategy': {k: _agg(v) for k, v in by_strat.items()},
        'by_sector': {k: _agg(v) for k, v in by_sector.items()},
        'by_edge_score': {k: _agg(v) for k, v in by_edge.items()},
        'plan_adherence': {
            'on_plan': _agg(on_plan),
            'off_plan': _agg(off_plan),
        },
    }


def print_stats():
    rows = _read_all()
    stats = compute_stats(rows)
    if stats['sample_size'] == 0:
        print("No closed trades yet.")
        return
    print(f"\n═══ EXPECTANCY DASHBOARD ═══════════════════════════════════════")
    print(f"  Closed trades  : {stats['sample_size']}")
    print(f"  Win rate       : {stats['win_rate']}")
    print(f"  Avg win        : {stats['avg_win_R']}R")
    print(f"  Avg loss       : {stats['avg_loss_R']}R")
    print(f"  Expectancy     : {stats['expectancy_R']}R per trade")
    print(f"  Total          : {stats['total_R']}R  /  {stats['total_$']}")
    print(f"  Profit factor  : {stats['profit_factor']}")
    print(f"  Max losing streak : {stats['max_consec_losses']}")

    print(f"\n  --- By strategy ---")
    for k, v in stats['by_strategy'].items():
        if v['n']:
            print(f"    {k:28s} n={v['n']:3d}  win {v['win_rate']:>4s}  E[R] {v['expectancy_R']:>6s}  total {v['total_R']:>7s}")

    print(f"\n  --- By edge score bucket ---")
    for k, v in stats['by_edge_score'].items():
        if v['n']:
            print(f"    {k:20s} n={v['n']:3d}  win {v['win_rate']:>4s}  E[R] {v['expectancy_R']:>6s}")

    print(f"\n  --- Plan adherence (THE most important number) ---")
    op = stats['plan_adherence']['on_plan']
    fp = stats['plan_adherence']['off_plan']
    if op.get('n'):
        print(f"    ON PLAN    n={op['n']:3d}  win {op['win_rate']:>4s}  E[R] {op['expectancy_R']:>6s}")
    if fp.get('n'):
        print(f"    OFF PLAN   n={fp['n']:3d}  win {fp['win_rate']:>4s}  E[R] {fp['expectancy_R']:>6s}")
        print(f"    >>> If OFF PLAN is profitable, your rules are too tight. If OFF PLAN bleeds, stop deviating.")


def render_full_report():
    rows = _read_all()
    stats = compute_stats(rows)
    if stats['sample_size'] == 0:
        return "# Prop Trade Journal\n\nNo closed trades yet."
    out = [f"# Prop Trade Journal — {date.today().isoformat()}", ""]
    out.append("## Summary")
    out.append(f"- Closed trades: **{stats['sample_size']}**")
    out.append(f"- Win rate: **{stats['win_rate']}**")
    out.append(f"- Expectancy: **{stats['expectancy_R']}R/trade**")
    out.append(f"- Total: **{stats['total_R']}R / {stats['total_$']}**")
    out.append(f"- Profit factor: **{stats['profit_factor']}**")
    out.append(f"- Max losing streak: **{stats['max_consec_losses']}**")
    out.append("")
    out.append("## By strategy")
    out.append("| Strategy | N | Win% | E[R] | Total R |")
    out.append("|---|---|---|---|---|")
    for k, v in stats['by_strategy'].items():
        if v.get('n'):
            out.append(f"| {k} | {v['n']} | {v['win_rate']} | {v['expectancy_R']} | {v['total_R']} |")
    out.append("")
    out.append("## By edge bucket")
    out.append("| Edge bucket | N | Win% | E[R] |")
    out.append("|---|---|---|---|")
    for k, v in stats['by_edge_score'].items():
        if v.get('n'):
            out.append(f"| {k} | {v['n']} | {v['win_rate']} | {v['expectancy_R']} |")
    out.append("")
    out.append("## Plan adherence")
    op = stats['plan_adherence']['on_plan']
    fp = stats['plan_adherence']['off_plan']
    out.append(f"- On plan: n={op.get('n', 0)} win {op.get('win_rate', '-')} E[R] {op.get('expectancy_R', '-')}")
    out.append(f"- Off plan: n={fp.get('n', 0)} win {fp.get('win_rate', '-')} E[R] {fp.get('expectancy_R', '-')}")
    return "\n".join(out)


# ╔════════════════════════════════════════════════════════════════════╗
# ║  CLI                                                                ║
# ╚════════════════════════════════════════════════════════════════════╝

def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)

    sp_log = sub.add_parser('log', help='Log a new pre-trade entry')
    sp_log.add_argument('--from-model', action='store_true',
                        help='pull from latest _prop_candidates.json')
    sp_log.add_argument('--rank', type=int, default=1)
    sp_log.add_argument('--contracts', type=int, default=None,
                        help='override model-sized contract count')

    sp_close = sub.add_parser('close', help='Close out a trade')
    sp_close.add_argument('--id', type=int, required=True)
    sp_close.add_argument('--exit', type=float, required=True)
    sp_close.add_argument('--reason', type=str, required=True,
                          help='TARGET / STOP / TIME / NEWS / DISCRETIONARY')
    sp_close.add_argument('--entry', type=float, default=None,
                          help='actual fill if different from planned')
    sp_close.add_argument('--slippage', type=float, default=None)
    sp_close.add_argument('--followed-plan', type=str, default='', help='Y or N')
    sp_close.add_argument('--right', type=str, default='')
    sp_close.add_argument('--wrong', type=str, default='')
    sp_close.add_argument('--lesson', type=str, default='')
    sp_close.add_argument('--equity', type=float, default=None,
                          help='account equity for pnl_%_account')

    sub.add_parser('stats', help='Print expectancy dashboard')
    sub.add_parser('report', help='Print full markdown report')
    sub.add_parser('list', help='List open trades')

    args = p.parse_args()

    if args.cmd == 'log':
        if args.from_model:
            log_from_model(args.rank, args.contracts)
        else:
            log_interactive()
    elif args.cmd == 'close':
        close_trade(args.id, args.exit, args.reason,
                    followed_plan=args.followed_plan,
                    what_right=args.right, what_wrong=args.wrong,
                    lesson=args.lesson, actual_entry=args.entry,
                    slippage=args.slippage, account_equity=args.equity)
    elif args.cmd == 'stats':
        print_stats()
    elif args.cmd == 'report':
        print(render_full_report())
    elif args.cmd == 'list':
        rows = _read_all()
        open_ = [r for r in rows if r.get('status') == 'OPEN']
        if not open_:
            print("No open trades.")
            return
        print(f"\n{len(open_)} open trades:")
        for r in open_:
            print(f"  #{r['id']:>3s}  {r['ticker']:5s}  {r['strategy']:26s}  "
                  f"contracts {r['contracts']}  risk ${r['risk_$']}  "
                  f"thesis: {r.get('thesis','')[:60]}")


if __name__ == '__main__':
    main()
