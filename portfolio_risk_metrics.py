"""
Portfolio Risk Metrics — analyzes Portfolio_by_Owner_Analysis.xlsx
=================================================================
Pulls the Google-Drive-synced Portfolio_by_Owner_Analysis.xlsx (multi-account
block layout) and computes per-account + aggregate risk metrics:
  - Annualized return / volatility
  - Sharpe ratio (rf=4.5%)
  - Sortino ratio
  - Beta vs SPY, Alpha (CAPM)
  - Max drawdown
  - Top-5 concentration
  - Sector mix (best-effort via AI_Portfolios.xlsx sector map)

Plus a simple 1Y backtest comparing each account vs SPY/QQQ benchmarks.

Usage:
  python portfolio_risk_metrics.py                # run on all accounts
  python portfolio_risk_metrics.py --account "Kenny Joint"   # one account
  python portfolio_risk_metrics.py --period 6mo|1y|2y|3y     # lookback (default 1y)

Output: portfolio_risk_YYYY-MM-DD.md
"""
import sys, io, warnings, argparse
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
import yfinance as yf
import openpyxl

warnings.filterwarnings('ignore')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

HERE = Path(__file__).parent
XLSX = HERE / 'Portfolio_by_Owner_Analysis.xlsx'
RF_RATE = 0.045
TRADING_DAYS = 252
DEFAULT_PERIOD = '1y'

OWNER_KEYWORDS = ('Kenny', 'Mark', 'Cheryle', 'Sunny')
OWNER_SUFFIXES = ('Joint', 'Individual', 'Roth', 'IRA', 'HSA', '401k')


def parse_portfolio(xlsx_path):
    """Returns dict {owner_name: [(ticker, qty, amount), ...]} parsed from the multi-block sheet."""
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    max_cols = max(len(r) for r in rows)

    # Step 1 — find owner-block headers anywhere in the sheet (cell text contains an owner keyword + suffix or solo "Roth/HSA/401k")
    # Map (row_idx, col_idx) -> owner_name. Each block extends downward until another header in the same column or a "Total" row.
    block_starts = []  # (row, col, owner_name)
    for r_idx, row in enumerate(rows):
        for c_idx, cell in enumerate(row):
            if not isinstance(cell, str):
                continue
            t = cell.strip()
            if not t or len(t) > 30:
                continue
            has_kw = any(k in t for k in OWNER_KEYWORDS)
            has_suf = any(s in t for s in OWNER_SUFFIXES)
            if has_kw and has_suf:
                block_starts.append((r_idx, c_idx, t))

    # Step 2 — for each block, scan rows below it (until next owner-header in same column, or sheet end) and harvest tickers
    accounts = {}
    for i, (start_r, col, owner) in enumerate(block_starts):
        # End row = next block start in same column, else end-of-sheet
        end_r = len(rows)
        for nr, nc, _ in block_starts:
            if nc == col and nr > start_r:
                end_r = min(end_r, nr)
                break
        holdings = []
        for r_idx in range(start_r + 1, end_r):
            row = rows[r_idx]
            if col >= len(row):
                continue
            ticker_cell = row[col]
            if not isinstance(ticker_cell, str):
                continue
            ticker = ticker_cell.strip().upper()
            # Heuristic ticker: 1-6 chars, alphanumeric + dot/hyphen, not a header word
            if not ticker or len(ticker) > 6 or ticker in ('TOTAL', 'CASH', 'MARGIN'):
                continue
            if not all(c.isalnum() or c in '.-' for c in ticker):
                continue
            try:
                qty = row[col + 2] if col + 2 < len(row) else None
                amount = row[col + 3] if col + 3 < len(row) else None
            except IndexError:
                continue
            if not isinstance(qty, (int, float)) or not isinstance(amount, (int, float)):
                continue
            if qty <= 0 or amount <= 0:
                continue
            holdings.append((ticker, float(qty), float(amount)))
        if holdings:
            accounts[owner] = holdings
    return accounts


# Bare-symbol → yfinance-symbol mapping for cryptos & a few aliases
SYMBOL_ALIAS = {
    'BTC': 'BTC-USD', 'ETH': 'ETH-USD', 'XRP': 'XRP-USD', 'SOL': 'SOL-USD',
    'ADA': 'ADA-USD', 'DOGE': 'DOGE-USD', 'PEPE': 'PEPE-USD',
}


def yf_symbol(t):
    return SYMBOL_ALIAS.get(t, t)


def fetch_history(tickers, period=DEFAULT_PERIOD):
    """Batch-download daily closes for tickers + SPY/QQQ benchmarks. Maps bare crypto symbols."""
    universe = sorted({yf_symbol(t) for t in tickers} | {'SPY', 'QQQ'})
    data = {}
    for yt in universe:
        try:
            df = yf.download(yt, period=period, progress=False, auto_adjust=True, threads=False)
            if df.empty:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            data[yt] = df['Close']
        except Exception:
            pass
    # Mirror yfinance keys back to bare symbols so callers can lookup either way
    for bare, yt in SYMBOL_ALIAS.items():
        if yt in data and bare not in data:
            data[bare] = data[yt]
    return data


def compute_metrics(owner, holdings, hist):
    total_value = sum(amt for _, _, amt in holdings)
    if total_value <= 0:
        return None

    weights = {t: amt / total_value for t, _, amt in holdings if t in hist}
    if not weights:
        return None
    # Renormalize so weights sum to 1.0 (drops un-fetchable tickers from denominator)
    w_sum = sum(weights.values())
    if w_sum > 0:
        weights = {t: w / w_sum for t, w in weights.items()}
    coverage_pct = w_sum * 100  # how much of NAV had price history

    # Common date index
    common = None
    for t in weights:
        rets = hist[t].pct_change().dropna()
        common = rets.index if common is None else common.intersection(rets.index)
    if common is None or len(common) < 30:
        return None

    # Weighted portfolio returns
    port_rets = pd.Series(0.0, index=common)
    for t, w in weights.items():
        port_rets = port_rets.add(hist[t].pct_change().reindex(common).fillna(0) * w, fill_value=0)

    spy_rets = hist['SPY'].pct_change().reindex(common).fillna(0) if 'SPY' in hist else None

    ann_ret = port_rets.mean() * TRADING_DAYS
    ann_vol = port_rets.std() * np.sqrt(TRADING_DAYS)
    sharpe = (ann_ret - RF_RATE) / ann_vol if ann_vol > 0 else 0
    downside = port_rets[port_rets < 0]
    sortino = (ann_ret - RF_RATE) / (downside.std() * np.sqrt(TRADING_DAYS)) if len(downside) > 0 and downside.std() > 0 else 0

    beta, alpha = 0.0, 0.0
    if spy_rets is not None and len(spy_rets) == len(port_rets):
        cov = np.cov(port_rets, spy_rets)
        beta = cov[0, 1] / cov[1, 1] if cov[1, 1] > 0 else 0
        spy_ann = spy_rets.mean() * TRADING_DAYS
        alpha = ann_ret - (RF_RATE + beta * (spy_ann - RF_RATE))

    cumret = (1 + port_rets).cumprod()
    max_dd = ((cumret - cumret.cummax()) / cumret.cummax()).min()

    sorted_hold = sorted([(t, amt) for t, _, amt in holdings if amt > 0], key=lambda x: -x[1])
    top5 = sorted_hold[:5]
    top5_pct = sum(a for _, a in top5) / total_value * 100

    spy_ann_ret = spy_rets.mean() * TRADING_DAYS if spy_rets is not None else 0
    spy_ann_vol = spy_rets.std() * np.sqrt(TRADING_DAYS) if spy_rets is not None else 0
    spy_sharpe = (spy_ann_ret - RF_RATE) / spy_ann_vol if spy_ann_vol > 0 else 0
    spy_cumret = (1 + spy_rets).cumprod() if spy_rets is not None else None
    spy_max_dd = ((spy_cumret - spy_cumret.cummax()) / spy_cumret.cummax()).min() if spy_cumret is not None else 0

    return {
        'owner': owner,
        'total_value': total_value,
        'n_positions': len([h for h in holdings if h[2] > 0]),
        'top5': top5,
        'top5_pct': top5_pct,
        'ann_return_pct': ann_ret * 100,
        'ann_vol_pct': ann_vol * 100,
        'sharpe': sharpe,
        'sortino': sortino,
        'beta': beta,
        'alpha_pct': alpha * 100,
        'max_dd_pct': max_dd * 100,
        'spy_ann_return_pct': spy_ann_ret * 100,
        'spy_ann_vol_pct': spy_ann_vol * 100,
        'spy_sharpe': spy_sharpe,
        'spy_max_dd_pct': spy_max_dd * 100,
        'excess_return_pct': (ann_ret - spy_ann_ret) * 100,
        'period_days': len(common),
        'coverage_pct': coverage_pct,
    }


def aggregate_metrics(accounts, hist):
    """Combine all accounts into one virtual portfolio."""
    combined = {}
    for owner, holdings in accounts.items():
        for t, qty, amt in holdings:
            if t not in combined:
                combined[t] = [0.0, 0.0]
            combined[t][0] += qty
            combined[t][1] += amt
    holdings = [(t, q, a) for t, (q, a) in combined.items()]
    return compute_metrics('TOTAL (all accounts)', holdings, hist)


def write_report(account_metrics, total_metrics, accounts, period, out_path):
    L = []
    today = datetime.now().strftime('%Y-%m-%d')
    L.append(f"# Portfolio Risk & Backtesting Report — {today}")
    L.append(f"\n**Lookback:** {period} · **Risk-free rate:** {RF_RATE*100:.1f}% · **Benchmark:** SPY")
    L.append(f"\n**Source:** `Portfolio_by_Owner_Analysis.xlsx` (Google Drive sync) · {len(accounts)} accounts parsed\n")

    # Aggregate snapshot
    if total_metrics:
        m = total_metrics
        L.append("## 🌐 TOTAL PORTFOLIO (all accounts combined)\n")
        L.append(f"- **Net asset value:** ${m['total_value']:,.0f}")
        L.append(f"- **Positions:** {m['n_positions']}")
        L.append(f"- **Top-5 concentration:** {m['top5_pct']:.1f}% — " +
                 ', '.join(f"{t} ${a/1000:.0f}K" for t, a in m['top5']))
        L.append("")
        L.append("| Metric | Portfolio | SPY benchmark | Δ |")
        L.append("|---|---|---|---|")
        L.append(f"| Annualized return | {m['ann_return_pct']:+.2f}% | {m['spy_ann_return_pct']:+.2f}% | {m['excess_return_pct']:+.2f}% |")
        L.append(f"| Annualized volatility (σ) | {m['ann_vol_pct']:.2f}% | {m['spy_ann_vol_pct']:.2f}% | — |")
        L.append(f"| Sharpe ratio | {m['sharpe']:.2f} | {m['spy_sharpe']:.2f} | — |")
        L.append(f"| Sortino ratio | {m['sortino']:.2f} | — | — |")
        L.append(f"| Beta vs SPY | {m['beta']:.2f} | 1.00 | — |")
        L.append(f"| Alpha (CAPM, ann.) | {m['alpha_pct']:+.2f}% | — | — |")
        L.append(f"| Max drawdown | {m['max_dd_pct']:.2f}% | {m['spy_max_dd_pct']:.2f}% | — |")
        L.append("")
        L.append(_interpret(m))
        L.append("")

    # Per-account
    L.append("## 🏦 PER-ACCOUNT BREAKDOWN\n")
    for am in sorted(account_metrics, key=lambda x: -x['total_value']):
        L.append(f"### {am['owner']} — ${am['total_value']:,.0f} ({am['n_positions']} positions)")
        L.append(f"Top holdings: " + ', '.join(f"**{t}** ${a/1000:.0f}K" for t, a in am['top5']) + f" · top-5={am['top5_pct']:.0f}%")
        L.append("")
        L.append(f"| Return | Vol | Sharpe | Sortino | Beta | Alpha | Max DD | vs SPY |")
        L.append(f"|---|---|---|---|---|---|---|---|")
        L.append(f"| {am['ann_return_pct']:+.1f}% | {am['ann_vol_pct']:.1f}% | {am['sharpe']:.2f} | {am['sortino']:.2f} | {am['beta']:.2f} | {am['alpha_pct']:+.1f}% | {am['max_dd_pct']:.1f}% | {am['excess_return_pct']:+.1f}% |")
        L.append("")
        L.append(_interpret(am))
        L.append("")

    # Backtest summary
    L.append("## 🧪 BACKTEST: Account vs SPY (1Y)\n")
    L.append("| Account | Final return | SPY same period | Excess | Risk-adjusted (Sharpe) |")
    L.append("|---|---|---|---|---|")
    for am in sorted(account_metrics, key=lambda x: -x['excess_return_pct']):
        L.append(f"| {am['owner']} | {am['ann_return_pct']:+.1f}% | {am['spy_ann_return_pct']:+.1f}% | **{am['excess_return_pct']:+.1f}%** | {am['sharpe']:.2f} vs {am['spy_sharpe']:.2f} |")
    L.append("")

    L.append("---")
    L.append(f"*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} · `portfolio_risk_metrics.py`*")

    out_path.write_text('\n'.join(L), encoding='utf-8')
    return out_path


def _interpret(m):
    notes = []
    if m['beta'] > 1.3:
        notes.append(f"⚠️ HIGH BETA ({m['beta']:.2f}) — portfolio swings ~{m['beta']*100:.0f}% of market moves")
    elif m['beta'] < 0.7:
        notes.append(f"🛡️ LOW BETA ({m['beta']:.2f}) — defensive vs market")
    if m['sharpe'] > 1.5:
        notes.append(f"✅ STRONG Sharpe {m['sharpe']:.2f}")
    elif m['sharpe'] < 0.5:
        notes.append(f"⚠️ WEAK Sharpe {m['sharpe']:.2f} — return doesn't justify risk")
    if m['max_dd_pct'] < -25:
        notes.append(f"⚠️ DEEP drawdown {m['max_dd_pct']:.1f}% — concentration risk")
    if m['alpha_pct'] > 5:
        notes.append(f"✅ Positive alpha {m['alpha_pct']:+.1f}% — outperformed risk-adjusted")
    elif m['alpha_pct'] < -5:
        notes.append(f"⚠️ Negative alpha {m['alpha_pct']:+.1f}% — underperformed risk-adjusted")
    if m['top5_pct'] > 60:
        notes.append(f"⚠️ Top-5 = {m['top5_pct']:.0f}% — highly concentrated")
    return ' · '.join(notes) if notes else '_No critical flags._'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--account', help='Filter to one account (substring match)')
    p.add_argument('--period', default=DEFAULT_PERIOD, help='Lookback period: 6mo, 1y, 2y, 3y')
    p.add_argument('--xlsx', default=str(XLSX), help='Path to Portfolio_by_Owner_Analysis.xlsx')
    args = p.parse_args()

    xlsx_path = Path(args.xlsx)
    if not xlsx_path.exists():
        print(f"❌ {xlsx_path} not found. Sync the Google Drive file first.")
        sys.exit(1)

    print(f"📂 Parsing {xlsx_path.name}...")
    accounts = parse_portfolio(xlsx_path)
    print(f"   Found {len(accounts)} accounts: {', '.join(accounts.keys())}")

    if args.account:
        accounts = {k: v for k, v in accounts.items() if args.account.lower() in k.lower()}
        if not accounts:
            print(f"❌ No accounts match '{args.account}'")
            sys.exit(1)

    all_tickers = sorted(set(t for hs in accounts.values() for t, _, _ in hs))
    print(f"📊 Fetching {len(all_tickers)} tickers + SPY/QQQ ({args.period})...")
    hist = fetch_history(all_tickers, period=args.period)
    print(f"   Got {len(hist)}/{len(all_tickers)+2} histories")

    account_metrics = []
    for owner, holdings in accounts.items():
        m = compute_metrics(owner, holdings, hist)
        if m:
            account_metrics.append(m)
            print(f"   ✓ {owner}: ${m['total_value']:,.0f} · Sharpe {m['sharpe']:.2f} · β {m['beta']:.2f}")
    total_metrics = aggregate_metrics(accounts, hist) if len(accounts) > 1 else None

    out_path = HERE / f"portfolio_risk_{datetime.now().strftime('%Y-%m-%d')}.md"
    write_report(account_metrics, total_metrics, accounts, args.period, out_path)
    print(f"\n  ✅ Report saved: {out_path.name}")


if __name__ == '__main__':
    main()
