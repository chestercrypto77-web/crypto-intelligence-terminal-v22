from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from v22.contracts import AnomalyLevel, CycleType


@dataclass(frozen=True)
class DerivedObservation:
    metric: str
    value: Any
    calculation: str
    evidence_metrics: tuple[str, ...]
    metadata: dict[str, Any]


def _num(metrics: dict[str, Any], name: str, default: float = 0.0) -> float:
    try:
        return float(metrics.get(name, default))
    except Exception:
        return default


def _direction(value: float, deadband: float = 0.05) -> str:
    if value > deadband:
        return "UP"
    if value < -deadband:
        return "DOWN"
    return "FLAT"


def calculate(cycle_type: CycleType, metrics: dict[str, Any]) -> list[DerivedObservation]:
    if cycle_type == CycleType.MARKET_15M:
        returns = [_num(metrics, x) for x in ("return_15m_pct", "return_1h_pct", "return_4h_pct", "return_24h_pct")]
        positive = sum(1 for x in returns if x > 0.05)
        negative = sum(1 for x in returns if x < -0.05)
        if positive >= 3:
            alignment = "UP"
        elif negative >= 3:
            alignment = "DOWN"
        else:
            alignment = "MIXED"
        rvol = _num(metrics, "relative_volume")
        rvol_d = _num(metrics, "relative_volume_delta")
        structure = "BREAKOUT" if bool(metrics.get("breakout")) else "BREAKDOWN" if bool(metrics.get("breakdown")) else "RANGE"
        return [
            DerivedObservation("multi_timeframe_direction", alignment, "mtf_return_alignment_v1",
                               ("return_15m_pct","return_1h_pct","return_4h_pct","return_24h_pct"), {"positive_windows": positive, "negative_windows": negative}),
            DerivedObservation("volume_flow", _direction(rvol_d, 0.05), "rvol_delta_direction_v1",
                               ("relative_volume_delta",), {"relative_volume": rvol, "delta": rvol_d}),
            DerivedObservation("volume_participation", "ELEVATED" if rvol >= 1.25 else "LOW" if rvol <= 0.5 else "NORMAL",
                               "relative_volume_band_v1", ("relative_volume",), {"relative_volume": rvol}),
            DerivedObservation("market_structure", structure, "breakout_structure_v1", ("breakout","breakdown"), {}),
        ]

    one_rvol = _num(metrics, "relative_volume_1m")
    five_rvol = _num(metrics, "relative_volume_5m")
    one_d = _num(metrics, "relative_volume_delta_1m")
    five_d = _num(metrics, "relative_volume_delta_5m")
    price = _num(metrics, "price_usd")
    e9_1, e21_1 = _num(metrics, "ema9_1m"), _num(metrics, "ema21_1m")
    e9_5, e21_5 = _num(metrics, "ema9_5m"), _num(metrics, "ema21_5m")
    one_dir = "UP" if price > e9_1 > e21_1 else "DOWN" if price < e9_1 < e21_1 else "MIXED"
    five_dir = "UP" if price > e9_5 > e21_5 else "DOWN" if price < e9_5 < e21_5 else "MIXED"
    alignment = one_dir if one_dir == five_dir and one_dir != "MIXED" else "MIXED"
    structure = "BREAKOUT" if bool(metrics.get("breakout_5m")) else "BREAKDOWN" if bool(metrics.get("breakdown_5m")) else "RANGE"
    return [
        DerivedObservation("micro_trend_alignment", alignment, "ema_alignment_1m_5m_v1",
                           ("price_usd","ema9_1m","ema21_1m","ema9_5m","ema21_5m"), {"one_minute": one_dir, "five_minute": five_dir}),
        DerivedObservation("volume_flow_1m", _direction(one_d, 0.05), "rvol_delta_direction_v1", ("relative_volume_delta_1m",), {"delta": one_d}),
        DerivedObservation("volume_flow_5m", _direction(five_d, 0.05), "rvol_delta_direction_v1", ("relative_volume_delta_5m",), {"delta": five_d}),
        DerivedObservation("volume_participation", "ELEVATED" if max(one_rvol, five_rvol) >= 1.25 else "LOW" if max(one_rvol, five_rvol) <= 0.5 else "NORMAL",
                           "relative_volume_band_v1", ("relative_volume_1m","relative_volume_5m"), {"one_minute": one_rvol, "five_minute": five_rvol}),
        DerivedObservation("market_structure", structure, "breakout_structure_v1", ("breakout_5m","breakdown_5m"), {}),
    ]


def anomaly_level(cycle_type: CycleType, metrics: dict[str, Any], derived: list[DerivedObservation]) -> tuple[AnomalyLevel, tuple[str, ...]]:
    reasons: list[str] = []
    if cycle_type == CycleType.MARKET_15M:
        rvol = _num(metrics, "relative_volume")
        rvol_d = abs(_num(metrics, "relative_volume_delta"))
        ret15 = abs(_num(metrics, "return_15m_pct"))
        ret1h = abs(_num(metrics, "return_1h_pct"))
        if rvol >= 2.5: reasons.append(f"relative volume {rvol:.2f}x")
        if rvol_d >= 1.0: reasons.append(f"relative-volume delta {rvol_d:.2f}x")
        if ret15 >= 2.0: reasons.append(f"15m move {ret15:.2f}%")
        if ret1h >= 4.0: reasons.append(f"1h move {ret1h:.2f}%")
        if bool(metrics.get("breakout")) or bool(metrics.get("breakdown")): reasons.append("range structure broken")
    else:
        rvol = max(_num(metrics,"relative_volume_1m"), _num(metrics,"relative_volume_5m"))
        ret = max(abs(_num(metrics,"return_1m_5bar_pct")), abs(_num(metrics,"return_5m_5bar_pct")))
        atr = max(_num(metrics,"atr_1m_pct"), _num(metrics,"atr_5m_pct"))
        if rvol >= 2.0: reasons.append(f"relative volume {rvol:.2f}x")
        if ret >= 1.5: reasons.append(f"short move {ret:.2f}%")
        if atr >= 2.0: reasons.append(f"ATR {atr:.2f}%")
        if bool(metrics.get("breakout_5m")) or bool(metrics.get("breakdown_5m")): reasons.append("5m range structure broken")

    n = len(reasons)
    if n >= 4: return AnomalyLevel.CRITICAL, tuple(reasons)
    if n == 3: return AnomalyLevel.ANOMALOUS, tuple(reasons)
    if n == 2: return AnomalyLevel.SIGNIFICANT, tuple(reasons)
    if n == 1: return AnomalyLevel.INTERESTING, tuple(reasons)
    return AnomalyLevel.NORMAL, tuple()
