"""Deterministic cross-module workflow checks; sensor scenario inputs are simulated."""

from datetime import datetime, timedelta, timezone
import unittest

from fireshield.decision_engine import DecisionConfig, DecisionEngine
from fireshield.risk_prediction.engine import calculate_zone_risk
from fireshield.sensor_monitoring.data import SCENARIOS, ZONES, flatten_snapshot, generate_readings
from fireshield.risk_prediction.adapters import latest_sensor_snapshots
from fireshield.suppression_control import ACTIVATED, ARMED, STANDBY, VirtualSuppressionController


START = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)


def evidence(at):
    return [
        {
            "source": "test temperature source", "source_group": "sensor:temperature",
            "kind": "sensor", "observed_at": at, "reliable": True,
            "simulated": False, "supports_risk": True, "value": 80.0,
        },
        {
            "source": "test camera source", "source_group": "camera",
            "kind": "camera", "observed_at": at, "reliable": True,
            "simulated": False, "supports_risk": True, "confidence": 0.95,
        },
    ]


class WorkflowIntegrationTests(unittest.TestCase):
    def test_all_sensor_scenarios_reach_risk_calculation_as_simulated_data(self):
        generated = {}
        for scenario in SCENARIOS:
            snapshots = generate_readings(scenario, START)
            generated[scenario] = snapshots
            flattened = flatten_snapshot(snapshots)
            rebuilt = latest_sensor_snapshots(flattened, ZONES)
            self.assertEqual(len(rebuilt), len(ZONES))
            self.assertTrue(all(item["simulated"] for snap in rebuilt for item in snap["readings"].values()))
            for snapshot in rebuilt:
                result = calculate_zone_risk(snapshot, None)
                if result["score"] is not None:
                    self.assertTrue(0 <= result["score"] <= 100)
                    self.assertIn(result["level"], {"WATCH", "ALERT", "ACT"})
        self.assertGreater(generated["Rising Temperature"][0]["readings"]["temperature"]["value"], 40)
        self.assertGreater(generated["Gas Leakage"][1]["readings"]["gas"]["value"], 800)
        self.assertGreater(generated["Smoke Detection"][3]["readings"]["smoke"]["value"], 70)
        failed = generated["Sensor Failure"][2]["readings"]["smoke"]
        self.assertIsNone(failed["value"])
        self.assertEqual(failed["status"], "OFFLINE")

    def test_gradually_increasing_simulated_temperature_does_not_reduce_risk(self):
        scores = []
        for temperature in (32.0, 42.0, 52.0, 62.0, 72.0):
            snapshot = {
                "zone": "Production Unit",
                "readings": {
                    "temperature": {"value": temperature, "unit": "°C", "status": "WARNING", "simulated": True},
                    "smoke": {"value": 8.0, "unit": "SU", "status": "ONLINE", "simulated": True},
                    "gas": {"value": 20.0, "unit": "ppm", "status": "ONLINE", "simulated": True},
                },
            }
            scores.append(calculate_zone_risk(snapshot, None)["score"])
        self.assertEqual(scores, sorted(scores))
        self.assertGreater(scores[-1], scores[0])

    def test_missing_evidence_is_not_an_all_clear_and_cannot_activate(self):
        snapshot = {
            "zone": "Production Unit",
            "readings": {
                "temperature": {"value": 28.0, "unit": "°C", "status": "ONLINE", "simulated": True},
                "smoke": {"value": None, "unit": "SU", "status": "OFFLINE", "simulated": True},
                "gas": {"value": 14.0, "unit": "ppm", "status": "ONLINE", "simulated": True},
            },
        }
        risk = calculate_zone_risk(snapshot, None)
        decision = DecisionEngine().evaluate(risk, [], now=START, observed_at=START)
        suppression = VirtualSuppressionController().update(decision, now=START)
        self.assertFalse(risk["complete"])
        missing = " ".join(risk["missing_evidence"]).lower()
        self.assertIn("yolo fire", missing)
        self.assertIn("smoke sensor", missing)
        self.assertNotEqual(decision["decision"], "ACT")
        self.assertFalse(decision["activation_authorized"])
        self.assertNotEqual(suppression["status"], ACTIVATED)
        if decision["decision"] == "WATCH":
            self.assertIn("not an all-clear", " ".join(decision["reasons"]))

    def test_decision_authorization_flows_to_virtual_suppression_and_cancel(self):
        engine = DecisionEngine(DecisionConfig(confirmation_duration_seconds=2, evidence_freshness_seconds=10))
        controller = VirtualSuppressionController()
        risk = {"zone": "Production Unit", "score": 22, "level": "WATCH", "complete": True}
        decision = engine.evaluate(risk, [], now=START, observed_at=START)
        self.assertEqual(controller.update(decision, now=START)["status"], STANDBY)

        risk.update(score=55, level="ALERT")
        decision = engine.evaluate(risk, [], now=START + timedelta(seconds=1), observed_at=START + timedelta(seconds=1))
        self.assertEqual(decision["decision"], "ALERT")
        self.assertEqual(controller.update(decision)["status"], ARMED)

        risk.update(score=90, level="ACT")
        for seconds in (0, 1):
            at = START + timedelta(seconds=2 + seconds)
            decision = engine.evaluate(risk, evidence(at), now=at, observed_at=at)
            self.assertFalse(decision["activation_authorized"])
        act_at = START + timedelta(seconds=4)
        decision = engine.evaluate(risk, evidence(act_at), now=act_at, observed_at=act_at)
        self.assertEqual(decision["decision"], "ACT")
        self.assertTrue(decision["activation_authorized"])
        self.assertEqual(controller.update(decision, now=act_at)["status"], ACTIVATED)

        cancelled = controller.cancel("Production Unit", decision, now=act_at + timedelta(seconds=1))
        self.assertEqual(cancelled["status"], STANDBY)
        self.assertEqual(controller.update(decision)["status"], STANDBY)
        self.assertFalse(cancelled["authorized"])


if __name__ == "__main__":
    unittest.main()
