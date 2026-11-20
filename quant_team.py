"""
QUANT TEAM ENGINE — the deterministic core shared by the quant-team agents
==========================================================================
The agents in .claude/agents/ (portfolio manager, stock research, AI-stocks
research, stock picker, macro strategist, quant researcher, risk manager,
execution trader) do the judgement work. This file does everything that must
be reproducible: data, factors, covariance, optimisation, risk and backtest.
No number in a team report should come from anywhere but here.

Stages (each maps to a desk on the team):
  screen    data QA -> macro regime -> price factors -> fundamentals ->
            AI-theme scores -> ranked candidate list            (stock picker)
  optimize  merge analyst views/vetoes -> expected returns -> shrunk
            covariance -> constrained max-Sharpe -> vol targeting -> risk
            report -> share-level orders                (quant / risk / trader)
  backtest  walk-forward monthly rebalance of every construction method vs
            SPY, QQQ and the equal-weight universe           (quant researcher)
  all       screen + optimize + backtest

Usage:
  python quant_team.py screen
  python quant_team.py optimize --views quant_team_views_*.json --capital 100000
  python quant_team.py backtest
  python quant_team.py all

Outputs (dated by the last price bar, not the wall clock):
  quant_team_candidates_<date>.json   quant_team_portfolio_<date>.json / .md
  quant_team_backtest_<date>.json

Views file (written by research agents, any number of files):
  {"views":  [{"ticker": "NVDA", "agent": "ai-stocks-research-analyst",
               "view": 1.5, "conviction": 0.7, "thesis": "...", "risks": "..."}],
   "vetoes": [{"ticker": "XYZ", "agent": "risk-manager", "reason": "..."}],
   "macro":  {"gross_exposure_cap": 0.6, "agent": "macro-strategist", "reason": "..."}}
  view is -2 (strong sell) .. +2 (strong buy); conviction is 0..1.

PAPER / RESEARCH ONLY. Nothing here places an order.
"""
from __future__ import annotations

import argparse
import ast
import json
import math
import pickle
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

HERE = Path(__file__).parent
CACHE = HERE / "_data_cache"
XLSX = HERE / "AI_Portfolios.xlsx"

# ── Policy (the team's investment mandate; change here, not in the agents) ──
BENCHMARKS = ["SPY", "QQQ"]
AUX = ["^VIX", "^IRX"]
HISTORY = "5y"
MIN_BARS = 260               # ~1y of history before a name is investable
MIN_PRICE = 3.0
MIN_DOLLAR_VOL = 20e6        # median 60d dollar volume
N_FUNDAMENTALS = 60          # fundamentals are fetched for the top-N by price alpha
N_CANDIDATES = 40            # handed to the research desks
N_NAMES = 25                 # max names entering the optimiser
NAME_CAP = 0.08              # max weight per name (of the risky sleeve)
SECTOR_CAP = 0.30            # max weight per sector (of the risky sleeve)
MIN_WEIGHT = 0.015           # positions smaller than this are dropped
TARGET_VOL = 0.25            # ex-ante annual vol ceiling for the whole book
IC_QUANT = 0.05              # information coefficient assumed for the factor score
IC_VIEW = 0.10               # ... and for a full-conviction analyst view
ERP = 0.05                   # equity risk premium used for the beta prior
COST_BPS = 10                # one-way trading cost in the backtest
REBAL_DAYS = 21
TRADING_DAYS = 252

FACTOR_WEIGHTS = {"momentum": 0.40, "trend": 0.20, "low_risk": 0.10,
                  "rel_strength": 0.15, "ai_theme": 0.15}
FUND_WEIGHTS = {"growth": 0.40, "quality": 0.35, "value": 0.25}
FUND_BLEND = 0.35            # composite = (1-b)*price alpha + b*fundamental score

AI_LAYERS = {
    "Hyperscaler": "Cloud & frontier models", "Semis": "Compute & semis",
    "AI Infrastructure": "Datacenter, neocloud & power gear", "Software": "AI applications & data",
    "Robotics": "Physical AI", "Self-Driving": "Physical AI", "Quantum": "Frontier compute",
    "Energy": "AI power & materials",
}
SKIP_SECTORS = {"Index"}
NON_USD_REPORTERS = {"TSM", "ASML", "INFY", "SPOT", "TCEHY", "BABA", "BIDU", "JD", "XPEV", "NIO", "PDD", "FUTU", "GRAB"}


# ════════════════════════════ universe & data ════════════════════════════
def _ticker_map() -> dict:
    """Read TICKER_MAP out of stock_analysis.py without importing it (the
    import rewraps stdout and pulls in yfinance at module load)."""
    tree = ast.parse((HERE / "stock_analysis.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "TICKER_MAP":
            return ast.literal_eval(node.value)
    return {}


def load_universe(include_crypto: bool = False) -> pd.DataFrame:
    import openpyxl
    tmap = _ticker_map()
    ws = openpyxl.load_workbook(XLSX, data_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    out, seen = [], set()
    for c, sector in enumerate(rows[0]):
        if not sector or sector in SKIP_SECTORS:
            continue
        for r in rows[1:]:
            name = r[c] if c < len(r) else None
            if not isinstance(name, str) or not name.strip():
                continue
            name = name.strip()
            t = tmap.get(name, name.upper())
            if t in seen or (t.endswith("-USD") and not include_crypto):
                continue
            seen.add(t)
            out.append(dict(ticker=t, name=name, sector=sector, ai_layer=AI_LAYERS.get(sector)))
    return pd.DataFrame(out).set_index("ticker")


def download(tickers: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    import yfinance as yf
    closes, vols = [], []
    for i in range(0, len(tickers), 60):
        chunk = tickers[i:i + 60]
        for attempt in range(3):
            d = yf.download(chunk, period=HISTORY, auto_adjust=True, progress=False, threads=4)
            if len(d):
                break
        if not len(d):
            continue
        closes.append(d["Close"]); vols.append(d["Volume"])
    if not closes:
        sys.exit("DATA OUTAGE: no prices downloaded (network policy or Yahoo rate limit). "
                 "Nothing was written; do not fill from memory.")
    close = pd.concat(closes, axis=1).sort_index()
    vol = pd.concat(vols, axis=1).sort_index()
    close.index = pd.to_datetime(close.index).tz_localize(None)
    vol.index = close.index
    keep = close["SPY"].notna() if "SPY" in close else close.notna().any(axis=1)   # US trading days only
    return close.loc[keep].dropna(how="all", axis=1), vol.loc[keep]


def is_intraday(asof: pd.Timestamp) -> bool:
    ny = datetime.now(ZoneInfo("America/New_York"))
    return asof.date() == ny.date() and ny.hour * 60 + ny.minute < 16 * 60 + 15


# ════════════════════════════ factor library ═════════════════════════════
def zscore(s: pd.Series, winsor: bool = True) -> pd.Series:
    s = s.astype(float).replace([np.inf, -np.inf], np.nan)
    if s.notna().sum() < 3:
        return s * 0.0
    if winsor:
        s = s.clip(s.quantile(0.05), s.quantile(0.95))
    sd = s.std()
    return ((s - s.mean()) / sd).clip(-3, 3) if sd and sd > 0 else s * 0.0


def wavg(df: pd.DataFrame, weights: dict) -> pd.Series:
    """NaN-aware weighted average of columns (weights renormalised per row)."""
    w = pd.Series(weights)[[c for c in weights if c in df.columns]]
    num = (df[w.index] * w).sum(axis=1, skipna=True)
    den = (df[w.index].notna() * w).sum(axis=1)
    return num / den.replace(0, np.nan)


def price_factors(close: pd.DataFrame, volume: pd.DataFrame | None, sectors: pd.Series) -> pd.DataFrame:
    """Cross-sectional price factors using only data up to close.index[-1]."""
    px = close.iloc[-1]
    n = close.notna().sum()
    ret = close.pct_change()
    f = pd.DataFrame(index=close.columns)
    f["price"] = px
    f["bars"] = n
    f["ret_1m"] = close.iloc[-1] / close.iloc[-22] - 1
    f["ret_3m"] = close.iloc[-1] / close.iloc[-64] - 1
    f["ret_6m"] = close.iloc[-1] / close.iloc[-127] - 1
    f["mom_12_1"] = close.iloc[-22] / close.iloc[-253] - 1
    f["mom_6_1"] = close.iloc[-22] / close.iloc[-127] - 1
    f["vol"] = ret.iloc[-126:].std() * math.sqrt(TRADING_DAYS)
    down = ret.iloc[-126:].clip(upper=0)
    f["down_vol"] = np.sqrt((down ** 2).mean()) * math.sqrt(TRADING_DAYS)
    ma50, ma200 = close.iloc[-50:].mean(), close.iloc[-200:].mean()
    f["dist_ma50"] = px / ma50 - 1
    f["dist_ma200"] = px / ma200 - 1
    f["golden"] = (ma50 > ma200).astype(float)
    f["off_high"] = px / close.iloc[-252:].max() - 1
    win = close.iloc[-252:]
    f["max_dd_1y"] = (win / win.cummax() - 1).min()
    if "QQQ" in close:
        f["rs_qqq_3m"] = f["ret_3m"] - f.at["QQQ", "ret_3m"]
    if volume is not None:
        f["dollar_vol"] = (close * volume).iloc[-60:].median()
    f["sector"] = sectors.reindex(f.index)

    f["eligible"] = (f["bars"] >= MIN_BARS) & px.notna() & (px >= MIN_PRICE) & f["sector"].notna()
    if volume is not None:
        f["eligible"] &= f["dollar_vol"].fillna(0) >= MIN_DOLLAR_VOL
    f["knife"] = (f["dist_ma200"] < 0) & (f["ret_1m"] < -0.25)   # falling knife: never a new buy

    e = f[f["eligible"]]
    z = pd.DataFrame(index=e.index)
    z["momentum"] = (0.5 * zscore(e["mom_12_1"] / e["vol"]) + 0.3 * zscore(e["mom_6_1"] / e["vol"])
                     + 0.2 * zscore(e["ret_3m"] / e["vol"]))
    z["trend"] = 0.5 * zscore(e["dist_ma200"].clip(-0.5, 0.8)) + 0.3 * zscore(e["off_high"]) + 0.2 * zscore(e["golden"])
    z["low_risk"] = 0.5 * zscore(-e["down_vol"]) + 0.5 * zscore(e["max_dd_1y"])
    z["rel_strength"] = zscore(e.get("rs_qqq_3m", e["ret_3m"]))
    # AI theme = strength + breadth of the name's layer of the AI value chain
    sec_mom = e.groupby("sector")["ret_3m"].median()
    sec_breadth = (e["dist_ma50"] > 0).groupby(e["sector"]).mean()
    theme = 0.6 * zscore(sec_mom) + 0.4 * zscore(sec_breadth)
    is_ai = e["sector"].map(lambda s: s in AI_LAYERS)
    z["ai_theme"] = e["sector"].map(theme).where(is_ai)
    for c in z:
        f["z_" + c] = z[c]
    f["alpha_price"] = zscore(wavg(z, FACTOR_WEIGHTS), winsor=False)   # keep the ranking in the tails
    return f


def regime(close: pd.DataFrame, universe: list[str]) -> dict:
    """Risk budget from trend, volatility and breadth. Mirrors the repo's
    gate culture (QQQ below MA50 = no fresh risk) but as a graded dial."""
    def above(t, n):
        s = close[t].dropna()
        return bool(s.iloc[-1] > s.iloc[-n:].mean()) if len(s) >= n else None
    u = close[[t for t in universe if t in close]]
    valid = u.iloc[-50:].notna().all()
    breadth = float((u.iloc[-1] > u.iloc[-50:].mean())[valid].mean())
    vix = float(close["^VIX"].dropna().iloc[-1]) if "^VIX" in close else float("nan")
    checks = {"SPY>MA200": above("SPY", 200), "SPY>MA50": above("SPY", 50), "QQQ>MA50": above("QQQ", 50),
              "VIX<20": (vix < 20) if vix == vix else None, "breadth>50%": breadth > 0.5}
    score = sum(1 for v in checks.values() if v) - (1 if vix == vix and vix > 30 else 0)
    gross = {5: 1.0, 4: 1.0, 3: 0.85, 2: 0.70, 1: 0.50}.get(score, 0.35)
    label = "RISK-ON" if score >= 4 else "NEUTRAL" if score >= 2 else "RISK-OFF"
    return dict(label=label, score=int(score), gross_exposure=gross, vix=vix,
                breadth_above_ma50=breadth, checks=checks)


# ════════════════════════════ fundamentals ═══════════════════════════════
FUND_FIELDS = ["revenue_growth_yoy", "net_income_growth_yoy", "gross_margin", "operating_margin", "roe",
               "fcf_ttm", "net_income_ttm", "revenue_ttm", "market_cap", "net_debt", "latest_quarter"]


def fetch_fundamentals(tickers: list[str], prices: pd.Series) -> pd.DataFrame:
    """Reported fundamentals from Yahoo's quarterly statements (the quote
    'info' endpoint needs a crumb that is rate-limited from cloud IPs, so
    there are no forward estimates or analyst targets here - the research
    agents source those from the web). Cached per day."""
    import yfinance as yf
    cache = CACHE / f"quant_team_fundamentals_{datetime.now():%Y-%m-%d}.json"
    done = json.loads(cache.read_text()) if cache.exists() else {}

    def row(df, *names):
        for n in names:
            if df is not None and n in df.index:
                return df.loc[n].dropna().sort_index(ascending=False)
        return pd.Series(dtype=float)

    def one(t):
        if t in done:
            return t, done[t]
        try:
            tk = yf.Ticker(t)
            inc, cf, bs = tk.quarterly_income_stmt, tk.quarterly_cashflow, tk.quarterly_balance_sheet
            rev, ni = row(inc, "Total Revenue"), row(inc, "Net Income")
            if len(rev) < 4:
                return t, {}
            ttm = lambda s: float(s.iloc[:4].sum()) if len(s) >= 4 else None
            yoy = lambda s: float(s.iloc[0] / s.iloc[4] - 1) if len(s) >= 5 and s.iloc[4] > 0 else None
            gp, op, fcf = row(inc, "Gross Profit"), row(inc, "Operating Income"), row(cf, "Free Cash Flow")
            eq, sh = row(bs, "Stockholders Equity"), row(bs, "Ordinary Shares Number", "Share Issued")
            debt, cash = row(bs, "Total Debt"), row(bs, "Cash And Cash Equivalents")
            rttm = ttm(rev)
            d = dict(revenue_growth_yoy=yoy(rev), net_income_growth_yoy=yoy(ni),
                     gross_margin=ttm(gp) / rttm if ttm(gp) is not None and rttm else None,
                     operating_margin=ttm(op) / rttm if ttm(op) is not None and rttm else None,
                     roe=ttm(ni) / float(eq.iloc[0]) if ttm(ni) is not None and len(eq) and eq.iloc[0] > 0 else None,
                     fcf_ttm=ttm(fcf), net_income_ttm=ttm(ni), revenue_ttm=rttm,
                     market_cap=float(sh.iloc[0]) * float(prices[t]) if len(sh) else None,
                     net_debt=float(debt.iloc[0] - cash.iloc[0]) if len(debt) and len(cash) else None,
                     latest_quarter=str(rev.index[0].date()))
            return t, d
        except Exception:
            return t, {}
    with ThreadPoolExecutor(3) as ex:
        rows = dict(ex.map(one, tickers))
    CACHE.mkdir(exist_ok=True)
    cache.write_text(json.dumps({**done, **{t: r for t, r in rows.items() if r}}))
    return pd.DataFrame.from_dict(rows, orient="index").reindex(columns=FUND_FIELDS)


def fundamental_score(fd: pd.DataFrame) -> pd.DataFrame:
    num = fd.drop(columns=["latest_quarter"], errors="ignore").apply(pd.to_numeric, errors="coerce")
    s = pd.DataFrame(index=fd.index)
    # market cap = share count x USD price: wrong for multi-class shares (BRK) and for
    # companies reporting in another currency, so the value leg is dropped for those
    mcap = num["market_cap"].where((num["market_cap"] / num["revenue_ttm"] > 0.05) & ~num.index.isin(NON_USD_REPORTERS))
    num["market_cap"] = mcap
    fcf_yield = num["fcf_ttm"] / mcap
    earn_yield = num["net_income_ttm"] / mcap
    s["growth"] = pd.concat([zscore(num["revenue_growth_yoy"].clip(-0.5, 2)),
                             zscore(num["net_income_growth_yoy"].clip(-1, 3))], axis=1).mean(axis=1)
    s["quality"] = pd.concat([zscore(num["operating_margin"].clip(-1, 1)), zscore(num["roe"].clip(-1, 1)),
                              zscore(num["gross_margin"])], axis=1).mean(axis=1)
    s["value"] = pd.concat([zscore(earn_yield.clip(-0.2, 0.2)), zscore(fcf_yield.clip(-0.2, 0.2))], axis=1).mean(axis=1)
    s["fund_score"] = wavg(s, FUND_WEIGHTS)
    s["fcf_yield"], s["earnings_yield"] = fcf_yield, earn_yield
    s["ps_ratio"] = num["market_cap"] / num["revenue_ttm"]
    return s


# ════════════════════════════ risk model ═════════════════════════════════
def ledoit_wolf_cc(returns: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """Ledoit-Wolf (2004) shrinkage towards the constant-correlation matrix.
    Returns the annualised covariance and the shrinkage intensity."""
    X = returns.fillna(0.0).values
    X = X - X.mean(axis=0)
    T, N = X.shape
    S = X.T @ X / T
    var = np.diag(S).copy()
    std = np.sqrt(var)
    R = S / np.outer(std, std)
    rbar = (R.sum() - N) / (N * (N - 1)) if N > 1 else 0.0
    F = rbar * np.outer(std, std)
    np.fill_diagonal(F, var)
    Y = X ** 2
    phi_mat = Y.T @ Y / T - S ** 2
    theta = (X ** 3).T @ X / T - var[:, None] * S
    np.fill_diagonal(theta, 0.0)
    rho = np.diag(phi_mat).sum() + rbar * (np.outer(1 / std, std) * theta).sum()
    gamma = np.linalg.norm(S - F, "fro") ** 2
    delta = float(np.clip((phi_mat.sum() - rho) / gamma / T, 0, 1)) if gamma > 0 else 1.0
    cov = (delta * F + (1 - delta) * S) * TRADING_DAYS
    return pd.DataFrame(cov, index=returns.columns, columns=returns.columns), delta


def cap_normalize(w: pd.Series, cap: float) -> pd.Series:
    w = w.clip(lower=0)
    w = w / w.sum()
    cap = max(cap, 1.0 / len(w) + 1e-9)
    for _ in range(50):
        over = w > cap + 1e-12
        if not over.any():
            break
        excess = (w[over] - cap).sum()
        w[over] = cap
        free = ~over & (w < cap)
        if not free.any():
            break
        w[free] += excess * w[free] / w[free].sum()
    return w / w.sum()


def construct(method: str, mu_ex: pd.Series, cov: pd.DataFrame, sectors: pd.Series,
              score: pd.Series, name_cap=NAME_CAP, sector_cap=SECTOR_CAP) -> pd.Series:
    """Long-only fully-invested weights for one construction method."""
    from scipy.optimize import minimize
    idx = list(mu_ex.index)
    n = len(idx)
    C, m = cov.loc[idx, idx].values, mu_ex.values
    vol = np.sqrt(np.diag(C))
    cap = max(name_cap, 1.0 / n + 1e-6)
    if method == "equal":
        return pd.Series(1.0 / n, index=idx)
    if method == "inv_vol":
        return cap_normalize(pd.Series(1 / vol, index=idx), cap)
    if method == "alpha_tilt":
        return cap_normalize(pd.Series((score.reindex(idx).fillna(0).clip(lower=-1) + 1.5).values / vol, index=idx), cap)
    secs = sectors.reindex(idx).fillna("Other")
    scap = max(sector_cap, 1.0 / secs.nunique() + 0.02)
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1}]
    for s in secs.unique():
        mask = (secs == s).values.astype(float)
        if mask.sum() * cap > scap:
            cons.append({"type": "ineq", "fun": lambda w, mask=mask: scap - w @ mask})
    if method == "min_var":
        obj = lambda w: w @ C @ w
    elif method == "max_sharpe":
        obj = lambda w: -(w @ m) / math.sqrt(max(w @ C @ w, 1e-12))
    else:
        raise ValueError(method)
    best = None
    for x0 in (np.full(n, 1.0 / n), cap_normalize(pd.Series(np.clip(m, 1e-4, None) / vol ** 2, index=idx), cap).values):
        r = minimize(obj, x0, method="SLSQP", bounds=[(0, cap)] * n, constraints=cons,
                     options={"maxiter": 500, "ftol": 1e-10})
        if r.success and (best is None or r.fun < best.fun):
            best = r
    if best is None:                       # optimiser failed: fall back to something sane
        return construct("alpha_tilt", mu_ex, cov, sectors, score, name_cap, sector_cap)
    w = pd.Series(np.clip(best.x, 0, None), index=idx)
    return w / w.sum()


def prune(method, w, mu_ex, cov, sectors, score, min_w=MIN_WEIGHT):
    """Drop dust positions and re-solve on the survivors."""
    for _ in range(4):
        keep = w[w >= min_w].index
        if len(keep) == len(w) or len(keep) < 5:
            break
        w = construct(method, mu_ex[keep], cov, sectors, score)
    return w[w > 1e-6].sort_values(ascending=False)


def enforce_risk_cap(w: pd.Series, cov: pd.DataFrame, cap: float = 0.15) -> pd.Series:
    """Trim any name that contributes more than `cap` of portfolio variance."""
    for _ in range(40):
        C = cov.loc[w.index, w.index].values
        rc = w.values * (C @ w.values) / (w.values @ C @ w.values)
        if rc.max() <= cap - 0.002:
            break
        w = w.copy()
        w.iloc[int(rc.argmax())] *= 0.92
        w = cap_normalize(w, NAME_CAP)
    return w.sort_values(ascending=False)


def expected_returns(z: pd.Series, vol: pd.Series, beta: pd.Series, view: pd.Series | None = None) -> pd.Series:
    """Excess return = beta*ERP (equilibrium prior) + Grinold alpha (IC*vol*score)."""
    alpha = IC_QUANT * vol * z.clip(-3, 3)
    if view is not None:
        alpha = alpha + IC_VIEW * vol * view.reindex(z.index).fillna(0)
    return beta.clip(0.3, 2.5) * ERP + alpha


def betas(ret: pd.DataFrame, bench: pd.Series) -> pd.Series:
    b = bench.reindex(ret.index).fillna(0)
    return ret.fillna(0).apply(lambda c: np.cov(c, b)[0, 1]) / b.var()


def risk_report(w: pd.Series, gross: float, close: pd.DataFrame, cov: pd.DataFrame, sectors: pd.Series) -> dict:
    """Everything the risk manager signs off on. w = sleeve weights (sum 1), gross = invested share."""
    ret = close[w.index].pct_change().iloc[-TRADING_DAYS:].fillna(0)
    port = (ret @ w) * gross
    C = cov.loc[w.index, w.index].values
    sleeve_vol = float(math.sqrt(w.values @ C @ w.values))
    rc = pd.Series(w.values * (C @ w.values) / sleeve_vol ** 2, index=w.index)
    curve = (1 + port).cumprod()
    corr = ret.corr().values
    avg_corr = float((corr.sum() - len(w)) / (len(w) * (len(w) - 1)))
    bench = {b: close[b].pct_change().reindex(ret.index).fillna(0) for b in BENCHMARKS if b in close}
    beta = {b: float(np.cov(port, r)[0, 1] / r.var()) for b, r in bench.items()}
    q = bench.get("QQQ")
    worst = q.nsmallest(10).index if q is not None else []
    sec_w = (w.groupby(sectors.reindex(w.index).fillna("Other")).sum() * gross).sort_values(ascending=False)
    var95 = float(-np.percentile(port, 5))
    limits = {
        f"name weight <= {NAME_CAP:.0%} of sleeve": bool(w.max() <= NAME_CAP + 1e-4 or len(w) * NAME_CAP < 1),
        f"sector weight <= {SECTOR_CAP:.0%} of sleeve": bool((sec_w / max(gross, 1e-9)).max() <= SECTOR_CAP + 0.021),
        f"ex-ante vol <= {TARGET_VOL:.0%}": bool(sleeve_vol * gross <= TARGET_VOL + 1e-3),
        "at least 12 names": bool(len(w) >= 12),
        "no name > 15% of risk": bool(rc.max() <= 0.15),
    }
    return dict(
        n_names=int(len(w)), effective_n=float(1 / (w ** 2).sum()), top5_weight=float(w.nlargest(5).sum() * gross),
        ex_ante_vol=sleeve_vol * gross, sleeve_vol=sleeve_vol, beta=beta, avg_pairwise_corr=avg_corr,
        var95_1d=var95, cvar95_1d=float(-port[port <= -var95].mean()), max_dd_1y_same_weights=float((curve / curve.cummax() - 1).min()),
        stress={"avg of 10 worst QQQ days (1y)": float(port.loc[worst].mean()) if len(worst) else None,
                "QQQ -10% shock (beta-implied)": float(-0.10 * beta.get("QQQ", float("nan"))),
                "QQQ -25% bear (beta-implied)": float(-0.25 * beta.get("QQQ", float("nan")))},
        sector_weights={k: float(v) for k, v in sec_w.items()},
        top_risk_contributors={k: float(v) for k, v in rc.nlargest(5).items()},
        limits=limits, passed=bool(all(limits.values())))


# ════════════════════════════ stages ═════════════════════════════════════
def state_path(asof: str) -> Path:
    return CACHE / f"quant_team_state_{asof}.pkl"


def stage_screen(args) -> dict:
    uni = load_universe(args.include_crypto)
    close, volume = download(list(uni.index) + BENCHMARKS + AUX)
    asof = close[BENCHMARKS[0]].dropna().index[-1]
    close, volume = close.loc[:asof], volume.loc[:asof]
    tickers = [t for t in uni.index if t in close]
    missing = [t for t in uni.index if t not in close]
    f = price_factors(close[tickers + BENCHMARKS], volume[tickers + BENCHMARKS], uni["sector"])
    f = f.loc[tickers]
    stale = [t for t in tickers if pd.isna(close[t].iloc[-1])]
    reg = regime(close, tickers)

    pool = f[f["eligible"] & ~f["knife"]].sort_values("alpha_price", ascending=False)
    fd = pd.DataFrame()
    if not args.no_fundamentals:
        fd = fetch_fundamentals(list(pool.index[:N_FUNDAMENTALS]), f["price"])
        fs = fundamental_score(fd)
        for c in fs:
            f[c] = fs[c]
    f["alpha"] = f["alpha_price"]
    if "fund_score" in f:
        has = f["fund_score"].notna()
        f.loc[has, "alpha"] = (1 - FUND_BLEND) * f.loc[has, "alpha_price"] + FUND_BLEND * f.loc[has, "fund_score"]
    f["name"], f["ai_layer"] = uni["name"], uni["ai_layer"]
    ranked = f[f["eligible"] & ~f["knife"]].sort_values("alpha", ascending=False)
    cands = ranked.head(N_CANDIDATES)

    asof_s = asof.strftime("%Y-%m-%d")
    excluded = {t: ("no data" if t in missing else "stale last bar" if t in stale else
                    "falling knife (below MA200, 1m < -25%)" if f.at[t, "knife"] else
                    f"history {int(f.at[t, 'bars'])} bars < {MIN_BARS}" if f.at[t, "bars"] < MIN_BARS else
                    "illiquid / price filter")
                for t in uni.index if t in missing or not f.at[t, "eligible"] or f.at[t, "knife"]}
    rf = float(close["^IRX"].dropna().iloc[-1]) / 100 if "^IRX" in close and close["^IRX"].notna().any() else 0.04
    CACHE.mkdir(exist_ok=True)
    state_path(asof_s).write_bytes(pickle.dumps(dict(close=close, factors=f, universe=uni, regime=reg, rf=rf,
                                                     fundamentals=fd, intraday=is_intraday(asof))))
    cols = ["name", "sector", "ai_layer", "price", "alpha", "alpha_price", "fund_score", "z_momentum", "z_trend",
            "z_low_risk", "z_rel_strength", "z_ai_theme", "growth", "quality", "value", "ret_1m", "ret_3m",
            "ret_6m", "mom_12_1", "vol", "dist_ma50", "dist_ma200", "off_high", "max_dd_1y", "fcf_yield", "earnings_yield", "ps_ratio"]
    cols = [c for c in cols if c in cands.columns]
    raw = fd.reindex(cands.index) if len(fd) else pd.DataFrame(index=cands.index)
    out = dict(
        as_of=asof_s, intraday_snapshot=is_intraday(asof), risk_free=rf, regime=reg,
        universe=dict(total=len(uni), with_data=len(tickers), eligible=int(f["eligible"].sum()),
                      after_knife_filter=len(ranked), excluded=excluded),
        benchmarks={b: {k: _f(v) for k, v in price_factors(close[[b] + BENCHMARKS[:1] + ["QQQ"]].loc[:, lambda d: ~d.columns.duplicated()], None,
                                                           pd.Series({b: "Index"})).loc[b, ["price", "ret_1m", "ret_3m", "ret_6m", "dist_ma50", "dist_ma200", "off_high"]].items()}
                    for b in BENCHMARKS},
        sector_view=_sector_view(f),
        candidates=[{"rank": i + 1, "ticker": t, **{c: _f(r[c]) for c in cols},
                     "fundamentals": {k: _f(v) for k, v in raw.loc[t].items()} if len(raw.columns) else {}}
                    for i, (t, r) in enumerate(cands.iterrows())],
        next_ranked=[t for t in ranked.index[N_CANDIDATES:N_CANDIDATES + 20]],
    )
    p = HERE / f"quant_team_candidates_{asof_s}.json"
    p.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"[screen] as of {asof_s}{' (INTRADAY snapshot)' if out['intraday_snapshot'] else ''} | "
          f"regime {reg['label']} score {reg['score']} gross {reg['gross_exposure']:.0%} | "
          f"universe {len(uni)} -> eligible {int(f['eligible'].sum())} -> ranked {len(ranked)} | wrote {p.name}")
    print("[screen] top 15:", ", ".join(cands.index[:15]))
    return out


def _f(v):
    if isinstance(v, (np.floating, float)):
        return None if (v != v or math.isinf(v)) else round(float(v), 4)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def _sector_view(f: pd.DataFrame) -> list:
    e = f[f["eligible"]]
    g = e.groupby("sector")
    df = pd.DataFrame({"n": g.size(), "ret_1m": g["ret_1m"].median(), "ret_3m": g["ret_3m"].median(),
                       "above_ma50": (e["dist_ma50"] > 0).groupby(e["sector"]).mean(),
                       "above_ma200": (e["dist_ma200"] > 0).groupby(e["sector"]).mean(),
                       "avg_alpha": g["alpha_price"].mean()}).sort_values("avg_alpha", ascending=False)
    return [{"sector": s, "ai_layer": AI_LAYERS.get(s), **{k: _f(v) for k, v in r.items()}} for s, r in df.iterrows()]


def load_views(paths: list[str]) -> tuple[pd.Series, dict, set, dict, dict]:
    """Merge every agent's views file. Same-ticker views are conviction-weighted."""
    acc, notes, vetoes, macro = {}, {}, {}, {}
    for p in paths:
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        for v in d.get("views", []):
            t = v["ticker"].upper()
            c = float(np.clip(v.get("conviction", 0.5), 0, 1))
            x = float(np.clip(v.get("view", 0), -2, 2))
            acc.setdefault(t, []).append((x, c))
            notes.setdefault(t, []).append({k: v.get(k) for k in ("agent", "view", "conviction", "thesis", "risks")})
        for v in d.get("vetoes", []):
            vetoes[v["ticker"].upper()] = f"{v.get('agent', '?')}: {v.get('reason', '')}"
        if d.get("macro", {}).get("gross_exposure_cap") is not None:
            if not macro or d["macro"]["gross_exposure_cap"] < macro["gross_exposure_cap"]:
                macro = d["macro"]
    # net signal = conviction-weighted view, scaled by the mean conviction behind it
    view = pd.Series({t: sum(x * c for x, c in xs) / len(xs) for t, xs in acc.items()}, dtype=float)
    return view, notes, set(vetoes), vetoes, macro


def stage_optimize(args) -> dict:
    states = sorted(CACHE.glob("quant_team_state_*.pkl"))
    if not states:
        stage_screen(args)
        states = sorted(CACHE.glob("quant_team_state_*.pkl"))
    st = pickle.loads(states[-1].read_bytes())
    asof = states[-1].stem.split("_")[-1]
    close, f, reg, rf = st["close"], st["factors"], st["regime"], st["rf"]
    view, notes, vetoed, veto_notes, macro = load_views(args.views or [])

    pool = f[f["eligible"] & ~f["knife"] & ~f.index.isin(vetoed)].copy()
    pool["view"] = view.reindex(pool.index).fillna(0)
    # information score: what the optimiser is actually paid for, per unit of vol
    pool["info"] = IC_QUANT * pool["alpha"].clip(-3, 3) + IC_VIEW * pool["view"]
    pool = pool[pool["info"] > 0].sort_values("info", ascending=False).head(args.names)
    names = list(pool.index)
    ret = close[names].pct_change().iloc[-TRADING_DAYS:]
    cov, delta = ledoit_wolf_cc(ret)
    vol = pd.Series(np.sqrt(np.diag(cov)), index=names)
    beta = betas(ret, close["SPY"].pct_change())
    mu_ex = expected_returns(pool["alpha"], vol, beta, pool["view"])

    method = args.method
    w = prune(method, construct(method, mu_ex, cov, pool["sector"], pool["alpha"]), mu_ex, cov, pool["sector"], pool["alpha"])
    w = enforce_risk_cap(w, cov)
    sleeve_vol = float(math.sqrt(w.values @ cov.loc[w.index, w.index].values @ w.values))
    gross_regime = reg["gross_exposure"]
    gross_vol = TARGET_VOL / sleeve_vol
    gross_macro = float(macro["gross_exposure_cap"]) if macro else 1.0
    gross = float(min(1.0, gross_regime, gross_vol, gross_macro))
    risk = risk_report(w, gross, close, cov, pool["sector"])
    exp_ret = float(w @ mu_ex[w.index]) * gross + rf
    sharpe = float(w @ mu_ex[w.index]) / sleeve_vol

    alts = {}
    for m in ("max_sharpe", "min_var", "inv_vol", "alpha_tilt", "equal"):
        wm = construct(m, mu_ex, cov, pool["sector"], pool["alpha"])
        v = float(math.sqrt(wm.values @ cov.values @ wm.values))
        alts[m] = dict(exp_excess_return=float(wm @ mu_ex), vol=v, sharpe=float(wm @ mu_ex) / v,
                       max_weight=float(wm.max()), effective_n=float(1 / (wm ** 2).sum()))

    capital = args.capital
    holdings = {}
    if args.holdings and Path(args.holdings).exists():
        h = pd.read_csv(args.holdings)
        holdings = dict(zip(h.iloc[:, 0].astype(str).str.upper(), h.iloc[:, 1].astype(float)))
    positions = []
    for t, wt in w.items():
        px = float(close[t].dropna().iloc[-1])
        tw = float(wt * gross)
        shares = math.floor(tw * capital / px)
        cur = holdings.get(t, 0.0)
        positions.append(dict(
            ticker=t, name=f.at[t, "name"], sector=f.at[t, "sector"], ai_layer=f.at[t, "ai_layer"],
            weight=round(tw, 4), sleeve_weight=round(float(wt), 4), price=round(px, 2), shares=shares,
            notional=round(shares * px, 2), trade_shares=shares - cur, alpha=_f(f.at[t, "alpha"]),
            view=_f(pool.at[t, "view"]), exp_excess_return=_f(mu_ex[t]), vol=_f(vol[t]), beta=_f(beta[t]),
            ret_3m=_f(f.at[t, "ret_3m"]), dist_ma50=_f(f.at[t, "dist_ma50"]), dist_ma200=_f(f.at[t, "dist_ma200"]),
            analyst_notes=notes.get(t, [])))
    exits = [dict(ticker=t, shares=-s, reason="not in target portfolio") for t, s in holdings.items() if t not in w.index and s]
    invested = sum(p["notional"] for p in positions)
    out = dict(
        as_of=asof, intraday_snapshot=st.get("intraday", False), method=method, capital=capital,
        regime=reg, risk_free=rf,
        exposure=dict(gross=gross, cash=1 - gross, regime_cap=gross_regime, vol_target_cap=min(1.0, gross_vol),
                      macro_cap=gross_macro, macro_note=macro or None,
                      binding="vol target" if gross == gross_vol else "macro strategist" if macro and gross == gross_macro and gross < gross_regime
                      else "regime" if gross < 1 else "none"),
        expected=dict(annual_return=exp_ret, sleeve_excess_return=float(w @ mu_ex[w.index]), ex_ante_vol=risk["ex_ante_vol"],
                      sharpe=sharpe, cov_shrinkage=delta,
                      assumptions=f"IC {IC_QUANT} on factor score, IC {IC_VIEW} on analyst views, ERP {ERP:.0%}; model estimate, not a forecast"),
        risk=risk, positions=positions, exits=exits, cash_dollars=round(capital - invested, 2),
        vetoes=veto_notes, views_used=len(view), alternatives=alts,
        not_selected=[dict(ticker=t, alpha=_f(r["alpha"]), view=_f(r["view"])) for t, r in pool.drop(index=w.index).iterrows()])
    (HERE / f"quant_team_portfolio_{asof}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=_f))
    (HERE / f"quant_team_portfolio_{asof}.md").write_text(render_md(out), encoding="utf-8")
    print(f"[optimize] {asof} {method}: {len(w)} names, gross {gross:.0%} ({out['exposure']['binding']}), "
          f"exp return {exp_ret:.1%}, vol {risk['ex_ante_vol']:.1%}, Sharpe {sharpe:.2f}, "
          f"risk limits {'PASS' if risk['passed'] else 'FAIL'}")
    print("[optimize] " + ", ".join(f"{p['ticker']} {p['weight']:.1%}" for p in positions))
    return out


def render_md(o: dict) -> str:
    r, e, x = o["risk"], o["expected"], o["exposure"]
    pct = lambda v, d=1: "n/a" if v is None else f"{v:.{d}%}"
    L = [f"# Quant team portfolio — {o['as_of']}", ""]
    if o["intraday_snapshot"]:
        L += ["> **Intraday snapshot**: prices were taken before the close; re-run after 4:15pm ET before acting.", ""]
    L += [f"**Regime**: {o['regime']['label']} (score {o['regime']['score']}/5, VIX {o['regime']['vix']:.1f}, "
          f"{o['regime']['breadth_above_ma50']:.0%} of universe above MA50)  ",
          f"**Exposure**: {pct(x['gross'], 0)} invested / {pct(x['cash'], 0)} cash — binding constraint: {x['binding']} "
          f"(regime cap {pct(x['regime_cap'], 0)}, vol-target cap {pct(x['vol_target_cap'], 0)}, macro cap {pct(x['macro_cap'], 0)})  ",
          f"**Model expectations**: return {pct(e['annual_return'])}/yr, vol {pct(e['ex_ante_vol'])}, Sharpe {e['sharpe']:.2f} "
          f"({e['assumptions']})", "",
          "## Positions", "",
          "| # | Ticker | Sector | Weight | Shares | Notional | Alpha z | View | Exp. excess | Vol | Beta | 3m | vs MA50 |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, p in enumerate(o["positions"], 1):
        L.append(f"| {i} | **{p['ticker']}** | {p['sector']} | {pct(p['weight'])} | {p['shares']} | ${p['notional']:,.0f} | "
                 f"{p['alpha']:+.2f} | {p['view'] or 0:+.1f} | {pct(p['exp_excess_return'])} | {pct(p['vol'], 0)} | "
                 f"{p['beta']:.2f} | {pct(p['ret_3m'], 0)} | {pct(p['dist_ma50'], 0)} |")
    L += ["", f"Cash: ${o['cash_dollars']:,.0f} of ${o['capital']:,.0f}", "", "## Risk", "",
          f"- Names {r['n_names']} (effective {r['effective_n']:.1f}); top-5 weight {pct(r['top5_weight'])}; avg pairwise correlation {r['avg_pairwise_corr']:.2f}",
          f"- Beta: " + ", ".join(f"{k} {v:.2f}" for k, v in r["beta"].items()),
          f"- 1-day VaR95 {pct(r['var95_1d'])}, CVaR95 {pct(r['cvar95_1d'])}; 1y max drawdown at these weights {pct(r['max_dd_1y_same_weights'])}",
          "- Stress: " + "; ".join(f"{k} {pct(v)}" for k, v in r["stress"].items()),
          "- Sector weights: " + ", ".join(f"{k} {pct(v, 0)}" for k, v in r["sector_weights"].items()),
          "- Top risk contributors: " + ", ".join(f"{k} {pct(v, 0)}" for k, v in r["top_risk_contributors"].items()),
          "- Limits: " + "; ".join(f"{'PASS' if v else 'FAIL'} {k}" for k, v in r["limits"].items()), ""]
    if o["vetoes"]:
        L += ["## Vetoes", ""] + [f"- {t}: {why}" for t, why in o["vetoes"].items()] + [""]
    notes = [(p["ticker"], n) for p in o["positions"] for n in p["analyst_notes"]]
    if notes:
        L += ["## Analyst views behind the weights", ""]
        L += [f"- **{t}** ({n.get('agent')}, view {n.get('view'):+}, conviction {n.get('conviction')}): {n.get('thesis') or ''}"
              + (f" _Risks: {n['risks']}_" if n.get("risks") else "") for t, n in notes] + [""]
    L += ["## Alternative constructions (same names, sleeve level)", "", "| Method | Exp. excess | Vol | Sharpe | Max weight | Effective N |", "|---|---|---|---|---|---|"]
    L += [f"| {m} | {pct(a['exp_excess_return'])} | {pct(a['vol'])} | {a['sharpe']:.2f} | {pct(a['max_weight'])} | {a['effective_n']:.1f} |"
          for m, a in o["alternatives"].items()]
    L += ["", "_Research output only. Not investment advice; nothing here places an order._"]
    return "\n".join(L) + "\n"


# ════════════════════════════ backtest ═══════════════════════════════════
def perf(r: pd.Series, rf: float) -> dict:
    curve = (1 + r).cumprod()
    yrs = len(r) / TRADING_DAYS
    vol = r.std() * math.sqrt(TRADING_DAYS)
    cagr = curve.iloc[-1] ** (1 / yrs) - 1
    dd = (curve / curve.cummax() - 1).min()
    return dict(cagr=_f(cagr), vol=_f(vol), sharpe=_f((r.mean() * TRADING_DAYS - rf) / vol) if vol else None,
                max_dd=_f(dd), calmar=_f(cagr / abs(dd)) if dd else None, total_return=_f(curve.iloc[-1] - 1))


def stage_backtest(args) -> dict:
    uni = load_universe(args.include_crypto)
    close, volume = download(list(uni.index) + BENCHMARKS + AUX)
    asof = close["SPY"].dropna().index[-1]
    close, volume = close.loc[:asof].ffill(limit=3), volume.loc[:asof]
    tickers = [t for t in uni.index if t in close]
    rets = close.pct_change()
    methods = ["max_sharpe", "min_var", "inv_vol", "alpha_tilt", "equal"]
    series = {m: [] for m in methods + ["max_sharpe+regime", "EW universe"]}
    prev = {m: pd.Series(dtype=float) for m in series}
    turnover = {m: [] for m in series}
    start = 2 * TRADING_DAYS + 10
    picks_log = []
    for i in range(start, len(close) - 1, REBAL_DAYS):
        hist = close.iloc[:i + 1]
        f = price_factors(hist[tickers + BENCHMARKS], volume.iloc[:i + 1][tickers + BENCHMARKS], uni["sector"]).loc[tickers]
        elig = f[f["eligible"] & ~f["knife"]]
        pool = elig[elig["alpha_price"] > 0].sort_values("alpha_price", ascending=False).head(args.names)
        if len(pool) < 8:
            continue
        names = list(pool.index)
        r = hist[names].pct_change().iloc[-TRADING_DAYS:]
        cov, _ = ledoit_wolf_cc(r)
        vol = pd.Series(np.sqrt(np.diag(cov)), index=names)
        mu = expected_returns(pool["alpha_price"], vol, betas(r, hist["SPY"].pct_change()))
        fwd = rets.iloc[i + 1:i + 1 + REBAL_DAYS]
        reg = regime(hist, tickers)
        weights = {m: construct(m, mu, cov, pool["sector"], pool["alpha_price"]) for m in methods}
        weights["max_sharpe+regime"] = weights["max_sharpe"] * reg["gross_exposure"]
        weights["EW universe"] = pd.Series(1.0 / len(elig), index=elig.index)
        picks_log.append(dict(date=hist.index[-1].strftime("%Y-%m-%d"), regime=reg["label"], top=names[:10]))
        for m, w in weights.items():
            growth = (1 + fwd[w.index].fillna(0)).cumprod()
            val = (growth * w).sum(axis=1) + (1 - w.sum())
            pr = val.pct_change().fillna(val.iloc[0] - 1)
            to = float((w.reindex(w.index.union(prev[m].index)).fillna(0)
                        - prev[m].reindex(w.index.union(prev[m].index)).fillna(0)).abs().sum())
            pr.iloc[0] -= to * COST_BPS / 1e4
            turnover[m].append(to)
            end_w = growth.iloc[-1] * w
            prev[m] = end_w / val.iloc[-1]
            series[m].append(pr)
    res = {m: pd.concat(s) for m, s in series.items() if s}
    idx = res["equal"].index
    rf = float(close["^IRX"].reindex(idx).mean()) / 100 if "^IRX" in close else 0.04
    for b in BENCHMARKS:
        res[b] = rets[b].reindex(idx).fillna(0)
    stats = {m: {**perf(r, rf), "avg_turnover_per_rebalance": _f(np.mean(turnover[m])) if m in turnover else 0.0} for m, r in res.items()}
    monthly = {m: (1 + r).groupby(np.arange(len(r)) // REBAL_DAYS).prod() - 1 for m, r in res.items()}
    for m in stats:
        stats[m]["periods_beating_QQQ"] = _f(float((monthly[m] > monthly["QQQ"]).mean()))
    by_year = {m: {str(y): _f(float((1 + g).prod() - 1)) for y, g in r.groupby(r.index.year)} for m, r in res.items()}
    out = dict(as_of=asof.strftime("%Y-%m-%d"), window=[idx[0].strftime("%Y-%m-%d"), idx[-1].strftime("%Y-%m-%d")],
               rebalance_days=REBAL_DAYS, cost_bps=COST_BPS, names=args.names, risk_free=rf, stats=stats, by_year=by_year,
               caveats=["SURVIVORSHIP / HINDSIGHT BIAS: the universe is today's hand-picked AI_Portfolios.xlsx list, so every "
                        "method is flattered. Judge methods against 'EW universe' (same bias), not against SPY/QQQ.",
                        "Price factors only - fundamentals and analyst views are not point-in-time and are excluded.",
                        "Rebalance at the close of the signal bar; 10 bps one-way cost; no slippage, taxes or borrow."],
               recent_rebalances=picks_log[-6:])
    p = HERE / f"quant_team_backtest_{out['as_of']}.json"
    p.write_text(json.dumps(out, indent=1))
    print(f"[backtest] {out['window'][0]} -> {out['window'][1]} ({len(picks_log)} rebalances) wrote {p.name}")
    print(f"{'method':<20}{'CAGR':>8}{'vol':>8}{'Sharpe':>8}{'maxDD':>8}{'>QQQ':>7}{'t/o':>6}")
    for m, s in stats.items():
        print(f"{m:<20}{s['cagr']:>8.1%}{s['vol']:>8.1%}{s['sharpe']:>8.2f}{s['max_dd']:>8.1%}"
              f"{s['periods_beating_QQQ']:>7.0%}{s['avg_turnover_per_rebalance']:>6.2f}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["screen", "optimize", "backtest", "all"])
    ap.add_argument("--views", nargs="*", help="analyst views JSON files to merge")
    ap.add_argument("--method", default="max_sharpe", choices=["max_sharpe", "min_var", "inv_vol", "alpha_tilt", "equal"])
    ap.add_argument("--names", type=int, default=N_NAMES)
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--holdings", help="CSV of current holdings: ticker,shares")
    ap.add_argument("--include-crypto", action="store_true", help="include the -USD coins from the Crypto column")
    ap.add_argument("--no-fundamentals", action="store_true")
    args = ap.parse_args()
    if args.stage in ("screen", "all"):
        stage_screen(args)
    if args.stage in ("optimize", "all"):
        stage_optimize(args)
    if args.stage in ("backtest", "all"):
        stage_backtest(args)


if __name__ == "__main__":
    main()
