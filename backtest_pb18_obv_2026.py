"""
打法18 OBV资金流打法 — mechanical version of the 3-image OBV rulebook (2026-09-04):
  选股: 只做 OBV 持续向上的票 (OBV > OBV20 且 OBV20 十日斜率向上)
  低吸买点(18a): 股价回调 (5日跌≥3%) 而 OBV 不跌 (OBV ≥ 5日前) → 企稳bar (收破前一根高点) 进
  启动买点(18b): OBV 突破前期高点 (60日) + 股价放量阳线 (≥1.5×20日均量) + MA50 上方 进
  持仓: OBV 同步无顶背离就拿
  卖点(OBV离场, 三选一): 股价新高 OBV 未新高 (顶背离) / OBV 跌破 10 日短期支撑 / 股价大涨 OBV 提前止步
  风控: 3-5% 硬止损 (取 5%) 且 OBV 跌破买入时 OBV 低位 → 无条件止损
  误区3: 大盘闸门变体 (QQQ > MA50 才开新仓)
Old playbooks (1/2/8/16纯图/14底背离/15金针/基线) are RE-RUN on the same data day.
Signals research only — not financial advice.
"""
import json
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")
from backtest_playbooks_2026 import (PLAYBOOKS, add_indicators, bench_returns, download_all,  # noqa: E402
                                     get_universe, run_trades, summarize, rotation_backtest)
from backtest_pb16_2026 import add_pb16_indicators, _w_bottom, _plat_break  # noqa: E402

HERE = Path(__file__).parent
TODAY = datetime.now().strftime("%Y-%m-%d")
WINDOWS = [("2024", "2024-01-01", "2025-01-01"), ("2025", "2025-01-01", "2026-01-01"),
           ("2026 YTD", "2026-01-01", None), ("3年累计", "2024-01-01", None)]
HARD_STOP = 0.05

# ── market gate (误区3) ───────────────────────────────────────────────
_q = yf.download("QQQ", start="2023-03-01", interval="1d", auto_adjust=True, progress=False)
if isinstance(_q.columns, pd.MultiIndex):
    _q.columns = _q.columns.get_level_values(0)
QQQ_OK = (_q["Close"] > _q["Close"].rolling(50).mean())


def gate_ok(d):
    i = QQQ_OK.index.searchsorted(d, side="right") - 1
    return bool(QQQ_OK.iloc[i]) if i >= 0 else False


# ── indicators ──────────────────────────────────────────────────────
def add18(df):
    step = np.sign(df["Close"].diff()).fillna(0) * df["Volume"]
    df["obv"] = step.cumsum()
    df["obv20"] = df["obv"].rolling(20).mean()
    df["obv_up"] = (df["obv"] > df["obv20"]) & (df["obv20"] > df["obv20"].shift(10))   # 选股: OBV持续向上
    df["obv_hi20"] = df["obv"].rolling(20).max().shift(1)
    df["obv_hi60"] = df["obv"].rolling(60).max().shift(1)
    df["obv_lo10"] = df["obv"].rolling(10).min().shift(1)
    df["obv_lo5"] = df["obv"].rolling(5).min()
    return df


def _stop(df, i, lo):
    """structural stop (low - 0.5 ATR) but never wider than the 5% hard stop."""
    c = float(df["Close"].iloc[i])
    return max(float(lo - 0.5 * df["atr"].iloc[i]), c * (1 - HARD_STOP))


def _pos(df, i, lo):
    return {"stop": _stop(df, i, lo), "obv_floor": float(df["obv_lo5"].iloc[i])}


# 18a 低吸: OBV选股通过 + 股价回调 + OBV不跌 + 企稳bar
def a_entry(df, i):
    if not df["obv_up"].iloc[i]:
        return None
    c = df["Close"]
    pulled = c.iloc[i - 1] <= c.iloc[i - 6] * 0.97 or c.iloc[i] <= c.iloc[i - 5] * 0.97
    obv_holds = df["obv"].iloc[i] >= df["obv"].iloc[i - 5]
    if pulled and obv_holds and c.iloc[i] > df["High"].iloc[i - 1] and c.iloc[i] > df["ma50"].iloc[i]:
        return _pos(df, i, df["Low"].iloc[i - 1:i + 1].min())
    return None


# 18b 启动: OBV突破60日前高 + 股价放量阳线 + MA50上方
def b_entry(df, i):
    if (df["obv"].iloc[i] > df["obv_hi60"].iloc[i]
            and df["Close"].iloc[i] > df["Open"].iloc[i]
            and df["Volume"].iloc[i] >= 1.5 * df["vol20"].iloc[i]
            and df["Close"].iloc[i] > df["ma50"].iloc[i]):
        return _pos(df, i, df["Low"].iloc[i])
    return None


def ab_entry(df, i):
    return a_entry(df, i) or b_entry(df, i)


def mk_gated(base):
    def f(df, i):
        return base(df, i) if gate_ok(df.index[i]) else None
    return f


# ── exits ───────────────────────────────────────────────────────────
def obv_exit(df, i, pos):
    """图2 三条卖点 + 图3 风控."""
    c = float(df["Close"].iloc[i])
    if c < pos["stop"]:
        return True
    if c < pos["entry"] and df["obv"].iloc[i] < pos["obv_floor"]:          # 风控: OBV跌破买入低位
        return True
    if c > df["hi20"].iloc[i] and df["obv"].iloc[i] < df["obv_hi20"].iloc[i]:  # 顶背离/OBV提前止步
        return True
    if df["obv"].iloc[i] < df["obv_lo10"].iloc[i]:                           # OBV跌破短期支撑
        return True
    return False


def chart_exit(df, i, pos):
    c = float(df["Close"].iloc[i])
    return c < df["ma20"].iloc[i] or c < pos["stop"]


def chart_exit_nohard(df, i, pos):
    """pure chart exit with structural stop only (no 5% cap) — isolates the hard-stop effect."""
    c = float(df["Close"].iloc[i])
    return c < df["ma20"].iloc[i] or c < pos["stop_struct"]


def a_entry_struct(df, i):
    e = a_entry(df, i)
    if e:
        e["stop_struct"] = float(df["Low"].iloc[i - 1:i + 1].min() - 0.5 * df["atr"].iloc[i])
    return e


def b_entry_struct(df, i):
    e = b_entry(df, i)
    if e:
        e["stop_struct"] = float(df["Low"].iloc[i] - 0.5 * df["atr"].iloc[i])
    return e


def ab_entry_struct(df, i):
    return a_entry_struct(df, i) or b_entry_struct(df, i)


# 打法16 (promoted 纯图版 16d)
def pb16_entry(df, i):
    return _w_bottom(df, i) or _plat_break(df, i)


NEW_PB = {
    "打法18 全套(低吸∪启动)+OBV离场+5%硬止损": (ab_entry, obv_exit),
    "打法18a 低吸(回调OBV不跌)+OBV离场":       (a_entry, obv_exit),
    "打法18b 启动(OBV破60日高+放量)+OBV离场":   (b_entry, obv_exit),
    "打法18g 全套+OBV离场+QQQ>MA50闸门":       (mk_gated(ab_entry), obv_exit),
    "打法18x 全套+纯图离场(MA20)+5%硬止损":     (ab_entry, chart_exit),
    "打法18y 全套+纯图离场(结构止损无5%)":      (ab_entry_struct, chart_exit_nohard),
    "打法18ay 低吸+纯图离场(结构止损)":         (a_entry_struct, chart_exit_nohard),
    "打法18by 启动+纯图离场(结构止损)":         (b_entry_struct, chart_exit_nohard),
}
OLD_PB = {
    "打法1 回踩企稳": PLAYBOOKS["打法1 回踩企稳"],
    "打法2 缩量平台突破": PLAYBOOKS["打法2 缩量平台突破"],
    "打法8 带行持有": PLAYBOOKS["打法8 带行持有"],
    "打法16 纯图突破(16d)": (pb16_entry, chart_exit),
    "打法14 MACD底背离(抄底1)": PLAYBOOKS["抄底1 MACD底背离"],
    "打法15 金针探底(抄底6)": PLAYBOOKS["抄底6 金针探底"],
    "基线 MACD金叉": PLAYBOOKS["基线 MACD金叉"],
}


def run_set(data, pbs, start, end):
    res, alltr = {}, {}
    for name, (efn, xfn) in pbs.items():
        trades = []
        for t, df in data.items():
            df.attrs["t"] = t
            for tr in run_trades(df, efn, xfn, name, start, end):
                tr["ticker"] = t
                trades.append(tr)
        res[name] = summarize(trades)
        alltr[name] = trades
        print(f"    {name}: {len(trades)}", flush=True)
    return res, alltr


def table(md, res):
    md += ["| 打法 | 交易数 | 胜率 | 平均单笔 | 中位数 | PF | 持仓天 | 每票复利均值 |",
           "|---|---|---|---|---|---|---|---|"]
    for name, s in res.items():
        if not s:
            md.append(f"| {name} | 0 | — | — | — | — | — | — |")
            continue
        md.append(f"| {name} | {s['n_trades']} | {s['win_rate']:.0%} | {s['avg_ret']:+.2%} | "
                  f"{s['median_ret']:+.2%} | {s['profit_factor']:.2f} | {s['avg_days']:.0f} | "
                  f"{s['avg_ticker_ytd']:+.2%} |")


def main():
    tickers, _ = get_universe()
    data = download_all(tickers)
    for t in data:
        data[t] = add18(add_pb16_indicators(add_indicators(data[t])))
    print(f"data ok: {len(data)}", flush=True)
    out = {"asof": TODAY, "windows": {}}
    md = [f"# 打法18 OBV资金流打法 回测 (as of {TODAY})",
          f"universe {len(data)} · entries at signal close · no costs · 老打法同日同数据重跑",
          "· 选股=OBV>OBV20且OBV20十日上行; 18a低吸=5日跌≥3%但OBV≥5日前+企稳bar+MA50上; "
          "18b启动=OBV破60日高+放量(≥1.5x)阳线+MA50上; OBV离场=价新高OBV不新高/OBV破10日低/OBV破买入低位(亏损时)/5%硬止损", ""]
    for label, start, end in WINDOWS:
        print(f"[{label}]", flush=True)
        res, _tr = run_set(data, {**NEW_PB, **OLD_PB}, start, end)
        bench = bench_returns(data, start, end)
        try:
            rot = rotation_backtest(data, start, end)
            bench["打法3 轮动(top10动量20日调仓)"] = float(rot["ytd_return"])
        except Exception as ex:  # noqa: BLE001
            print("rotation failed", ex)
        out["windows"][label] = {"results": res, "benchmarks": bench}
        md += [f"## {label} ({start} → {end or TODAY})", ""]
        table(md, res)
        md.append("\n基准: " + " · ".join(f"{b} {r:+.2%}" for b, r in bench.items()) + "\n")
        (HERE / f"backtest_pb18_{TODAY}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        (HERE / f"backtest_pb18_{TODAY}.md").write_text("\n".join(md), encoding="utf-8")
    print("saved", flush=True)


if __name__ == "__main__":
    main()
