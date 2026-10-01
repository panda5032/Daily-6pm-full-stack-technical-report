# -*- coding: utf-8 -*-
"""
$3M forward paper portfolio run with the 12-playbook engine (same rules as
backtest_twelve_playbooks.py). Signals only — no real orders.

Usage:
  python paper_playbook_portfolio.py init   # create state (baseline 2026-08-18 close)
  python paper_playbook_portfolio.py run    # process all completed trading days since last run

State:   paper_playbook_state.json
Trades:  paper_playbook_trades.csv (rewritten from state each run)
Period:  2026-08-19 .. 2026-09-18 (one month), then final report vs QQQ/SPY.

Rules (identical to backtest):
  P1 pullback-to-MA20 stabilization; P9 first MA50 touch; P2 squeeze breakout
  (RVOL>=1.5); P7 lower-band panic reversal (half risk, above-MA200 only).
  Exits: hard stop -> breakeven at +2R -> MA20-close trail once >= +1R.
  Sizing: 1% equity risk/trade, <=6R total, <=2R/sector, <=25% notional, no leverage,
  5bp slippage. Gates: QQQ<MA50 no new entries; HSI<MA200 blocks China;
  KOSPI<MA50 halves Semis; BTC<MA20 blocks crypto-equities, halves Quantum.
"""
import json, math, os, sys, warnings
from datetime import datetime, date
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings('ignore')
sys.stdout.reconfigure(encoding='utf-8')

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_F = os.path.join(BASE, 'paper_playbook_state.json')
TRADES_F = os.path.join(BASE, 'paper_playbook_trades.csv')
PLANS_F = os.path.join(BASE, 'trade_plans_2026-08-18.json')

START_CAP = 3_000_000.0
RISK_PCT = 0.01
MAX_TOTAL_R = 6.0
MAX_SECTOR_R = 2.0
NOTIONAL_CAP = 0.25
SLIP = 0.0005
BASELINE_DAY = '2026-08-18'
END_DAY = '2026-09-18'
DATA_START = '2025-06-01'

SECTOR = {t: p['sector'] for t, p in
          json.load(open(PLANS_F, encoding='utf-8'))['plans'].items()}
TICKERS = list(SECTOR.keys())
CRYPTO_EQ = [t for t, s in SECTOR.items() if s == 'Crypto' and not t.endswith('-USD')]
IDX = ['QQQ', 'SPY', '^HSI', '^KS11', 'BTC-USD']

# ---------------- data ----------------
def load_data():
    raw = yf.download(sorted(set(TICKERS + IDX)), start=DATA_START, interval='1d',
                      group_by='ticker', auto_adjust=True, threads=True, progress=False)
    out = {}
    for sym in set(TICKERS + IDX):
        try:
            df = raw[sym].dropna(subset=['Close']).copy()
        except Exception:
            continue
        if len(df) < 220:
            continue
        c, h, l, o, v = df['Close'], df['High'], df['Low'], df['Open'], df['Volume']
        df['ma20'] = c.rolling(20).mean()
        df['ma50'] = c.rolling(50).mean()
        df['ma200'] = c.rolling(200).mean()
        sd = c.rolling(20).std()
        df['ub'] = df['ma20'] + 2 * sd
        df['lb'] = df['ma20'] - 2 * sd
        bw = (df['ub'] - df['lb']) / df['ma20']
        df['bw'] = bw
        df['bw_q25'] = bw.rolling(126).quantile(0.25)
        df['hi20'] = h.rolling(20).max().shift(1)
        tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
        df['atr'] = tr.ewm(alpha=1 / 14, adjust=False).mean()
        d = c.diff()
        up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
        dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
        df['rsi'] = 100 - 100 / (1 + up / dn)
        df['rvol'] = v / v.rolling(20).mean().shift(1)
        rng = (h - l).replace(0, np.nan)
        df['body'] = (c - o).abs() / rng
        df['lowsh'] = (np.minimum(c, o) - l) / rng
        df['green'] = c >= o
        df['mom20'] = c.pct_change(20)
        out[sym] = df
    return out

def asof(df, ts):
    i = df.index.searchsorted(ts, side='right') - 1
    return df.iloc[i] if i >= 0 else None

def knife_recent(df, i):
    for k in range(max(0, i - 2), i + 1):
        r = df.iloc[k]
        if (not r['green']) and r['body'] > 0.7 and r['rvol'] > 1.2:
            return True
    return False

def stab_bar(r):
    if r['body'] < 0.3 and r['rvol'] < 0.9:
        return 'doji'
    if r['lowsh'] >= 0.5:
        return 'hammer'
    return None

def engulf(df, i):
    r, p = df.iloc[i], df.iloc[i - 1]
    return bool(r['green'] and (not p['green']) and r['Close'] > p['Open'] and r['rvol'] >= 1.0)

def scan_signals(data, ts, positions, pending, gates):
    """signal scan at close of ts -> new pending list entries"""
    gate_market, gate_china, gate_hibeta = gates['market'], gates['china'], gates['hibeta']
    if not gate_market:
        return []
    cands = []
    for t, df in data.items():
        if t not in SECTOR or t in positions or any(s['ticker'] == t for s in pending):
            continue
        if ts not in df.index:
            continue
        i = df.index.get_loc(ts)
        if i < 210:
            continue
        row = df.iloc[i]
        sec = SECTOR[t]
        if sec == 'China' and not gate_china:
            continue
        if not gate_hibeta and t in CRYPTO_EQ:
            continue
        mult = 0.5 if (sec == 'Quantum' and not gate_hibeta) else 1.0
        uptrend = row['Close'] > row['ma50'] and row['Close'] > row['ma200']
        sb = stab_bar(row) or ('engulf' if (i > 0 and engulf(df, i)) else None)
        score = row['mom20'] if not math.isnan(row['mom20']) else -9
        if uptrend and row['Low'] <= row['ma20'] * 1.02 and row['Close'] > row['ma20'] * 0.97 \
           and sb and not knife_recent(df, i):
            cands.append({'ticker': t, 'pb': 'P1', 'trigger': float(row['High']),
                          'stop': float(row['Low'] * 0.995), 'ttl': 2, 'mult': mult,
                          'score': float(score), 'signal_date': str(ts.date()), 'bar': sb})
            continue
        if row['Close'] > row['ma200'] and row['Close'] < row['ma20'] \
           and row['Low'] <= row['ma50'] * 1.02 and row['Close'] > row['ma50'] * 0.98 \
           and sb and not knife_recent(df, i):
            cands.append({'ticker': t, 'pb': 'P9', 'trigger': float(row['High']),
                          'stop': float(row['ma50'] - 1.5 * row['atr']), 'ttl': 2, 'mult': mult,
                          'score': float(score), 'signal_date': str(ts.date()), 'bar': sb})
            continue
        if row['bw'] <= row['bw_q25'] and row['Close'] > row['ub'] \
           and row['Close'] > row['hi20'] and row['rvol'] >= 1.5:
            cands.append({'ticker': t, 'pb': 'P2', 'trigger': None,
                          'stop': float(row['ma20']), 'ttl': 1, 'mult': mult,
                          'score': float(score), 'signal_date': str(ts.date()), 'bar': 'squeeze-breakout'})
            continue
        if row['Close'] > row['ma200'] * 0.98 and row['rsi'] < 30 \
           and df.iloc[i - 1]['Close'] < df.iloc[i - 1]['lb'] \
           and row['green'] and row['Close'] > row['lb'] and row['rvol'] >= 1.0:
            cands.append({'ticker': t, 'pb': 'P7', 'trigger': float(row['High']),
                          'stop': float(min(row['Low'], df.iloc[i - 1]['Low']) * 0.99),
                          'ttl': 2, 'mult': 0.5 * mult, 'score': float(score),
                          'signal_date': str(ts.date()), 'bar': 'panic-reversal'})
    cands.sort(key=lambda x: -x['score'])
    return cands[:10]

def equity_now(state, data, ts):
    val = state['cash']
    for t, pos in state['positions'].items():
        row = asof(data[t], ts)
        val += pos['shares'] * float(row['Close'])
    return val

def gates_for(data, ts):
    q = asof(data['QQQ'], ts)
    h_ = asof(data.get('^HSI'), ts) if '^HSI' in data else None
    k_ = asof(data.get('^KS11'), ts) if '^KS11' in data else None
    b_ = asof(data.get('BTC-USD'), ts) if 'BTC-USD' in data else None
    return {'market': bool(q['Close'] > q['ma50']),
            'china': bool(h_ is not None and h_['Close'] > h_['ma200']),
            'semi_mult': 1.0 if (k_ is not None and k_['Close'] > k_['ma50']) else 0.5,
            'hibeta': bool(b_ is not None and b_['Close'] > b_['ma20'])}

def process_day(state, data, ts):
    gates = gates_for(data, ts)
    # exits
    for t in list(state['positions'].keys()):
        df = data.get(t)
        if df is None or ts not in df.index:
            continue
        row = df.loc[ts]
        pos = state['positions'][t]
        if not pos['be'] and row['High'] >= pos['entry'] + 2 * pos['risk_ps']:
            pos['stop'] = max(pos['stop'], pos['entry'])
            pos['be'] = True
            pos['open_R'] = 0.0
        if not pos['trail'] and row['High'] >= pos['entry'] + pos['risk_ps']:
            pos['trail'] = True
        exit_px = None; reason = None
        if row['Low'] <= pos['stop']:
            exit_px = min(float(row['Open']), pos['stop']); reason = 'stop'
        elif pos['trail'] and row['Close'] < row['ma20']:
            exit_px = float(row['Close']); reason = 'ma20_trail'
        if exit_px is not None:
            exit_px *= (1 - SLIP)
            pnl = (exit_px - pos['entry']) * pos['shares']
            state['cash'] += pos['shares'] * exit_px
            state['trades'].append({'ticker': t, 'pb': pos['pb'], 'sector': SECTOR[t],
                                    'side': 'SELL', 'date': str(ts.date()),
                                    'price': round(exit_px, 4), 'shares': round(pos['shares'], 2),
                                    'pnl': round(pnl, 2),
                                    'R': round(pnl / pos['risk_usd'], 2) if pos['risk_usd'] else 0,
                                    'reason': reason, 'entry_date': pos['date'],
                                    'entry': round(pos['entry'], 4)})
            del state['positions'][t]
    # pending triggers
    still = []
    for sig in state['pending']:
        t = sig['ticker']; df = data.get(t)
        if t in state['positions'] or df is None or ts not in df.index:
            continue
        row = df.loc[ts]
        sig['ttl'] -= 1
        fired = False
        if sig['pb'] == 'P2':
            entry_px = float(row['Open']); fired = True
        elif float(row['High']) > sig['trigger']:
            entry_px = max(float(row['Open']), sig['trigger']); fired = True
        if fired:
            eq = equity_now(state, data, ts)
            tot_R = sum(p['open_R'] for p in state['positions'].values())
            by_sec = {}
            for tt, p in state['positions'].items():
                by_sec[SECTOR[tt]] = by_sec.get(SECTOR[tt], 0) + p['open_R']
            sec = SECTOR[t]
            mult = sig['mult'] * (gates['semi_mult'] if sec == 'Semis' else 1.0)
            if tot_R + mult <= MAX_TOTAL_R and by_sec.get(sec, 0) + mult <= MAX_SECTOR_R:
                stop = sig['stop']; risk_ps = entry_px - stop
                if risk_ps > 0:
                    risk_usd = eq * RISK_PCT * mult
                    shares = risk_usd / risk_ps
                    cap = min(NOTIONAL_CAP * eq, state['cash'])
                    if shares * entry_px > cap:
                        shares = cap / entry_px
                        risk_usd = shares * risk_ps
                    if shares > 0 and shares * entry_px > 1000:
                        fill = entry_px * (1 + SLIP)
                        state['cash'] -= shares * fill
                        state['positions'][t] = {
                            'shares': shares, 'entry': fill, 'stop': stop,
                            'risk_ps': fill - stop, 'risk_usd': risk_usd,
                            'open_R': risk_usd / (eq * RISK_PCT),
                            'pb': sig['pb'], 'date': str(ts.date()),
                            'be': False, 'trail': False}
                        state['trades'].append({'ticker': t, 'pb': sig['pb'], 'sector': sec,
                                                'side': 'BUY', 'date': str(ts.date()),
                                                'price': round(fill, 4), 'shares': round(shares, 2),
                                                'pnl': '', 'R': '', 'reason': f"signal {sig['signal_date']} {sig.get('bar','')}",
                                                'entry_date': '', 'entry': ''})
        elif sig['ttl'] > 0:
            still.append(sig)
    state['pending'] = still
    # new signals at close
    state['pending'].extend(scan_signals(data, ts, state['positions'], state['pending'], gates))
    eq = equity_now(state, data, ts)
    state['equity'].append([str(ts.date()), round(eq, 2)])
    state['last_processed'] = str(ts.date())
    return eq, gates

def completed_days(data):
    """trading days with a final bar (exclude today's bar if before 16:30 ET)"""
    idx = data['QQQ'].index
    now_et = datetime.now(ZoneInfo('America/New_York'))
    days = []
    for ts in idx:
        d = ts.date()
        if d > now_et.date():
            continue
        if d == now_et.date() and (now_et.hour, now_et.minute) < (16, 30):
            continue
        days.append(ts)
    return days

def save(state):
    json.dump(state, open(STATE_F, 'w'), indent=1)
    pd.DataFrame(state['trades']).to_csv(TRADES_F, index=False)

def report(state, data):
    ts_last = pd.Timestamp(state['last_processed'])
    eq = state['equity'][-1][1] if state['equity'] else START_CAP
    q0, s0 = state['baseline']['QQQ'], state['baseline']['SPY']
    q1 = float(asof(data['QQQ'], ts_last)['Close'])
    s1 = float(asof(data['SPY'], ts_last)['Close'])
    print(f"\n===== PAPER PORTFOLIO  {state['last_processed']} =====")
    print(f"Equity ${eq:,.0f}  ({(eq/START_CAP-1)*100:+.2f}%)   "
          f"QQQ {(q1/q0-1)*100:+.2f}%   SPY {(s1/s0-1)*100:+.2f}%   (baseline {BASELINE_DAY} close)")
    print(f"Cash ${state['cash']:,.0f}   positions {len(state['positions'])}   "
          f"pending {len(state['pending'])}   trades {len(state['trades'])}")
    if state['positions']:
        print('--- open positions ---')
        for t, p in state['positions'].items():
            last = float(asof(data[t], ts_last)['Close'])
            upnl = (last - p['entry']) * p['shares']
            print(f"  {t:8s} {p['pb']}  {p['date']}  entry {p['entry']:.2f}  last {last:.2f}  "
                  f"stop {p['stop']:.2f}  uPnL ${upnl:,.0f} ({upnl/p['risk_usd']:+.2f}R)"
                  f"{'  [BE]' if p['be'] else ''}{'  [trail]' if p['trail'] else ''}")
    if state['pending']:
        print('--- pending triggers ---')
        for s_ in state['pending']:
            trg = f"{s_['trigger']:.2f}" if s_['trigger'] else 'next open'
            print(f"  {s_['ticker']:8s} {s_['pb']}  trigger>{trg}  stop {s_['stop']:.2f}  ttl {s_['ttl']}  ({s_.get('bar','')})")
    recent = [t for t in state['trades'] if t['date'] == state['last_processed']]
    if recent:
        print('--- today\'s fills ---')
        for t in recent:
            print(f"  {t['side']:4s} {t['ticker']:8s} {t['pb']}  {t['shares']} @ {t['price']}"
                  + (f"  PnL ${t['pnl']:,} ({t['R']}R) {t['reason']}" if t['side'] == 'SELL' else f"  [{t['reason']}]"))

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'run'
    data = load_data()
    if cmd == 'init':
        if os.path.exists(STATE_F):
            print('State exists — refusing to overwrite. Delete paper_playbook_state.json to re-init.')
            return
        base_ts = pd.Timestamp(BASELINE_DAY)
        state = {'start_cap': START_CAP, 'created': str(date.today()),
                 'baseline': {'date': BASELINE_DAY,
                              'QQQ': float(asof(data['QQQ'], base_ts)['Close']),
                              'SPY': float(asof(data['SPY'], base_ts)['Close'])},
                 'cash': START_CAP, 'positions': {}, 'pending': [],
                 'trades': [], 'equity': [], 'last_processed': BASELINE_DAY}
        # seed signals from baseline close
        gates = gates_for(data, base_ts)
        state['pending'] = scan_signals(data, base_ts, {}, [], gates)
        save(state)
        print(f"Initialized. Baseline {BASELINE_DAY}: QQQ {state['baseline']['QQQ']:.2f}  SPY {state['baseline']['SPY']:.2f}")
        print(f"Seeded {len(state['pending'])} pending signals:")
        for s_ in state['pending']:
            trg = f"{s_['trigger']:.2f}" if s_['trigger'] else 'next open'
            print(f"  {s_['ticker']:8s} {s_['pb']} trigger>{trg} stop {s_['stop']:.2f} ({s_.get('bar','')})")
        return
    state = json.load(open(STATE_F))
    last = pd.Timestamp(state['last_processed'])
    todo = [ts for ts in completed_days(data) if ts > last and ts <= pd.Timestamp(END_DAY)]
    if not todo:
        print('No completed trading days to process.')
        report(state, data)
        return
    for ts in todo:
        eq, gates = process_day(state, data, ts)
        g = ''.join(['M' if gates['market'] else 'm', 'C' if gates['china'] else 'c',
                     'B' if gates['hibeta'] else 'b'])
        print(f"processed {ts.date()}  equity ${eq:,.0f}  gates[{g}] semis x{gates['semi_mult']}")
    save(state)
    report(state, data)
    if state['last_processed'] >= END_DAY:
        print('\n*** ONE-MONTH PERIOD COMPLETE — produce final comparison report. ***')

if __name__ == '__main__':
    main()
