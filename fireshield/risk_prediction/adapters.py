"""Adapters from existing sensor and camera session interfaces to risk inputs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable


def latest_sensor_snapshots(
    history: Iterable[dict[str, Any]], zones: Iterable[str]
) -> list[dict[str, Any]]:
    """Rebuild zone snapshots from the sensor module's flattened history records."""
    latest: dict[str, dict[str, dict[str, Any]]] = {zone: {} for zone in zones}
    seen: set[str] = set()
    for record in history:
        zone = str(record.get("zone", ""))
        sensor = str(record.get("sensor", ""))
        if zone not in latest or not sensor:
            continue
        seen.add(zone)
        previous = latest[zone].get(sensor)
        timestamp = record.get("timestamp")
        if previous is None or _timestamp_key(timestamp) >= _timestamp_key(previous.get("timestamp")):
            latest[zone][sensor] = record

    snapshots = []
    for zone in zones:
        if zone not in seen:
            continue
        readings = {}
        for sensor, record in latest[zone].items():
            readings[sensor] = {
                "sensor_id": record.get("sensor_id", f"{zone}-{sensor}"),
                "label": record.get("label", sensor.replace("_", " ").title()),
                "value": record.get("value"),
                "unit": record.get("unit", ""),
                "status": record.get("status", "UNKNOWN"),
                "timestamp": record.get("timestamp"),
                # Current sensor module's history explicitly marks its readings simulated.
                "simulated": record.get("simulated", True),
            }
        latest_timestamp = max(
            (record.get("timestamp") for record in latest[zone].values()),
            key=_timestamp_key,
            default=None,
        )
        snapshots.append({
            "zone": zone,
            "timestamp": latest_timestamp,
            "scenario": latest[zone][next(iter(latest[zone]))].get("scenario") if latest[zone] else None,
            "readings": readings,
        })
    return snapshots


def _timestamp_key(value: Any) -> float:
    if value is None:
        return float("-inf")
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        return parsed.timestamp()
    except (TypeError, ValueError, OverflowError, OSError):
        return float("-inf")


def camera_evidence_by_zone(
    events: Iterable[dict[str, Any]],
    zones: Iterable[str],
    now: datetime | None = None,
    max_age_minutes: float = 15.0,
) -> dict[str, dict[str, float] | None]:
    """Extract recent positive detections from camera event history.

    The current camera contract records positive model detections only. No event
    therefore means unavailable evidence, not a confirmed negative observation.
    Stale events are ignored.
    """
    if max_age_minutes < 0:
        raise ValueError("max_age_minutes cannot be negative.")
    reference = now or datetime.now().astimezone()
    reference_ts = reference.timestamp()
    evidence: dict[str, dict[str, float] | None] = {zone: None for zone in zones}
    for event in events:
        zone = str(event.get("zone", ""))
        if zone not in evidence or event.get("origin") != "camera_model_inference":
            continue
        age_seconds = reference_ts - _timestamp_key(event.get("timestamp"))
        if age_seconds < 0 or age_seconds > max_age_minutes * 60:
            continue
        class_name = str(event.get("detection_class", "")).strip().lower()
        normalized = "Fire" if class_name in {"fire", "flame"} else "Smoke" if class_name == "smoke" else None
        try:
            confidence = float(event.get("confidence"))
        except (TypeError, ValueError):
            continue
        if normalized is None or not 0.0 <= confidence <= 1.0:
            continue
        if evidence[zone] is None:
            evidence[zone] = {}
        evidence[zone][normalized] = max(confidence, evidence[zone].get(normalized, 0.0))
    return evidence


def decision_evidence_by_zone(
    snapshots: Iterable[dict[str, Any]],
    risk_results: Iterable[dict[str, Any]],
    camera_events: Iterable[dict[str, Any]],
    now: datetime | None = None,
    max_age_seconds: float = 45.0,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, datetime | None]]:
    """Build time-stamped evidence items for the decision confirmation policy."""
    reference = now or datetime.now().astimezone()
    reference_ts = reference.timestamp()
    snapshots_by_zone = {item["zone"]: item for item in snapshots}
    risks_by_zone = {item["zone"]: item for item in risk_results}
    evidence: dict[str, list[dict[str, Any]]] = {zone: [] for zone in snapshots_by_zone}
    observation_times: dict[str, datetime | None] = {
        zone: _datetime_or_none(snapshot.get("timestamp"))
        for zone, snapshot in snapshots_by_zone.items()
    }

    for zone, snapshot in snapshots_by_zone.items():
        factors = {item["key"]: item for item in risks_by_zone.get(zone, {}).get("factors", [])}
        for sensor_key in ("temperature", "smoke", "gas"):
            reading = snapshot.get("readings", {}).get(sensor_key)
            factor = factors.get(sensor_key, {})
            if not isinstance(reading, dict) or reading.get("value") is None:
                continue
            status = str(reading.get("status", "UNKNOWN")).upper()
            evidence[zone].append({
                "source": f"{sensor_key.title()} sensor",
                "source_group": f"sensor:{sensor_key}",
                "kind": "sensor",
                "observed_at": reading.get("timestamp"),
                "reliable": status in {"ONLINE", "WARNING"},
                "simulated": reading.get("simulated") is True,
                "supports_risk": bool(factor.get("contribution") and factor["contribution"] > 0),
                "value": reading.get("value"),
            })

    for event in camera_events:
        zone = str(event.get("zone", ""))
        if zone not in evidence or event.get("origin") != "camera_model_inference":
            continue
        observed = _datetime_or_none(event.get("timestamp"))
        if observed is None:
            continue
        age = reference_ts - observed.timestamp()
        if age < 0 or age > max_age_seconds:
            continue
        class_name = str(event.get("detection_class", "")).strip().lower()
        factor_key = "camera_fire" if class_name in {"fire", "flame"} else "camera_smoke" if class_name == "smoke" else None
        if factor_key is None:
            continue
        factor = next(
            (item for item in risks_by_zone.get(zone, {}).get("factors", []) if item["key"] == factor_key),
            {},
        )
        try:
            confidence = float(event.get("confidence"))
        except (TypeError, ValueError):
            continue
        evidence[zone].append({
            "source": f"Camera {class_name.title()} detection",
            "source_group": "camera",
            "kind": "camera",
            "observed_at": observed,
            "reliable": True,
            "simulated": event.get("simulated") is True,
            "supports_risk": bool(factor.get("contribution") and factor["contribution"] > 0),
            "confidence": confidence,
            "event_id": event.get("event_id"),
        })
        previous = observation_times.get(zone)
        if previous is None or observed.timestamp() > previous.timestamp():
            observation_times[zone] = observed
    return evidence, observation_times


def _datetime_or_none(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed.astimezone() if parsed.tzinfo is not None else parsed.astimezone()
