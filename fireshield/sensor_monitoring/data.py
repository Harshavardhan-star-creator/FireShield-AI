"""Reusable simulated sensor structures and scenario generation."""

from __future__ import annotations

from datetime import datetime
import random

ZONES = (
    "Production Unit",
    "Chemical Storage",
    "Electrical Room",
    "Packaging Unit",
)

SCENARIOS = (
    "Normal Conditions",
    "Rising Temperature",
    "Smoke Detection",
    "Gas Leakage",
    "Fire Emergency",
    "Sensor Failure",
)

SENSOR_LABELS = {
    "temperature": ("Temperature", "°C"),
    "smoke": ("Smoke level", "SU"),
    "gas": ("Gas concentration", "ppm"),
    "humidity": ("Humidity", "%"),
}

_BASELINES = {
    "Production Unit": {"temperature": 29.5, "smoke": 5.0, "gas": 18.0, "humidity": 48.0},
    "Chemical Storage": {"temperature": 27.0, "smoke": 4.0, "gas": 24.0, "humidity": 52.0},
    "Electrical Room": {"temperature": 31.0, "smoke": 6.0, "gas": 16.0, "humidity": 43.0},
    "Packaging Unit": {"temperature": 28.0, "smoke": 5.0, "gas": 14.0, "humidity": 49.0},
}

# Scenario changes are demo examples only and are not safety thresholds.
_SCENARIO_CHANGES = {
    "Rising Temperature": {
        "Production Unit": {"temperature": 18.0},
        "Chemical Storage": {"temperature": 9.0},
    },
    "Smoke Detection": {
        "Packaging Unit": {"smoke": 72.0},
        "Electrical Room": {"smoke": 38.0},
    },
    "Gas Leakage": {
        "Chemical Storage": {"gas": 820.0},
        "Production Unit": {"gas": 180.0},
    },
    "Fire Emergency": {
        "Electrical Room": {"temperature": 48.0, "smoke": 88.0, "gas": 230.0},
    },
}


def generate_readings(scenario: str, timestamp: datetime | None = None) -> list[dict]:
    """Create one simulated snapshot per zone in a stable, reusable structure."""
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario}")

    sampled_at = timestamp or datetime.now().astimezone()
    rng = random.Random(sampled_at.timestamp_ns() if hasattr(sampled_at, "timestamp_ns") else sampled_at.timestamp())
    changes = _SCENARIO_CHANGES.get(scenario, {})
    snapshots = []

    for zone in ZONES:
        zone_values = {}
        zone_changes = changes.get(zone, {})
        for sensor_key, baseline in _BASELINES[zone].items():
            label, unit = SENSOR_LABELS[sensor_key]
            value = round(baseline + zone_changes.get(sensor_key, 0) + rng.uniform(-1.1, 1.1), 1)
            status = "WARNING" if sensor_key in zone_changes else "ONLINE"
            if scenario == "Fire Emergency" and zone == "Electrical Room" and sensor_key in {"temperature", "smoke", "gas"}:
                status = "WARNING"
            if scenario == "Sensor Failure" and zone == "Electrical Room" and sensor_key == "smoke":
                value = None
                status = "OFFLINE"
            zone_values[sensor_key] = {
                "sensor_id": f"{zone.lower().replace(' ', '-')}-{sensor_key}",
                "label": label,
                "value": value,
                "unit": unit,
                "status": status,
            }

        snapshots.append({
            "timestamp": sampled_at,
            "zone": zone,
            "scenario": scenario,
            "readings": zone_values,
        })
    return snapshots


def flatten_snapshot(snapshots: list[dict]) -> list[dict]:
    """Convert zone snapshots to long-form records for charts and future consumers."""
    return [
        {
            "timestamp": snapshot["timestamp"],
            "zone": snapshot["zone"],
            "scenario": snapshot["scenario"],
            "sensor": sensor_key,
            "sensor_id": reading["sensor_id"],
            "value": reading["value"],
            "unit": reading["unit"],
            "status": reading["status"],
            "simulated": True,
        }
        for snapshot in snapshots
        for sensor_key, reading in snapshot["readings"].items()
    ]
