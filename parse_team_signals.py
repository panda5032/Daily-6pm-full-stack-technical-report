"""
Team Signals Parser
===================
Reads today's 8 analyst reports and consolidates per-ticker signals into a
single ranked verdict. Applies the portfolio-manager-lead weighted scoring:

  Weights: Value 1.2, Rules 1.2, RightSide 1.0, Elliott 1.0, Tech 1.0,
           DayTrade 0.6, Whale 0.8, Earnings 1.1 (when active)

  Numeric: STRONG_BUY=+1 conv9, BUY=+1 conv7, HOLD=0, SELL=-1 conv6,
           STRONG_SELL=-1 conv8, AVOID=-1.5 conv8, N/A=skip

Outputs:
  team_master_YYYY-MM-DD.csv  (sortable; one row per ticker × all analysts)
  team_summary_YYYY-MM-DD.md  (top picks + exits + dissents)
"""
import re
import csv
import sys
import io
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

HERE = Path(__file__).parent

def latest(prefix):
    """Find the most recent dated report matching prefix_YYYY-MM-DD.md."""
    files = sorted(HERE.glob(f'{prefix}_*.md'))
    return files[-1] if files else None

REPORTS = {
    'right_side': latest('right_side_trading'),
    'day_trade':  latest('short_term_report'),
    'value':      latest('long_term_strategy'),
    'elliott':    latest('elliott_wave_recommendations'),
    'rules':      latest('chinese_principles'),
    'tech':       latest('technical_macd_volume'),
    'whale':      latest('whale_options'),
    'earnings':   latest('earnings_plays'),
}
# Use the date from the most-recent file across all reports for output naming
_dates = [p.stem.split('_')[-1] for p in REPORTS.values() if p]
TODAY = max(_dates) if _dates else datetime.now().strftime('%Y-%m-%d')

WEIGHTS = {
    'value': 1.2, 'rules': 1.2, 'right_side': 1.0, 'elliott': 1.0,
    'tech': 1.0, 'day_trade': 0.6, 'whale': 0.8, 'earnings': 1.1,
}

# ─── Action → (numeric_signal, conviction) ──────────────────────────
ACTION_MAP = {
    'STRONG BUY':   (1.0,  9),
    'STRONG_BUY':   (1.0,  9),
    'BUY':          (1.0,  7),
    'HOLD':         (0.0,  3),
    'WAIT':         (0.0,  3),
    'OBSERVE':      (0.0,  3),
    'REDUCE':       (-1.0, 5),
    'SELL':         (-1.0, 6),
    'STRONG SELL':  (-1.0, 8),
    'STRONG_SELL':  (-1.0, 8),
    'AVOID':        (-1.5, 8),
    'NO SIGNAL':    (None, None),
    'NO_SIGNAL':    (None, None),
    'NO OPTIONS':   (None, None),
    'NO_OPTIONS':   (None, None),
    'NO DATA':      (None, None),
    'NO_DATA':      (None, None),
    'NO_PRICE':     (None, None),
}


def normalize(action):
    """Map analyst-specific action labels to canonical."""
    if not action:
        return None
    a = action.upper().strip()
    a = a.replace('🟢🟢', '').replace('🟢', '').replace('🔴🔴', '').replace('🔴', '')
    a = a.replace('🟡', '').replace('⛔', '').replace('🚫', '').replace('⚪', '')
    a = a.replace('✅', '').replace('🔵', '').replace('⏳', '').replace('👀', '')
    a = a.replace('➡️', '').replace('❌', '').replace('❓', '').replace('📈', '')
    a = a.replace('📉', '').replace('🚀', '').replace('⚡', '').replace('📊', '')
    a = a.replace('TAKE PROFIT', 'SELL').replace('TAKE_PROFIT', 'SELL')
    a = a.replace('CORE 持仓', 'BUY').replace('增持', 'BUY').replace('买入', 'BUY')
    a = a.replace('回避', 'AVOID').replace('减持', 'SELL').replace('持有', 'HOLD').replace('观望', 'HOLD')
    a = a.replace('卖出', 'SELL').replace('暂不入场', 'HOLD')
    a = re.sub(r'\s+', ' ', a).strip()
    a = re.sub(r'\s*/\s*.*$', '', a)  # drop trailing "/REDUCE" etc
    if 'STRONG BUY' in a or 'STRONG_BUY' in a:
        return 'STRONG BUY'
    if 'STRONG SELL' in a or 'STRONG_SELL' in a:
        return 'STRONG SELL'
    if 'AVOID' in a:
        return 'AVOID'
    if 'REDUCE' in a:
        return 'REDUCE'
    if 'BUY' in a:
        return 'BUY'
    if 'SELL' in a:
        return 'SELL'
    if 'HOLD' in a or 'OBSERVE' in a or 'WAIT' in a:
        return 'HOLD'
    if 'NO' in a:
        return 'NO_SIGNAL'
    return None


# ── PARSERS — one per report ────────────────────────────────────────
TICKER_RE = r'[A-Z][A-Z0-9-]{0,7}'

def parse_action_line(text):
    """Match patterns like '**AAPL** — 🟢 **BUY** (score: +1.0)' or '**AAPL** — 🟢🟢 **STRONG BUY** (...)'"""
    pattern = rf'\*\*({TICKER_RE})\*\*\s*[—–-]\s*[^*]*\*\*([^*]+?)\*\*'
    return re.findall(pattern, text)


def parse_value(content):
    """long_term_strategy report: per-sector tables with action column."""
    sigs = {}
    # Match table rows: | **TICKER** | $price | 12M | MA200 | RSI | rev | PEG | **score** | 🟢 action |
    rows = re.findall(
        rf'\|\s*\*\*({TICKER_RE})\*\*\s*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|\s*\*\*?(\d+)\*\*?\s*\|\s*[^|]*?(?:买入|增持|持有|观望|减持|回避)[^|]*?\|',
        content
    )
    for ticker, score in rows:
        # Determine action from the line
        # Re-find the full line for this ticker
        line_match = re.search(
            rf'\|\s*\*\*{re.escape(ticker)}\*\*\s*\|.*?(?:买入|增持|持有|观望|减持|回避)[^|]*?\|',
            content
        )
        if not line_match:
            continue
        line = line_match.group(0)
        if '买入' in line:
            action = 'BUY'
        elif '增持' in line:
            action = 'BUY'
        elif '持有' in line or '观望' in line:
            action = 'HOLD'
        elif '减持' in line:
            action = 'SELL'
        elif '回避' in line:
            action = 'AVOID'
        else:
            continue
        sigs[ticker] = {'action': action, 'score': int(score)}
    return sigs


def parse_rules(content):
    """chinese_principles: '**TICKER** — 🟢🟢 **STRONG BUY** (score: +X.X)'"""
    sigs = {}
    pattern = rf'\*\*({TICKER_RE})\*\*\s*[—–-]\s*[^*\n]*\*\*([A-Z\s]+?)\*\*\s*\(score:\s*([+-]?\d+\.?\d*)\)'
    for m in re.finditer(pattern, content):
        ticker, action, score = m.group(1), normalize(m.group(2)), float(m.group(3))
        if action and action != 'NO_SIGNAL':
            sigs[ticker] = {'action': action, 'score': score}
    return sigs


def parse_tech(content):
    """technical_macd_volume: '**TICKER** — 🟢🟢 **STRONG BUY** (总分: +X.X | ...)'"""
    sigs = {}
    pattern = rf'\*\*({TICKER_RE})\*\*\s*[—–-]\s*[^*\n]*\*\*([A-Z\s]+?)\*\*\s*\(总分:\s*([+-]?\d+\.?\d*)'
    for m in re.finditer(pattern, content):
        ticker, action, score = m.group(1), normalize(m.group(2)), float(m.group(3))
        if action and action != 'NO_SIGNAL':
            sigs[ticker] = {'action': action, 'score': score}
    return sigs


def parse_whale(content):
    """whale_options: '**TICKER** — 🟢 **BUY** (score: +X.X)'"""
    sigs = {}
    pattern = rf'\*\*({TICKER_RE})\*\*\s*[—–-]\s*[^*\n]*\*\*([A-Z\s_]+?)\*\*\s*\(score:\s*([+-]?\d+\.?\d*)\)'
    for m in re.finditer(pattern, content):
        ticker, action, score = m.group(1), normalize(m.group(2)), float(m.group(3))
        if action and action != 'NO_SIGNAL':
            sigs[ticker] = {'action': action, 'score': score}
    return sigs


def parse_elliott(content):
    """elliott_wave: action column in the main per-sector tables."""
    sigs = {}
    # Match: | **TICKER** | $price | timeframe | wave | score | 🟢🟢 STRONG BUY | ...
    pattern = rf'\|\s*\*\*({TICKER_RE})\*\*\s*\|[^|]+\|[^|]+\|[^|]+\|\s*(\d+)\s*\|\s*[🟢🔴🟡⛔❓⚪]*\s*([A-Z_\s/]+?)\s*\|'
    for m in re.finditer(pattern, content):
        ticker, score, action_raw = m.group(1), int(m.group(2)), m.group(3).strip()
        action = normalize(action_raw)
        if action and action != 'NO_SIGNAL':
            sigs[ticker] = {'action': action, 'score': score}
    return sigs


def parse_right_side(content):
    """right_side_trading: '### [Sector] Name (TICKER)' followed by score line."""
    sigs = {}
    # Match section header + score
    sections = re.findall(
        rf'###\s*\[([^\]]+)\][^(]*\(({TICKER_RE})\)\s*\n[^\n]*\*\*\$[\d,.]+\*\*[^\n]*得分\s*\*\*([+-]?\d+\.?\d*)\*\*\s*\n[^\n]*状态:\s*\*\*([^*]+)\*\*',
        content
    )
    for sector, ticker, score, status in sections:
        score_f = float(score)
        if '右侧交易' in status and '左侧' not in status:
            action = 'BUY'
        elif '偏右侧' in status:
            action = 'HOLD'  # 持续观察
        elif '偏左侧' in status:
            action = 'HOLD'
        elif '左侧交易' in status:
            action = 'SELL' if score_f < -3 else 'HOLD'
        elif '回避' in status or 'AVOID' in status.upper():
            action = 'AVOID'
        else:
            action = 'HOLD'
        # Score-based escalation
        if score_f >= 10:
            action = 'STRONG BUY' if action == 'BUY' else action
        elif score_f <= -8:
            action = 'AVOID' if action == 'SELL' else 'SELL'
        sigs[ticker] = {'action': action, 'score': score_f, 'sector': sector}
    return sigs


def parse_day_trade(content):
    """short_term_report: extract setups (BUY) and avoid list."""
    sigs = {}
    # Setups table: HIGH/MED/LOW signal, setup type, ticker
    setup_rows = re.findall(
        rf'\|\s*\*\*(HIGH|MED|LOW)\*\*\s*\|[^|]*\|\s*\*\*({TICKER_RE})\*\*',
        content
    )
    for conf, ticker in setup_rows:
        score = {'HIGH': 8, 'MED': 6, 'LOW': 4}.get(conf, 5)
        sigs[ticker] = {'action': 'BUY', 'score': score, 'confidence': conf}
    # Avoid section
    avoid_match = re.search(r'## 🚫 回避.*?(?=\n##|\Z)', content, re.S)
    if avoid_match:
        avoid_rows = re.findall(rf'\|[^|]+\|\s*({TICKER_RE})\s*\(', avoid_match.group(0))
        for ticker in avoid_rows:
            if ticker not in sigs:
                sigs[ticker] = {'action': 'SELL', 'score': -3}
    return sigs


def parse_earnings(content):
    """earnings_plays: calendar with play type per ticker."""
    sigs = {}
    rows = re.findall(
        rf'\|\s*\*\*({TICKER_RE})\*\*\s*\|[^|]+\|[^|]+\|\s*(\d+/\d+)\s*\|\s*(\d+)d\s*\|[^|]+\|\s*[📈🎯⚡🚫🎰📉👀❓]*\s*([^|]+?)\s*\|\s*(\w+)\s*\|',
        content
    )
    for ticker, date, days_away, play, conv in rows:
        play_clean = play.strip().lower()
        if 'pre-earnings run-up' in play_clean or 'hold (bullish)' in play_clean:
            action = 'BUY'
        elif 'hold (bearish)' in play_clean or 'pre-earnings fade' in play_clean:
            action = 'SELL'
        elif 'avoid' in play_clean or 'watch' in play_clean or 'gamble' in play_clean:
            action = 'HOLD'
        else:
            action = 'HOLD'
        score = {'HIGH': 8, 'MED': 6, 'LOW': 4, 'NONE': 2}.get(conv.upper(), 4)
        sigs[ticker] = {
            'action': action,
            'score': score,
            'days_away': int(days_away),
            'play': play.strip()[:30],
        }
    return sigs


PARSERS = {
    'value': parse_value,
    'rules': parse_rules,
    'tech': parse_tech,
    'whale': parse_whale,
    'elliott': parse_elliott,
    'right_side': parse_right_side,
    'day_trade': parse_day_trade,
    'earnings': parse_earnings,
}


def compute_verdict(per_analyst):
    """Apply weighted scoring to a single ticker's signals dict."""
    num = 0.0
    denom = 0.0
    contributors = 0
    bull_count = 0
    bear_count = 0
    for analyst, weight in WEIGHTS.items():
        sig = per_analyst.get(analyst)
        if not sig or sig.get('action') is None:
            continue
        action = sig['action']
        numeric, conv = ACTION_MAP.get(action, (None, None))
        if numeric is None:
            continue
        num += numeric * weight * (conv / 10.0)
        denom += weight
        contributors += 1
        if numeric > 0:
            bull_count += 1
        elif numeric < 0:
            bear_count += 1
    if denom == 0:
        return None
    weighted = num / denom
    # Verdict tier
    if weighted >= 0.55:
        verdict = 'STRONG BUY'
    elif weighted >= 0.25:
        verdict = 'BUY'
    elif weighted >= -0.25:
        verdict = 'HOLD'
    elif weighted >= -0.55:
        verdict = 'REDUCE'
    else:
        verdict = 'SELL/AVOID'
    conviction = max(1, min(10, round(abs(weighted) * 10)))
    # Dispersion penalty
    if bull_count >= 3 and bear_count >= 3:
        conviction = max(1, conviction - 2)
    return {
        'weighted': round(weighted, 3),
        'verdict': verdict,
        'conviction': conviction,
        'contributors': contributors,
        'bull_count': bull_count,
        'bear_count': bear_count,
    }


def main():
    print(f"📂 Reading 8 reports for {TODAY}...")
    all_signals = defaultdict(dict)
    for analyst, path in REPORTS.items():
        if not path.exists():
            print(f"   ⚠️  {path.name} not found — skipping {analyst}")
            continue
        try:
            content = path.read_text(encoding='utf-8')
        except Exception as e:
            print(f"   ⚠️  {path.name} read error: {e}")
            continue
        sigs = PARSERS[analyst](content)
        for ticker, sig in sigs.items():
            all_signals[ticker][analyst] = sig
        print(f"   ✓ {analyst}: {len(sigs)} signals")

    print(f"\n🧮 Computing verdicts for {len(all_signals)} tickers...")
    verdicts = []
    for ticker in sorted(all_signals.keys()):
        if ticker in ('TOTAL', 'CASH', 'MARGIN', 'TICKER', 'NA'):
            continue
        per_analyst = all_signals[ticker]
        v = compute_verdict(per_analyst)
        if v is None:
            continue
        # Get sector from right_side or value if available
        sector = ''
        for a in ('right_side', 'value'):
            if a in per_analyst and 'sector' in per_analyst[a]:
                sector = per_analyst[a].get('sector', '')
                break
        # Earnings flag
        earnings = per_analyst.get('earnings', {})
        earnings_days = earnings.get('days_away', '')
        earnings_play = earnings.get('play', '')
        verdicts.append({
            'ticker': ticker,
            'sector': sector,
            'verdict': v['verdict'],
            'conviction': v['conviction'],
            'weighted': v['weighted'],
            'contributors': v['contributors'],
            'bulls': v['bull_count'],
            'bears': v['bear_count'],
            'value': per_analyst.get('value', {}).get('action', '—'),
            'value_score': per_analyst.get('value', {}).get('score', ''),
            'rules': per_analyst.get('rules', {}).get('action', '—'),
            'rules_score': per_analyst.get('rules', {}).get('score', ''),
            'elliott': per_analyst.get('elliott', {}).get('action', '—'),
            'elliott_score': per_analyst.get('elliott', {}).get('score', ''),
            'tech': per_analyst.get('tech', {}).get('action', '—'),
            'tech_score': per_analyst.get('tech', {}).get('score', ''),
            'right_side': per_analyst.get('right_side', {}).get('action', '—'),
            'right_side_score': per_analyst.get('right_side', {}).get('score', ''),
            'day_trade': per_analyst.get('day_trade', {}).get('action', '—'),
            'whale': per_analyst.get('whale', {}).get('action', '—'),
            'whale_score': per_analyst.get('whale', {}).get('score', ''),
            'earnings_play': earnings_play,
            'earnings_days': earnings_days,
        })

    # Sort by weighted score descending
    verdicts.sort(key=lambda x: -x['weighted'])

    # Write CSV
    out_csv = HERE / f'team_master_{TODAY}.csv'
    if verdicts:
        with out_csv.open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=verdicts[0].keys())
            writer.writeheader()
            writer.writerows(verdicts)
        print(f"\n✅ Wrote {len(verdicts)} ticker verdicts → {out_csv.name}")

    # Summary stats
    by_verdict = defaultdict(int)
    for v in verdicts:
        by_verdict[v['verdict']] += 1
    print("\n📊 Verdict distribution:")
    for k in ('STRONG BUY', 'BUY', 'HOLD', 'REDUCE', 'SELL/AVOID'):
        print(f"   {k:14s}: {by_verdict[k]:3d}")

    # Top 10 / Bottom 10
    print("\n🟢 TOP 10 STRONG BUYs (highest weighted score):")
    for v in verdicts[:10]:
        print(f"   {v['ticker']:7s} {v['verdict']:12s} conv={v['conviction']:2d} score={v['weighted']:+.3f} bulls={v['bulls']} bears={v['bears']} contrib={v['contributors']}")
    print("\n🔴 BOTTOM 10 SELL/AVOIDs (lowest weighted score):")
    for v in verdicts[-10:]:
        print(f"   {v['ticker']:7s} {v['verdict']:12s} conv={v['conviction']:2d} score={v['weighted']:+.3f} bulls={v['bulls']} bears={v['bears']} contrib={v['contributors']}")

    # Earnings landmines next 3 days
    print("\n📅 EARNINGS in next 3 days:")
    for v in verdicts:
        if v['earnings_days'] != '' and isinstance(v['earnings_days'], int) and v['earnings_days'] <= 3:
            print(f"   {v['ticker']:7s} in {v['earnings_days']}d · {v['earnings_play']:30s} · verdict {v['verdict']} conv {v['conviction']}")


if __name__ == '__main__':
    main()
