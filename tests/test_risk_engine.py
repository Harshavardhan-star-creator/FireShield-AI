"""Focused tests for rule-based risk scores and missing-evidence behavior."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from fireshield.risk_prediction.adapters import camera_evidence_by_zone, latest_sensor_snapshots
from fireshield.risk_prediction.engine import RiskConfig, calculate_zone_risk


def snapshot(temperature=25, smoke=5, gas=10, smoke_status="ONLINE"):
    values = {
        "temperature": (temperature, "°C", "ONLINE"),
        "smoke": (smoke, "SU", smoke_status),
        "gas": (gas, "ppm", "ONLINE"),
    }
    return {
        "zone": "Production Unit",
        "readings": {
            key: {"value": value, "unit": unit, "status": status}
            for key, (value, unit, status) in values.items()
        },
    }


class RiskEngineTests(unittest.TestCase):
    def test_normal_conditions_are_deterministic_watch(self):
        result = calculate_zone_risk(snapshot())
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["level"], "WATCH")
        self.assertFalse(result["complete"])

    def test_rising_temperature_contributes(self):
        result = calculate_zone_risk(snapshot(temperature=60))
        factor = next(item for item in result["factors"] if item["key"] == "temperature")
        self.assertGreater(factor["contribution"], 0)

    def test_smoke_sensor_contributes(self):
        result = calculate_zone_risk(snapshot(smoke=80))
        factor = next(item for item in result["factors"] if item["key"] == "smoke")
        self.assertGreater(factor["contribution"], 0)

    def test_gas_leakage_contributes(self):
        result = calculate_zone_risk(snapshot(gas=800))
        factor = next(item for item in result["factors"] if item["key"] == "gas")
        self.assertGreater(factor["contribution"], 0)

    def test_fire_detection_can_reach_act(self):
        result = calculate_zone_risk(snapshot(), {"Fire": 0.95})
        self.assertEqual(result["level"], "ACT")
        self.assertEqual(result["score"], 76.0)

    def test_smoke_detection_contributes_to_risk(self):
        result = calculate_zone_risk(snapshot(), {"Smoke": 0.9})
        self.assertEqual(result["level"], "ALERT")
        self.assertEqual(result["score"], 45.0)

    def test_multiple_warning_signals_combine_and_cap(self):
        result = calculate_zone_risk(
            snapshot(temperature=70, smoke=100, gas=1000, smoke_status="WARNING"),
            {"Fire": 0.99, "Smoke": 0.99},
        )
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["level"], "ACT")

    def test_missing_sensor_and_camera_are_not_treated_as_normal(self):
        data = snapshot(temperature=50, smoke=None, gas=None, smoke_status="OFFLINE")
        data["readings"]["gas"]["status"] = "OFFLINE"
        result = calculate_zone_risk(data, None)
        self.assertEqual(result["score"], 11)
        self.assertFalse(result["complete"])
        self.assertIn("Smoke sensor", result["missing_evidence"])
        self.assertIn("YOLO Fire confidence", result["missing_evidence"])
        self.assertIn("not an all-clear", result["reason"])

    def test_no_available_evidence_has_no_score(self):
        result = calculate_zone_risk(None, None)
        self.assertIsNone(result["score"])
        self.assertEqual(result["level"], "UNAVAILABLE")

    def test_risk_bands_are_configurable(self):
        config = RiskConfig(watch_max=10, alert_max=50)
        result = calculate_zone_risk(snapshot(temperature=70), config=config)
        self.assertEqual(result["level"], "ALERT")


class ExistingInterfaceAdapterTests(unittest.TestCase):
    def test_latest_sensor_history_rebuilds_sensor_snapshot(self):
        now = datetime.now(timezone.utc)
        rows = [
            {"timestamp": now - timedelta(seconds=10), "zone": "Production Unit", "sensor": "temperature", "value": 30, "unit": "°C", "status": "ONLINE"},
            {"timestamp": now, "zone": "Production Unit", "sensor": "temperature", "value": 41, "unit": "°C", "status": "WARNING"},
        ]
        rebuilt = latest_sensor_snapshots(rows, ["Production Unit"])
        self.assertEqual(rebuilt[0]["readings"]["temperature"]["value"], 41)
        self.assertEqual(rebuilt[0]["readings"]["temperature"]["status"], "WARNING")

    def test_camera_adapter_uses_only_fresh_actual_events(self):
        now = datetime.now(timezone.utc)
        event = {
            "timestamp": now,
            "zone": "Production Unit",
            "detection_class": "Flame",
            "confidence": 0.82,
            "origin": "camera_model_inference",
        }
        result = camera_evidence_by_zone([event], ["Production Unit"], now)
        self.assertEqual(result["Production Unit"], {"Fire": 0.82})
        stale = camera_evidence_by_zone([event], ["Production Unit"], now + timedelta(hours=1))
        self.assertIsNone(stale["Production Unit"])


if __name__ == "__main__":
    unittest.main()
