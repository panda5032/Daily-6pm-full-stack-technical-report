"""
Playbook Backtest 2026 YTD — mechanical versions of the 12-playbook system
(打法1/2/3/7/8/9; 打法4事件驱动 and 11/12仓位管理层 excluded — not price-testable)
plus two classic baselines and buy-hold benchmarks.

Universe: AI_Portfolios.xlsx via technical_macd_volume_strategy.load_portfolio().
Window: entries 2026-01-01 → today; data warmup from 2025-03 for MA200.

Output: backtest_playbooks_<date>.md + .json in this folder.
Signals research only — not financial advice, no live orders.
"""

import json
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

HERE = Path(__file__).parent
TODAY = datetime.now().strftime("%Y-%m-%d")
BT_START = "2026-01-01"          # first allowed entry date (default single-year run)
DATA_START = "2023-03-01"        # warmup for MA200 ahead of the 2024 window

# multi-year windows: (label, first entry date, hard end exclusive)
WINDOWS = [
    ("2024",     "2024-01-01", "2025-01-01"),
    ("2025",     "2025-01-01", "2026-01-01"),
    ("2026 YTD", "2026-01-01", None),
]

from technical_macd_volume_strategy import load_portfolio  # noqa: E402


# ────────────────────────── data ──────────────────────────
def get_universe():
    sectors = load_portfolio()
    tickers, sector_of = [], {}
    for sec, tks in sectors.items():
        for t in tks:
            if t not in sector_of:
                sector_of[t] = sec
                tickers.append(t)
    return tickers, sector_of


def download_all(tickers):
    """Batched daily OHLCV download → {ticker: df}."""
    out = {}
    for i in range(0, len(tickers), 40):
        batch = tickers[i:i + 40]
        raw = yf.download(batch, start=DATA_START, interval="1d",
                          auto_adjust=True, group_by="ticker",
                          progress=False, threads=True)
        for t in batch:
            try:
                df = raw[t].dropna(subset=["Close"]) if len(batch) > 1 else raw.dropna(subset=["Close"])
            except (KeyError, TypeError):
                continue
            if len(df) >= 220:
                out[t] = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    return out


def add_indicators(df):
    c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]
    df["ma20"] = c.rolling(20).mean()
    df["ma50"] = c.rolling(50).mean()
    df["ma200"] = c.rolling(200).mean()
    sd = c.rolling(20).std()
    df["bb_up"] = df["ma20"] + 2 * sd
    df["bb_lo"] = df["ma20"] - 2 * sd
    df["pctb"] = (c - df["bb_lo"]) / (df["bb_up"] - df["bb_lo"])
    df["bw"] = (df["bb_up"] - df["bb_lo"]) / df["ma20"] * 100
    df["bw_q20"] = df["bw"].rolling(120).quantile(0.20)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()
    delta = c.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df["rsi"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    df["vol20"] = v.rolling(20).mean()
    df["ma60"] = c.rolling(60).mean()
    df["vol5"] = v.rolling(5).mean()
    df["vol60"] = v.rolling(60).mean()
    df["hi20"] = h.rolling(20).max().shift(1)
    df["ret20"] = c.pct_change(20)
    df["ema12"] = c.ewm(span=12).mean()
    df["ema26"] = c.ewm(span=26).mean()
    df["macd"] = df["ema12"] - df["ema26"]
    df["macds"] = df["macd"].ewm(span=9).mean()
    return df


# ────────────────────────── trade engine ──────────────────────────
def run_trades(df, entry_fn, exit_fn, label, start=BT_START, end=None):
    """Walk bars; entry_fn(df,i)->entry dict|None when flat, exit_fn(df,i,pos)->bool when long.
    Entries only in [start, end). Entry executed at close of signal bar; open
    positions are marked to the last bar inside the window."""
    if end is not None:
        df = df[df.index < pd.Timestamp(end)]
    if len(df) < 220:
        return []
    trades, pos = [], None
    idx = df.index
    start_i = int(np.searchsorted(idx, pd.Timestamp(start)))
    for i in range(max(start_i, 210), len(df)):
        if pos is None:
            e = entry_fn(df, i)
            if e is not None:
                pos = {"entry_i": i, "entry": float(df["Close"].iloc[i]), **e}
        else:
            if exit_fn(df, i, pos):
                px = float(df["Close"].iloc[i])
                trades.append({"strategy": label,
                               "entry_date": str(idx[pos["entry_i"]].date()),
                               "exit_date": str(idx[i].date()),
                               "days": i - pos["entry_i"],
                               "ret": px / pos["entry"] - 1})
                pos = None
    if pos is not None:  # mark open trade to last close in window
        px = float(df["Close"].iloc[-1])
        trades.append({"strategy": label,
                       "entry_date": str(idx[pos["entry_i"]].date()),
                       "exit_date": "OPEN" if end is None else f"EOW {idx[-1].date()}",
                       "days": len(df) - 1 - pos["entry_i"],
                       "ret": px / pos["entry"] - 1})
    return trades


def _up(df, i):
    return df["Close"].iloc[i] > df["ma50"].iloc[i] and (
        df["Close"].iloc[i] > df["ma200"].iloc[i] or df["ma50"].iloc[i] > df["ma50"].iloc[i - 10])


# 打法1 回踩企稳: uptrend, pulled back to ±3.5% of MA20 within last 3 bars,
# stabilization = close takes out prior bar high. Exit: first close < MA20 -1%,
# or stop = stabilization bar low - 0.5*ATR.
def pb1_entry(df, i):
    if not _up(df, i):
        return None
    near = [abs(df["Close"].iloc[j] / df["ma20"].iloc[j] - 1) <= 0.035 and
            df["Close"].iloc[j] < df["Close"].iloc[j - 5] for j in (i - 2, i - 1, i)]
    if not any(near):
        return None
    if df["Close"].iloc[i] > df["High"].iloc[i - 1]:
        return {"stop": float(df["Low"].iloc[i] - 0.5 * df["atr"].iloc[i])}
    return None


def pb1_exit(df, i, pos):
    c = df["Close"].iloc[i]
    return c < pos["stop"] or c < df["ma20"].iloc[i] * 0.99


# 打法2 缩量平台突破: squeeze (BW ≤ 120d 20th pct within last 5 bars), close > 20d high,
# volume ≥ 1.5×avg, above MA50. Exit: first close < MA20.
def pb2_entry(df, i):
    sq = (df["bw"].iloc[i - 5:i + 1] <= df["bw_q20"].iloc[i - 5:i + 1]).any()
    if (sq and df["Close"].iloc[i] > df["hi20"].iloc[i]
            and df["Volume"].iloc[i] >= 1.5 * df["vol20"].iloc[i]
            and df["Close"].iloc[i] > df["ma50"].iloc[i]):
        return {}
    return None


def pb2_exit(df, i, pos):
    return df["Close"].iloc[i] < df["ma20"].iloc[i]


# 打法7 下轨恐慌反转: capitulation (close<lower band & RSI<32) in last 5 bars,
# reversal bar closes above prior high. Target midline, stop = setup low, 15-bar time stop.
def pb7_entry(df, i):
    win = range(i - 5, i)
    cap = [j for j in win if df["Close"].iloc[j] < df["bb_lo"].iloc[j] and df["rsi"].iloc[j] < 32]
    if cap and df["Close"].iloc[i] > df["High"].iloc[i - 1]:
        return {"stop": float(df["Low"].iloc[i - 5:i + 1].min())}
    return None


def pb7_exit(df, i, pos):
    c = df["Close"].iloc[i]
    return (c >= df["ma20"].iloc[i] or c < pos["stop"]
            or i - pos["entry_i"] >= 15)


# 打法8 带行持有: %B crosses ≥0.8 in uptrend (fresh: %B<0.8 for prior 10 bars at least once...
# simple: first %B≥0.8 after being <0.8). Exit: first close < MA20 on volume ≥1.2×avg,
# or close < MA20 two consecutive bars.
def pb8_entry(df, i):
    if (df["pctb"].iloc[i] >= 0.8 and df["pctb"].iloc[i - 1] < 0.8
            and df["Close"].iloc[i] > df["ma20"].iloc[i] > df["ma50"].iloc[i]):
        return {}
    return None


def pb8_exit(df, i, pos):
    c, ma = df["Close"].iloc[i], df["ma20"].iloc[i]
    heavy = df["Volume"].iloc[i] >= 1.2 * df["vol20"].iloc[i]
    two = df["Close"].iloc[i - 1] < df["ma20"].iloc[i - 1]
    return c < ma and (heavy or two)


# 打法9 首回踩MA50: below MA20 but within ±2% of rising MA50, stabilization bar.
# Stop = MA50 - 1.5*ATR at entry. Exit: close < stop, or close < MA20 after recovering above it.
def pb9_entry(df, i):
    if (df["Close"].iloc[i - 1] < df["ma20"].iloc[i - 1]
            and abs(df["Close"].iloc[i] / df["ma50"].iloc[i] - 1) <= 0.02
            and df["ma50"].iloc[i] > df["ma50"].iloc[i - 10]
            and df["Close"].iloc[i] > df["High"].iloc[i - 1]):
        return {"stop": float(df["ma50"].iloc[i] - 1.5 * df["atr"].iloc[i]),
                "recovered": False}
    return None


def pb9_exit(df, i, pos):
    c = df["Close"].iloc[i]
    if c > df["ma20"].iloc[i]:
        pos["recovered"] = True
    return c < pos["stop"] or (pos["recovered"] and c < df["ma20"].iloc[i])


# 打法9改 质量闸: same as 打法9 but only above a rising MA200 (proxy for the
# LT-quality gate the live system applies via long_term_strategy scores).
def pb9b_entry(df, i):
    if (df["Close"].iloc[i] > df["ma200"].iloc[i]
            and df["ma200"].iloc[i] > df["ma200"].iloc[i - 20]):
        return pb9_entry(df, i)
    return None


# ═══════════ 抄底六式 (六大成熟抄底技巧 cheat-sheet, added 2026-08-20) ═══════════
# 抄底1 MACD底背离: price trough undercuts prior trough but MACD (below zero) holds
# higher; trigger = MACD golden cross. Exit: MACD dead cross / stop / 40 bars.
def cd1_entry(df, i):
    if not (df["macd"].iloc[i] > df["macds"].iloc[i]
            and df["macd"].iloc[i - 1] <= df["macds"].iloc[i - 1]):
        return None
    c = df["Close"]
    seg = c.iloc[i - 8:i + 1]
    j = i - 8 + int(np.argmin(seg.values))
    prev = c.iloc[i - 60:j - 5]
    if len(prev) < 10:
        return None
    pj = i - 60 + int(np.argmin(prev.values))
    if (c.iloc[j] < c.iloc[pj]                      # 股价创新低
            and df["macd"].iloc[j] > df["macd"].iloc[pj]   # 指标不创新低
            and df["macd"].iloc[j] < 0):
        return {"stop": float(df["Low"].iloc[i - 10:i + 1].min() - 0.5 * df["atr"].iloc[i])}
    return None


def cd1_exit(df, i, pos):
    dead = (df["macd"].iloc[i] < df["macds"].iloc[i]
            and df["macd"].iloc[i - 1] >= df["macds"].iloc[i - 1])
    return dead or df["Close"].iloc[i] < pos["stop"] or i - pos["entry_i"] >= 40


# 抄底2 均线支撑(20/60日线): pullback tags MA60 from above, stabilization bar.
# Exit: target = prior 20d high, stop = MA60 - 1×ATR, 30-bar time stop.
def cd2_entry(df, i):
    ma60 = df["ma60"].iloc[i]
    if np.isnan(ma60) or df["Close"].iloc[i] < ma60:
        return None
    touched = (df["Low"].iloc[i - 1:i + 1] <= df["ma60"].iloc[i - 1:i + 1] * 1.015).any()
    if (touched and df["Close"].iloc[i] < df["Close"].iloc[i - 5]
            and df["ma60"].iloc[i] >= df["ma60"].iloc[i - 10] * 0.99
            and df["Close"].iloc[i] > df["High"].iloc[i - 1]):
        return {"target": float(df["hi20"].iloc[i])}
    return None


def cd2_exit(df, i, pos):
    c = df["Close"].iloc[i]
    return (c < df["ma60"].iloc[i] - df["atr"].iloc[i] or c >= pos["target"]
            or i - pos["entry_i"] >= 30)


# 抄底3 W双底: second trough holds ≥97% of first, breakout closes above the
# middle peak on ≥1.3× volume. Target = neckline + depth, stop = trough2.
def cd3_entry(df, i):
    c = df["Close"]
    seg2 = c.iloc[i - 15:i - 2]
    if len(seg2) < 5:
        return None
    j2 = i - 15 + int(np.argmin(seg2.values))
    seg1 = c.iloc[i - 60:j2 - 7]
    if len(seg1) < 10:
        return None
    j1 = i - 60 + int(np.argmin(seg1.values))
    t1, t2 = float(c.iloc[j1]), float(c.iloc[j2])
    neck = float(c.iloc[j1:j2 + 1].max())
    if (t2 >= t1 * 0.97 and neck > t2 * 1.03
            and c.iloc[i] > neck and c.iloc[i - 1] <= neck
            and df["Volume"].iloc[i] >= 1.3 * df["vol20"].iloc[i]):
        return {"stop": t2, "target": neck + (neck - min(t1, t2))}
    return None


def cd3_exit(df, i, pos):
    c = df["Close"].iloc[i]
    return c < pos["stop"] or c >= pos["target"] or i - pos["entry_i"] >= 40


# 抄底4 KDJ/RSI超卖: RSI dipped <25 within last 3 bars, now ticking up on an
# up close. Quick-rebound trade: exit at RSI≥50 / MA20 / stop / 10 bars.
def cd4_entry(df, i):
    if ((df["rsi"].iloc[i - 3:i] < 25).any()
            and df["rsi"].iloc[i] > df["rsi"].iloc[i - 1]
            and df["Close"].iloc[i] > df["Close"].iloc[i - 1]):
        return {"stop": float(df["Low"].iloc[i - 5:i + 1].min())}
    return None


def cd4_exit(df, i, pos):
    c = df["Close"].iloc[i]
    return (df["rsi"].iloc[i] >= 50 or c >= df["ma20"].iloc[i]
            or c < pos["stop"] or i - pos["entry_i"] >= 10)


# 抄底5 地量地价: 5d volume ≤55% of 60d avg near the 60d low, then a
# ≥1.8×-volume up candle = 入场时机. Target = prior 20d high.
def cd5_entry(df, i):
    if np.isnan(df["vol60"].iloc[i - 1]) or df["vol60"].iloc[i - 1] <= 0:
        return None
    lo60 = df["Close"].iloc[i - 60:i].min()
    if (df["vol5"].iloc[i - 1] <= 0.55 * df["vol60"].iloc[i - 1]
            and df["Close"].iloc[i - 1] <= lo60 * 1.05
            and df["Close"].iloc[i] > df["Open"].iloc[i]
            and df["Close"].iloc[i] / df["Close"].iloc[i - 1] - 1 >= 0.01
            and df["Volume"].iloc[i] >= 1.8 * df["vol20"].iloc[i]):
        return {"stop": float(df["Low"].iloc[i] - 0.5 * df["atr"].iloc[i]),
                "target": float(df["hi20"].iloc[i])}
    return None


def cd5_exit(df, i, pos):
    c = df["Close"].iloc[i]
    return c < pos["stop"] or c >= pos["target"] or i - pos["entry_i"] >= 30


# 抄底6 金针探底: after weakness, long lower wick ≥2×body and ≥1.2×ATR with a
# close in the upper half of the range. 轻仓试错: tight stop under the wick,
# target = MA20 repair, 12-bar time stop.
def cd6_entry(df, i):
    o, h, l, c = (df["Open"].iloc[i], df["High"].iloc[i],
                  df["Low"].iloc[i], df["Close"].iloc[i])
    body = abs(c - o)
    wick = min(o, c) - l
    rng = (h - l) or 1e-9
    weak = c < df["ma20"].iloc[i] or df["Close"].iloc[i] / df["Close"].iloc[i - 5] - 1 <= -0.05
    if (wick >= 2 * body and wick >= 1.2 * df["atr"].iloc[i]
            and (c - l) / rng >= 0.5 and weak):
        return {"stop": float(l - 0.25 * df["atr"].iloc[i])}
    return None


def cd6_exit(df, i, pos):
    c = df["Close"].iloc[i]
    return (c < pos["stop"] or c >= df["ma20"].iloc[i]
            or i - pos["entry_i"] >= 12)


# ═══════════ 逃顶五式 (顶底结构 cheat-sheet, added 2026-08-20) ═══════════
# Detectors: sig(df, i) -> bool, fired at bar i's close. Used two ways:
# (a) event study of forward returns, (b) exit overlays on 打法8 entries.

# 逃顶1 M双顶: two peaks within 3% of each other, close breaks the neckline
# (lowest close between the peaks) today after holding it yesterday.
def t1_mtop(df, i):
    c = df["Close"]
    seg2 = c.iloc[i - 15:i - 2]
    if len(seg2) < 5:
        return False
    j2 = i - 15 + int(np.argmax(seg2.values))
    seg1 = c.iloc[i - 60:j2 - 7]
    if len(seg1) < 10:
        return False
    j1 = i - 60 + int(np.argmax(seg1.values))
    p1, p2 = float(c.iloc[j1]), float(c.iloc[j2])
    neck = float(c.iloc[j1:j2 + 1].min())
    return (abs(p2 / p1 - 1) <= 0.03 and neck < min(p1, p2) * 0.97
            and float(c.iloc[i]) < neck and float(c.iloc[i - 1]) >= neck)


# 逃顶2 头肩顶: head ≥3% above both shoulders (shoulders within 10% of each
# other), close breaks below the lower of the two troughs (neckline).
def t2_hstop(df, i):
    c = df["Close"]
    seg_h = c.iloc[i - 60:i - 8]
    if len(seg_h) < 20:
        return False
    jh = i - 60 + int(np.argmax(seg_h.values))
    seg_l = c.iloc[max(0, i - 100):jh - 5]
    seg_r = c.iloc[jh + 5:i + 1]
    if len(seg_l) < 8 or len(seg_r) < 5:
        return False
    jl = max(0, i - 100) + int(np.argmax(seg_l.values))
    jr = jh + 5 + int(np.argmax(seg_r.values))
    head, ls, rs = float(c.iloc[jh]), float(c.iloc[jl]), float(c.iloc[jr])
    neck = min(float(c.iloc[jl:jh + 1].min()), float(c.iloc[jh:jr + 1].min()))
    return (head > ls * 1.03 and head > rs * 1.03 and abs(rs / ls - 1) <= 0.10
            and float(c.iloc[i]) < neck and float(c.iloc[i - 1]) >= neck)


# 逃顶3 MACD顶背离: recent 9-bar peak exceeds the prior 60-bar peak but MACD
# (above zero) is lower; trigger = fresh MACD dead cross.
def t3_topdiv(df, i):
    if not (df["macd"].iloc[i] < df["macds"].iloc[i]
            and df["macd"].iloc[i - 1] >= df["macds"].iloc[i - 1]):
        return False
    cv, mv = df["Close"].values, df["macd"].values
    j = i - 8 + int(np.argmax(cv[i - 8:i + 1]))
    lo_b, hi_b = i - 60, j - 5
    if hi_b - lo_b < 10:
        return False
    pj = lo_b + int(np.argmax(cv[lo_b:hi_b]))
    return bool(cv[j] > cv[pj] and mv[j] < mv[pj] and mv[j] > 0)


# 逃顶4 K线见顶组合: near the 20d high and above MA20 —
# 射击之星 / 乌云盖顶 / 黄昏之星.
def t4_candle(df, i):
    if np.isnan(df["ma20"].iloc[i]) or df["Close"].iloc[i - 1] < df["ma20"].iloc[i - 1]:
        return False
    hi = df["hi20"].iloc[i]
    if np.isnan(hi) or df["High"].iloc[i - 3:i + 1].max() < hi * 0.98:
        return False
    o, h = float(df["Open"].iloc[i]), float(df["High"].iloc[i])
    l, cl = float(df["Low"].iloc[i]), float(df["Close"].iloc[i])
    po, ph = float(df["Open"].iloc[i - 1]), float(df["High"].iloc[i - 1])
    pl, pc = float(df["Low"].iloc[i - 1]), float(df["Close"].iloc[i - 1])
    atr = float(df["atr"].iloc[i])
    body, rng = abs(cl - o), (h - l) or 1e-9
    up_wick = h - max(o, cl)
    if up_wick >= 2 * body and up_wick >= 1.2 * atr and (cl - l) / rng <= 0.5:
        return True                                   # 射击之星
    pbody, prng = abs(pc - po), (ph - pl) or 1e-9
    if (pc > po and pbody >= 0.6 * prng and cl < o
            and o >= pc and cl <= po + 0.5 * pbody):
        return True                                   # 乌云盖顶
    o2, c2 = float(df["Open"].iloc[i - 2]), float(df["Close"].iloc[i - 2])
    h2, l2 = float(df["High"].iloc[i - 2]), float(df["Low"].iloc[i - 2])
    b2, r2 = abs(c2 - o2), (h2 - l2) or 1e-9
    if (c2 > o2 and b2 >= 0.6 * r2 and pbody <= 0.3 * prng
            and cl < o and cl <= o2 + 0.5 * b2):
        return True                                   # 黄昏之星
    return False


# 逃顶5 天量见顶/量价背离: (a) a ≥3×-volume bar that tagged the 20d high in the
# last 3 bars, today closes below its low; (b) fresh 20d closing high on
# dried-up 5d volume (≤0.75× 20d avg), today closes down.
def t5_volume(df, i):
    if np.isnan(df["vol20"].iloc[i]) or df["vol20"].iloc[i] <= 0:
        return False
    for k in range(1, 4):
        j = i - k
        if (df["Volume"].iloc[j] >= 3 * df["vol20"].iloc[j]
                and df["High"].iloc[j] >= df["hi20"].iloc[j]
                and df["Close"].iloc[i] < df["Low"].iloc[j]):
            return True
    if df["Close"].iloc[i] < df["Close"].iloc[i - 1]:
        for k in range(1, 4):
            j = i - k
            if (df["Close"].iloc[j] >= df["Close"].iloc[j - 20:j].max()
                    and df["vol5"].iloc[j] <= 0.75 * df["vol20"].iloc[j]):
                return True
    return False


TOPSIGS = {
    "逃顶1 M双顶":      t1_mtop,
    "逃顶2 头肩顶":     t2_hstop,
    "逃顶3 MACD顶背离": t3_topdiv,
    "逃顶4 K线见顶":    t4_candle,
    "逃顶5 天量/量价背离": t5_volume,
}


def es_stats(rows):
    out = {"n": len(rows)}
    for k in (5, 10, 20):
        v = np.array([r[f"f{k}"] for r in rows if f"f{k}" in r])
        if len(v):
            out[f"mean{k}"] = float(v.mean())
            out[f"med{k}"] = float(np.median(v))
            out[f"down{k}"] = float((v < 0).mean())
    return out


# Baseline A — 50/200 MA金叉: long while MA50>MA200 (enter on cross up, exit cross down).
def bl_ma_entry(df, i):
    return {} if df["ma50"].iloc[i] > df["ma200"].iloc[i] and df["ma50"].iloc[i - 1] <= df["ma200"].iloc[i - 1] else None


def bl_ma_exit(df, i, pos):
    return df["ma50"].iloc[i] < df["ma200"].iloc[i]


# Baseline B — MACD金叉/死叉.
def bl_macd_entry(df, i):
    return {} if df["macd"].iloc[i] > df["macds"].iloc[i] and df["macd"].iloc[i - 1] <= df["macds"].iloc[i - 1] else None


def bl_macd_exit(df, i, pos):
    return df["macd"].iloc[i] < df["macds"].iloc[i] and df["macd"].iloc[i - 1] >= df["macds"].iloc[i - 1]


PLAYBOOKS = {
    "打法1 回踩企稳":     (pb1_entry, pb1_exit),
    "打法2 缩量平台突破":  (pb2_entry, pb2_exit),
    "打法7 下轨恐慌反转":  (pb7_entry, pb7_exit),
    "打法8 带行持有":     (pb8_entry, pb8_exit),
    "打法9 首回踩MA50":   (pb9_entry, pb9_exit),
    "打法9改 质量闸":     (pb9b_entry, pb9_exit),
    "抄底1 MACD底背离":   (cd1_entry, cd1_exit),
    "抄底2 均线支撑MA60": (cd2_entry, cd2_exit),
    "抄底3 W双底":       (cd3_entry, cd3_exit),
    "抄底4 RSI超卖":     (cd4_entry, cd4_exit),
    "抄底5 地量地价":     (cd5_entry, cd5_exit),
    "抄底6 金针探底":     (cd6_entry, cd6_exit),
    "基线 MA50/200金叉":  (bl_ma_entry, bl_ma_exit),
    "基线 MACD金叉":      (bl_macd_entry, bl_macd_exit),
}


# 打法3 强弱轮动 — portfolio level: every 20 bars hold top-10 by 20d momentum among
# names above MA50; equal weight; return compounded over 2026.
def rotation_backtest(data, start=BT_START, end=None):
    closes = pd.DataFrame({t: d["Close"] for t, d in data.items()}).dropna(how="all")
    # crypto trades weekends → stock columns NaN on those rows; ffill so rolling
    # indicators stay valid across the mixed calendar (limit avoids reviving dead names)
    closes = closes.ffill(limit=5)
    ma50 = closes.rolling(50).mean()
    mom = closes.pct_change(20)
    mask = closes.index >= pd.Timestamp(start)
    if end is not None:
        mask &= closes.index < pd.Timestamp(end)
    dates = closes.index[mask]
    if len(dates) == 0:
        return None
    equity, curve = 1.0, []
    rebal_points = list(range(0, len(dates), 20))
    for k, rp in enumerate(rebal_points):
        d0 = dates[rp]
        d1 = dates[rebal_points[k + 1]] if k + 1 < len(rebal_points) else dates[-1]
        i0 = closes.index.get_loc(d0)
        elig = [t for t in closes.columns
                if not np.isnan(closes.iloc[i0][t]) and not np.isnan(ma50.iloc[i0][t])
                and closes.iloc[i0][t] > ma50.iloc[i0][t] and not np.isnan(mom.iloc[i0][t])]
        top = sorted(elig, key=lambda t: mom.iloc[i0][t], reverse=True)[:10]
        if not top:
            curve.append((str(d1.date()), equity, []))
            continue
        leg = np.mean([closes.loc[d1, t] / closes.loc[d0, t] for t in top])
        equity *= leg
        curve.append((str(d1.date()), equity, top))
    return {"ytd_return": equity - 1, "legs": curve}


# ────────────────────────── stats ──────────────────────────
def summarize(trades):
    if not trades:
        return None
    r = np.array([t["ret"] for t in trades])
    wins, losses = r[r > 0], r[r <= 0]
    pf = wins.sum() / abs(losses.sum()) if losses.sum() != 0 else float("inf")
    # per-ticker compounding
    by_tk = {}
    for t in trades:
        by_tk.setdefault(t["ticker"], []).append(t["ret"])
    tk_returns = {tk: float(np.prod([1 + x for x in rs]) - 1) for tk, rs in by_tk.items()}
    return {
        "n_trades": len(r),
        "n_tickers": len(by_tk),
        "win_rate": float((r > 0).mean()),
        "avg_ret": float(r.mean()),
        "median_ret": float(np.median(r)),
        "profit_factor": float(pf),
        "avg_days": float(np.mean([t["days"] for t in trades])),
        "avg_ticker_ytd": float(np.mean(list(tk_returns.values()))),
        "best": max(trades, key=lambda t: t["ret"]),
        "worst": min(trades, key=lambda t: t["ret"]),
        "open_trades": sum(1 for t in trades if t["exit_date"] == "OPEN"),
    }


def bench_returns(data, start, end):
    bench = {}
    for b in ["SPY", "QQQ"]:
        d = yf.download(b, start="2023-12-01", interval="1d", auto_adjust=True, progress=False)
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = d.columns.get_level_values(0)
        c = d["Close"].dropna()
        c = c[c.index >= pd.Timestamp(start)]
        if end is not None:
            c = c[c.index < pd.Timestamp(end)]
        bench[b] = float(c.iloc[-1] / c.iloc[0] - 1)
    ew = []
    for t, df in data.items():
        c = df["Close"][df.index >= pd.Timestamp(start)]
        if end is not None:
            c = c[c.index < pd.Timestamp(end)]
        if len(c) > 10:
            ew.append(float(c.iloc[-1] / c.iloc[0] - 1))
    bench["EqualWeight-Universe"] = float(np.mean(ew))
    return bench


def main():
    tickers, sector_of = get_universe()
    print(f"universe: {len(tickers)} tickers")
    data = download_all(tickers)
    print(f"data ok: {len(data)} tickers")
    for t in data:
        data[t] = add_indicators(data[t])

    out = {"asof": TODAY, "universe_size": len(data), "windows": {}}
    md2 = [f"# 逃顶五式回测 2024 / 2025 / 2026 YTD (as of {TODAY})",
           f"universe: {len(data)} tickers · 信号在收盘触发 · 事件研究去重冷却5根K线", ""]
    md = [f"# 打法回测 2024 / 2025 / 2026 YTD (as of {TODAY})",
          f"universe: {len(data)} tickers · entries at signal-bar close · no costs/slippage",
          "· per-ticker warmup 210 bars (late IPOs join late) · window-end marks open trades", ""]

    for label, start, end in WINDOWS:
        results, all_trades = {}, []
        for name, (efn, xfn) in PLAYBOOKS.items():
            trades = []
            for t, df in data.items():
                for tr in run_trades(df, efn, xfn, name, start, end):
                    tr["ticker"] = t
                    trades.append(tr)
            results[name] = summarize(trades)
            all_trades += trades
        rot = rotation_backtest(data, start, end)
        bench = bench_returns(data, start, end)

        # ── 逃顶: (a) event study of forward returns after each signal ──
        es = {}
        for sname, sig in TOPSIGS.items():
            rows = []
            for t, df in data.items():
                dfw = df if end is None else df[df.index < pd.Timestamp(end)]
                if len(dfw) < 220:
                    continue
                si = int(np.searchsorted(dfw.index, pd.Timestamp(start)))
                lastf = -9
                for i in range(max(si, 210), len(dfw)):
                    if i - lastf < 5:
                        continue
                    try:
                        fired = sig(dfw, i)
                    except Exception:
                        fired = False
                    if fired:
                        lastf = i
                        row = {"ticker": t, "date": str(dfw.index[i].date())}
                        for k in (5, 10, 20):
                            if i + k < len(df):
                                row[f"f{k}"] = float(df["Close"].iloc[i + k]
                                                     / df["Close"].iloc[i] - 1)
                        rows.append(row)
            es[sname] = rows
        # baseline: forward returns from every 3rd bar above MA20 (the context
        # top signals fire in) — what "not escaping" would have earned
        base_rows = []
        for t, df in data.items():
            dfw = df if end is None else df[df.index < pd.Timestamp(end)]
            if len(dfw) < 220:
                continue
            si = int(np.searchsorted(dfw.index, pd.Timestamp(start)))
            for i in range(max(si, 210), len(dfw), 3):
                if dfw["Close"].iloc[i] > dfw["ma20"].iloc[i]:
                    row = {}
                    for k in (5, 10, 20):
                        if i + k < len(df):
                            row[f"f{k}"] = float(df["Close"].iloc[i + k]
                                                 / df["Close"].iloc[i] - 1)
                    if row:
                        base_rows.append(row)
        es_summary = {n: es_stats(r) for n, r in es.items()}
        es_summary["基线 MA20上方随机时点"] = es_stats(base_rows)

        # ── 逃顶: (b) exit overlays on 打法8 entries ──
        oresults = {"打法8 原版(破MA20离场)": results["打法8 带行持有"]}
        for sname, sig in TOPSIGS.items():
            xfn = (lambda s: (lambda df, i, pos: s(df, i)
                              or pb8_exit(df, i, pos)))(sig)
            otr = []
            for t, df in data.items():
                for tr in run_trades(df, pb8_entry, xfn, f"打法8+{sname}", start, end):
                    tr["ticker"] = t
                    otr.append(tr)
            oresults[f"打法8+{sname}"] = summarize(otr)

        def any_exit(df, i, pos):
            return (any(s(df, i) for s in TOPSIGS.values())
                    or pb8_exit(df, i, pos))
        otr = []
        for t, df in data.items():
            for tr in run_trades(df, pb8_entry, any_exit, "打法8+逃顶ANY", start, end):
                tr["ticker"] = t
                otr.append(tr)
        oresults["打法8+逃顶ANY"] = summarize(otr)
        print(f"  [{label}] taoding: " + ", ".join(f"{n.split()[0]}={len(r)}" for n, r in es.items()))

        out["windows"][label] = {"results": results, "rotation_打法3": rot,
                                 "benchmarks": bench, "trades": all_trades,
                                 "taoding_event_study": es_summary,
                                 "taoding_overlays": oresults}
        print(f"[{label}] {sum(len([x for x in all_trades if x['strategy']==n]) for n in PLAYBOOKS)} trades, "
              f"rotation {rot['ytd_return']:+.1%}" if rot else f"[{label}] no rotation")

        md += [f"## {label} ({start} → {end or TODAY})", "",
               "| 打法 | 交易数 | 胜率 | 平均单笔 | 中位数 | 盈亏比PF | 平均持仓天 | 每票复利均值 |",
               "|---|---|---|---|---|---|---|---|"]
        for name, s in results.items():
            if not s:
                md.append(f"| {name} | 0 | — | — | — | — | — | — |")
                continue
            md.append(f"| {name} | {s['n_trades']} | {s['win_rate']:.0%} | {s['avg_ret']:+.2%} | "
                      f"{s['median_ret']:+.2%} | {s['profit_factor']:.2f} | {s['avg_days']:.0f} | "
                      f"{s['avg_ticker_ytd']:+.2%} |")
        if rot:
            md.append(f"\n**打法3 强弱轮动 (top-10动量, 20日调仓)**: **{rot['ytd_return']:+.2%}**")
        md.append("\n基准: " + " · ".join(f"{b} {r:+.2%}" for b, r in bench.items()))
        md.append("")

        md2 += [f"## {label} ({start} → {end or TODAY})", "",
                "### A. 信号质量 — 触发后前瞻收益 (负值=逃对了)", "",
                "| 信号 | 次数 | 5日均值 | 10日均值 | 10日中位 | 10日下跌率 | 20日均值 | 20日下跌率 |",
                "|---|---|---|---|---|---|---|---|"]
        for n, s in es_summary.items():
            if s["n"] == 0 or "mean10" not in s:
                md2.append(f"| {n} | {s['n']} | — | — | — | — | — | — |")
                continue
            md2.append(f"| {n} | {s['n']} | {s.get('mean5', 0):+.2%} | {s['mean10']:+.2%} | "
                       f"{s['med10']:+.2%} | {s['down10']:.0%} | {s.get('mean20', 0):+.2%} | "
                       f"{s.get('down20', 0):.0%} |")
        md2 += ["", "### B. 作为打法8的离场升级 (入场相同, 只换离场)", "",
                "| 离场规则 | 交易数 | 胜率 | 平均单笔 | 中位数 | 盈亏比PF | 平均持仓天 | 每票复利均值 |",
                "|---|---|---|---|---|---|---|---|"]
        for n, s in oresults.items():
            if not s:
                md2.append(f"| {n} | 0 | — | — | — | — | — | — |")
                continue
            md2.append(f"| {n} | {s['n_trades']} | {s['win_rate']:.0%} | {s['avg_ret']:+.2%} | "
                       f"{s['median_ret']:+.2%} | {s['profit_factor']:.2f} | {s['avg_days']:.0f} | "
                       f"{s['avg_ticker_ytd']:+.2%} |")
        md2.append("")

    (HERE / f"backtest_playbooks_multiyear_{TODAY}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (HERE / f"backtest_playbooks_multiyear_{TODAY}.md").write_text("\n".join(md), encoding="utf-8")
    (HERE / f"backtest_taoding_multiyear_{TODAY}.md").write_text("\n".join(md2), encoding="utf-8")
    print("saved md+json")


if __name__ == "__main__":
    main()
