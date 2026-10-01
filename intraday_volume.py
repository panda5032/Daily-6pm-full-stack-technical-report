# -*- coding: utf-8 -*-
"""盘中量能归一化 — 部分bar的成交量不能直接和20日全日均量比。

问题(2026-08-25 实盘暴露): 任务在 10:58 ET 被盘中触发时, yfinance 的今日日线
bar 只累积了约 28% 的全日成交量, 但 RVOL 仍按 vol[-1]/20日均量 计算 →
全场 RVOL 显示 0.1–0.7x, 于是:
  - 带顶引擎 R3 把每一只 %B>1 的票都判成"缩量假突破"(HOOD 被误判减仓,
    实际全日量能外推 ≈2.4x, 是放量突破)
  - 带底引擎 B2 把下跌全判成"麻木阴跌无恐慌"
  - 四支柱 BB_缩量假突破嫌疑 无差别扣分
  - trade_plan_charts 的刀/放量确认/突破确认全部失真

修法: 用美股日内成交量分布曲线(U型、前置)把部分bar外推成全日等效量,
再算 RVOL; 同时回传 is_estimate 标志, 让"低量能→负面判定"的规则在估算
模式下用更严的阈值, 避免外推误差制造假信号。

用法:
    from intraday_volume import rvol_now
    rv, est = rvol_now(df.Volume, ticker=tkr, index=df.index)
"""
from __future__ import annotations

from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    _ET = None

# 美股日内累计成交量占全日比例 (分钟数自 09:30 起, 经验U型曲线:
# 开盘30min ~13%, 尾盘30min ~21% 含收盘集合竞价)
_CURVE = [
    (0, 0.000), (15, 0.080), (30, 0.130), (60, 0.210), (90, 0.275),
    (120, 0.335), (150, 0.390), (180, 0.440), (210, 0.487), (240, 0.535),
    (270, 0.585), (300, 0.640), (330, 0.705), (360, 0.790), (390, 1.000),
]

# 外推误差在开盘初期发散: 低于此比例直接判定 RVOL 不可用
_MIN_FRAC = 0.05


def _interp(minutes: float) -> float:
    """按曲线插值出 minutes 时点的累计成交量占比。"""
    if minutes <= 0:
        return 0.0
    if minutes >= 390:
        return 1.0
    for (m0, f0), (m1, f1) in zip(_CURVE, _CURVE[1:]):
        if m0 <= minutes <= m1:
            return f0 + (f1 - f0) * (minutes - m0) / (m1 - m0)
    return 1.0


def session_fraction(ticker: str = "", now=None) -> float:
    """当前时点已完成的全日成交量比例。1.0 = 收盘后/完整bar。

    加密货币(-USD)按 UTC 自然日线性推进; 美股按 U 型日内曲线。"""
    is_crypto = ticker.upper().endswith("-USD")
    if is_crypto:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)
        elapsed = now.hour * 60 + now.minute
        return min(1.0, max(0.0, elapsed / 1440.0))
    if _ET is None:
        return 1.0
    now = now or datetime.now(_ET)
    if now.tzinfo is not None:
        now = now.astimezone(_ET)
    if now.weekday() >= 5:
        return 1.0
    minutes = (now.hour * 60 + now.minute) - (9 * 60 + 30)
    if minutes <= 0:      # 盘前 — 上一根bar是完整的
        return 1.0
    if minutes >= 390:    # 收盘后 — 今日bar已完整
        return 1.0
    return _interp(minutes)


def _last_bar_is_today(index, ticker: str = "", now=None) -> bool:
    """最后一根bar是否就是今天这根(未完成的)bar。

    盘中运行但 yfinance 尚未吐出今日bar时, 最后一根是昨天的完整bar,
    绝不能再做外推 — 否则把一根完整bar放大成 3x 假放量。"""
    if index is None or len(index) == 0:
        return False
    try:
        last = index[-1]
        is_crypto = ticker.upper().endswith("-USD")
        tz = timezone.utc if is_crypto else _ET
        now = now or datetime.now(tz)
        last_date = last.date() if hasattr(last, "date") else None
        if last_date is None:
            return False
        now_date = now.astimezone(tz).date() if now.tzinfo else now.date()
        return last_date == now_date
    except Exception:
        return False


def rvol_now(vol_series, ticker: str = "", index=None, window: int = 20, now=None):
    """归一化后的 RVOL 与估算标志。

    返回 (rvol, is_estimate):
      rvol        — 全日等效 RVOL; 数据不足或开盘初期无法外推时为 None
      is_estimate — True 表示由部分bar外推而来, 调用方对"低量能→负面
                    判定"的规则应收紧阈值 (见 low_volume_threshold)
    """
    try:
        if vol_series is None or len(vol_series) < window + 1:
            return None, False
        idx = index if index is not None else getattr(vol_series, "index", None)
        # 均量用前 window 根已完成的bar, 排除今日这根未完成的
        base = float(vol_series.iloc[-(window + 1):-1].mean())
        if base <= 0:
            return None, False
        last_vol = float(vol_series.iloc[-1])
        raw = last_vol / base

        if not _last_bar_is_today(idx, ticker, now):
            return round(raw, 2), False       # 完整bar, 原样返回

        frac = session_fraction(ticker, now)
        if frac >= 0.999:
            return round(raw, 2), False       # 已收盘
        if frac < _MIN_FRAC:
            return None, True                 # 开盘初期, 外推不可信
        return round(raw / frac, 2), True
    except Exception:
        return None, False


def low_volume_threshold(base: float, is_estimate: bool) -> float:
    """低量能类负面规则(假突破/缩量/麻木阴跌)在估算模式下的阈值。

    外推有误差, 收紧 20% 后才允许开负面判定, 宁可漏报不要误报 —
    正是 8/25 HOOD 被误判"缩量假突破"的那类错误。"""
    return base * 0.8 if is_estimate else base


def note(is_estimate: bool) -> str:
    """给 reason 字符串加的估算标注。"""
    return "(盘中估算)" if is_estimate else ""
