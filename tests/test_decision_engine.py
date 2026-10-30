"""Decision policy tests use explicit inputs; no live readings are generated."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from fireshield.decision_engine import DecisionConfig, DecisionEngine


START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def risk(level="ACT", score=85, complete=True):
    return {
        "zone": "Production Unit",
        "score": score,
        "level": level,
        "complete": complete,
        "factors": [],
    }


def evidence(at=START, *, include_camera=True, simulated=False):
    records = [{
        "source": "Temperature sensor",
        "source_group": "sensor:temperature",
        "kind": "sensor",
        "observed_at": at,
        "reliable": not simulated,
        "simulated": simulated,
        "supports_risk": True,
        "value": 68.0,
    }]
    if include_camera:
        records.append({
            "source": "Camera Fire detection",
            "source_group": "camera",
            "kind": "camera",
            "observed_at": at,
            "reliable": True,
            "simulated": False,
            "supports_risk": True,
            "confidence": 0.91,
        })
    return records


class DecisionEngineTests(unittest.TestCase):
    def test_watch_monitors_and_records_current_state(self):
        engine = DecisionEngine()
        result = engine.evaluate(risk("WATCH", 12, False), now=START, observed_at=START)
        self.assertEqual(result["decision"], "WATCH")
        self.assertIn("continue collecting", result["action"])
        self.assertEqual(engine.history[0]["decision"], "WATCH")

    def test_alert_creates_high_priority_notification_and_virtual_prep(self):
        result = DecisionEngine().evaluate(risk("ALERT", 54), now=START, observed_at=START)
        self.assertEqual(result["decision"], "ALERT")
        self.assertEqual(result["notification"]["priority"], "HIGH")
        self.assertEqual(result["notification"]["zone"], "Production Unit")
        self.assertFalse(result["virtual_suppression"]["activated"])
        self.assertFalse(result["virtual_suppression"]["hardware_control"])

    def test_act_requires_complete_independent_and_sustained_evidence(self):
        engine = DecisionEngine(DecisionConfig(confirmation_duration_seconds=20, evidence_freshness_seconds=60))
        result = engine.evaluate(risk(), evidence(), now=START, observed_at=START)
        self.assertEqual(result["decision"], "ALERT")
        for seconds in (10, 20):
            at = START + timedelta(seconds=seconds)
            result = engine.evaluate(risk(), evidence(at), now=at, observed_at=at)
        self.assertEqual(result["decision"], "ACT")
        self.assertEqual(set(result["supporting_sources"]), {"camera", "sensor:temperature"})
        self.assertTrue(result["activation_authorized"])
        self.assertFalse(result["virtual_suppression"]["activated"])

    def test_insufficient_independent_sources_remains_alert(self):
        engine = DecisionEngine(DecisionConfig(confirmation_duration_seconds=1))
        result = engine.evaluate(
            risk(), evidence(include_camera=False), now=START, observed_at=START
        )
        self.assertEqual(result["decision"], "ALERT")
        self.assertFalse(result["act_eligible"])
        self.assertFalse(result["activation_authorized"])
        self.assertTrue(any("independent reliable" in reason for reason in result["reasons"]))

    def test_incomplete_or_simulated_evidence_cannot_qualify_act(self):
        result = DecisionEngine().evaluate(
            risk(complete=False), evidence(simulated=True), now=START, observed_at=START
        )
        self.assertEqual(result["decision"], "ALERT")
        self.assertFalse(result["evidence_complete"])
        self.assertFalse(result["act_eligible"])

    def test_stale_evidence_resets_confirmation(self):
        engine = DecisionEngine(DecisionConfig(confirmation_duration_seconds=20, evidence_freshness_seconds=10))
        result = engine.evaluate(risk(), evidence(), now=START, observed_at=START)
        self.assertEqual(result["decision"], "ALERT")
        later = START + timedelta(seconds=30)
        result = engine.evaluate(
            risk(), evidence(START), now=later, observed_at=later
        )
        self.assertEqual(result["decision"], "ALERT")
        self.assertFalse(result["act_eligible"])

    def test_operator_can_cancel_act_and_history_marks_override(self):
        config = DecisionConfig(confirmation_duration_seconds=1, evidence_freshness_seconds=60)
        engine = DecisionEngine(config)
        auto = engine.evaluate(risk(), evidence(), now=START, observed_at=START)
        at_act = START + timedelta(seconds=1)
        auto = engine.evaluate(risk(), evidence(at_act), now=at_act, observed_at=at_act)
        self.assertEqual(auto["decision"], "ACT")
        cancel_at = START + timedelta(seconds=2)
        cancelled = engine.evaluate(
            risk(), evidence(cancel_at), now=cancel_at,
            observed_at=cancel_at, operator_override="HOLD_ALERT",
        )
        self.assertEqual(cancelled["decision"], "ALERT")
        self.assertEqual(cancelled["decision_source"], "OPERATOR_OVERRIDE")
        self.assertTrue(cancelled["operator_hold"])
        self.assertEqual(engine.history[-1]["decision_source"], "OPERATOR_OVERRIDE")
        self.assertFalse(cancelled["virtual_suppression"]["hardware_control"])


if __name__ == "__main__":
    unittest.main()
