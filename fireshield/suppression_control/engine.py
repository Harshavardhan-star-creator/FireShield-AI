"""Session-local virtual suppression state machine; contains no hardware control."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


STANDBY = "STANDBY"
ARMED = "ARMED"
ACTIVATED = "ACTIVATED"
VALID_DECISIONS = {"WATCH", "ALERT", "ACT"}


def _timestamp(value: datetime | None) -> datetime:
    current = value or datetime.now().astimezone()
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current


class VirtualSuppressionController:
    """Manage independent virtual states for zones, never issue actuator commands.

    An ACT transition requires an explicit ``activation_authorized`` flag from
    the decision engine plus its eligibility and evidence-completeness checks.
    Operator cancellation is latched until explicitly released.
    """

    def __init__(self) -> None:
        self._zones: dict[str, dict[str, Any]] = {}
        self._cancelled: set[str] = set()
        self.event_history: list[dict[str, Any]] = []

    def get_state(self, zone: str) -> dict[str, Any]:
        return dict(self._zones.get(zone, self._initial(zone)))

    def states(self) -> list[dict[str, Any]]:
        return [dict(state) for state in self._zones.values()]

    def update(
        self,
        decision_result: Mapping[str, Any] | None,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Apply a decision result; missing/invalid decisions fail safe to ARMED."""
        result = decision_result or {}
        zone = str(result.get("zone") or "Unknown zone")
        current = _timestamp(now or result.get("timestamp"))
        old = self._zones.get(zone, self._initial(zone))
        decision = str(result.get("decision", "UNAVAILABLE")).upper()
        authorized = (
            decision == "ACT"
            and result.get("activation_authorized") is True
            and result.get("act_eligible") is True
            and result.get("evidence_complete") is True
            and result.get("decision_source") == "AUTOMATIC"
            and result.get("operator_hold") is not True
        )

        if zone in self._cancelled:
            state = STANDBY
            reason = "Operator cancellation is active; virtual suppression remains in standby."
            override = "CANCELLED — HOLD ACTIVE"
        elif decision == "WATCH":
            state = STANDBY
            reason = "Decision engine is WATCH; continue monitoring."
            override = "NONE"
        elif decision == "ALERT":
            state = ARMED
            reason = "Decision engine is ALERT; virtual interface is prepared without activation."
            override = "NONE"
        elif decision == "ACT" and authorized:
            state = ACTIVATED
            reason = "Decision engine explicitly authorized ACT after its evidence and confirmation gates. Virtual only."
            override = "NONE"
        elif decision == "ACT":
            state = ARMED
            reason = "ACT authorization is missing or invalid; activation denied and virtual interface remains armed."
            override = "AUTHORIZATION DENIED"
        else:
            state = ARMED
            reason = "Decision is missing or unavailable; remain prepared for operator review without activation."
            override = "REVIEW REQUIRED"

        activation_timestamp = old.get("activation_timestamp")
        if state == ACTIVATED and old.get("status") != ACTIVATED:
            activation_timestamp = current
        new = {
            "zone": zone,
            "status": state,
            "activation_timestamp": activation_timestamp,
            "triggering_decision": decision,
            "reason": reason,
            "operator_override_status": override,
            "authorized": authorized,
            "virtual_only": True,
            "updated_at": current,
        }
        self._zones[zone] = new
        if self._signature(old) != self._signature(new):
            self._record(new, result.get("evidence", []), current)
        return dict(new)

    def cancel(
        self,
        zone: str,
        decision_result: Mapping[str, Any] | None = None,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Immediately return the zone to STANDBY and latch operator cancellation."""
        self._cancelled.add(zone)
        result = dict(decision_result or {})
        result["zone"] = zone
        state = self.update(result, now=now)
        state.update({
            "status": STANDBY,
            "operator_override_status": "CANCELLED — OPERATOR",
            "reason": "Operator cancelled virtual suppression; state returned immediately to standby.",
            "authorized": False,
        })
        self._zones[zone] = state
        self._record(state, result.get("evidence", []), _timestamp(now))
        return dict(state)

    def release_cancellation(self, zone: str) -> None:
        """Clear the operator cancel latch; the next decision update sets state."""
        self._cancelled.discard(zone)

    def cancellation_active(self, zone: str) -> bool:
        return zone in self._cancelled

    def _initial(self, zone: str) -> dict[str, Any]:
        return {
            "zone": zone,
            "status": STANDBY,
            "activation_timestamp": None,
            "triggering_decision": "UNAVAILABLE",
            "reason": "No decision has been received; virtual suppression is in standby.",
            "operator_override_status": "NONE",
            "authorized": False,
            "virtual_only": True,
            "updated_at": None,
        }

    @staticmethod
    def _signature(state: Mapping[str, Any]) -> tuple[Any, ...]:
        return (
            state.get("status"), state.get("triggering_decision"),
            state.get("operator_override_status"), state.get("reason"),
        )

    def _record(self, state: Mapping[str, Any], evidence: Any, current: datetime) -> None:
        evidence_items = evidence if isinstance(evidence, list) else []
        contributing = [
            str(item.get("source", "unknown evidence"))
            for item in evidence_items
            if isinstance(item, Mapping) and item.get("supports_risk")
        ]
        self.event_history.append({
            "timestamp": current,
            "zone": state["zone"],
            "status": state["status"],
            "activation_timestamp": state.get("activation_timestamp"),
            "decision": state["triggering_decision"],
            "reason": state["reason"],
            "operator_override_status": state["operator_override_status"],
            "evidence": ", ".join(contributing) or "No contributing evidence recorded",
            "virtual_only": True,
        })
        self.event_history = self.event_history[-1000:]
