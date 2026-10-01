# -*- coding: utf-8 -*-
"""
Trade-Plan Charts — daily 8 PM run over the full AI_Portfolios.xlsx universe.
==============================================================================
For every ticker: 1-year daily chart (price + MA20/50/200 with entry/stop/
target levels drawn on, volume + OBV, MACD) plus a rule-based trade plan:

  UPTREND   (price>MA50>MA200 or price>MA20>MA50)
            entry = pullback to MA20 (or market if already there)
            add   = above 20-day high +0.5%
            stop  = min(MA50, entry - 2*ATR);  T1 = +1.5R, T2 = +3R
  DOWNTREND (price<MA50<MA200 or price<MA20 & <MA50)
            no new longs; exit bounces into MA20,
            hard exit below 20-day low -0.25*ATR,
            thesis wrong above 20-day high +0.5*ATR; risk marker = 60-day low
  RANGE     buy near support/MA50, stop 1*ATR under 20-day low,
            target = range high

Outputs (all in this directory):
  trade_plan_charts/<DATE>/<TICKER>.png          — all charts
  trade_plans_<DATE>.json                        — machine-readable plans
  trade_plans_<DATE>.md                          — full summary table
  trade_plans_<DATE>.html                        — FULL report, all charts embedded
  trade_plans_actionable_<DATE>.html             — top long setups + top exits only
                                                   (small enough to publish as artifact)
"""
import os, re, sys, io, json, base64
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from intraday_volume import rvol_now as _iv_rvol_now, low_volume_threshold
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
# NOTE: this import also re-wraps sys.stdout as UTF-8 at module level — do not wrap it here too.
from technical_macd_volume_strategy import load_portfolio  # reuses xlsx loader + name→ticker map

TODAY = datetime.now().strftime("%Y-%m-%d")
CHART_DIR = HERE / "trade_plan_charts" / TODAY
CHART_DIR.mkdir(parents=True, exist_ok=True)

N_ACTIONABLE = 15  # top long setups and top exits embedded in the actionable HTML
# 刀 位置过滤: 放量长阴出现在 MA20 上方这么多 % 以外时, 它不是"支撑位接刀",
# 而是抛物线后的顶部派发 — 改判 8减仓-派发 (禁买语义相同, 但持仓纪律不同)。
KNIFE_FAR_ABOVE_MA20 = 10.0


# ── indicators ─────────────────────────────────────────────────────────
def _rsi(c, n=14):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def _macd(c):
    line = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    sig = line.ewm(span=9, adjust=False).mean()
    return line, sig, line - sig


def _atr(df, n=14):
    tr = pd.concat([df.High - df.Low,
                    (df.High - df.Close.shift()).abs(),
                    (df.Low - df.Close.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def _obv(c, v):
    return (np.sign(c.diff().fillna(0)) * v).cumsum()


# ── pattern detection (same thresholds as technical_macd_volume_strategy,
#    but returns chart locations so patterns can be drawn) ───────────────
def detect_patterns(df, m_line):
    """Return list of dicts: {kind, msg, ...draw data}. kinds:
    double_bottom/double_top (points=[(ts, px), (ts, px)]),
    breakout_bull/breakout_bull_weak/breakout_bear (level),
    cup_handle (start, rim), golden_cross/death_cross (ts),
    macd_bull_div/macd_bear_div (no draw data)."""
    pats = []
    c, high, low, vol = df.Close, df.High, df.Low, df.Volume
    last = float(c.iloc[-1])

    if len(low) >= 40:  # double bottom
        win = low.iloc[-40:]
        sm = win.nsmallest(5)
        if len(sm) >= 2:
            l1, l2 = float(sm.iloc[0]), float(sm.iloc[1])
            i1, i2 = sm.index[0], sm.index[1]
            apart = abs(win.index.get_loc(i1) - win.index.get_loc(i2))
            if l1 > 0 and abs(l1 - l2) / l1 * 100 < 4 and apart >= 8 and last > l1 * 1.05:
                pts = sorted([(i1, l1), (i2, l2)])
                neck = float(c.loc[pts[0][0]:pts[1][0]].max())
                tgt = neck + (neck - (l1 + l2) / 2)
                pats.append(dict(kind="double_bottom", points=pts, neckline=neck, target=tgt,
                                 msg=f"Double bottom ${min(l1,l2):,.2f}/${max(l1,l2):,.2f}, {apart} bars apart; "
                                     f"neckline ${neck:,.2f} → measured target ${tgt:,.2f}"))
    if len(high) >= 40:  # double top
        win = high.iloc[-40:]
        lg = win.nlargest(5)
        if len(lg) >= 2:
            h1, h2 = float(lg.iloc[0]), float(lg.iloc[1])
            i1, i2 = lg.index[0], lg.index[1]
            apart = abs(win.index.get_loc(i1) - win.index.get_loc(i2))
            if h1 > 0 and abs(h1 - h2) / h1 * 100 < 4 and apart >= 8 and last < h1 * 0.95:
                pts = sorted([(i1, h1), (i2, h2)])
                neck = float(c.loc[pts[0][0]:pts[1][0]].min())
                tgt = neck - ((h1 + h2) / 2 - neck)
                pats.append(dict(kind="double_top", points=pts, neckline=neck, target=tgt,
                                 msg=f"Double top ${max(h1,h2):,.2f}/${min(h1,h2):,.2f}, {apart} bars apart; "
                                     f"neckline ${neck:,.2f} → measured target ${tgt:,.2f}"))
    if len(c) >= 25:  # 20-day breakout / breakdown
        prior_high = float(high.iloc[-21:-1].max())
        prior_low = float(c.iloc[-21:-1].min())
        v_avg = float(vol.iloc[-20:].mean())
        surge = float(vol.iloc[-1]) > v_avg * 1.5 if v_avg > 0 else False
        ratio = float(vol.iloc[-1]) / v_avg if v_avg > 0 else 0
        if last > prior_high * 1.01:
            tgt = prior_high + (prior_high - prior_low)  # range height projected up
            pats.append(dict(kind="breakout_bull" if surge else "breakout_bull_weak",
                             level=prior_high, target=tgt,
                             msg=f"Breakout above 20-day high ${prior_high:,.2f} "
                                 f"({'volume-confirmed' if surge else 'weak volume'} {ratio:.1f}x); "
                                 f"measured target ${tgt:,.2f}"))
        elif last < prior_low * 0.99 and surge:
            tgt = prior_low - (prior_high - prior_low)
            pats.append(dict(kind="breakout_bear", level=prior_low, target=tgt,
                             msg=f"High-volume breakdown below 20-day low ${prior_low:,.2f} ({ratio:.1f}x); "
                                 f"measured target ${tgt:,.2f}"))
    if len(c) >= 80:  # cup & handle
        seg = c.iloc[-80:]
        left, bottom = float(seg.iloc[:20].max()), float(seg.iloc[20:60].min())
        right, handle = float(seg.iloc[55:75].max()), float(seg.iloc[-10:].min())
        if left > 0 and right > 0:
            depth = (left - bottom) / left * 100
            pull = (right - handle) / right * 100
            if (abs(left - right) / left * 100 < 8 and 12 < depth < 50
                    and 0 < pull < 15 and last > right * 1.005):
                tgt = right + (right - bottom)  # cup depth projected above the rim
                pats.append(dict(kind="cup_handle", start=seg.index[0], rim=right, target=tgt,
                                 msg=f"Cup & handle breakout (cup depth {depth:.0f}%, handle -{pull:.1f}%); "
                                     f"measured target ${tgt:,.2f}"))
    if len(c) >= 205 and not (np.isnan(df.MA200.iloc[-1]) or np.isnan(df.MA50.iloc[-1])):
        cur = float(df.MA50.iloc[-1]) - float(df.MA200.iloc[-1])
        prev = float(df.MA50.iloc[-5]) - float(df.MA200.iloc[-5])
        if prev < 0 and cur > 0:
            pats.append(dict(kind="golden_cross", ts=df.index[-3],
                             msg="Golden cross: MA50 crossed above MA200"))
        elif prev > 0 and cur < 0:
            pats.append(dict(kind="death_cross", ts=df.index[-3],
                             msg="Death cross: MA50 crossed below MA200"))
    if len(c) >= 30:  # MACD divergence
        cc, mm = c.iloc[-30:], m_line.iloc[-30:]
        if float(cc.iloc[15:].min()) < float(cc.iloc[:15].min()) * 0.98 and \
                float(mm.iloc[15:].min()) > float(mm.iloc[:15].min()):
            pats.append(dict(kind="macd_bull_div",
                             msg="Bullish MACD divergence: price lower low, MACD higher low"))
        elif float(cc.iloc[15:].max()) > float(cc.iloc[:15].max()) * 1.02 and \
                float(mm.iloc[15:].max()) < float(mm.iloc[:15].max()):
            pats.append(dict(kind="macd_bear_div",
                             msg="Bearish MACD divergence: price higher high, MACD lower high"))
    return pats


# ── geometric pattern detection (drawn as lines on the chart) ──────────
def _pivot_idx(vals, order=4, kind="high"):
    """Positions of local extremes; plateaus thinned to one pivot."""
    out = []
    for i in range(order, len(vals) - order):
        seg = vals[i - order:i + order + 1]
        hit = vals[i] >= seg.max() if kind == "high" else vals[i] <= seg.min()
        if hit and (not out or i - out[-1] > order):
            out.append(i)
    return out


def _fit_line(xs, ys):
    xs, ys = np.asarray(xs, float), np.asarray(ys, float)
    if len(xs) < 2:
        return None
    a, b = np.polyfit(xs, ys, 1)
    err = float(np.mean(np.abs(ys - (a * xs + b))))
    return float(a), float(b), err


def detect_geometric(df):
    """Patterns with drawable geometry. Coordinates are integer bar
    positions into df (converted to timestamps at draw time). Kinds:
    sr_levels(levels), trendline(side, x0, y0, x1, y1),
    hs_top/hs_inv(pts, neck, target), triangle_asc/desc/sym(upper, lower),
    flag_bull/flag_bear(pole, top, bot, target)."""
    pats = []
    n = len(df)
    if n < 60:
        return pats
    c, high, low = df.Close, df.High, df.Low
    last = float(c.iloc[-1])
    atr = float(df.ATR.iloc[-1]) if "ATR" in df and not np.isnan(df.ATR.iloc[-1]) \
        else float((high - low).tail(14).mean())
    look = min(n, 130)
    base = n - look
    h, l, cl = high.values[-look:], low.values[-look:], c.values[-look:]
    ph, pl = _pivot_idx(h, 4, "high"), _pivot_idx(l, 4, "low")

    # 1) horizontal support/resistance from pivot-price clusters
    levels = []
    for p in sorted([h[i] for i in ph] + [l[i] for i in pl]):
        for lv in levels:
            if abs(p - lv["px"]) / lv["px"] < 0.015:
                lv["hits"] += 1
                lv["px"] += (p - lv["px"]) / lv["hits"]
                break
        else:
            levels.append(dict(px=float(p), hits=1))
    strong = sorted((lv for lv in levels
                     if lv["hits"] >= 3 and 0.75 * last <= lv["px"] <= 1.3 * last),
                    key=lambda lv: -lv["hits"])[:3]
    if strong:
        pats.append(dict(kind="sr_levels", levels=[round(lv["px"], 2) for lv in strong],
                         msg="S/R " + " · ".join(f"${lv['px']:,.2f} ({lv['hits']} touches)"
                                                 for lv in strong)))

    # 2) diagonal trendlines through the last 3-4 pivots
    def _trend(pivs, vals):
        pts = pivs[-4:] if len(pivs) >= 4 else pivs
        if len(pts) < 3:
            return None
        fit = _fit_line(pts, [vals[i] for i in pts])
        if fit is None or fit[2] > atr * 0.6:
            return None
        return fit[0], fit[1], pts

    t = _trend(pl, l)
    if t and t[0] * (look - 1 - t[2][0]) > 1.5 * atr:  # meaningfully rising
        a, b, pts = t
        pats.append(dict(kind="trendline", side="support",
                         x0=base + pts[0], y0=a * pts[0] + b,
                         x1=n - 1, y1=a * (look - 1) + b,
                         msg=f"Rising support trendline ({len(pts)} touches), now ${a*(look-1)+b:,.2f}"))
    t = _trend(ph, h)
    if t and t[0] * (look - 1 - t[2][0]) < -1.5 * atr:  # meaningfully falling
        a, b, pts = t
        pats.append(dict(kind="trendline", side="resistance",
                         x0=base + pts[0], y0=a * pts[0] + b,
                         x1=n - 1, y1=a * (look - 1) + b,
                         msg=f"Falling resistance trendline ({len(pts)} touches), now ${a*(look-1)+b:,.2f}"))

    # 3) head & shoulders top / inverse (most recent qualifying triple)
    def _hs(pivs, vals, inv):
        s = -1.0 if inv else 1.0
        for i in range(len(pivs) - 3, -1, -1):
            a_, b_, c_ = pivs[i], pivs[i + 1], pivs[i + 2]
            if c_ < look - 70:
                break  # pattern too old to matter
            va, vb, vc = s * vals[a_], s * vals[b_], s * vals[c_]
            if vb > va and vb > vc and abs(va - vc) <= 0.05 * abs(vb) \
                    and vb - max(va, vc) >= 0.015 * abs(vb):
                return a_, b_, c_
        return None

    hs = _hs(ph, h, inv=False)
    if hs:
        a_, b_, c_ = hs
        n1 = a_ + int(np.argmin(l[a_:b_ + 1]))
        n2 = b_ + int(np.argmin(l[b_:c_ + 1]))
        fit = _fit_line([n1, n2], [l[n1], l[n2]]) if n2 > n1 else None
        if fit:
            ka, kb, _ = fit
            neck_now = ka * (look - 1) + kb
            height = h[b_] - (ka * b_ + kb)
            # invalid once price takes out the head; stale once far below neckline
            if height > 0 and last < h[b_] and last > neck_now * 0.85:
                pats.append(dict(kind="hs_top",
                                 pts=[(base + a_, float(h[a_])), (base + b_, float(h[b_])),
                                      (base + c_, float(h[c_]))],
                                 neck=((base + n1, float(l[n1])), (n - 1, float(neck_now))),
                                 target=float(neck_now - height),
                                 msg=f"Head & shoulders top: head ${h[b_]:,.2f}, neckline ${neck_now:,.2f}, "
                                     f"measured target ${neck_now - height:,.2f}"))
    hs = _hs(pl, l, inv=True)
    if hs:
        a_, b_, c_ = hs
        n1 = a_ + int(np.argmax(h[a_:b_ + 1]))
        n2 = b_ + int(np.argmax(h[b_:c_ + 1]))
        fit = _fit_line([n1, n2], [h[n1], h[n2]]) if n2 > n1 else None
        if fit:
            ka, kb, _ = fit
            neck_now = ka * (look - 1) + kb
            height = (ka * b_ + kb) - l[b_]
            # invalid once price undercuts the head; stale once far above neckline
            if height > 0 and last > l[b_] and last < neck_now * 1.15:
                pats.append(dict(kind="hs_inv",
                                 pts=[(base + a_, float(l[a_])), (base + b_, float(l[b_])),
                                      (base + c_, float(l[c_]))],
                                 neck=((base + n1, float(h[n1])), (n - 1, float(neck_now))),
                                 target=float(neck_now + height),
                                 msg=f"Inverse head & shoulders: head ${l[b_]:,.2f}, neckline ${neck_now:,.2f}, "
                                     f"measured target ${neck_now + height:,.2f}"))

    # 4) triangles over the last ~55 bars
    w0 = look - 55
    ph2 = [i for i in ph if i >= w0]
    pl2 = [i for i in pl if i >= w0]
    if len(ph2) >= 2 and len(pl2) >= 2:
        fh_ = _fit_line(ph2, [h[i] for i in ph2])
        fl_ = _fit_line(pl2, [l[i] for i in pl2])
        if fh_ and fl_ and fh_[2] < atr * 0.7 and fl_[2] < atr * 0.7:
            ah, bh, al, bl = fh_[0], fh_[1], fl_[0], fl_[1]
            x_start = min(ph2[0], pl2[0])
            span = (look - 1) - x_start
            rise_h, rise_l = ah * span, al * span
            kind = name = None
            if abs(rise_h) < 1.2 * atr and rise_l > 2 * atr:
                kind, name = "triangle_asc", "Ascending triangle"
            elif rise_h < -2 * atr and abs(rise_l) < 1.2 * atr:
                kind, name = "triangle_desc", "Descending triangle"
            elif rise_h < -2 * atr and rise_l > 2 * atr:
                kind, name = "triangle_sym", "Symmetrical triangle"
            if kind:
                res_now, sup_now = ah * (look - 1) + bh, al * (look - 1) + bl
                if res_now > sup_now and sup_now - atr <= last <= res_now + atr:
                    height = (ah * x_start + bh) - (al * x_start + bl)
                    pats.append(dict(kind=kind,
                                     target_up=float(res_now + height), target_dn=float(sup_now - height),
                                     upper=((base + x_start, float(ah * x_start + bh)), (n - 1, float(res_now))),
                                     lower=((base + x_start, float(al * x_start + bl)), (n - 1, float(sup_now))),
                                     msg=f"{name}: resistance ${res_now:,.2f} / support ${sup_now:,.2f}; "
                                         f"break-up target ${res_now + height:,.2f}, break-down ${sup_now - height:,.2f}"))

    # 5) bull/bear flag: sharp 12-bar pole then tight 8-16 bar drift
    for fl_len in (8, 12, 16):
        pe = look - fl_len - 1  # pole end / flag start
        ps = pe - 12
        if ps < 0:
            break
        pole = cl[pe] - cl[ps]
        if abs(pole) < 3.5 * atr:
            continue
        f_hi, f_lo = float(h[pe:].max()), float(l[pe:].min())
        if f_hi - f_lo > abs(pole) * 0.6:
            continue  # consolidation too deep for a flag
        drift = cl[-1] - cl[pe]
        if pole > 0 and -0.6 * pole <= drift <= 0.15 * pole:
            pats.append(dict(kind="flag_bull",
                             pole=((base + ps, float(cl[ps])), (base + pe, float(cl[pe]))),
                             top=((base + pe, f_hi), (n - 1, f_hi)),
                             bot=((base + pe, f_lo), (n - 1, f_lo)),
                             target=float(f_hi + abs(pole)),
                             msg=f"Bull flag: pole +${abs(pole):,.2f}, flag ${f_lo:,.2f}–${f_hi:,.2f}; "
                                 f"breakout target ${f_hi + abs(pole):,.2f}"))
            break
        if pole < 0 and -0.15 * abs(pole) <= drift <= 0.6 * abs(pole):
            pats.append(dict(kind="flag_bear",
                             pole=((base + ps, float(cl[ps])), (base + pe, float(cl[pe]))),
                             top=((base + pe, f_hi), (n - 1, f_hi)),
                             bot=((base + pe, f_lo), (n - 1, f_lo)),
                             target=float(f_lo - abs(pole)),
                             msg=f"Bear flag: pole −${abs(pole):,.2f}, flag ${f_lo:,.2f}–${f_hi:,.2f}; "
                                 f"breakdown target ${f_lo - abs(pole):,.2f}"))
            break
    return pats


# ── volume-confirmed breakout detection ────────────────────────────────
def detect_volume_breakouts(df, other_pats):
    """Breakouts through meaningful levels on elevated volume (≥1.5× the
    20-day average), plus pre-breakout coils. Levels come from range
    highs/lows and the geometric patterns already detected (S/R clusters,
    trendlines, triangle edges, H&S necklines, flag channels).
    Kinds: vol_breakout(dir, level, bar, rvol, src), coil(level, x0)."""
    pats = []
    n = len(df)
    if n < 30:
        return pats
    c, high, low, vol = df.Close, df.High, df.Low, df.Volume
    last = float(c.iloc[-1])
    v20 = float(vol.iloc[-21:-1].mean())
    if not v20 > 0:
        return pats
    atr = float(df.ATR.iloc[-1]) if not np.isnan(df.ATR.iloc[-1]) else 0.0
    cl = c.values

    # candidate levels, most significant first (deduped within 0.5%)
    cands = []

    def _add(level, label):
        level = float(level)
        if not 0.5 * last < level < 1.8 * last:
            return
        if any(abs(level - lv) / lv < 0.005 for lv, _ in cands):
            return
        cands.append((level, label))

    if n >= 240:
        _add(high.iloc[:-5].max(), "52-week high")
    if n >= 70:
        _add(high.iloc[-65:-5].max(), "60-day high")
        _add(low.iloc[-65:-5].min(), "60-day low")
    _add(high.iloc[-26:-5].max(), "20-day high")
    _add(low.iloc[-26:-5].min(), "20-day low")
    for pat in other_pats:
        k = pat.get("kind", "")
        if k == "sr_levels":
            for lv in pat["levels"]:
                _add(lv, "S/R level")
        elif k == "trendline":
            _add(pat["y1"], "rising support line" if pat["side"] == "support"
                 else "falling resistance line")
        elif k.startswith("triangle"):
            _add(pat["upper"][1][1], "triangle resistance")
            _add(pat["lower"][1][1], "triangle support")
        elif k in ("hs_top", "hs_inv"):
            _add(pat["neck"][1][1], "H&S neckline" if k == "hs_top" else "inverse H&S neckline")
        elif k.startswith("flag"):
            _add(pat["top"][1][1], "flag top")
            _add(pat["bot"][1][1], "flag bottom")

    def _crossed(level):
        """('up'|'down', bar_pos) if a close crossed the level within the
        last 5 bars and price still holds beyond it."""
        for i in range(max(1, n - 5), n):
            if cl[i - 1] < level * 0.999 and cl[i] > level * 1.001 and last > level:
                return "up", i
            if cl[i - 1] > level * 1.001 and cl[i] < level * 0.999 and last < level:
                return "down", i
        return None

    ups, downs = [], []
    for lv, lab in cands:
        x = _crossed(lv)
        if not x:
            continue
        d, i = x
        rv = float(vol.iloc[i]) / v20
        if rv < 1.5:
            continue  # breakout without volume = not confirmed, skip
        (ups if d == "up" else downs).append((lv, lab, i, rv))

    if ups:
        lv, lab, i, rv = max(ups, key=lambda z: z[0])  # highest level broken
        obv_hi = n >= 60 and float(df.OBV.iloc[-1]) >= float(df.OBV.iloc[-60:].max()) * 0.999
        pats.append(dict(kind="vol_breakout", dir="up", level=lv, bar=i, rvol=rv, src=lab,
                         msg=f"Volume breakout above {lab} ${lv:,.2f} on {rv:.1f}x avg volume"
                             + (", OBV at 60-day high" if obv_hi else "")))
    if downs:
        lv, lab, i, rv = min(downs, key=lambda z: z[0])  # lowest level broken
        pats.append(dict(kind="vol_breakout", dir="down", level=lv, bar=i, rvol=rv, src=lab,
                         msg=f"Volume breakdown below {lab} ${lv:,.2f} on {rv:.1f}x avg volume"))

    # pre-breakout coil: tight range just under resistance, volume building
    if not ups and atr > 0 and n >= 30:
        res_above = sorted(lv for lv, _ in cands if last < lv <= last * 1.02)
        if res_above:
            lvl = res_above[0]
            rng10 = float(high.iloc[-10:].max() - low.iloc[-10:].min())
            rng_prior = float(high.iloc[-30:-10].max() - low.iloc[-30:-10].min())
            v5 = float(vol.iloc[-5:].mean())
            obv_up = float(df.OBV.iloc[-5:].mean()) > float(df.OBV.iloc[-20:].mean())
            if rng_prior > 0 and rng10 < rng_prior * 0.65 and (v5 > v20 * 1.1 or obv_up):
                pats.append(dict(kind="coil", level=float(lvl), x0=n - 10,
                                 msg=f"Coiling under ${lvl:,.2f} — range tightening, "
                                     f"{'volume building' if v5 > v20 * 1.1 else 'OBV accumulating'}; "
                                     f"breakout watch"))
    return pats


# ── fibonacci retracements & extensions ─────────────────────────────────
def fib_analysis(df):
    """Fibonacci retracement + extension levels off the dominant swing of
    the last ~250 bars. Returns a pattern dict (kind='fib') with drawable
    levels, or None."""
    look = min(len(df), 250)
    if look < 40:
        return None
    h, l = df.High.iloc[-look:], df.Low.iloc[-look:]
    hi_ts, lo_ts = h.idxmax(), l.idxmin()
    hi, lo = float(h.max()), float(l.min())
    rng = hi - lo
    last = float(df.Close.iloc[-1])
    if rng <= 0:
        return None
    up = lo_ts < hi_ts  # swing ran low→high: retracements act as support
    ratios = (0.236, 0.382, 0.5, 0.618, 0.786)
    if up:
        retr = [(r, hi - rng * r) for r in ratios]
        ext = [(1.272, hi + 0.272 * rng), (1.618, hi + 0.618 * rng)]
    else:
        retr = [(r, lo + rng * r) for r in ratios]
        ext = [(1.272, lo - 0.272 * rng), (1.618, lo - 0.618 * rng)]
    sup = max((px for _, px in retr if px < last), default=None)
    res = min((px for _, px in retr if px > last), default=None)
    near = ([f"nearest fib support ${sup:,.2f}"] if sup else []) + \
           ([f"nearest fib resistance ${res:,.2f}"] if res else [])
    msg = (f"Fib ({'up' if up else 'down'}swing ${lo:,.2f}→${hi:,.2f}): "
           + " · ".join(f"{r:.1%} ${px:,.2f}" for r, px in retr)
           + f"; extensions 127.2% ${ext[0][1]:,.2f} / 161.8% ${ext[1][1]:,.2f}"
           + (" — " + ", ".join(near) if near else ""))
    return dict(kind="fib", up=up, hi=hi, lo=lo, hi_ts=hi_ts, lo_ts=lo_ts,
                retr=retr, ext=ext, fib_sup=sup, fib_res=res, msg=msg)


PAT_NAME = {"double_bottom": "Double bottom", "double_top": "Double top",
            "cup_handle": "Cup & handle", "breakout_bull": "Range breakout",
            "breakout_bull_weak": "Range breakout (weak vol)", "breakout_bear": "Range breakdown",
            "hs_top": "H&S top", "hs_inv": "Inverse H&S",
            "triangle_asc": "Ascending triangle", "triangle_desc": "Descending triangle",
            "triangle_sym": "Symmetrical triangle", "flag_bull": "Bull flag",
            "flag_bear": "Bear flag"}


# ── plan + chart per ticker ────────────────────────────────────────────
def analyze(tkr, sector, df):
    c = df.Close
    df["MA20"], df["MA50"], df["MA200"] = c.rolling(20).mean(), c.rolling(50).mean(), c.rolling(200).mean()
    m_line, m_sig, m_hist = _macd(c)
    df["ATR"], df["OBV"], df["RSI"] = _atr(df), _obv(c, df.Volume), _rsi(c)
    bb_std = c.rolling(20).std()
    df["BB_UP"], df["BB_LO"] = df.MA20 + 2 * bb_std, df.MA20 - 2 * bb_std

    last = float(c.iloc[-1])
    ma20, ma50 = float(df.MA20.iloc[-1]), float(df.MA50.iloc[-1])
    ma200 = float(df.MA200.iloc[-1]) if not np.isnan(df.MA200.iloc[-1]) else None
    a, r = float(df.ATR.iloc[-1]), float(df.RSI.iloc[-1])
    hi20, lo20 = float(df.High.iloc[-21:-1].max()), float(df.Low.iloc[-21:-1].min())
    lo60 = float(df.Low.iloc[-60:].min())
    chg20 = last / float(c.iloc[-21]) - 1 if len(c) > 21 else 0.0

    if ma200 and last > ma50 > ma200 and last > ma20:
        trend = "UPTREND"
    elif ma200 and last < ma50 < ma200:
        trend = "DOWNTREND"
    elif last > ma50 and last > ma20:
        trend = "UPTREND"
    elif last < ma50 and last < ma20:
        trend = "DOWNTREND"
    else:
        trend = "RANGE"

    p = dict(sector=sector, trend=trend, last=last, rsi=round(r), atr=round(a, 2),
             macd="bullish" if m_line.iloc[-1] > m_sig.iloc[-1] else "bearish",
             chg20=round(chg20 * 100, 1))
    if trend == "UPTREND":
        entry = ma20 if last > ma20 * 1.02 else last
        stop = min(ma50, entry - 2 * a)
        risk = entry - stop
        p.update(bias="LONG", entry=entry,
                 entry_note="pullback to MA20" if entry == ma20 else "at market (at/near MA20)",
                 entry2=hi20 * 1.005, entry2_note="breakout add above 20-day high",
                 stop=stop, stop_note="below MA50 / 2×ATR",
                 t1=entry + 1.5 * risk, t2=entry + 3 * risk)
    elif trend == "DOWNTREND":
        p.update(bias="AVOID / EXIT", entry=ma20,
                 entry_note="if holding: exit bounces into MA20",
                 entry2=lo20 - 0.25 * a, entry2_note="hard exit: breakdown below 20-day low",
                 stop=hi20 + 0.5 * a, stop_note="bear thesis wrong above 20-day high +0.5×ATR",
                 t1=lo60, t2=None)
    else:
        entry = max(lo20 + 0.25 * a, min(ma50, last))
        stop = lo20 - 1.0 * a
        p.update(bias="RANGE / NEUTRAL", entry=entry, entry_note="buy near range support / MA50",
                 entry2=hi20 * 1.005, entry2_note="or wait for breakout above 20-day high",
                 stop=stop, stop_note="below 20-day low − 1×ATR",
                 t1=hi20, t2=round(entry + 2.5 * (entry - stop), 2) if entry + 2.5 * (entry - stop) > hi20 else None)
    # ── bear-plan invalidation override (added 2026-08-21, TSLA case) ──
    # MA structure says DOWNTREND, but the close is already ABOVE the bear plan's own
    # "thesis wrong" line (20-day high + 0.5×ATR) while MA50 is not yet reclaimed.
    # The short case is dead even though the trend lens has not flipped — downgrade to
    # RANGE / NEUTRAL with a retest / MA50-reclaim plan instead of a stale AVOID / EXIT.
    if trend == "DOWNTREND" and last > p["stop"]:
        brk = hi20
        entry = brk
        stop = brk - 1.0 * a
        t2 = ma200 if (ma200 and ma200 > ma50) else entry + 2.5 * (entry - stop)
        trend = "RANGE"
        p.update(trend="RANGE", bias="RANGE / NEUTRAL", bear_invalidated=True,
                 entry=entry, entry_note="bear plan invalidated — buy retest of 20-day-high breakout",
                 entry2=ma50 * 1.005, entry2_note="or add on MA50 reclaim (trend flips to UPTREND)",
                 stop=stop, stop_note="below breakout level − 1×ATR",
                 t1=ma50, t2=t2)
    for k in ("entry", "entry2", "stop", "t1", "t2"):
        if p.get(k) is not None:
            p[k] = round(float(p[k]), 2)
    # target hygiene: an extended name has already outrun its pullback-anchored
    # targets — promote t2 / drop, so a LONG plan never shows T1 below the price.
    if p.get("bias") == "LONG":
        if p.get("t2") is not None and p["t2"] <= last:
            p["t2"] = None
        if p.get("t1") is not None and p["t1"] <= last:
            p["t1"], p["t2"] = p.get("t2"), None

    pats = detect_patterns(df, m_line)
    try:
        pats += detect_geometric(df)
    except Exception as e:  # geometry must never kill the chart run
        print(f"  [geo-pattern warn] {tkr}: {e}")
    try:
        pats += detect_volume_breakouts(df, pats)
    except Exception as e:
        print(f"  [vol-breakout warn] {tkr}: {e}")
    fib = None
    try:
        fib = fib_analysis(df)
        if fib:
            pats.append(fib)
    except Exception as e:
        print(f"  [fib warn] {tkr}: {e}")
    p["patterns"] = [x["msg"] for x in pats]
    # 盘中部分bar归一化为全日等效量 — 否则 RVOL 系统性偏低, 把放量突破
    # 误判成缩量假突破 (2026-08-25 HOOD)。见 intraday_volume.py
    _rv, _rv_est = _iv_rvol_now(df.Volume, ticker=tkr, index=df.index)
    p["rvol"] = _rv
    p["rvol_est"] = _rv_est          # True = 由未完成bar外推
    p["rvol_unusable"] = _rv is None  # 开盘初期外推不可信

    # ── extra metrics consumed by the 12-playbook classifier (打法归属) ──
    p["d5"] = round((last / float(c.iloc[-6]) - 1) * 100, 1) if len(c) > 6 else 0.0
    p["dist_ma20"] = round((last / ma20 - 1) * 100, 1)
    p["dist_ma50"] = round((last / ma50 - 1) * 100, 1)
    p["dist_ma200"] = round((last / ma200 - 1) * 100, 1) if ma200 else None
    p["ma10"] = round(float(c.rolling(10).mean().iloc[-1]), 2)
    p["ma20v"], p["ma50v"] = round(ma20, 2), round(ma50, 2)
    p["lo5"] = round(float(df.Low.iloc[-5:].min()), 2)  # 打法7 death-stop anchor
    v20_roll = df.Volume.rolling(20).mean()
    knife = False
    for i in (-2, -1):
        rng_ = float(df.High.iloc[i] - df.Low.iloc[i]) or 1e-9
        body_ = abs(float(df.Close.iloc[i] - df.Open.iloc[i])) / rng_
        chg_ = float(df.Close.iloc[i] / df.Close.iloc[i - 1] - 1)
        rv_ = (float(df.Volume.iloc[i] / v20_roll.iloc[i])
               if not np.isnan(v20_roll.iloc[i]) and v20_roll.iloc[i] > 0 else 0.0)
        if i == -1:                       # 今日未完成bar
            if p.get("rvol_unusable"):
                continue                  # 量能不可信 — 不判刀
            if p.get("rvol_est"):
                rv_ = p.get("rvol") or 0.0
        if chg_ < -0.03 and body_ > 0.70 and rv_ > 1.0:
            knife = True
    p["knife"] = knife
    # downtrend sub-typing inputs: box levels, death-cross, how long/fresh the break is
    p["hi20"], p["lo20"] = round(hi20, 2), round(lo20, 2)
    p["death_cross"] = bool(ma200 and ma50 < ma200)

    def _run_below(ma_series):
        n = 0
        for cv, mv in zip(c.iloc[::-1], ma_series.iloc[::-1]):
            if not np.isnan(mv) and cv < mv:
                n += 1
            else:
                break
        return n

    p["days_below_ma20"] = _run_below(df.MA20)
    p["days_below_ma50"] = _run_below(df.MA50)

    def _run_above(ma_series):
        n = 0
        for cv, mv in zip(c.iloc[::-1], ma_series.iloc[::-1]):
            if not np.isnan(mv) and cv > mv:
                n += 1
            else:
                break
        return n

    p["days_above_ma20"] = _run_above(df.MA20)
    p["days_above_ma50"] = _run_above(df.MA50)
    p["golden_cross"] = bool(ma200 and ma50 > ma200)
    # 打法13 金叉趋势闸: how many bars the current MA50-vs-MA200 state has held
    ma_d = (df.MA50 - df.MA200).dropna()
    cross_age = 0
    if len(ma_d):
        sgn = bool(ma_d.iloc[-1] > 0)
        for v in ma_d.iloc[::-1]:
            if bool(v > 0) == sgn:
                cross_age += 1
            else:
                break
    p["cross_age"] = cross_age
    # saturated = state held for the whole available MA200 window (true age unknown)
    p["cross_age_capped"] = bool(len(ma_d)) and cross_age == len(ma_d)

    # 打法14 MACD底背离 (backtested 抄底1): recent trough undercuts the prior
    # trough but MACD (below zero) holds higher; fresh golden cross ≤2 bars old.
    p["macd_div14"] = False
    if len(c) >= 70:
        cv, mv, sv = c.values, m_line.values, m_sig.values
        gc_fresh = any(mv[k] > sv[k] and mv[k - 1] <= sv[k - 1] for k in (-1, -2))
        j = len(cv) - 9 + int(np.argmin(cv[-9:]))
        lo_b, hi_b = len(cv) - 61, j - 5
        if gc_fresh and hi_b - lo_b >= 10:
            pj = lo_b + int(np.argmin(cv[lo_b:hi_b]))
            if cv[j] < cv[pj] and mv[j] > mv[pj] and mv[j] < 0:
                p["macd_div14"] = True
                p["div_low14"] = round(float(df.Low.values[j]), 2)  # 打法14 stop anchor

    # M顶禁买闸 (逃顶回测 2026-08-20: M双顶颈线破位后20日均值-6.7%, 下跌率68%):
    # scan the last 20 bars for a fresh M-top neckline break.
    p["mtop_break_days"] = None
    n_ = len(c)
    for k in range(0, min(20, max(0, n_ - 80))):
        i2 = n_ - 1 - k
        if i2 - 60 < 0:
            break
        seg2 = c.iloc[i2 - 15:i2 - 2]
        if len(seg2) < 5:
            break
        j2 = i2 - 15 + int(np.argmax(seg2.values))
        seg1 = c.iloc[i2 - 60:j2 - 7]
        if len(seg1) < 10:
            continue
        j1 = i2 - 60 + int(np.argmax(seg1.values))
        pk1, pk2 = float(c.iloc[j1]), float(c.iloc[j2])
        neck = float(c.iloc[j1:j2 + 1].min())
        if (abs(pk2 / pk1 - 1) <= 0.03 and neck < min(pk1, pk2) * 0.97
                and float(c.iloc[i2]) < neck and float(c.iloc[i2 - 1]) >= neck):
            p["mtop_break_days"] = k
            break

    # 打法15 金针探底 (backtested 抄底6): today/yesterday closed a long lower
    # wick (≥2×body and ≥1.2×ATR) in the upper half of the range after weakness.
    p["pin_bar15"] = False
    for k in (-1, -2):
        o_, h_ = float(df.Open.iloc[k]), float(df.High.iloc[k])
        l_, cl_ = float(df.Low.iloc[k]), float(df.Close.iloc[k])
        body_p = abs(cl_ - o_)
        wick_p = min(o_, cl_) - l_
        rng_p = (h_ - l_) or 1e-9
        atr_k = float(df.ATR.iloc[k]) if not np.isnan(df.ATR.iloc[k]) else 0.0
        weak_p = (not np.isnan(df.MA20.iloc[k]) and cl_ < float(df.MA20.iloc[k])) or \
                 float(df.Close.iloc[k] / df.Close.iloc[k - 5] - 1) <= -0.05
        if (atr_k > 0 and wick_p >= 2 * body_p and wick_p >= 1.2 * atr_k
                and (cl_ - l_) / rng_p >= 0.5 and weak_p):
            p["pin_bar15"] = True
            p["pin_low15"] = round(l_, 2)
            break
    # 打法16 纯图突破 (backtested 2026-08-21, backtest_pb16_gate_2026.py: 双闸 3yr
    # 单笔+6.9%/PF 2.72, MA50闸 +5.6%/PF 2.27; 量能/MACD确认反而减分, MACD死叉离场
    # 砍右尾): W双底颈线突破 or 20日平台新高, MA50上方, 今日或昨日触发;
    # 缩量蓄势闸 = 近5根BB带宽曾≤120日20分位 (打法2同款).
    p["pb16"] = None
    n16 = len(c)
    if n16 >= 130:
        bw_s = (df.BB_UP - df.BB_LO) / df.MA20 * 100
        bw_q20 = bw_s.rolling(120).quantile(0.20)
        hi20_s = df.High.rolling(20).max().shift(1)
        for k in (-1, -2):
            i2 = n16 + k
            if np.isnan(df.MA50.iloc[i2]) or float(c.iloc[i2]) <= float(df.MA50.iloc[i2]):
                continue
            pat16 = None
            seg2 = c.iloc[i2 - 15:i2 - 2]
            if len(seg2) >= 5:
                j2 = i2 - 15 + int(np.argmin(seg2.values))
                seg1 = c.iloc[i2 - 60:j2 - 7]
                if len(seg1) >= 10:
                    j1 = i2 - 60 + int(np.argmin(seg1.values))
                    tr1, tr2 = float(c.iloc[j1]), float(c.iloc[j2])
                    neck = float(c.iloc[j1:j2 + 1].max())
                    if (tr2 >= tr1 * 0.97 and neck > tr2 * 1.03
                            and float(c.iloc[i2]) > neck and float(c.iloc[i2 - 1]) <= neck):
                        pat16 = ("W双底颈线突破", neck, tr2)
            if (pat16 is None and not np.isnan(hi20_s.iloc[i2])
                    and float(c.iloc[i2]) > float(hi20_s.iloc[i2])
                    and float(c.iloc[i2 - 1]) <= float(hi20_s.iloc[i2 - 1])):
                atr16 = float(df.ATR.iloc[i2]) if not np.isnan(df.ATR.iloc[i2]) else 0.0
                pat16 = ("平台新高突破", float(hi20_s.iloc[i2]), float(df.Low.iloc[i2]) - 0.5 * atr16)
            if pat16:
                sq16 = bool((bw_s.iloc[i2 - 5:i2 + 1] <= bw_q20.iloc[i2 - 5:i2 + 1]).any())
                p["pb16"] = {"pattern": pat16[0], "level": round(pat16[1], 2),
                             "stop": round(pat16[2], 2), "squeeze": sq16, "age": -k - 1}
                break

    brk = []
    if len(c) >= 2:
        if last < ma20 and float(c.iloc[-2]) >= float(df.MA20.iloc[-2]):
            brk.append("MA20")
        if last < ma50 and float(c.iloc[-2]) >= float(df.MA50.iloc[-2]):
            brk.append("MA50")
        if last < lo20:
            brk.append("箱底")
    p["break_event"] = "+".join(brk) if brk else None
    p["break_volume_confirmed"] = bool(brk) and not p["rvol_unusable"] \
        and (p["rvol"] or 0) >= low_volume_threshold(1.2, p["rvol_est"])
    brk_up = []
    if len(c) >= 2:
        if last > ma20 and float(c.iloc[-2]) <= float(df.MA20.iloc[-2]):
            brk_up.append("MA20↑")
        if last > ma50 and float(c.iloc[-2]) <= float(df.MA50.iloc[-2]):
            brk_up.append("MA50↑")
        if last > hi20:
            brk_up.append("箱顶↑")
    p["break_event_up"] = "+".join(brk_up) if brk_up else None
    # asymmetry rule: UPSIDE breaks DO require volume (≥1.5x) — 缩量突破=假突破嫌疑
    p["break_up_volume_confirmed"] = bool(brk_up) and not p["rvol_unusable"] \
        and (p["rvol"] or 0) >= low_volume_threshold(1.5, p["rvol_est"])

    # ── explicit pattern target prices (measured moves + fib extensions) ──
    tgts = []
    for x in pats:
        nm = PAT_NAME.get(x["kind"], x["kind"])
        if x.get("target") is not None:
            tgts.append(dict(pattern=nm, target=round(float(x["target"]), 2)))
        if x.get("target_up") is not None:
            tgts.append(dict(pattern=nm + " break-up", target=round(float(x["target_up"]), 2)))
        if x.get("target_dn") is not None:
            tgts.append(dict(pattern=nm + " break-down", target=round(float(x["target_dn"]), 2)))
    if fib and fib["up"] and last >= fib["hi"] * 0.97:  # pressing the swing high → extensions in play
        for rr, px in fib["ext"]:
            tgts.append(dict(pattern=f"Fib ext {rr:.1%}", target=round(float(px), 2)))
    p["pattern_targets"] = tgts

    # ── analyst notes: patterns, MACD, RSI, MAs, volume, volatility ──
    obv_up = float(df.OBV.iloc[-5:].mean()) > float(df.OBV.iloc[-20:].mean())
    p["obv_up"] = bool(obv_up)
    m_now, s_now = float(m_line.iloc[-1]), float(m_sig.iloc[-1])
    h_now = float(m_hist.iloc[-1])
    h_pre = float(m_hist.iloc[-4]) if len(m_hist) >= 4 else 0.0
    sgn = np.sign((m_line - m_sig).values[-8:])
    fl = np.where(np.diff(sgn) != 0)[0]
    cross_txt = (f"; {'bullish' if sgn[-1] > 0 else 'bearish'} cross "
                 f"{len(sgn) - 2 - int(fl[-1])} bar(s) ago" if len(fl) else "")
    notes = dict(
        trend=f"{trend} — price {'above' if last > ma20 else 'below'} MA20 ${ma20:,.2f}, "
              f"{'above' if last > ma50 else 'below'} MA50 ${ma50:,.2f}"
              + (f", {'above' if last > ma200 else 'below'} MA200 ${ma200:,.2f}" if ma200 else ""),
        rsi=f"RSI(14) {r:.0f} — " + ("overbought, extended — don't chase" if r > 70 else
                                     "oversold — bounce-prone" if r < 30 else
                                     "bullish momentum zone" if r >= 55 else
                                     "bearish momentum zone" if r <= 45 else "neutral"),
        macd=f"MACD {m_now:+.2f} vs signal {s_now:+.2f} — {'bullish' if m_now > s_now else 'bearish'}, "
             f"histogram {'expanding' if abs(h_now) > abs(h_pre) else 'fading'}, "
             f"{'above' if m_now > 0 else 'below'} zero line{cross_txt}",
        volume=f"RVOL {p['rvol'] if p['rvol'] is not None else '—'}x vs 20-day avg · "
               f"OBV {'rising — accumulation' if obv_up else 'falling — distribution'}",
        volatility=f"ATR(14) ${a:,.2f} (~{a / last * 100:.1f}% daily range)",
    )
    # ── Bollinger Bands (20, 2σ): %B, bandwidth, squeeze, band-touch state ──
    bb_up_now = float(df.BB_UP.iloc[-1]) if not np.isnan(df.BB_UP.iloc[-1]) else None
    bb_lo_now = float(df.BB_LO.iloc[-1]) if not np.isnan(df.BB_LO.iloc[-1]) else None
    if bb_up_now is not None and bb_lo_now is not None and bb_up_now > bb_lo_now:
        pctb = (last - bb_lo_now) / (bb_up_now - bb_lo_now)
        bw = (bb_up_now - bb_lo_now) / ma20 * 100 if ma20 else None
        bw_series = ((df.BB_UP - df.BB_LO) / df.MA20 * 100).dropna()
        squeeze = (bw is not None and len(bw_series) >= 60
                   and float((bw_series.iloc[-120:] < bw).mean()) <= 0.15)
        rvol_now = p["rvol"] if p["rvol"] is not None else 0
        if last > bb_up_now:
            bb_state = ("volume-confirmed upper-band breakout — true breakout"
                        if rvol_now >= 1.5 and m_now > s_now else
                        "above upper band on light volume — suspect breakout, watch for fade"
                        if rvol_now < 1.0 else "above upper band — needs volume to confirm")
        elif last < bb_lo_now:
            bb_state = ("volume-confirmed lower-band breakdown — distribution"
                        if rvol_now >= 1.5 and m_now < s_now else
                        f"at/below lower band, RSI {r:.0f} — mean-reversion bounce candidate"
                        if r < 32 else "below lower band — stretched to the downside")
        elif pctb > 0.8:
            bb_state = "riding the upper band — strong trend (hold until midline break)"
        elif pctb < 0.2:
            bb_state = "hugging the lower band — weak tape"
        else:
            bb_state = "mid-band" + (", above midline (20SMA)" if last > ma20 else ", below midline (20SMA)")
        p["bb_pctb"], p["bb_bandwidth"], p["bb_squeeze"] = round(pctb, 2), round(bw, 1) if bw else None, bool(squeeze)
        notes["bollinger"] = (f"BB(20,2σ) {money(bb_lo_now)}–{money(bb_up_now)} · %B {pctb:.2f} · "
                              f"bandwidth {bw:.1f}%" + (" · SQUEEZE (tightest 15% of 6mo — big move brewing)"
                                                        if squeeze else "") + f" — {bb_state}")
    if fib:
        fibbits = ([f"support {money(fib['fib_sup'])}"] if fib.get("fib_sup") else []) + \
                  ([f"resistance {money(fib['fib_res'])}"] if fib.get("fib_res") else [])
        notes["fibonacci"] = (f"{'up' if fib['up'] else 'down'}swing ${fib['lo']:,.2f}→${fib['hi']:,.2f}; "
                              + ", ".join(fibbits) if fibbits else "no nearby fib level")
    if p["patterns"]:
        notes["patterns"] = " · ".join(m for m in p["patterns"] if not m.startswith("Fib ("))
    p["notes"] = notes

    # ── written trading recommendation ──
    pt_txt = ("; pattern targets " + ", ".join(f"{money(x['target'])} ({x['pattern']})"
              for x in tgts[:3])) if tgts else ""
    basis = (f"{trend.lower()}, MACD {'bullish' if m_now > s_now else 'bearish'}, RSI {r:.0f}, "
             f"OBV {'accumulating' if obv_up else 'distributing'}")
    if p["bias"] == "LONG":
        p["recommendation"] = (
            f"BUY — enter {money(p['entry'])} ({p['entry_note']}), add above {money(p['entry2'])}; "
            f"stop {money(p['stop'])}; targets {money(p['t1'])} then {money(p.get('t2'))}{pt_txt}. "
            f"Basis: {basis}.")
    elif p["bias"] == "AVOID / EXIT":
        p["recommendation"] = (
            f"AVOID new longs — if holding, exit bounces into {money(p['entry'])}, hard-exit below "
            f"{money(p['entry2'])}; bear thesis wrong above {money(p['stop'])}{pt_txt}. "
            f"Basis: {basis}.")
    elif p.get("bear_invalidated"):
        p["recommendation"] = (
            f"BEAR PLAN INVALIDATED — close above the 20-day-high +0.5×ATR line but MA50 not yet reclaimed; "
            f"buy retest of {money(p['entry'])}, add on MA50 reclaim {money(p['entry2'])}; "
            f"stop {money(p['stop'])}; targets MA50 {money(p['t1'])} then {money(p.get('t2'))}{pt_txt}. "
            f"Basis: {basis}.")
    else:
        p["recommendation"] = (
            f"RANGE — buy near {money(p['entry'])} or wait for the breakout above {money(p['entry2'])}; "
            f"stop {money(p['stop'])}; target {money(p['t1'])}{pt_txt}. Basis: {basis}.")

    # ── chart ──
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(11, 7.6), sharex=True,
        gridspec_kw=dict(height_ratios=[3, 1.1, 1.1], hspace=0.07))
    fig.patch.set_facecolor("white")
    ax1.fill_between(df.index, df.BB_LO, df.BB_UP, color="#5dade2", alpha=0.10, zorder=1)
    ax1.plot(df.index, df.BB_UP, color="#c0392b", lw=0.7, alpha=0.65, label="BB(20,2σ)")
    ax1.plot(df.index, df.BB_LO, color="#1a7f37", lw=0.7, alpha=0.65)
    ax1.plot(df.index, c, color="#1f77b4", lw=1.5, label="Close", zorder=5)
    ax1.plot(df.index, df.MA20, color="#e67e22", lw=0.9, label="MA20 / BB mid")
    ax1.plot(df.index, df.MA50, color="#9b59b6", lw=0.9, label="MA50")
    if ma200:
        ax1.plot(df.index, df.MA200, color="#7f8c8d", lw=1.0, ls="--", label="MA200")

    x0 = df.index[int(len(df) * 0.55)]
    price_span = float(df.High.max() - df.Low.min()) or 1.0
    drawn_labels = []  # y-values of level labels already placed, to avoid overlap

    def hline(y, col, label, ls="--"):
        if y is None:
            return
        ax1.plot([x0, df.index[-1]], [y, y], color=col, lw=1.3, ls=ls, zorder=4)
        dy = 0
        while any(abs((y + dy * price_span / 220) - prev) < price_span * 0.028 for prev in drawn_labels):
            dy += 7  # nudge label up until it clears earlier ones
        y_lab = y + dy * price_span / 220
        drawn_labels.append(y_lab)
        ax1.annotate(f"{label} ${y:,.2f}", xy=(df.index[-1], y_lab), xytext=(6, 0),
                     textcoords="offset points", fontsize=8, color=col,
                     fontweight="bold", va="center")

    if p["bias"] == "LONG":
        hline(p["entry"], "#1a7f37", "ENTRY"); hline(p["entry2"], "#1a7f37", "ADD>", ls=":")
        hline(p["stop"], "#c0392b", "STOP"); hline(p["t1"], "#2b8fbd", "T1"); hline(p["t2"], "#2b8fbd", "T2")
    elif p["bias"] == "AVOID / EXIT":
        hline(p["entry"], "#b8860b", "EXIT@"); hline(p["entry2"], "#c0392b", "BRKDN")
        hline(p["stop"], "#1a7f37", "RECLAIM"); hline(p["t1"], "#c0392b", "RISK→")
    else:
        hline(p["entry"], "#1a7f37", "BUY~"); hline(p["stop"], "#c0392b", "STOP")
        hline(p["t1"], "#2b8fbd", "T1"); hline(p["t2"], "#2b8fbd", "T2")

    # pattern-derived target prices (measured moves / fib extensions)
    ylo_d, yhi_d = float(df.Low.min()) * 0.9, float(df.High.max()) * 1.12
    for pt_ in p["pattern_targets"][:3]:
        tv = pt_["target"]
        if ylo_d < tv < yhi_d and abs(tv - last) / last > 0.01:
            hline(tv, "#8e44ad", f"PT {pt_['pattern'].split(' break-')[0][:14]}", ls=":")

    # draw detected patterns on the price panel
    for pat in pats:
        k = pat["kind"]
        if k in ("double_bottom", "double_top"):
            col = "#1a7f37" if k == "double_bottom" else "#c0392b"
            lab = "Bot" if k == "double_bottom" else "Top"
            for n, (ts, px) in enumerate(pat["points"], 1):
                ax1.scatter([ts], [px], s=85, facecolors="none", edgecolors=col, lw=1.8, zorder=6)
                ax1.annotate(f"{lab}{n} ${px:,.2f}", xy=(ts, px),
                             xytext=(0, -26 if k == "double_bottom" else 20),
                             textcoords="offset points", ha="center", fontsize=8,
                             color=col, fontweight="bold",
                             arrowprops=dict(arrowstyle="-", color=col, lw=0.8))
        elif k.startswith("breakout"):
            col = "#c0392b" if k == "breakout_bear" else "#1a7f37"
            ax1.axhline(pat["level"], color=col, lw=1.1, ls="-.", alpha=0.8)
            ax1.annotate(("BRKDN " if k == "breakout_bear" else "BRKOUT ") + f"${pat['level']:,.2f}",
                         xy=(df.index[max(0, len(df) - 90)], pat["level"]), xytext=(0, 5),
                         textcoords="offset points", fontsize=8, color=col, fontweight="bold")
        elif k == "cup_handle":
            ax1.axvspan(pat["start"], df.index[-2], color="#1a7f37", alpha=0.06)
            ax1.axhline(pat["rim"], color="#1a7f37", lw=1.0, ls="-.", alpha=0.8)
            ax1.annotate(f"cup rim ${pat['rim']:,.2f}", xy=(pat["start"], pat["rim"]),
                         xytext=(4, 5), textcoords="offset points", fontsize=8,
                         color="#1a7f37", fontweight="bold")
        elif k == "sr_levels":
            for lv in pat["levels"]:
                ax1.axhline(lv, color="#7f8c8d", lw=0.9, ls=(0, (2, 3)), alpha=0.7, zorder=3)
                ax1.annotate(f"S/R ${lv:,.2f}", xy=(df.index[3], lv), xytext=(0, 3),
                             textcoords="offset points", fontsize=7, color="#7f8c8d")
        elif k == "trendline":
            col = "#1a7f37" if pat["side"] == "support" else "#c0392b"
            ax1.plot([df.index[pat["x0"]], df.index[pat["x1"]]], [pat["y0"], pat["y1"]],
                     color=col, lw=1.5, alpha=0.9, zorder=5)
            ax1.annotate(f"{pat['side']} line", xy=(df.index[pat["x1"]], pat["y1"]),
                         xytext=(-64, 8 if pat["side"] == "support" else -12),
                         textcoords="offset points", fontsize=8, color=col, fontweight="bold")
        elif k in ("hs_top", "hs_inv"):
            col = "#c0392b" if k == "hs_top" else "#1a7f37"
            xs = [df.index[i] for i, _ in pat["pts"]]
            ys = [v for _, v in pat["pts"]]
            ax1.plot(xs, ys, color=col, lw=1.2, marker="o", mfc="none", ms=8, zorder=6)
            off = 10 if k == "hs_top" else -16
            for lab, xi, yi in zip(("LS", "HEAD", "RS"), xs, ys):
                ax1.annotate(lab, xy=(xi, yi), xytext=(0, off), textcoords="offset points",
                             ha="center", fontsize=7.5, color=col, fontweight="bold")
            (x0, y0), (x1, y1) = pat["neck"]
            ax1.plot([df.index[x0], df.index[x1]], [y0, y1], color=col, lw=1.4, ls="--", zorder=5)
            ax1.annotate(f"neckline → tgt ${pat['target']:,.2f}", xy=(df.index[x1], y1),
                         xytext=(6, 0), textcoords="offset points", fontsize=8,
                         color=col, fontweight="bold", va="center")
        elif k.startswith("triangle"):
            col = "#8e44ad"
            for side in ("upper", "lower"):
                (x0, y0), (x1, y1) = pat[side]
                ax1.plot([df.index[x0], df.index[x1]], [y0, y1], color=col, lw=1.6,
                         alpha=0.9, zorder=5)
            (x0, y0), _ = pat["upper"]
            ax1.annotate(pat["msg"].split(":")[0], xy=(df.index[x0], y0), xytext=(0, 12),
                         textcoords="offset points", fontsize=8, color=col, fontweight="bold")
        elif k.startswith("flag"):
            col = "#1a7f37" if k == "flag_bull" else "#c0392b"
            (x0, y0), (x1, y1) = pat["pole"]
            ax1.plot([df.index[x0], df.index[x1]], [y0, y1], color=col, lw=2.4,
                     alpha=0.55, zorder=5)
            for side in ("top", "bot"):
                (a0, b0), (a1, b1) = pat[side]
                ax1.plot([df.index[a0], df.index[a1]], [b0, b1], color=col, lw=1.2,
                         ls="--", zorder=5)
            ax1.annotate(("Bull flag" if k == "flag_bull" else "Bear flag") +
                         f" → tgt ${pat['target']:,.2f}",
                         xy=(df.index[x1], y1), xytext=(6, -14), textcoords="offset points",
                         fontsize=8, color=col, fontweight="bold")
        elif k == "vol_breakout":
            up_ = pat["dir"] == "up"
            col = "#1a7f37" if up_ else "#c0392b"
            bx = df.index[pat["bar"]]
            by = float(df.Low.iloc[pat["bar"]]) * 0.985 if up_ else float(df.High.iloc[pat["bar"]]) * 1.015
            ax1.scatter([bx], [by], marker="^" if up_ else "v", s=120, color=col,
                        zorder=7, edgecolors="white", lw=0.6)
            ax1.axhline(pat["level"], color=col, lw=1.2, ls="-.", alpha=0.85)
            ax1.annotate(f"{'VOL BRKOUT' if up_ else 'VOL BRKDN'} {pat['rvol']:.1f}x @ ${pat['level']:,.2f}",
                         xy=(bx, by), xytext=(-12, -20 if up_ else 14),
                         textcoords="offset points", fontsize=8, color=col, fontweight="bold")
        elif k == "coil":
            ax1.axhline(pat["level"], color="#b8860b", lw=1.2, ls="-.", alpha=0.9)
            ax1.axvspan(df.index[pat["x0"]], df.index[-1], color="#b8860b", alpha=0.10)
            ax1.annotate(f"coiling < ${pat['level']:,.2f}", xy=(df.index[pat["x0"]], pat["level"]),
                         xytext=(2, 5), textcoords="offset points", fontsize=8,
                         color="#b8860b", fontweight="bold")
        elif k == "fib":
            x_sw = min(pat["hi_ts"], pat["lo_ts"])
            for rr, px in pat["retr"]:
                ax1.plot([x_sw, df.index[-1]], [px, px], color="#b087c4", lw=0.8,
                         ls=(0, (4, 3)), alpha=0.7, zorder=3)
                ax1.annotate(f"{rr:.1%}", xy=(x_sw, px), xytext=(-2, 1),
                             textcoords="offset points", ha="right", fontsize=7, color="#9b59b6")
            ylo_f, yhi_f = float(df.Low.min()) * 0.97, float(df.High.max()) * 1.06
            for rr, px in pat["ext"]:
                if ylo_f < px < yhi_f:
                    ax1.plot([x_sw, df.index[-1]], [px, px], color="#9b59b6", lw=0.9,
                             ls=":", alpha=0.85, zorder=3)
                    ax1.annotate(f"fib ext {rr:.1%} ${px:,.2f}", xy=(x_sw, px), xytext=(2, 3),
                                 textcoords="offset points", fontsize=7.5,
                                 color="#9b59b6", fontweight="bold")
            ax1.scatter([pat["lo_ts"], pat["hi_ts"]], [pat["lo"], pat["hi"]], s=42,
                        marker="D", color="#9b59b6", zorder=6, alpha=0.9)
        elif k in ("golden_cross", "death_cross"):
            col = "#1a7f37" if k == "golden_cross" else "#c0392b"
            ax1.axvline(pat["ts"], color=col, lw=1.0, ls=":", alpha=0.8)
            ax1.annotate("golden cross" if k == "golden_cross" else "death cross",
                         xy=(pat["ts"], float(df.MA50.iloc[-3])), xytext=(-4, 10),
                         textcoords="offset points", fontsize=8, color=col,
                         fontweight="bold", rotation=90, va="bottom", ha="right")
    macd_div = next((x["msg"] for x in pats if x["kind"].startswith("macd_")), None)

    vcol = {"UPTREND": "#1a7f37", "DOWNTREND": "#c0392b", "RANGE": "#b8860b"}[trend]
    title_pat = next((x for x in pats if x["kind"] != "sr_levels"), None)
    pat_note = f"  |  {title_pat['msg'].split('(')[0].strip()}" if title_pat else ""
    ax1.set_title(f"{tkr}  ${last:,.2f}  |  {trend}, MACD {p['macd']}, RSI {p['rsi']}  |  {sector}{pat_note}",
                  loc="left", fontsize=11, fontweight="bold", color=vcol)
    ax1.legend(loc="upper left", fontsize=7.5, ncol=4, frameon=False)
    ax1.grid(alpha=0.22); ax1.set_ylabel("Price ($)")

    up = c.diff() >= 0
    ax2.bar(df.index[up], df.Volume[up], color="#2ecc71", alpha=0.5, width=1.0)
    ax2.bar(df.index[~up], df.Volume[~up], color="#e74c3c", alpha=0.5, width=1.0)
    ax2.plot(df.index, df.Volume.rolling(20).mean(), color="#b8860b", lw=1.0,
             alpha=0.9, label="Vol MA20")
    for pat in pats:  # highlight the volume bar that confirmed a breakout
        if pat["kind"] == "vol_breakout":
            bcol = "#1a7f37" if pat["dir"] == "up" else "#c0392b"
            ax2.bar([df.index[pat["bar"]]], [float(df.Volume.iloc[pat["bar"]])],
                    color=bcol, alpha=1.0, width=1.4, edgecolor="#1c2530", lw=0.7, zorder=6)
            ax2.annotate(f"{pat['rvol']:.1f}x", xy=(df.index[pat["bar"]],
                         float(df.Volume.iloc[pat["bar"]])), xytext=(0, 3),
                         textcoords="offset points", ha="center", fontsize=7.5,
                         color=bcol, fontweight="bold")
    ax2.set_ylabel("Vol"); ax2.grid(alpha=0.22)
    ax2b = ax2.twinx()
    ax2b.plot(df.index, df.OBV, color="#34495e", lw=1.0)
    ax2b.set_ylabel("OBV"); ax2b.set_yticklabels([])

    ax3.plot(df.index, m_line, color="#1f77b4", lw=1.0, label="MACD")
    ax3.plot(df.index, m_sig, color="#e67e22", lw=1.0, label="Signal")
    ax3.bar(df.index, m_hist, color=np.where(m_hist >= 0, "#2ecc71", "#e74c3c"), alpha=0.55, width=1.0)
    ax3.axhline(0, color="#7f8c8d", lw=0.7)
    ax3.legend(loc="upper left", fontsize=7.5, ncol=2, frameon=False)
    ax3.grid(alpha=0.22); ax3.set_ylabel("MACD")
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    if macd_div:
        col = "#1a7f37" if "Bullish" in macd_div else "#c0392b"
        ax3.annotate(macd_div, xy=(0.99, 0.92), xycoords="axes fraction",
                     ha="right", va="top", fontsize=8, color=col, fontweight="bold")

    fig.savefig(CHART_DIR / f"{tkr}.png", dpi=92, bbox_inches="tight")
    plt.close(fig)
    return p


# ── HTML rendering ─────────────────────────────────────────────────────
CSS = """
:root { --bg:#f7f8f9; --card:#fff; --ink:#1c2530; --muted:#5b6875; --line:#dde3e8;
 --accent:#2b5f8f; --buy:#1a7f37; --buy-bg:#e7f3ea; --hold:#9a6d00; --hold-bg:#f8f0da;
 --sell:#b3352b; --sell-bg:#f9e8e6; }
@media (prefers-color-scheme: dark) { :root { --bg:#12161c; --card:#1a2029; --ink:#e2e8ef;
 --muted:#9aa7b4; --line:#2a3340; --accent:#7aaede; --buy:#5fbf7d; --buy-bg:#16301f;
 --hold:#d9ae4a; --hold-bg:#332a12; --sell:#e07b71; --sell-bg:#381e1b; } }
:root[data-theme="dark"] { --bg:#12161c; --card:#1a2029; --ink:#e2e8ef; --muted:#9aa7b4;
 --line:#2a3340; --accent:#7aaede; --buy:#5fbf7d; --buy-bg:#16301f; --hold:#d9ae4a;
 --hold-bg:#332a12; --sell:#e07b71; --sell-bg:#381e1b; }
:root[data-theme="light"] { --bg:#f7f8f9; --card:#fff; --ink:#1c2530; --muted:#5b6875;
 --line:#dde3e8; --accent:#2b5f8f; --buy:#1a7f37; --buy-bg:#e7f3ea; --hold:#9a6d00;
 --hold-bg:#f8f0da; --sell:#b3352b; --sell-bg:#f9e8e6; }
body { background:var(--bg); color:var(--ink); margin:0; padding:32px 20px 64px;
 font:15px/1.55 "Segoe UI", system-ui, sans-serif; }
main { max-width:1040px; margin:0 auto; }
h1 { font-family:Charter, Georgia, serif; font-size:29px; margin:0 0 6px; }
h2 { font-family:Charter, Georgia, serif; font-size:21px; margin:38px 0 14px;
 padding-top:20px; border-top:2px solid var(--line); }
h3 { font-family:Charter, Georgia, serif; font-size:19px; margin:0; }
.sub { color:var(--muted); font-size:14px; margin:0 0 18px; } .sub b { color:var(--ink); }
.summary-wrap { overflow-x:auto; background:var(--card); border:1px solid var(--line); border-radius:10px; }
table.summary { border-collapse:collapse; width:100%; font-size:13px; font-variant-numeric:tabular-nums; }
table.summary th, table.summary td { padding:6px 11px; text-align:right; border-bottom:1px solid var(--line); white-space:nowrap; }
table.summary th:first-child, table.summary td:first-child,
table.summary th:nth-child(2), table.summary td:nth-child(2),
table.summary th:nth-child(4), table.summary td:nth-child(4) { text-align:left; }
table.summary thead th { color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:0.06em; }
.tag { font-size:11px; font-weight:700; padding:2px 8px; border-radius:5px; }
.tag.buy { color:var(--buy); background:var(--buy-bg); } .tag.hold { color:var(--hold); background:var(--hold-bg); }
.tag.sell { color:var(--sell); background:var(--sell-bg); }
.tk { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:20px 22px; margin-bottom:22px; }
.tk-head { display:flex; justify-content:space-between; gap:14px; flex-wrap:wrap; align-items:flex-start; margin-bottom:12px; }
.co { color:var(--muted); font-size:14px; font-weight:400; font-family:"Segoe UI", system-ui, sans-serif; }
.meta { margin:3px 0 0; color:var(--muted); font-size:13px; }
.badge { font-size:12.5px; font-weight:700; letter-spacing:0.04em; padding:6px 13px; border-radius:6px; white-space:nowrap; }
.badge.buy { color:var(--buy); background:var(--buy-bg); } .badge.hold { color:var(--hold); background:var(--hold-bg); }
.badge.sell { color:var(--sell); background:var(--sell-bg); }
.chart { background:#fff; border:1px solid var(--line); border-radius:8px; padding:6px; overflow-x:auto; }
.chart img { display:block; width:100%; height:auto; }
table.plan { border-collapse:collapse; width:100%; margin-top:12px; font-size:13.5px; font-variant-numeric:tabular-nums; }
table.plan th { text-align:left; color:var(--muted); font-weight:600; padding:5px 12px 5px 0; width:230px; }
table.plan td { padding:5px 12px 5px 0; border-bottom:1px dotted var(--line); }
table.plan td:nth-child(2) { font-weight:700; white-space:nowrap; }
.pos { color:var(--buy); } .neg { color:var(--sell); }
.method { background:var(--card); border:1px solid var(--line); border-radius:10px;
 padding:16px 20px; font-size:13.5px; color:var(--muted); margin:18px 0 8px; } .method b { color:var(--ink); }
footer { color:var(--muted); font-size:13px; margin-top:26px; border-top:1px solid var(--line); padding-top:14px; }
"""

METHOD = ('<div class="method"><b>How the levels are set.</b> Trend from the MA20/MA50/MA200 stack. '
          '<b>Uptrends</b>: enter on a pullback to MA20 (or at market when already there), add above the '
          '20-day high; stop below MA50 or 2×ATR; T1 = +1.5R, T2 = +3R with an MA20 trail. '
          '<b>Ranges</b>: buy near support/MA50, stop 1×ATR under the 20-day low, target the range high. '
          '<b>Downtrends</b>: no new longs — sell bounces into MA20, hard-exit on a close below the 20-day '
          'low; the long thesis only reopens above the 20-day high +0.5×ATR. Size so a stop-out risks ≤1% '
          'of the account: shares = (1% × account) ÷ (entry − stop).</div>')

CSS += """
.rec { margin:12px 0 4px; padding:9px 13px; border-radius:8px; font-size:14px;
 background:var(--hold-bg); border-left:3px solid var(--hold); }
.rec.buy { background:var(--buy-bg); border-left-color:var(--buy); }
.rec.sell { background:var(--sell-bg); border-left-color:var(--sell); }
ul.notes { margin:10px 0 0; padding-left:18px; font-size:13px; color:var(--muted); }
ul.notes li { margin:2px 0; } ul.notes b { color:var(--ink); text-transform:uppercase; font-size:11px; letter-spacing:.4px; }
"""

FOOT = ('<footer>Algorithmic technical analysis only — not financial advice. '
        'Levels move with price — refresh before acting.</footer>')


# ═══════════════════════════════════════════════════════════════════════════
#  12-playbook assignment (打法归属) — runs after all plans are computed.
#  Self-contained on this script's own indicators; optionally enriched by
#  same-day band-engine reports, the latest LT-quality scores, and the
#  cross-market gates (恒生→中概 12b, BTC→高贝塔 12c) when available.
# ═══════════════════════════════════════════════════════════════════════════
PLAYBOOK_LEGEND = ("打法: 1=回踩企稳 2=缩量平台突破 3=强弱轮动 4=事件驱动 "
                   "7=下轨恐慌反转 8=带行持有/离场 9=首回踩MA50 11=金字塔加仓 "
                   "12b/12c=跨市场修正 13=金叉趋势闸(长线底仓) "
                   "14=MACD底背离 15=金针探底(轻仓) 16=纯图突破(W底/平台+MA50闸) 避=不做")


def _parse_band_md(path, sections):
    """{ticker: (bucket_label, signals_text)}.

    The signals text is kept because a band bucket is filled by several
    different rules — e.g. the SELL bucket holds R3 fake-breakouts and
    R4/R5 exhaustion tags as well as genuine R7 midline breaks — and the
    playbook mapping must tell them apart.
    """
    out = {}
    try:
        txt = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for header, label in sections:
        m = re.search(re.escape(header) + r".*?(?=\n## |\Z)", txt, re.S)
        if m:
            for row in re.finditer(r"\n\| ([A-Z0-9.\-]+) \|([^\n]*)", m.group(0)):
                out.setdefault(row.group(1), (label, row.group(2)))
    return out


RUN_WARNINGS = []  # collected across the run; written into the JSON so downstream
                   # readers (6PM report) can see degraded inputs instead of silence


def _load_band_verdicts():
    """Same-day band-top/-bottom engine verdicts; empty dicts if not run yet.
    Missing or stale files are WARNED, not silently degraded — without them the
    band-driven playbooks (7 / 8离场 / 8减仓 / 避-向下带行) all vanish."""
    for path, tag in ((HERE / f"bollinger_top_{TODAY}.md", "带顶引擎"),
                      (HERE / f"bollinger_bottom_{TODAY}.md", "带底引擎")):
        if not path.exists():
            RUN_WARNINGS.append(f"{tag}文件缺失({path.name}) — 带轨打法(7/8)静默降级为纯技术规则; "
                                "先跑 bollinger_top/bottom_strategy.py 再跑本脚本")
        else:
            age_h = (datetime.now().timestamp() - path.stat().st_mtime) / 3600
            if age_h > 2:
                RUN_WARNINGS.append(f"{tag}报告为 {age_h:.1f} 小时前生成 — 桶判定基于旧价格, 建议重跑")
    top = _parse_band_md(HERE / f"bollinger_top_{TODAY}.md", [
        ("## 🔴 SELL / TRIM", "SELL"), ("## 🟠 SELL-PARTIAL", "SELL-PART"),
        ("## ⛔ DON'T ADD", "DONT-ADD"), ("## 👀 APPROACHING", "APPROACH"),
        ("## 🟢 HOLD-RIDE", "HOLD-RIDE")])
    bot = _parse_band_md(HERE / f"bollinger_bottom_{TODAY}.md", [
        ("## 🟢 BUY / ACCUMULATE", "BOT-BUY"), ("## 👀 BOTTOM-WATCH", "BOT-WATCH"),
        ("## ⚠️ BEAR-SQUEEZE", "BEAR-SQZ"), ("## 🔻 WALK-DOWN", "WALK-DN")])
    return top, bot


def _load_lt_scores():
    """Latest long_term_strategy_*.json → {ticker: score} (quality gate for 打法7)."""
    files = sorted(HERE.glob("long_term_strategy_*.json"))
    if not files:
        return {}
    try:
        data = json.loads(files[-1].read_text(encoding="utf-8"))
        return {t: v.get("score") for t, v in data.items() if isinstance(v, dict)}
    except Exception:
        return {}


def _market_gates():
    """12b: 恒生 below MA200 → China longs get观察仓 only.
       12c: BTC not at a fresh 20-day high → crypto high-beta stays half-size."""
    g = dict(hsi_below_ma200=None, btc_ignited=None)
    try:
        raw = yf.download(["^HSI", "BTC-USD"], period="1y", interval="1d",
                          auto_adjust=True, group_by="ticker", progress=False)
        hc = raw["^HSI"]["Close"].dropna()
        if len(hc) >= 200:
            g["hsi_below_ma200"] = bool(float(hc.iloc[-1]) < float(hc.rolling(200).mean().iloc[-1]))
        bc = raw["BTC-USD"]["Close"].dropna()
        if len(bc) >= 21:
            g["btc_ignited"] = bool(float(bc.iloc[-1]) >= float(bc.iloc[-21:-1].max()))
    except Exception as e:
        print(f"  [gate warn] cross-market gates unavailable: {e}")
    return g


def _deep_discount_map(tickers):
    """深折扣区 shadow tag (backtest_smc_bottom_2026.py, 2026-09-19): 前一段大升浪(≥30%)
    L→H 回吐 ≥.786 且收盘仍在 L 上方。2022-26 回测: 打法14 区内 PF 2.08 vs 区外 1.41
    (5年全胜), 打法15 区内 86%胜率 (n=21); 回撤越深越好(单调), 不是 .786 魔法数字。
    只当 14/15 的升级修正器 — 单独触及不是买点(触及后平均再跌 24%)。需要 2y 数据,
    主下载只有 1y, 所以单独拉一次。"""
    out = {}
    try:
        raw = yf.download(list(tickers), period="2y", interval="1d", auto_adjust=True,
                          group_by="ticker", progress=False, threads=True)
    except Exception as e:
        print(f"  [deep-discount warn] 2y download failed: {e}")
        return out
    for t in tickers:
        try:
            d = raw[t].dropna(subset=["Close"])
            if len(d) < 300:
                continue
            h, l = d["High"].values, d["Low"].values
            k = len(h) - 253 + int(np.argmax(h[-253:]))
            lo_start = max(0, k - 252)
            if k - lo_start < 20:
                continue
            H, L = float(h[k]), float(l[lo_start:k + 1].min())
            if H / L - 1 < 0.30:
                continue
            z = H - 0.786 * (H - L)
            c = float(d["Close"].iloc[-1])
            if float(l[-10:].min()) <= z and c > L:
                out[t] = {"swing_low": round(L, 2), "swing_high": round(H, 2), "z786": round(z, 2),
                          "retrace": round((H - c) / (H - L), 3)}
        except Exception:
            continue
    return out


def _playbook_one(p, bt_raw, bb_raw, lt_score):
    bt, bt_sig = bt_raw if isinstance(bt_raw, tuple) else (bt_raw, "")
    bb, bb_sig = bb_raw if isinstance(bb_raw, tuple) else (bb_raw, "")
    quality = (lt_score or 0) >= 50 or (p.get("dist_ma200") or -1) > 0
    up = (p.get("dist_ma50") or -1) > 0
    # 打法8 的离场定义只有一条: 首次放量收破 MA20 中轨。价仍在中轨上方时,
    # 带顶引擎的 R3 假突破 / R4-R5 衰竭触带只构成"减仓+收紧止损", 不构成离场
    # (触上轨不是卖点, RSI 高不是卖出理由)。None 视为未知 → 保守走减仓。
    dm20 = p.get("dist_ma20")
    below_mid = dm20 is not None and dm20 <= 0
    midline_break = "R7" in bt_sig and below_mid
    if bt == "SELL":
        if midline_break:
            return "8离场", "带行首次收破MA20中轨 — 离场信号"
        return "8减仓", ("带顶衰竭/假突破触发但价仍在MA20中轨上方 — 兑现1/3–1/2, "
                        "止损上移MA10; 唯一离场仍是收盘放量破MA20")
    if bt == "SELL-PART":
        if midline_break:
            return "8减仓", "带行中轨破位 — 兑现部分, 止损上移MA10, 收盘确认破中轨则全退"
        return "8减仓", "带顶衰竭迹象 — 兑现部分, 止损上移MA10, 破中轨全退"
    if p.get("knife"):
        # 位置决定语义: 远在中轨上方的放量长阴是派发, 不是接刀。禁买相同,
        # 但持仓纪律走打法8(减仓+MA10跟踪), 离场仍只认收盘放量破MA20。
        if dm20 is not None and dm20 > KNIFE_FAR_ABOVE_MA20:
            return "8减仓-派发", (f"放量长阴(实体>70%·RVOL>1)但价在MA20上方{dm20:.1f}% — "
                                "抛物线后顶部派发, 非支撑位接刀; 兑现1/3–1/2并禁新买, "
                                "唯一离场仍是收盘放量破MA20")
        return "刀-禁接", "近两日放量长阴(实体>70%·RVOL>1) — 出现缩量企稳+反包前禁买"
    if bb == "BOT-BUY":
        if quality:
            return "7", "带底反转确认+质量合格 — 小仓死止损, 目标中轨"
        return "避(7质量不合格)", "带底信号但LT<50且MA200下方 — 恐慌反转不适用"
    if bb == "BOT-WATCH":
        if quality:
            return "7候选-等确认", "底部原料就位 — 等洗仓反转序列完成再进"
        return "避(7质量不合格)", "深度超卖但质量差 — 只记录不接"
    if bb == "BEAR-SQZ":
        return "避(空头挤压)", "贴下轨窄带 — 变盘偏下, 非买点"
    if bb == "WALK-DN":
        return "避(向下带行)", "向下带行 — 收复MA20中轨前不接"
    if p.get("pb16") and up:
        g16 = p["pb16"]
        gate16 = "双闸(蓄势+MA50)" if g16["squeeze"] else "MA50闸(无蓄势)"
        return "16", (f"纯图突破 {g16['pattern']} {money(g16['level'])} "
                      f"({'今日' if g16['age'] == 0 else '昨日'}触发) + {gate16} — "
                      "回测不看量不看MACD, 止损形态低点, 唯一离场=收盘跌破MA20")
    if p.get("bb_squeeze") and up:
        return "2", "布林挤压+趋势向上 — 挂突破触发单, 量能须≥1.5x, 缩量突破不追"
    if up and (p.get("d5") or 0) < 0 and abs(p.get("dist_ma20") or 99) <= 3.5:
        return "1", "趋势股回踩MA20/前突破位 — 等企稳K线(缩量十字/长下影/放量反包)三选一"
    if up and (p.get("dist_ma20") or 0) < 0 and abs(p.get("dist_ma50") or 99) <= 2.0:
        return "9", "MA20失守后首回踩MA50±2% — 等企稳bar, 止损MA50下方1.5×ATR"
    if bt in ("HOLD-RIDE", "APPROACH") or ((p.get("bb_pctb") or 0) >= 0.8 and up):
        return "8持有", "带行%B>0.8 — 触上轨不是卖点, 唯一离场=首次放量收破MA20"
    if bt == "DONT-ADD":
        return "8持有-禁加", "贴上轨但缩量/过热 — 持有可以, 不开新仓不加仓"
    if up and (p.get("chg20") or 0) > 8:
        return "3/11", "相对强势领先 — 轮动名单内, 回调按金字塔三段式加仓"
    if up:
        return "1等回调", "趋势完好但价位未到 — 等回踩MA20/前突破位再启动打法1"
    # 抄底信号 (回测晋升 2026-08-20): 排在带轨引擎结论之后、默认"避"之前
    if p.get("pin_bar15") and p.get("macd_div14"):
        return "14+15", ("MACD底背离+金针探底共振 — 中期反转概率升级, 仍轻仓, "
                         f"止损 {p.get('pin_low15')} 下方")
    if p.get("pin_bar15"):
        return "15金针", (f"大跌收超长下影(金针) — 轻仓试错博短线修复, "
                         f"止损 {p.get('pin_low15')} 下方, 目标MA20")
    if p.get("macd_div14"):
        return "14底背离", "股价创新低但MACD不创新低+金叉触发 — 中期反转波段, 小仓, 止损背离低点"
    if p.get("trend") == "RANGE":
        return "避(箱体)", "箱体震荡无边际 — 等突破方向或催化剂(打法4)落地"
    return "避", "趋势空头 — 不做多"


def assign_playbooks(plans):
    top, bot = _load_band_verdicts()
    lt = _load_lt_scores()
    gates = _market_gates()
    deep = _deep_discount_map(list(plans))
    enrich = []
    if top or bot:
        enrich.append("band-engine")
    if lt:
        enrich.append("LT-quality")
    if gates["hsi_below_ma200"] is not None:
        enrich.append("cross-market")
    if deep:
        enrich.append(f"deep-discount:{len(deep)}")
    for t, p in plans.items():
        pb, why = _playbook_one(p, top.get(t), bot.get(t), lt.get(t))
        if (p["sector"] == "China" and gates["hsi_below_ma200"]
                and not pb.startswith("避") and "离场" not in pb):
            pb += "·12b闸"
            why += "; 恒生MA200下方 — 中概多头降一级只给观察仓"
        if (p["sector"] == "Crypto" and gates["btc_ignited"] is False
                and t != "BTC-USD" and pb.split("·")[0] in ("2", "3/11", "8持有", "1", "1等回调", "16")):
            pb += "·12c"
            why += "; BTC挤压未引爆 — 高贝塔仓位减半"
        # 打法13 金叉趋势闸 — 长线底仓过滤器 (2024-26回测: 每票复利+49%/+19%/+4%, 胜率~50%)
        if p.get("death_cross") and not pb.startswith("避") and "离场" not in pb:
            age = f"{'≥' if p.get('cross_age_capped') else ''}{p.get('cross_age', '?')}"
            pb += "·13死叉闸"
            why += (f"; MA50<MA200死叉{age}日 — "
                    "长线底仓不持有, 仅限短线打法轻仓")
        elif (p.get("golden_cross") and (p.get("cross_age") or 99) <= 10
                and not p.get("cross_age_capped")):
            pb += "·13新金叉"
            why += (f"; MA50上穿MA200仅{p.get('cross_age')}日 — 长线底仓可开始建仓, "
                    "死叉即清底仓")
        # M顶禁买闸: fresh M-top neckline break vetoes buy-side playbooks for 20 days
        if (p.get("mtop_break_days") is not None
                and pb.split("·")[0] in ("1", "2", "7", "7候选-等确认", "9", "3/11",
                                          "1等回调", "14底背离", "15金针", "14+15", "16")):
            pb += "·M顶闸"
            why += (f"; M双顶破颈线{p['mtop_break_days']}日内(禁买期20日) — "
                    "不接回调不抄底, 回测破位后20日均值-6.7%")
        # 深折扣区 — 影子标签: 只升级 14/15 的置信度, 不改行动档位/仓位 (2026-09-19, 待3个月影子期验证)
        dd = deep.get(t)
        p["deep_disc"] = dd
        if dd and (p.get("macd_div14") or p.get("pin_bar15")) and "M顶闸" not in pb:
            pb += "·深折扣区"
            sig = "+".join(n for n, f in (("14底背离", "macd_div14"), ("15金针", "pin_bar15")) if p.get(f))
            why += (f"; {sig} 落在深折扣区(大升浪 {dd['swing_low']}→{dd['swing_high']} 已回吐 {dd['retrace']:.0%}, "
                    f".786线 {dd['z786']}) — 回测区内 打法14 PF 2.08 vs 1.41 / 打法15 胜率86%, 置信度升级(影子标签, 不改仓位)")
        p["playbook"], p["playbook_note"] = pb, why
    print(f"  playbooks assigned ({', '.join(enrich) if enrich else 'technicals only'})")
    for w in RUN_WARNINGS:
        print(f"  ⚠️ {w}")


# ═══════════════════════════════════════════════════════════════════════════
#  Per-ticker ACTION PLAN — concrete "what do I do tonight" instruction:
#  action tier + trigger price + confirmation条件 + stop + R-sizing (打法10).
# ═══════════════════════════════════════════════════════════════════════════
ACTION_TIERS = ["✅ 分批买入", "👀 企稳等确认", "🎯 突破触发单", "🟢 持有",
                "🟠 减仓", "🔴 离场", "⚪ 观察", "❌ 回避"]


def _rsize(entry, stop):
    """打法10: 仓位% = 1% ÷ 止损距离%. Returns (risk%, size%) or None."""
    if not entry or not stop or entry <= 0 or stop >= entry:
        return None
    risk = (entry - stop) / entry * 100
    if risk <= 0.5:
        return None
    return risk, min(100.0, 100.0 / risk)


def _fmt_rsize(entry, stop):
    rs = _rsize(entry, stop)
    return f"止损距 {rs[0]:.1f}% → R仓位≈{rs[1]:.0f}%" if rs else "止损距离异常, 手动核对"


def _dt_profile(p):
    """Sub-type a bearish name — the four downtrends require different handling:
       结构空头 (death-cross, deep) / 破位初期 (fresh break, reclaim line near) /
       麻木阴跌 (long numb walk-down, no capitulation) / 空头 (generic)."""
    if 1 <= (p.get("days_below_ma20") or 0) <= 2 and not (p.get("death_cross") and (p.get("days_below_ma50") or 0) > 10):
        return "破位初期"
    if (p.get("days_below_ma20") or 0) >= 8 and not p.get("rvol_unusable") \
            and (p.get("rvol") or 1) < low_volume_threshold(0.9, p.get("rvol_est")):
        return "麻木阴跌"
    if p.get("death_cross") and (p.get("dist_ma50") or 0) < 0:
        return "结构空头"
    return "空头"


def _up_profile(p):
    """Sub-type a bullish name — fresh breakouts, fresh reclaims, extension and
       band-rides all demand different entries:
       突破初期 (broke out today, volume decides real/fake) / 修复初期 (just
       reclaimed MA20, right-side start) / 强势延伸 (extended, don't chase) /
       带行 (%B ride) / 多头 (generic)."""
    # 突破初期 = a REAL box-top breakout while the trend is still young; a new
    # 20-day high on an established 2-week+ ride is just band-walk, not an event
    if "箱顶↑" in (p.get("break_event_up") or "") and (p.get("days_above_ma20") or 99) <= 5:
        return "突破初期"
    if 1 <= (p.get("days_above_ma20") or 0) <= 2:
        return "修复初期"
    if (p.get("dist_ma20") or 0) >= 12 or (p.get("rsi") or 0) >= 78:
        return "强势延伸"
    if (p.get("bb_pctb") or 0) >= 0.8:
        return "带行"
    return "多头"


BUY_SIDE_PLAYBOOKS = ("1", "2", "9", "3/11", "1等回调", "7", "7候选-等确认",
                      "14底背离", "15金针", "14+15", "16")


def _action_one(p):
    pbfull = p.get("playbook") or ""
    base = pbfull.split("·")[0]
    gated_12b = "12b闸" in pbfull
    gated_12c = "12c" in pbfull
    # ── unified gate intercept: a veto suffix must veto the ACTION in every
    #    buy-side branch, not only the branches that remember to check it
    #    (2026-08-24 fix: FUTU had "16·12b闸" yet the action said 分批买入) ──
    if base in BUY_SIDE_PLAYBOOKS and "M顶闸" in pbfull:
        g16m = p.get("pb16") or {}
        head = (f"[纯图突破-{g16m.get('pattern')}] 突破 {money(g16m.get('level'))} 但"
                if base == "16" else f"打法{base}信号成立但")
        return "⚪ 观察", (f"{head}处于M双顶破颈线禁买期({p.get('mtop_break_days')}日/20日) — "
                          "不接回调不追突破; 禁买期满且信号仍成立再按原打法执行")
    if base in BUY_SIDE_PLAYBOOKS and gated_12b:
        return "⚪ 观察", (f"打法{base}信号成立但恒生MA200下方(12b闸) — 中概多头只给观察仓; "
                          "恒生收复MA200后按原打法执行")
    e, e2, st, t1, t2 = p.get("entry"), p.get("entry2"), p.get("stop"), p.get("t1"), p.get("t2")
    ma10, ma20, ma50 = p.get("ma10"), p.get("ma20v"), p.get("ma50v")
    rsi, atr = p.get("rsi"), p.get("atr") or 0
    pctb = p.get("bb_pctb") or 0
    # 量能不可用时用 None 传下去, 绝不退化成 0 — 0 会被下游读成"缩量"
    rvol = None if p.get("rvol_unusable") else (p.get("rvol") or 0)
    rvol_txt = "不可用(盘中)" if rvol is None else f"{rvol}"
    rvol_est_txt = "(盘中估算)" if p.get("rvol_est") else ""
    # bullish-side sub-profile + distribution warning (mirror of the downtrend sub-typing)
    up_prof = _up_profile(p) if p.get("trend") == "UPTREND" else None
    dist_warn = ("; ⚠️量价背离(价升OBV降, 资金流出) — 收紧止损, 禁加仓"
                 if p.get("trend") == "UPTREND" and (p.get("d5") or 0) > 0 and not p.get("obv_up") else "")

    if base == "8离场":
        return "🔴 离场", (f"离场 — 反弹至 MA20 {money(e)} 即出, 跌破 {money(e2)} 无条件清仓; "
                          f"空头论点失效线 {money(st)}")
    if base == "8减仓":
        return "🟠 减仓", (f"兑现 1/3–1/2, 剩余止损上移 MA10 {money(ma10)}; "
                          f"收盘破 MA20 {money(ma20)} 全退, 不开新仓")
    if base == "8减仓-派发":
        return "🟠 减仓", (f"顶部派发阴线(价仍在 MA20 上方 {p.get('dist_ma20')}%) — 兑现 1/3–1/2, "
                          f"剩余止损上移 MA10 {money(ma10)}; 禁新买/禁加仓 2-3 日, "
                          "等缩量止跌小实体 + 放量反包阳再谈; "
                          f"收盘放量破 MA20 {money(ma20)} 全退")
    if base == "刀-禁接":
        hold = (f"若持有: 趋势未破可持有, 收盘破 MA20 {money(ma20)} 清仓"
                if (p.get("dist_ma20") or 0) > 0 else
                f"若持有: 反弹至 MA10 {money(ma10)} 减仓, 不等回本")
        return "❌ 回避", ("刀-禁接 2-3 日 — 任何反弹不接不加仓; 重新考虑条件: 缩量止跌小实体 + "
                          f"放量反包阳, 序列完成前观望; {hold}")
    obv_txt = "; OBV逆势上行(洗盘嫌疑, 只观察不预判)" if p.get("obv_up") and p.get("trend") == "DOWNTREND" else ""
    if base in ("避(空头挤压)", "避(向下带行)"):
        return "❌ 回避", (f"{p.get('playbook_note', '')}; 收复 MA20 {money(ma20)} 前无任何多头操作; "
                          f"若持有: 反弹即减, 不抄底不摊平{obv_txt}")
    if base == "避(7质量不合格)":
        return "❌ 回避", "超卖但质量差(LT<50 且 MA200 下方) — 不接恐慌反转, 只记录"
    if base == "避":
        prof = _dt_profile(p)
        if prof == "破位初期":
            lvl = p.get("break_event") or "MA20"
            cf = "放量→即时确认" if p.get("break_volume_confirmed") else "缩量→未确认, 给1-2日反抽"
            floor = p.get("lo20")
            hard = round(floor - 0.25 * atr, 2) if floor else None
            return "❌ 回避", (f"[破位初期] 昨日/今日破{lvl}({cf}) — 收盘收回 MA20 {money(ma20)} = 假破翻回箱体; "
                              f"反抽失败或续收低 = 确认, 下看箱底 {money(floor)}, 破箱清仓确认线 {money(hard)}; "
                              f"若持有: 反弹 MA10 {money(ma10)} 减{obv_txt}")
        if prof == "麻木阴跌":
            return "❌ 回避", (f"[麻木阴跌] MA20下方已{p.get('days_below_ma20')}日+持续缩量 — 无恐慌就无底(不适用打法7), "
                              f"反弹即减不抄底; 收复 MA20 {money(ma20)} 前无操作{obv_txt}")
        if prof == "结构空头":
            if (p.get("dist_ma20") or 0) > 0:  # bear-trend bounce above MA20
                return "❌ 回避", (f"[结构空头 MA50<MA200] 趋势内反弹 — 不做多; 若持有: 反弹至 MA50 {money(ma50)} "
                                  f"区分批出, 跌破 MA20 {money(ma20)} 无条件清; 修复门槛: 放量收复 MA50 且走平{obv_txt}")
            return "❌ 回避", (f"[结构空头 MA50<MA200] — 反弹到 MA20 {money(ma20)} 即出; "
                              f"修复门槛: 收复 MA50 {money(ma50)} 且走平, 之前所有反弹不属于你{obv_txt}")
        return "❌ 回避", (f"空头趋势不做多 — 收复 MA20 {money(ma20)} 且 MA50 走平才重新评估; "
                          f"若持有: 反弹到 MA20 即出{obv_txt}")
    if base == "避(箱体)":
        return "⚪ 观察", (f"箱体观望 — 放量上破 {money(e2)} 跟多(止损 {money(st)}), "
                          f"否则等催化剂落地定方向")
    if base == "7":
        # 打法7 death stop = below the signal-bar low (5-day low proxy), NOT the
        # generic trend stop — the generic MA50/2×ATR stop overstated risk 3-4x
        # and crushed the R-sizing (2026-08-24 MARA: 34% dist → 3% position).
        st7 = round(p["lo5"] - 0.25 * atr, 2) if p.get("lo5") is not None else st
        return "👀 企稳等确认", (f"带底反转小仓试探 — 入场: 反转线高点上方; "
                              f"死止损 {money(st7)} (5日信号低点下方) "
                              f"({_fmt_rsize(p.get('last'), st7)}); "
                              f"目标中轨 {money(ma20)}; 仓位减半执行")
    if base == "7候选-等确认":
        return "⚪ 观察", "底部原料就位 — 等洗仓反转序列(放量长阴→缩量企稳→放量反包收回下轨)完成再进"
    if base == "16":
        g16 = p.get("pb16") or {}
        st16, lvl16 = g16.get("stop"), g16.get("level")
        size16 = "1/2 仓" if g16.get("squeeze") else "1/3 仓"
        gate16 = "双闸: 蓄势+MA50, 回测PF 2.7" if g16.get("squeeze") else "MA50闸无蓄势, 回测PF 2.3"
        note16 = "; 12c: 仓位减半" if gated_12c else ""
        vol16 = (f"RVOL {rvol_txt}{rvol_est_txt}"
                 + ("" if rvol is None else
                    ("(放量加分)" if rvol >= 1.5 else "(缩量不是否决项)")))
        tail16 = (f"止损 {money(st16)} ({_fmt_rsize(p.get('last'), st16)}); "
                  f"唯一离场=收盘跌破 MA20 {money(ma20)}; {vol16}; 右尾型(胜率~38%)必须拿住赢家"
                  + note16 + dist_warn)
        if lvl16 and p.get("last") and p["last"] < lvl16:
            return "⚪ 观察", (f"[纯图突破-{g16.get('pattern')}] 曾破 {money(lvl16)} 但现价已跌回其下方 — "
                              f"突破失败不进; 重新收盘站上 {money(lvl16)} 再按打法16进 {size16}; "
                              f"跌破形态止损 {money(st16)} 信号作废")
        if lvl16 and p.get("last") and p["last"] > lvl16 * 1.06:
            return "👀 企稳等确认", (f"[纯图突破-{g16.get('pattern')}] 已离突破位 {money(lvl16)} "
                                  f"超6%, 不追 — 等回踩 {money(lvl16)} 不破再进 {size16} ({gate16}); " + tail16)
        return "✅ 分批买入", (f"[纯图突破-{g16.get('pattern')}] 突破 {money(lvl16)} 已触发 — "
                            f"现价进 {size16} ({gate16}), 回踩 {money(lvl16)} 不破补至满仓; " + tail16)
    if base == "2":
        note = "; 12c: BTC未引爆, 触发后仓位减半" if gated_12c else ""
        return "🎯 突破触发单", (f"挂突破单 {money(e2)}, 触发必须 RVOL≥1.5x(缩量越轨不追); "
                              f"止损 {money(st)} ({_fmt_rsize(e2, st)}); T1 {money(t1)}"
                              + (f" / T2 {money(t2)}" if t2 else "") + note)
    if base == "1":
        return "👀 企稳等确认", (f"已回踩至 {money(e)} 支撑区 — 等企稳K线(缩量十字/长下影/放量反包)三选一, "
                              f"确认后进 1/2 仓; 止损 {money(st)} ({_fmt_rsize(e, st)}); "
                              f"T1 {money(t1)}" + (f" / T2 {money(t2)}" if t2 else ""))
    if base == "9":
        lvl = round(ma50 - 1.5 * atr, 2) if ma50 else None
        return "👀 企稳等确认", (f"首回踩 MA50 {money(ma50)}±2% — 出企稳bar进场, "
                              f"止损 MA50 下 1.5×ATR ≈ {money(lvl)}; 第一次测试胜率最高")
    if base == "1等回调":
        if up_prof == "修复初期":
            return "👀 企稳等确认", (f"[修复初期] 刚收复 MA20 仅{p.get('days_above_ma20')}日(右侧起点) — "
                                  f"回踩 {money(ma20)} 不破可先试 1/3 仓, 站稳 3 日后按打法1/11 补; "
                                  f"止损 {money(st)}{dist_warn}")
        if up_prof == "突破初期" and not p.get("break_up_volume_confirmed"):
            _tag = "量能待收盘确认" if rvol is None else "缩量"
            return "⚪ 观察", (f"[突破初期-{_tag}] 今破{p.get('break_event_up')} RVOL {rvol_txt}{rvol_est_txt} — "
                              f"确认前不追; 回踩 {money(p.get('hi20'))} 不破再进{dist_warn}")
        return "⚪ 观察", (f"趋势完好但价位未到 — 等回踩 {money(e)} (MA20区) 出企稳bar再进; "
                          f"当前不动手{dist_warn}")
    if base in ("8持有", "8持有-禁加"):
        extra = " (RSI 过热禁加仓)" if (rsi or 0) > 75 or base.endswith("禁加") else ""
        return "🟢 持有", (f"[{up_prof or '带行'}] 持有{extra} — 唯一离场信号: 首次放量收破 MA20 {money(ma20)}; "
                          f"触上轨/RSI高不是卖出理由{dist_warn}")
    if base == "3/11":
        if up_prof == "突破初期":
            if p.get("break_up_volume_confirmed"):
                return "✅ 分批买入", (f"[突破初期-放量确认] 今放量突破{p.get('break_event_up')} (RVOL {rvol}) — "
                                    f"可追 1/3 仓, 回踩突破位 {money(p.get('hi20'))} 不破补至 1/2; "
                                    f"止损 {money(st)} ({_fmt_rsize(p.get('last'), st)}); T1 {money(t1)}"
                                    + (f" / T2 {money(t2)}" if t2 else "") + dist_warn)
            _tag = "量能待收盘确认" if rvol is None else "缩量"
            return "⚪ 观察", (f"[突破初期-{_tag}] 今破{p.get('break_event_up')} RVOL {rvol_txt}{rvol_est_txt} — "
                              f"确认前不追; 剧本: 回踩旧箱顶 {money(p.get('hi20'))} 不破 = 真突破确认再进, "
                              f"缩量滑回箱内 = 假突破放弃{dist_warn}")
        if up_prof == "修复初期":
            return "👀 企稳等确认", (f"[修复初期] 刚收复 MA20 仅{p.get('days_above_ma20')}日(右侧起点) — "
                                  f"回踩 {money(ma20)} 不破先试 1/3 仓, 站稳 3 日再按打法11补齐; "
                                  f"止损 {money(st)}{dist_warn}")
        if up_prof == "强势延伸" or (rsi or 0) > 70 or (pctb >= 0.85 and rvol is not None and rvol < 0.8):
            return "🟢 持有", (f"[强势延伸] 强者但已过热(RSI {rsi}/%B {pctb:.2f}/距MA20 "
                              f"{p.get('dist_ma20')}%) — 已持有按打法8管理(离场线 MA20 {money(ma20)}), "
                              f"新仓只等回踩 {money(e)}{dist_warn}")
        note = "; 12c: 仓位减半" if gated_12c else ""
        return "✅ 分批买入", (f"[{up_prof or '多头'}] 相对强势+结构健康 — 现价分批建 1/2 仓, 突破 {money(e2)} "
                            f"加 1/4, 回踩 MA20 不破加最后 1/4 (打法11); 止损 {money(st)} "
                            f"({_fmt_rsize(p.get('last'), st)}); T1 {money(t1)}"
                            + (f" / T2 {money(t2)}" if t2 else "") + note + dist_warn)
    if base in ("14底背离", "14+15"):
        lo14 = p.get("div_low14") or p.get("lo20")  # divergence trough; 20d low as fallback anchor
        st14 = round(lo14 - 0.25 * atr, 2) if lo14 is not None else None
        extra = "+金针共振(概率升级)" if base == "14+15" else ""
        return "✅ 分批买入", (f"[MACD底背离{extra}] 空头衰竭+金叉新鲜触发 — 小仓(标准仓一半)现价进; "
                            f"止损 {money(st14)} (背离低点下方) ({_fmt_rsize(p.get('last'), st14)}); "
                            f"目标 MA50 {money(ma50)} → 前高 {money(p.get('hi20'))}; 中期波段, 破止损即认错")
    if base == "15金针":
        lo15 = p.get("pin_low15")
        st15 = round(lo15 - 0.15 * atr, 2) if lo15 is not None else None
        return "✅ 分批买入", (f"[金针探底] 长下影pin bar — 轻仓(≤1/3标准仓)现价试错; "
                            f"止损 {money(st15)} (影线低点下方) ({_fmt_rsize(p.get('last'), st15)}); "
                            f"目标 MA20 {money(ma20)}; 12个交易日未达即时间止损离场")
    return "⚪ 观察", p.get("playbook_note", "无明确行动")


def build_action_plans(plans):
    for p in plans.values():
        p["action"], p["action_plan"] = _action_one(p)
    from collections import Counter
    cnt = Counter(p["action"] for p in plans.values())
    print("  actions: " + " | ".join(f"{a.split(' ')[-1]} {cnt[a]}" for a in ACTION_TIERS if cnt.get(a)))


def action_section_md(plans):
    out = ["## 🎯 Action Plan（按行动分组）", ""]
    for tier in ACTION_TIERS:
        tks = [t for t, p in plans.items() if p.get("action") == tier]
        if not tks:
            continue
        tks.sort(key=lambda t: -(plans[t].get("chg20") or 0))
        out.append(f"### {tier} ({len(tks)})")
        for t in tks:
            p = plans[t]
            out.append(f"- **{t}** {money(p['last'])} · 打法{p.get('playbook', '—')} — {p['action_plan']}")
        out.append("")
    return out


def action_section_html(plans):
    blocks = []
    for tier in ACTION_TIERS:
        tks = [t for t, p in plans.items() if p.get("action") == tier]
        if not tks:
            continue
        tks.sort(key=lambda t: -(plans[t].get("chg20") or 0))
        lis = "".join(
            f'<li><a href="#{t.lower()}"><b>{t}</b></a> {money(plans[t]["last"])} · '
            f'打法{plans[t].get("playbook", "—")} — {plans[t]["action_plan"]}</li>' for t in tks)
        blocks.append(f'<h3>{tier} ({len(tks)})</h3><ul class="notes">{lis}</ul>')
    return ('<section><h2>🎯 Action Plan（按行动分组）</h2>' + "".join(blocks)
            + '</section>') if blocks else ""


def money(v):
    return f"${v:,.2f}" if v is not None else "—"


def plan_rows_html(p):
    extra = ""
    if p.get("pattern_targets"):
        pts = p["pattern_targets"][:3]
        extra = ('<tr><th>Pattern targets</th><td class="pos">'
                 + "<br>".join(money(x["target"]) for x in pts) + "</td><td>"
                 + "<br>".join(x["pattern"] for x in pts) + "</td></tr>")
    return _plan_rows_html_inner(p) + extra


def _plan_rows_html_inner(p):
    if p["bias"] == "LONG":
        return (f'<tr><th>Entry 1</th><td>{money(p["entry"])}</td><td>{p["entry_note"]}</td></tr>'
                f'<tr><th>Entry 2 (add)</th><td>{money(p["entry2"])}</td><td>{p["entry2_note"]}</td></tr>'
                f'<tr><th>Stop-loss</th><td class="neg">{money(p["stop"])}</td><td>{p["stop_note"]}</td></tr>'
                f'<tr><th>Target 1</th><td class="pos">{money(p["t1"])}</td><td>take ⅓–½ off at +1.5R</td></tr>'
                f'<tr><th>Target 2</th><td class="pos">{money(p["t2"])}</td><td>trail remainder (MA20) toward +3R</td></tr>')
    if p["bias"] == "AVOID / EXIT":
        return (f'<tr><th>If holding — exit into strength</th><td>{money(p["entry"])}</td><td>{p["entry_note"]}</td></tr>'
                f'<tr><th>Hard exit (breakdown)</th><td class="neg">{money(p["entry2"])}</td><td>{p["entry2_note"]}</td></tr>'
                f'<tr><th>Bear thesis wrong above</th><td class="pos">{money(p["stop"])}</td><td>{p["stop_note"]}</td></tr>'
                f'<tr><th>Downside risk</th><td>{money(p["t1"])}</td><td>60-day low</td></tr>')
    return (f'<tr><th>Buy zone</th><td>{money(p["entry"])}</td><td>{p["entry_note"]}</td></tr>'
            f'<tr><th>Breakout alternative</th><td>{money(p["entry2"])}</td><td>{p["entry2_note"]}</td></tr>'
            f'<tr><th>Stop-loss</th><td class="neg">{money(p["stop"])}</td><td>{p["stop_note"]}</td></tr>'
            f'<tr><th>Target</th><td class="pos">{money(p["t1"])}</td>'
            f'<td>range high{" · T2 " + money(p["t2"]) if p.get("t2") else ""}</td></tr>')


def card_html(tkr, p, with_chart=True):
    cls = {"LONG": "buy", "RANGE / NEUTRAL": "hold", "AVOID / EXIT": "sell"}[p["bias"]]
    img = ""
    if with_chart:
        with open(CHART_DIR / f"{tkr}.png", "rb") as f:
            img = (f'<div class="chart"><img src="data:image/png;base64,'
                   f'{base64.b64encode(f.read()).decode()}" alt="{tkr} chart"></div>')
    pat_html = ""
    if p.get("playbook"):
        pat_html += (f'<p class="meta">打法 <b>{p["playbook"]}</b> — {p.get("playbook_note", "")}</p>')
    if p.get("action"):
        pat_html += (f'<p class="meta">Action <b>{p["action"]}</b> — {p.get("action_plan", "")}</p>')
    if p.get("patterns"):
        pat_html += ('<p class="meta">Patterns: <b>' + " · ".join(p["patterns"]) + "</b></p>")
    rec_html = (f'<p class="rec {cls}"><b>Recommendation:</b> {p["recommendation"]}</p>'
                if p.get("recommendation") else "")
    notes_html = ""
    if p.get("notes"):
        notes_html = ('<ul class="notes">'
                      + "".join(f"<li><b>{k}</b> — {v}</li>" for k, v in p["notes"].items())
                      + "</ul>")
    return (f'<article class="tk" id="{tkr.lower()}"><header class="tk-head"><div>'
            f'<h3>{tkr} <span class="co">{p["sector"]}</span></h3>'
            f'<p class="meta">{p["trend"]} · MACD {p["macd"]} · RSI {p["rsi"]} · '
            f'ATR {money(p["atr"])} · 20D {p["chg20"]:+.1f}%</p>{pat_html}</div>'
            f'<div class="badge {cls}">{p["bias"]}</div></header>{img}'
            f'<table class="plan"><tbody>{plan_rows_html(p)}</tbody></table>'
            f'{rec_html}{notes_html}</article>')


def summary_table(plans, link=True):
    rows = []
    for t, p in plans.items():
        cls = {"UPTREND": "buy", "RANGE": "hold", "DOWNTREND": "sell"}[p["trend"]]
        name = f'<a href="#{t.lower()}">{t}</a>' if link else f"<b>{t}</b>"
        rows.append(f'<tr><td>{name}</td><td>{p["sector"]}</td><td>{money(p["last"])}</td>'
                    f'<td><span class="tag {cls}">{p["trend"]}</span></td><td>{p["chg20"]:+.1f}%</td>'
                    f'<td>{money(p["entry"])}</td><td>{money(p["stop"])}</td>'
                    f'<td>{money(p["t1"])}</td><td>{money(p.get("t2"))}</td>'
                    f'<td><b>{p.get("playbook", "—")}</b></td></tr>')
    return ('<div class="summary-wrap"><table class="summary"><thead><tr><th>Ticker</th><th>Sector</th>'
            '<th>Price</th><th>Trend</th><th>20D%</th><th>Entry</th><th>Stop</th><th>T1</th><th>T2</th>'
            '<th>打法</th>'
            f'</tr></thead><tbody>{"".join(rows)}</tbody></table>'
            f'<p class="sub">{PLAYBOOK_LEGEND}</p></div>')


def build_html(plans, path, chart_tickers, title, sub):
    order = [("LONG", "Long setups — uptrends"), ("RANGE / NEUTRAL", "Range-bound"),
             ("AVOID / EXIT", "Downtrends — no new longs")]
    sections = []
    for bias, gtitle in order:
        tks = [t for t, p in plans.items() if p["bias"] == bias]
        if not tks:
            continue
        cards = "".join(card_html(t, plans[t], with_chart=t in chart_tickers) for t in tks)
        sections.append(f'<section><h2>{gtitle} ({len(tks)})</h2>{cards}</section>')
    html = (f'<title>{title}</title><style>{CSS}</style><main><h1>{title}</h1>'
            f'<p class="sub">{sub}</p>{summary_table(plans)}{action_section_html(plans)}'
            f'{METHOD}{"".join(sections)}{FOOT}</main>')
    path.write_text(html, encoding="utf-8")
    print(f"  wrote {path.name} ({len(html)//1024} KB)")


def main():
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    # optional: --tickers AAPL,MSFT  (subset run for the pattern team; writes
    # *_custom_* files so the nightly full-universe outputs are never clobbered)
    custom = None
    if "--tickers" in sys.argv:
        raw_arg = sys.argv[sys.argv.index("--tickers") + 1]
        custom = [t.strip().upper() for t in raw_arg.replace(",", " ").split() if t.strip()]
    print("=" * 70)
    print(f"  Trade-Plan Charts — {'custom list' if custom else 'AI Portfolio'}    {stamp}")
    print("=" * 70)
    # intraday guard: volume-derived signals (RVOL / knife / 放量确认 / 假突破)
    # are systematically wrong on a partial bar — flag the whole run so the
    # 6PM report knows to distrust them (2026-08-24: a 10:20 ET misfire made
    # the band-top engine tag every stock as a low-volume fake breakout).
    intraday = False
    try:
        from zoneinfo import ZoneInfo
        _et = datetime.now(ZoneInfo("America/New_York"))
        intraday = _et.weekday() < 5 and (_et.hour, _et.minute) >= (9, 30) and _et.hour < 16
    except Exception:
        pass
    if intraday:
        RUN_WARNINGS.append("盘中运行(美股开市时段) — 今日bar不完整。RVOL 已按日内成交量曲线归一化为全日等效值"
                             "(intraday_volume.py, JSON 字段 rvol_est=true), 量能类信号可用但属估算; "
                             "开盘首15分钟外推不可信时 rvol_unusable=true, 相关规则自动关闭。"
                             "最终确认仍以收盘为准")
        print("  ⚠️ " + RUN_WARNINGS[-1])
    sectors = load_portfolio()
    tick2sec = {t: s for s, ts in sectors.items() for t in ts}
    # duplicate-ticker audit: the same ticker in two sector columns silently
    # resolves to whichever sector is parsed last — make the choice visible,
    # since sector gates (12b/12c) and the 2R sector budget depend on it.
    _seen = {}
    for s, ts in sectors.items():
        for t in ts:
            _seen.setdefault(t, []).append(s)
    for t, ss in _seen.items():
        if len(ss) > 1:
            RUN_WARNINGS.append(f"ticker {t} 同时出现在 {'/'.join(ss)} — 按 {tick2sec[t]} 归属(板块闸门与2R预算以此为准)")
            print("  ⚠️ " + RUN_WARNINGS[-1])
    if custom:
        tick2sec = {t: tick2sec.get(t, "—") for t in custom}
    tickers = list(tick2sec)
    print(f"Loaded {len(tickers)} tickers" + ("" if custom else f" across {len(sectors)} sectors"))

    raw = yf.download(tickers, period="1y", interval="1d", auto_adjust=True,
                      group_by="ticker", progress=False, threads=True)
    plans, failed = {}, []
    for i, tkr in enumerate(tickers, 1):
        try:
            df = raw[tkr].dropna(subset=["Close"]).copy()
            if len(df) < 60:
                raise ValueError(f"only {len(df)} bars")
            plans[tkr] = analyze(tkr, tick2sec[tkr], df)
        except Exception as e:
            failed.append((tkr, str(e)))
        if i % 25 == 0:
            print(f"  {i}/{len(tickers)} complete")
    print(f"  {len(plans)} analyzed, {len(failed)} failed")
    if failed:
        print("  FAILED:", ", ".join(t for t, _ in failed))

    assign_playbooks(plans)
    build_action_plans(plans)

    # rank: longs by 20-day momentum; exits by 20-day decline
    longs = sorted((t for t, p in plans.items() if p["bias"] == "LONG"),
                   key=lambda t: -plans[t]["chg20"])
    exits = sorted((t for t, p in plans.items() if p["bias"] == "AVOID / EXIT"),
                   key=lambda t: plans[t]["chg20"])
    counts = {b: sum(1 for p in plans.values() if p["bias"] == b)
              for b in ("LONG", "RANGE / NEUTRAL", "AVOID / EXIT")}
    print(f"  LONG: {counts['LONG']} | RANGE: {counts['RANGE / NEUTRAL']} | AVOID/EXIT: {counts['AVOID / EXIT']}")

    tag = f"custom_{TODAY}" if custom else TODAY
    with open(HERE / f"trade_plans_{tag}.json", "w") as f:
        json.dump(dict(generated=stamp, intraday_run=intraday,
                       warnings=RUN_WARNINGS, failed=failed, plans=plans), f, indent=1)

    # markdown summary (all tickers)
    md = [f"# Trade Plans — {stamp}", "",
          f"**{len(plans)} tickers** | LONG {counts['LONG']} · RANGE {counts['RANGE / NEUTRAL']} · "
          f"AVOID/EXIT {counts['AVOID / EXIT']}", "",
          f"> {PLAYBOOK_LEGEND}", ""]
    if RUN_WARNINGS:
        md += ["> ⚠️ " + w for w in RUN_WARNINGS] + [""]
    md += [
          "| Ticker | Sector | Price | Trend | 20D% | Entry | Stop | T1 | T2 | 打法 |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    ordered = longs + [t for t, p in plans.items() if p["bias"] == "RANGE / NEUTRAL"] + exits
    for t in ordered:
        p = plans[t]
        md.append(f"| {t} | {p['sector']} | {money(p['last'])} | {p['trend']} | {p['chg20']:+.1f}% | "
                  f"{money(p['entry'])} | {money(p['stop'])} | {money(p['t1'])} | {money(p.get('t2'))} | "
                  f"{p.get('playbook', '—')} |")
    md += [""] + action_section_md(plans)
    md += ["", "## Recommendations & analyst notes", ""]
    for t in ordered:
        p = plans[t]
        md.append(f"### {t} — {p['bias']} ({money(p['last'])})")
        if p.get("playbook"):
            md.append(f"**打法 {p['playbook']}** — {p.get('playbook_note', '')}")
        if p.get("action"):
            md.append(f"**Action: {p['action']}** — {p.get('action_plan', '')}")
        if p.get("recommendation"):
            md.append(p["recommendation"])
        for kk, vv in (p.get("notes") or {}).items():
            md.append(f"- **{kk}**: {vv}")
        if p.get("pattern_targets"):
            md.append("- **pattern targets**: " + ", ".join(
                f"{money(x['target'])} ({x['pattern']})" for x in p["pattern_targets"]))
        md.append("")
    md += ["> Algorithmic technical analysis only — not financial advice."]
    (HERE / f"trade_plans_{tag}.md").write_text("\n".join(md), encoding="utf-8")
    print(f"  wrote trade_plans_{tag}.md / .json")

    sub = (f"Run {stamp} · {len(plans)} tickers · 1-year daily bars · "
           f"ATR-anchored levels drawn on each chart")
    ordered = {t: plans[t] for t in longs} | \
              {t: p for t, p in plans.items() if p["bias"] == "RANGE / NEUTRAL"} | \
              {t: plans[t] for t in exits}
    if custom:
        build_html(ordered, HERE / f"trade_plans_{tag}.html", set(plans),
                   f"Trade Plans ({len(plans)} tickers) — {TODAY}", sub + " · all charts")
    else:
        build_html(ordered, HERE / f"trade_plans_{TODAY}.html", set(plans),
                   f"AI Portfolio Trade Plans — {TODAY}", sub + " · full universe, all charts")
        action = {t: plans[t] for t in longs[:N_ACTIONABLE]} | {t: plans[t] for t in exits[:N_ACTIONABLE]}
        build_html(action, HERE / f"trade_plans_actionable_{TODAY}.html", set(action),
                   f"Actionable Trade Plans — {TODAY}",
                   sub + f" · top {N_ACTIONABLE} long setups + top {N_ACTIONABLE} exits "
                         f"(full universe table + all charts in trade_plans_{TODAY}.html)")

    print("\n  Top long setups: " + ", ".join(longs[:10]))
    print("  Top exits:       " + ", ".join(exits[:10]))
    print("DONE")


if __name__ == "__main__":
    main()
