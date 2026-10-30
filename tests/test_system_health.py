"""Status assessment tests use explicit component inputs and no hardware."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fireshield.sensor_monitoring.data import ZONES
from fireshield.system_health import (
    NOT_CONFIGURED,
    OFFLINE,
    ONLINE,
    WARNING,
    collect_system_health,
)


NOW = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


def readings(*, timestamp=NOW, simulated=True, unavailable_sensor=None):
    rows = []
    for zone in ZONES:
        for sensor in ("temperature", "smoke", "gas"):
            unavailable = unavailable_sensor == (zone, sensor)
            rows.append({
                "zone": zone,
                "sensor": sensor,
                "timestamp": timestamp,
                "value": None if unavailable else 25.0,
                "status": "OFFLINE" if unavailable else "ONLINE",
                "simulated": simulated,
            })
    return rows


def component(result, name):
    return next(row for row in result["components"] if row["name"] == name)


class SystemHealthTests(unittest.TestCase):
    def test_simulated_sensor_readings_are_warning_not_hardware_online(self):
        result = collect_system_health(
            sensor_history=readings(), database_check=lambda: True,
            database_path="existing.db", risk_engine_ready=True,
            decision_engine_ready=True, suppression_controller_ready=True,
            now=NOW,
        )
        for name in ("Temperature sensor readings", "Smoke sensor readings", "Gas sensor readings"):
            item = component(result, name)
            self.assertEqual(item["status"], WARNING)
            self.assertIn("simulated", item["detail"])

    def test_missing_camera_and_model_are_not_configured(self):
        with tempfile.TemporaryDirectory() as directory:
            result = collect_system_health(
                camera_capture_available=False,
                model_path=Path(directory) / "missing.pt",
                database_path=Path(directory) / "missing.db",
                risk_engine_ready=True, decision_engine_ready=True,
                suppression_controller_ready=True, now=NOW,
            )
        self.assertEqual(component(result, "Camera input")["status"], NOT_CONFIGURED)
        self.assertEqual(component(result, "YOLO fire/smoke model")["status"], NOT_CONFIGURED)
        self.assertEqual(component(result, "SQLite database")["status"], NOT_CONFIGURED)

    def test_browser_capture_does_not_claim_live_camera_connectivity(self):
        result = collect_system_health(
            camera_capture_available=True,
            database_path="missing.db", database_check=lambda: True, now=NOW,
        )
        camera = component(result, "Camera input")
        self.assertEqual(camera["status"], WARNING)
        self.assertIn("continuous camera", camera["detail"])

    def test_missing_ultralytics_dependency_is_offline_when_weights_exist(self):
        with tempfile.TemporaryDirectory() as directory:
            weights = Path(directory) / "fire.pt"
            weights.write_bytes(b"test placeholder")
            with patch("fireshield.system_health.importlib.util.find_spec", return_value=None):
                result = collect_system_health(
                    model_path=weights, database_path=Path(directory) / "db.db", now=NOW,
                )
        self.assertEqual(component(result, "YOLO fire/smoke model")["status"], OFFLINE)

    def test_stale_sensor_readings_raise_warning(self):
        old = NOW - timedelta(seconds=120)
        result = collect_system_health(
            sensor_history=readings(timestamp=old),
            database_check=lambda: True, database_path="db.db", now=NOW,
            risk_engine_ready=True, decision_engine_ready=True,
            suppression_controller_ready=True,
        )
        for name in ("Temperature sensor readings", "Smoke sensor readings", "Gas sensor readings"):
            self.assertEqual(component(result, name)["status"], WARNING)
            self.assertIn("stale", component(result, name)["detail"])

    def test_partial_sensor_failure_is_warning(self):
        result = collect_system_health(
            sensor_history=readings(unavailable_sensor=(ZONES[0], "smoke")),
            database_check=lambda: True, database_path="db.db", now=NOW,
        )
        self.assertEqual(component(result, "Smoke sensor readings")["status"], WARNING)

    def test_database_connection_failure_is_offline_without_crashing(self):
        def fail():
            raise OSError("database locked")

        result = collect_system_health(database_check=fail, database_path="db.db", now=NOW)
        self.assertEqual(component(result, "SQLite database")["status"], OFFLINE)
        self.assertEqual(result["overall_status"], OFFLINE)

    def test_module_initialization_failures_are_offline(self):
        result = collect_system_health(
            database_check=lambda: True, database_path="db.db", now=NOW,
            risk_engine_ready=False, decision_engine_ready=False,
            suppression_controller_ready=False,
        )
        self.assertEqual(component(result, "Risk prediction engine")["status"], OFFLINE)
        self.assertEqual(component(result, "Decision engine")["status"], OFFLINE)
        self.assertEqual(component(result, "Virtual suppression controller")["status"], OFFLINE)

    def test_overall_health_aggregates_component_statuses(self):
        result = collect_system_health(
            sensor_history=readings(), database_check=lambda: True,
            database_path="db.db", risk_engine_ready=True,
            decision_engine_ready=True, suppression_controller_ready=True,
            now=NOW,
        )
        self.assertEqual(result["overall_status"], WARNING)
        self.assertEqual(len(result["components"]), 9)


if __name__ == "__main__":
    unittest.main()
