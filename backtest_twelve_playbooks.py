# -*- coding: utf-8 -*-
"""
Backtest of the 12-playbook system (mechanizable subset), YTD 2026.
Capital $3M. Long only, no leverage, no commissions, 5bp slippage per side.

Implemented:
  P1  pullback-to-MA20 stabilization entry (doji/hammer/engulf bar, knife filter)
  P9  first MA50 touch after MA20 loss (same bar logic, wider stop)
  P2  BB-squeeze breakout with RVOL>=1.5 (stop = MA20)
  P7  panic reversal at lower band (quality gate: above MA200, RSI<25, reversal bar; half risk)
  P8  exit discipline: hard stop -> breakeven at +2R -> MA20-close trail once >= +1R
  P10 sizing: risk 1% of equity per trade, <=6R total open risk, <=2R per sector,
      25% equity notional cap per position, no leverage
  P3/gate: no new entries when QQQ closes below MA50
  P12 gates: HSI<MA200 blocks China; KOSPI<MA50 halves Semis risk; BTC<MA20 blocks
      crypto-equity/miners and halves Quantum
Not backtestable (no historical data): P5 whale flow, P4/P6 earnings scripts, P11 pyramiding (skipped).
"""
import json, math, sys, warnings
import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings('ignore')
sys.stdout.reconfigure(encoding='utf-8')

START_CAP = 3_000_000.0
RISK_PCT = 0.01          # 1% of equity per trade (1R)
MAX_TOTAL_R = 6.0
MAX_SECTOR_R = 2.0
NOTIONAL_CAP = 0.25      # per position
SLIP = 0.0005
BT_START = '2026-01-02'
BT_END = '2026-08-18'
DATA_START = '2025-01-01'

plans = json.load(open('trade_plans_2026-08-18.json', encoding='utf-8'))['plans']
SECTOR = {t: p['sector'] for t, p in plans.items()}
TICKERS = list(SECTOR.keys())
CRYPTO_EQ = [t for t, s in SECTOR.items() if s == 'Crypto' and not t.endswith('-USD')]
IDX = ['QQQ', '^HSI', '^KS11', 'BTC-USD']

print(f'Universe: {len(TICKERS)} tickers')

# ---------- data ----------
all_syms = sorted(set(TICKERS + IDX))
raw = yf.download(all_syms, start=DATA_START, end='2026-08-19', interval='1d',
                  group_by='ticker', auto_adjust=True, threads=True, progress=False)

qqq = raw['QQQ'].dropna(subset=['Close'])
cal = qqq.loc[BT_START:BT_END].index  # trading calendar
print(f'Calendar: {cal[0].date()} -> {cal[-1].date()}  ({len(cal)} days)')

def prep(sym):
    try:
        df = raw[sym].dropna(subset=['Close']).copy()
    except Exception:
        return None
    if len(df) < 220:
        return None
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
    return df

data = {}
for t in TICKERS:
    df = prep(t)
    if df is not None:
        data[t] = df
missing = sorted(set(TICKERS) - set(data.keys()))
print(f'Prepared {len(data)} tickers, missing/short-history: {missing}')

qqq_full = prep('QQQ')
hsi = prep('^HSI')
kospi = prep('^KS11')
btc = prep('BTC-USD')

def asof(df, ts):
    """last row with index <= ts"""
    idx = df.index.searchsorted(ts, side='right') - 1
    return df.iloc[idx] if idx >= 0 else None

def knife_recent(df, i):
    """big red body + volume within last 3 bars -> no catching"""
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
    return r['green'] and (not p['green']) and r['Close'] > p['Open'] and r['rvol'] >= 1.0

# ---------- portfolio state ----------
cash = START_CAP
positions = {}   # ticker -> dict
pending = []     # signals awaiting trigger
closed = []
equity_curve = []

def equity_now(ts):
    val = cash
    for t, pos in positions.items():
        row = asof(data[t], ts)
        val += pos['shares'] * row['Close']
    return val

def open_risk_R():
    tot, by_sec = 0.0, {}
    for t, pos in positions.items():
        r = pos['open_R']
        tot += r
        by_sec[SECTOR[t]] = by_sec.get(SECTOR[t], 0) + r
    return tot, by_sec

for ts in cal:
    # ---- gates (use prior info up to today's close for entries executed tomorrow;
    #      for simplicity gate on today's values) ----
    q = asof(qqq_full, ts)
    gate_market = q['Close'] > q['ma50']
    h_ = asof(hsi, ts)
    gate_china = (h_ is not None) and (h_['Close'] > h_['ma200'])
    k_ = asof(kospi, ts)
    semi_mult = 1.0 if (k_ is not None and k_['Close'] > k_['ma50']) else 0.5
    b_ = asof(btc, ts)
    gate_hibeta = (b_ is not None) and (b_['Close'] > b_['ma20'])

    # ---- manage exits ----
    for t in list(positions.keys()):
        df = data[t]
        if ts not in df.index:
            continue
        i = df.index.get_loc(ts)
        row = df.iloc[i]
        pos = positions[t]
        # breakeven after +2R
        if not pos['be'] and row['High'] >= pos['entry'] + 2 * pos['risk_ps']:
            pos['stop'] = max(pos['stop'], pos['entry'])
            pos['be'] = True
            pos['open_R'] = 0.0
        # trail active flag after +1R
        if not pos['trail'] and row['High'] >= pos['entry'] + pos['risk_ps']:
            pos['trail'] = True
        exit_px = None; reason = None
        if row['Low'] <= pos['stop']:
            exit_px = min(row['Open'], pos['stop']); reason = 'stop'
        elif pos['trail'] and row['Close'] < row['ma20']:
            exit_px = row['Close']; reason = 'ma20_trail'
        if exit_px is not None:
            exit_px *= (1 - SLIP)
            pnl = (exit_px - pos['entry']) * pos['shares']
            cash += pos['shares'] * exit_px
            closed.append({'ticker': t, 'pb': pos['pb'], 'sector': SECTOR[t],
                           'entry_date': pos['date'], 'exit_date': ts.date(),
                           'entry': pos['entry'], 'exit': exit_px, 'pnl': pnl,
                           'R': pnl / pos['risk_usd'] if pos['risk_usd'] else 0,
                           'reason': reason})
            del positions[t]

    # ---- execute pending triggers ----
    still = []
    for sig in pending:
        t = sig['ticker']; df = data[t]
        if t in positions or ts not in df.index:
            continue
        i = df.index.get_loc(ts)
        row = df.iloc[i]
        sig['ttl'] -= 1
        fired = False
        if sig['pb'] == 'P2':
            entry_px = row['Open']
            fired = True
        elif row['High'] > sig['trigger']:
            entry_px = max(row['Open'], sig['trigger'])
            fired = True
        if fired:
            eq = equity_now(ts)
            tot_R, by_sec = open_risk_R()
            sec = SECTOR[t]
            mult = sig['mult']
            if sec == 'Semis':
                mult *= semi_mult
            if tot_R + mult <= MAX_TOTAL_R and by_sec.get(sec, 0) + mult <= MAX_SECTOR_R:
                stop = sig['stop']
                risk_ps = entry_px - stop
                if risk_ps > 0:
                    risk_usd = eq * RISK_PCT * mult
                    shares = risk_usd / risk_ps
                    notional = shares * entry_px
                    cap = min(NOTIONAL_CAP * eq, cash)
                    if notional > cap:
                        shares = cap / entry_px
                        risk_usd = shares * risk_ps
                    if shares > 0 and shares * entry_px > 1000:
                        fill = entry_px * (1 + SLIP)
                        cash -= shares * fill
                        positions[t] = {'shares': shares, 'entry': fill, 'stop': stop,
                                        'risk_ps': fill - stop, 'risk_usd': risk_usd,
                                        'open_R': risk_usd / (eq * RISK_PCT),
                                        'pb': sig['pb'], 'date': ts.date(),
                                        'be': False, 'trail': False}
        elif sig['ttl'] > 0:
            still.append(sig)
    pending = still

    # ---- scan for new signals at today's close (trigger tomorrow) ----
    if gate_market:
        cands = []
        for t, df in data.items():
            if t in positions or any(s['ticker'] == t for s in pending):
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
            if not gate_hibeta and (t in CRYPTO_EQ):
                continue
            mult = 1.0
            if sec == 'Quantum' and not gate_hibeta:
                mult = 0.5
            uptrend = row['Close'] > row['ma50'] and row['Close'] > row['ma200']
            sb = stab_bar(row) or ('engulf' if (i > 0 and engulf(df, i)) else None)
            # P1: pullback to MA20
            if uptrend and row['Low'] <= row['ma20'] * 1.02 and row['Close'] > row['ma20'] * 0.97 \
               and sb and not knife_recent(df, i):
                cands.append({'ticker': t, 'pb': 'P1', 'trigger': row['High'],
                              'stop': row['Low'] * 0.995, 'ttl': 2, 'mult': mult,
                              'score': row['mom20']})
                continue
            # P9: first MA50 touch after MA20 loss
            if row['Close'] > row['ma200'] and row['Close'] < row['ma20'] \
               and row['Low'] <= row['ma50'] * 1.02 and row['Close'] > row['ma50'] * 0.98 \
               and sb and not knife_recent(df, i):
                cands.append({'ticker': t, 'pb': 'P9', 'trigger': row['High'],
                              'stop': row['ma50'] - 1.5 * row['atr'], 'ttl': 2, 'mult': mult,
                              'score': row['mom20']})
                continue
            # P2: squeeze breakout (enter next open)
            if row['bw'] <= row['bw_q25'] * 1.0 and row['Close'] > row['ub'] \
               and row['Close'] > row['hi20'] and row['rvol'] >= 1.5:
                cands.append({'ticker': t, 'pb': 'P2', 'trigger': None,
                              'stop': row['ma20'], 'ttl': 1, 'mult': mult,
                              'score': row['mom20']})
                continue
            # P7: panic reversal at lower band (quality: above MA200), half risk
            if row['Close'] > row['ma200'] * 0.98 and row['rsi'] < 30 \
               and df.iloc[i - 1]['Close'] < df.iloc[i - 1]['lb'] \
               and row['green'] and row['Close'] > row['lb'] and row['rvol'] >= 1.0:
                cands.append({'ticker': t, 'pb': 'P7', 'trigger': row['High'],
                              'stop': min(row['Low'], df.iloc[i - 1]['Low']) * 0.99,
                              'ttl': 2, 'mult': 0.5 * mult, 'score': row['mom20']})
        cands.sort(key=lambda x: -(x['score'] if not math.isnan(x['score']) else -9))
        pending.extend(cands[:10])

    equity_curve.append((ts, equity_now(ts)))

# liquidate remaining at last close (mark-to-market only for report)
eq = pd.Series({ts: v for ts, v in equity_curve})

# ---------- stats ----------
ret_total = eq.iloc[-1] / START_CAP - 1
daily = eq.pct_change().dropna()
sharpe = daily.mean() / daily.std() * math.sqrt(252) if daily.std() > 0 else 0
dd = (eq / eq.cummax() - 1).min()
tr = pd.DataFrame(closed)
open_mtm = []
for t, pos in positions.items():
    row = asof(data[t], cal[-1])
    open_mtm.append({'ticker': t, 'pb': pos['pb'], 'entry_date': pos['date'],
                     'entry': pos['entry'], 'last': row['Close'],
                     'pnl': (row['Close'] - pos['entry']) * pos['shares'],
                     'R': (row['Close'] - pos['entry']) * pos['shares'] / pos['risk_usd']})

qqq_ret = qqq_full.loc[BT_START:BT_END, 'Close']
qqq_ytd = qqq_ret.iloc[-1] / qqq_ret.iloc[0] - 1
spy = yf.download('SPY', start=BT_START, end='2026-08-19', progress=False)['Close'].squeeze()
spy_ytd = float(spy.iloc[-1] / spy.iloc[0] - 1)

print('\n================ RESULTS ================')
print(f'Final equity  : ${eq.iloc[-1]:,.0f}  (start $3,000,000)')
print(f'Total return  : {ret_total*100:+.2f}%   | QQQ YTD {qqq_ytd*100:+.2f}%  SPY YTD {spy_ytd*100:+.2f}%')
print(f'Max drawdown  : {dd*100:.2f}%   Sharpe(daily): {sharpe:.2f}')
print(f'Closed trades : {len(tr)}   open positions: {len(positions)}')
if len(tr):
    win = tr[tr.pnl > 0]
    print(f'Win rate      : {len(win)/len(tr)*100:.1f}%   avg win {win.R.mean():+.2f}R  avg loss {tr[tr.pnl<=0].R.mean():+.2f}R')
    pf = win.pnl.sum() / abs(tr[tr.pnl <= 0].pnl.sum()) if len(tr[tr.pnl <= 0]) else float('inf')
    print(f'Profit factor : {pf:.2f}   total closed PnL ${tr.pnl.sum():,.0f}')
    print('\n--- by playbook ---')
    print(tr.groupby('pb').agg(n=('pnl', 'size'), win=('pnl', lambda x: (x > 0).mean()),
                               pnl=('pnl', 'sum'), avgR=('R', 'mean')).round(2).to_string())
    print('\n--- by sector ---')
    print(tr.groupby('sector').agg(n=('pnl', 'size'), pnl=('pnl', 'sum')).round(0)
          .sort_values('pnl', ascending=False).to_string())
    print('\n--- exit reasons ---')
    print(tr.groupby('reason').agg(n=('pnl', 'size'), pnl=('pnl', 'sum')).round(0).to_string())
    print('\n--- top 10 trades ---')
    print(tr.nlargest(10, 'pnl')[['ticker', 'pb', 'entry_date', 'exit_date', 'R', 'pnl']].round(2).to_string(index=False))
    print('\n--- worst 10 trades ---')
    print(tr.nsmallest(10, 'pnl')[['ticker', 'pb', 'entry_date', 'exit_date', 'R', 'pnl']].round(2).to_string(index=False))
if open_mtm:
    om = pd.DataFrame(open_mtm)
    print(f'\n--- open positions (MTM) ---  unrealized ${om.pnl.sum():,.0f}')
    print(om.round(2).to_string(index=False))

print('\n--- monthly returns ---')
m = eq.resample('ME').last().pct_change()
m.iloc[0] = eq.resample('ME').last().iloc[0] / START_CAP - 1
print((m * 100).round(2).to_string())

eq.to_csv('backtest_equity_2026.csv')
tr.to_csv('backtest_trades_2026.csv', index=False)
print('\nSaved: backtest_equity_2026.csv, backtest_trades_2026.csv')

# chart
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 1, figsize=(12, 8), sharex=True,
                           gridspec_kw={'height_ratios': [3, 1]})
    ax[0].plot(eq.index, eq / START_CAP * 100 - 100, label='12-Playbook system', lw=2)
    qn = qqq_ret / qqq_ret.iloc[0] * 100 - 100
    ax[0].plot(qn.index, qn.values, label='QQQ', alpha=0.7)
    sn = spy / spy.iloc[0] * 100 - 100
    ax[0].plot(sn.index, sn.values.ravel(), label='SPY', alpha=0.7)
    ax[0].set_ylabel('Return %'); ax[0].legend(); ax[0].grid(alpha=0.3)
    ax[0].set_title(f'12-Playbook backtest YTD 2026  ($3M start, final ${eq.iloc[-1]/1e6:.2f}M, {ret_total*100:+.1f}%)')
    dds = (eq / eq.cummax() - 1) * 100
    ax[1].fill_between(dds.index, dds.values, 0, color='red', alpha=0.4)
    ax[1].set_ylabel('Drawdown %'); ax[1].grid(alpha=0.3)
    plt.tight_layout(); plt.savefig('backtest_2026_curve.png', dpi=110)
    print('Saved: backtest_2026_curve.png')
except Exception as e:
    print('chart failed:', e)
