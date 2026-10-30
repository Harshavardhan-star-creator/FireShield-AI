"""Explainable, deterministic risk scoring independent of the Streamlit UI.

The default breakpoints and weights are illustrative project settings only.
They are not certified fire-safety limits, probabilities, or operational advice.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping


@dataclass(frozen=True)
class RiskConfig:
    """Configurable demo breakpoints, contribution weights, and risk bands."""

    watch_max: int = 39
    alert_max: int = 69
    temperature_caution_c: float = 35.0
    temperature_high_c: float = 70.0
    smoke_caution_su: float = 15.0
    smoke_high_su: float = 100.0
    gas_caution_ppm: float = 50.0
    gas_high_ppm: float = 1000.0
    temperature_weight: float = 25.0
    smoke_sensor_weight: float = 25.0
    gas_weight: float = 25.0
    fire_detection_weight: float = 80.0
    smoke_detection_weight: float = 50.0
    warning_sensor_points: float = 8.0

    def __post_init__(self) -> None:
        if not 0 <= self.watch_max < self.alert_max < 100:
            raise ValueError("Risk bands must satisfy 0 <= watch_max < alert_max < 100.")
        for caution, high in (
            (self.temperature_caution_c, self.temperature_high_c),
            (self.smoke_caution_su, self.smoke_high_su),
            (self.gas_caution_ppm, self.gas_high_ppm),
        ):
            if not isfinite(caution) or not isfinite(high) or high <= caution:
                raise ValueError("Each demo sensor high point must exceed its caution point.")


DEFAULT_RISK_CONFIG = RiskConfig()


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _sensor_value(snapshot: Mapping[str, Any] | None, key: str) -> tuple[float | None, str]:
    if snapshot is None:
        return None, "Sensor snapshot unavailable"
    reading = (snapshot.get("readings") or {}).get(key)
    if not isinstance(reading, Mapping):
        return None, "Reading unavailable; missing data is not treated as normal"
    value = _number(reading.get("value"))
    status = str(reading.get("status", "UNKNOWN")).upper()
    if value is None or status == "OFFLINE":
        return None, f"Reading unavailable (sensor status: {status}); not treated as normal"
    return value, status


def _sensor_factor(
    *,
    snapshot: Mapping[str, Any] | None,
    key: str,
    label: str,
    unit: str,
    caution: float,
    high: float,
    weight: float,
    config: RiskConfig,
) -> dict[str, Any]:
    value, status = _sensor_value(snapshot, key)
    if value is None:
        return {
            "key": key,
            "label": label,
            "value": None,
            "unit": unit,
            "contribution": None,
            "available": False,
            "detail": status,
        }
    severity = max(0.0, min(1.0, (value - caution) / (high - caution)))
    contribution = severity * weight
    notes = []
    if severity > 0:
        notes.append(f"above illustrative caution point {caution:g} {unit}")
    else:
        notes.append(f"below illustrative caution point {caution:g} {unit}")
    if status == "WARNING":
        contribution = min(100.0, contribution + config.warning_sensor_points)
        notes.append(f"sensor reports WARNING (+{config.warning_sensor_points:g} demo points)")
    return {
        "key": key,
        "label": label,
        "value": value,
        "unit": unit,
        "contribution": round(contribution, 2),
        "available": True,
        "detail": "; ".join(notes),
    }


def _camera_factor(
    detections: Mapping[str, Any] | None,
    class_name: str,
    label: str,
    weight: float,
) -> dict[str, Any]:
    raw_confidence = None if detections is None else detections.get(class_name)
    confidence = _number(raw_confidence)
    if confidence is None or not 0.0 <= confidence <= 1.0:
        return {
            "key": f"camera_{class_name.lower()}",
            "label": f"YOLO {label} confidence",
            "value": None,
            "unit": "confidence",
            "contribution": None,
            "available": False,
            "detail": "No current recorded model detection; absence of an event is not treated as a negative detection",
        }
    contribution = confidence * weight
    return {
        "key": f"camera_{class_name.lower()}",
        "label": f"YOLO {label} confidence",
        "value": confidence,
        "unit": "confidence",
        "contribution": round(contribution, 2),
        "available": True,
        "detail": f"Actual model event confidence {confidence:.3f} × {weight:g} demo points",
    }


def calculate_zone_risk(
    sensor_snapshot: Mapping[str, Any] | None,
    camera_detections: Mapping[str, Any] | None = None,
    config: RiskConfig = DEFAULT_RISK_CONFIG,
) -> dict[str, Any]:
    """Calculate a reproducible 0–100 risk score from one zone's available evidence.

    ``sensor_snapshot`` uses the sensor module's ``{zone, readings: {...}}``
    structure. ``camera_detections`` maps ``Fire``/``Smoke`` to actual model
    confidence values. A missing input remains explicitly unavailable.
    """
    zone = str((sensor_snapshot or {}).get("zone", "Unknown zone"))
    factors = [
        _sensor_factor(snapshot=sensor_snapshot, key="temperature", label="Temperature", unit="°C",
                       caution=config.temperature_caution_c, high=config.temperature_high_c,
                       weight=config.temperature_weight, config=config),
        _sensor_factor(snapshot=sensor_snapshot, key="smoke", label="Smoke sensor", unit="SU",
                       caution=config.smoke_caution_su, high=config.smoke_high_su,
                       weight=config.smoke_sensor_weight, config=config),
        _sensor_factor(snapshot=sensor_snapshot, key="gas", label="Gas concentration", unit="ppm",
                       caution=config.gas_caution_ppm, high=config.gas_high_ppm,
                       weight=config.gas_weight, config=config),
        _camera_factor(camera_detections, "Fire", "Fire", config.fire_detection_weight),
        _camera_factor(camera_detections, "Smoke", "Smoke", config.smoke_detection_weight),
    ]
    available = [factor for factor in factors if factor["available"]]
    missing = [factor["label"] for factor in factors if not factor["available"]]
    if not available:
        return {
            "zone": zone,
            "score": None,
            "level": "UNAVAILABLE",
            "complete": False,
            "missing_evidence": missing,
            "factors": factors,
            "reason": "Risk cannot be scored: no sensor readings or camera detections are available. Missing evidence is unknown, not normal.",
        }

    # Expose whole-number scores so the displayed score and the 0–39/40–69/70–100
    # bands use the same boundaries.
    score = int(round(min(100.0, sum(factor["contribution"] or 0.0 for factor in available))))
    if score <= config.watch_max:
        level = "WATCH"
    elif score <= config.alert_max:
        level = "ALERT"
    else:
        level = "ACT"

    contributors = [
        f"{factor['label']} (+{factor['contribution']:g})"
        for factor in available
        if factor["contribution"] and factor["contribution"] > 0
    ]
    if contributors:
        reason = f"{level}: score {score:g}/100 from " + ", ".join(contributors) + "."
    else:
        reason = f"{level}: no available evidence crossed the configured illustrative caution points (score {score}/100)."
    if missing:
        reason += " Incomplete evidence: " + ", ".join(missing) + "; this score is not an all-clear."

    return {
        "zone": zone,
        "score": score,
        "level": level,
        "complete": not missing,
        "missing_evidence": missing,
        "factors": factors,
        "reason": reason,
    }


def calculate_facility_risk(
    sensor_snapshots: list[Mapping[str, Any]],
    camera_by_zone: Mapping[str, Mapping[str, Any] | None] | None = None,
    config: RiskConfig = DEFAULT_RISK_CONFIG,
) -> list[dict[str, Any]]:
    """Calculate zone risks from sensor snapshots and per-zone camera evidence."""
    camera_by_zone = camera_by_zone or {}
    return [
        calculate_zone_risk(
            snapshot,
            camera_by_zone.get(str(snapshot.get("zone"))),
            config,
        )
        for snapshot in sensor_snapshots
    ]
