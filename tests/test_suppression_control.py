"""Tests for virtual suppression transitions without hardware side effects."""

from datetime import datetime, timedelta, timezone
import unittest

from fireshield.suppression_control import (
    ACTIVATED,
    ARMED,
    STANDBY,
    VirtualSuppressionController,
)


START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def decision(zone="Production Unit", state="WATCH", **overrides):
    result = {
        "zone": zone,
        "decision": state,
        "timestamp": START,
        "decision_source": "AUTOMATIC",
        "evidence_complete": True,
        "act_eligible": state == "ACT",
        "activation_authorized": state == "ACT",
        "operator_hold": False,
        "evidence": [{"source": "test sensor", "supports_risk": True}],
    }
    result.update(overrides)
    return result


class VirtualSuppressionTests(unittest.TestCase):
    def test_watch_maps_to_standby(self):
        controller = VirtualSuppressionController()
        self.assertEqual(controller.update(decision("A", "WATCH"))["status"], STANDBY)

    def test_alert_maps_to_armed(self):
        controller = VirtualSuppressionController()
        self.assertEqual(controller.update(decision("A", "ALERT"))["status"], ARMED)

    def test_authorized_act_activates_and_records_timestamp(self):
        controller = VirtualSuppressionController()
        at = START + timedelta(seconds=1)
        result = controller.update(decision("A", "ACT", timestamp=at), now=at)
        self.assertEqual(result["status"], ACTIVATED)
        self.assertEqual(result["activation_timestamp"], at)
        self.assertTrue(result["virtual_only"])
        self.assertEqual(controller.event_history[-1]["status"], ACTIVATED)

    def test_act_without_explicit_authorization_is_denied(self):
        controller = VirtualSuppressionController()
        result = controller.update(decision("A", "ACT", activation_authorized=False))
        self.assertEqual(result["status"], ARMED)
        self.assertFalse(result["authorized"])
        self.assertEqual(result["operator_override_status"], "AUTHORIZATION DENIED")

    def test_risk_score_alone_cannot_authorize(self):
        controller = VirtualSuppressionController()
        result = controller.update({"zone": "A", "score": 100, "level": "ACT"})
        self.assertNotEqual(result["status"], ACTIVATED)

    def test_missing_evidence_blocks_act(self):
        controller = VirtualSuppressionController()
        result = controller.update(decision("A", "ACT", evidence_complete=False))
        self.assertEqual(result["status"], ARMED)

    def test_unavailable_decision_does_not_activate(self):
        controller = VirtualSuppressionController()
        result = controller.update(None)
        self.assertEqual(result["status"], ARMED)
        self.assertEqual(result["operator_override_status"], "REVIEW REQUIRED")

    def test_operator_cancellation_immediately_standby_and_is_latched(self):
        controller = VirtualSuppressionController()
        act = decision("A", "ACT")
        controller.update(act)
        cancelled = controller.cancel("A", act, now=START + timedelta(seconds=2))
        self.assertEqual(cancelled["status"], STANDBY)
        self.assertEqual(cancelled["operator_override_status"], "CANCELLED — OPERATOR")
        self.assertEqual(controller.update(act)["status"], STANDBY)
        controller.release_cancellation("A")
        self.assertEqual(controller.update(act)["status"], ACTIVATED)

    def test_zone_states_are_independent(self):
        controller = VirtualSuppressionController()
        controller.update(decision("Production", "ACT"))
        controller.update(decision("Chemical", "ALERT"))
        controller.update(decision("Electrical", "WATCH"))
        controller.update(decision("Packaging", "ALERT"))
        states = {item["zone"]: item["status"] for item in controller.states()}
        self.assertEqual(states, {
            "Production": ACTIVATED,
            "Chemical": ARMED,
            "Electrical": STANDBY,
            "Packaging": ARMED,
        })

    def test_act_from_operator_override_cannot_activate(self):
        controller = VirtualSuppressionController()
        result = controller.update(decision("A", "ACT", decision_source="OPERATOR_OVERRIDE"))
        self.assertEqual(result["status"], ARMED)


if __name__ == "__main__":
    unittest.main()
