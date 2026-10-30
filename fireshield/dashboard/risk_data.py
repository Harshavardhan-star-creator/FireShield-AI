"""Join existing sensor/camera session data to the independent risk engine."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fireshield.risk_prediction.adapters import (
    camera_evidence_by_zone,
    decision_evidence_by_zone,
    latest_sensor_snapshots,
)
from fireshield.risk_prediction.engine import calculate_facility_risk
from fireshield.sensor_monitoring.data import ZONES, generate_readings


def get_dashboard_risk_data(
    sensor_history: list[dict[str, Any]] | None,
    camera_history: list[dict[str, Any]] | None,
    now: datetime | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return sensor-backed dashboard rows and their rule-based risk details.

    If the Sensor Monitoring page has not yet produced session history, use its
    own simulated ``Normal Conditions`` generator as the clearly labelled
    dashboard input. Once history exists, missing zones/sensors remain missing.
    """
    timestamp = now or datetime.now().astimezone()
    snapshots = latest_sensor_snapshots(sensor_history or [], ZONES)
    if not sensor_history:
        snapshots = generate_readings("Normal Conditions", timestamp)
        for snapshot in snapshots:
            snapshot["timestamp"] = timestamp
            for reading in snapshot["readings"].values():
                reading["timestamp"] = timestamp
                reading["simulated"] = True
    snapshots_by_zone = {snapshot["zone"]: snapshot for snapshot in snapshots}
    ordered_snapshots = [
        snapshots_by_zone.get(zone, {"zone": zone, "readings": {}, "scenario": None})
        for zone in ZONES
    ]
    camera_evidence = camera_evidence_by_zone(camera_history or [], ZONES, timestamp)
    risks = calculate_facility_risk(ordered_snapshots, camera_evidence)
    decision_evidence, observation_times = decision_evidence_by_zone(
        ordered_snapshots, risks, camera_history or [], timestamp
    )

    rows = []
    for snapshot, risk in zip(ordered_snapshots, risks):
        readings = snapshot.get("readings", {})
        rows.append({
            "zone": snapshot["zone"],
            "temperature": _value(readings.get("temperature")),
            "smoke": _value(readings.get("smoke")),
            "gas": _value(readings.get("gas")),
            "humidity": _value(readings.get("humidity")),
            "risk": risk["score"],
            "risk_level": risk["level"],
            "risk_complete": risk["complete"],
            "risk_reason": risk["reason"],
            "risk_factors": risk["factors"],
            "missing_evidence": risk["missing_evidence"],
            "scenario": snapshot.get("scenario"),
            "decision_evidence": decision_evidence.get(snapshot["zone"], []),
            "observed_at": observation_times.get(snapshot["zone"]),
        })
    return rows, risks


def _value(reading: dict[str, Any] | None) -> float | None:
    if not reading or reading.get("value") is None:
        return None
    try:
        return float(reading["value"])
    except (TypeError, ValueError):
        return None
