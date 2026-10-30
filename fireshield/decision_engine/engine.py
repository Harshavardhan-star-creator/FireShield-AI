"""Stateful, explainable decision policy; virtual only and never actuates hardware."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


@dataclass(frozen=True)
class DecisionConfig:
    """Configurable decision confirmation and evidence-quality requirements."""

    confirmation_duration_seconds: float = 30.0
    minimum_independent_sources: int = 2
    evidence_freshness_seconds: float = 45.0
    minimum_camera_confidence: float = 0.50

    def __post_init__(self) -> None:
        if self.confirmation_duration_seconds <= 0:
            raise ValueError("confirmation_duration_seconds must be positive.")
        if self.minimum_independent_sources < 2:
            raise ValueError("ACT requires at least two independent evidence sources.")
        if self.evidence_freshness_seconds <= 0:
            raise ValueError("evidence_freshness_seconds must be positive.")
        if not 0.0 <= self.minimum_camera_confidence <= 1.0:
            raise ValueError("minimum_camera_confidence must be between 0 and 1.")


DEFAULT_DECISION_CONFIG = DecisionConfig()


def _datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if result.tzinfo is None:
        return result.replace(tzinfo=timezone.utc)
    return result


def _seconds_between(later: datetime, earlier: datetime) -> float:
    return later.timestamp() - earlier.timestamp()


class DecisionEngine:
    """Evaluate risk results over time and keep a session-local audit history.

    ACT is a policy state only. This class has no hardware drivers, network
    actuators, or suppression-control calls.
    """

    def __init__(self, config: DecisionConfig = DEFAULT_DECISION_CONFIG) -> None:
        self.config = config
        self.history: list[dict[str, Any]] = []
        self._candidate_since: dict[str, datetime] = {}
        self._last_observation: dict[str, datetime] = {}
        self._operator_holds: set[str] = set()
        self._last_record_signature: dict[str, tuple[Any, ...]] = {}

    def evaluate(
        self,
        risk_result: Mapping[str, Any],
        evidence: list[Mapping[str, Any]] | None = None,
        *,
        now: datetime | None = None,
        observed_at: datetime | None = None,
        operator_override: str | None = None,
    ) -> dict[str, Any]:
        """Return WATCH/ALERT/ACT and record meaningful state/evidence changes.

        Evidence items use ``source_group``, ``observed_at``, ``reliable``,
        ``simulated`` and ``supports_risk``. For camera items, confidence must
        meet the configured minimum. Simulated sensor inputs cannot qualify ACT.
        Operator actions can hold/cancel ACT or release that hold; they cannot
        force an ACT decision or bypass evidence gates.
        """
        current = _datetime(now) or datetime.now().astimezone()
        zone = str(risk_result.get("zone", "Unknown zone"))
        risk_level = str(risk_result.get("level", "UNAVAILABLE")).upper()
        score = risk_result.get("score")
        evidence_items = list(evidence or [])
        reasons: list[str] = []
        decision_source = "AUTOMATIC"

        if operator_override == "HOLD_ALERT":
            self._operator_holds.add(zone)
            self._candidate_since.pop(zone, None)
            reasons.append("Operator cancelled/held the ACT path; the zone remains at ALERT.")
            decision_source = "OPERATOR_OVERRIDE"
        elif operator_override == "RELEASE_HOLD":
            self._operator_holds.discard(zone)
            self._candidate_since.pop(zone, None)
            self._last_observation.pop(zone, None)
            reasons.append("Operator released the hold; ACT confirmation starts again from fresh evidence.")
            decision_source = "OPERATOR_OVERRIDE"

        act_eligible = False
        confirmation_elapsed = 0.0
        supporting, evidence_reasons = self._supporting_evidence(evidence_items, current)

        if zone in self._operator_holds and risk_level == "ACT":
            decision = "ALERT"
            reasons.append("Operator hold is active; automatic ACT is cancelled until the hold is released.")
            decision_source = "OPERATOR_OVERRIDE"
        elif risk_level == "WATCH":
            decision = "WATCH"
            reasons.append("Monitor the zone and continue collecting sensor/camera readings.")
            if risk_result.get("complete") is not True:
                reasons.append("Evidence is incomplete; WATCH is not an all-clear.")
        elif risk_level == "UNAVAILABLE" or score is None:
            decision = "ALERT"
            reasons.append("Risk evidence is unavailable; high-priority operator review is required.")
            reasons.extend(evidence_reasons)
        elif risk_level == "ALERT":
            decision = "ALERT"
            reasons.append("Risk engine classified this zone as ALERT; operator attention is required.")
            reasons.extend(evidence_reasons)
        elif risk_level == "ACT":
            risk_complete = risk_result.get("complete") is True
            if not risk_complete:
                reasons.append("Evidence completeness check failed; missing risk inputs cannot qualify ACT.")
            if len(supporting) < self.config.minimum_independent_sources:
                reasons.append(
                    f"Only {len(supporting)} independent reliable risk source(s) are confirmed; "
                    f"{self.config.minimum_independent_sources} are required."
                )
            reasons.extend(evidence_reasons)

            observed = _datetime(observed_at)
            if risk_complete and len(supporting) >= self.config.minimum_independent_sources and observed:
                previous_observation = self._last_observation.get(zone)
                candidate_start = self._candidate_since.get(zone)
                if candidate_start is None:
                    candidate_start = observed
                    self._candidate_since[zone] = candidate_start
                    reasons.append("ACT confirmation started; waiting for sustained fresh evidence.")
                elif previous_observation and _seconds_between(observed, previous_observation) > self.config.evidence_freshness_seconds:
                    candidate_start = observed
                    self._candidate_since[zone] = observed
                    reasons.append("Evidence gap reset the sustained confirmation timer.")

                if previous_observation is None or _seconds_between(observed, previous_observation) > 0:
                    self._last_observation[zone] = observed
                confirmation_elapsed = max(0.0, _seconds_between(observed, candidate_start))
                if confirmation_elapsed >= self.config.confirmation_duration_seconds:
                    act_eligible = True
                    reasons.append("Independent, reliable evidence remained confirmed for the required duration.")
                else:
                    remaining = max(0.0, self.config.confirmation_duration_seconds - confirmation_elapsed)
                    reasons.append(f"Sustained confirmation: {confirmation_elapsed:.1f}s observed; {remaining:.1f}s remain.")
            else:
                self._candidate_since.pop(zone, None)
                self._last_observation.pop(zone, None)
                if observed_at is None:
                    reasons.append("Observation timestamp is missing; sustained confirmation cannot be established.")
            decision = "ACT" if act_eligible else "ALERT"
        else:
            decision = "ALERT"
            reasons.append(f"Unrecognized risk classification {risk_level!r}; conservatively held at ALERT.")

        if risk_level != "ACT" and operator_override not in {"HOLD_ALERT", "RELEASE_HOLD"}:
            self._candidate_since.pop(zone, None)
            self._last_observation.pop(zone, None)

        virtual_state = {
            "WATCH": "NOT PREPARED",
            "ALERT": "PREPARED · VIRTUAL ONLY · NOT ACTIVATED",
            "ACT": "VIRTUAL ACT STATE · NO HARDWARE COMMAND",
        }[decision]
        if decision == "WATCH":
            action = "Monitor the zone; record state and continue collecting readings."
        elif decision == "ALERT":
            action = "Send high-priority operator notification; prepare virtual suppression interface only."
        else:
            action = "Record ACT decision and virtual suppression recommendation; no physical action is sent."

        decision_result = {
            "timestamp": current,
            "zone": zone,
            "decision": decision,
            "decision_source": decision_source,
            "risk_score": score,
            "risk_level": risk_level,
            "action": action,
            "reasons": reasons,
            "evidence": [dict(item) for item in evidence_items],
            "supporting_sources": sorted(supporting),
            "evidence_complete": risk_result.get("complete") is True,
            "act_eligible": act_eligible,
            # Downstream virtual suppression accepts this explicit authorization
            # only; it must never infer permission from the risk score.
            "activation_authorized": bool(
                decision == "ACT"
                and act_eligible
                and risk_result.get("complete") is True
                and zone not in self._operator_holds
                and decision_source == "AUTOMATIC"
            ),
            "confirmation_elapsed_seconds": round(confirmation_elapsed, 1),
            "operator_hold": zone in self._operator_holds,
            "virtual_suppression": {"state": virtual_state, "activated": False, "hardware_control": False},
            "notification": (
                {"priority": "HIGH", "zone": zone, "message": " ".join(reasons)}
                if decision == "ALERT"
                else None
            ),
        }
        self._record_if_changed(decision_result, observed_at)
        return decision_result

    def _supporting_evidence(
        self, evidence: list[Mapping[str, Any]], now: datetime
    ) -> tuple[set[str], list[str]]:
        groups: set[str] = set()
        reasons = []
        for item in evidence:
            if not item.get("supports_risk"):
                continue
            source = str(item.get("source", "unknown source"))
            if item.get("simulated") is True or item.get("reliable") is not True:
                reasons.append(f"{source} is simulated or not marked reliable and cannot qualify ACT.")
                continue
            confidence = item.get("confidence")
            if item.get("kind") == "camera":
                try:
                    confidence = float(confidence)
                except (TypeError, ValueError):
                    confidence = 0.0
                if confidence < self.config.minimum_camera_confidence:
                    reasons.append(f"{source} confidence is below the configured reliability minimum.")
                    continue
            observed = _datetime(item.get("observed_at"))
            if observed is None or _seconds_between(now, observed) < 0 or _seconds_between(now, observed) > self.config.evidence_freshness_seconds:
                reasons.append(f"{source} evidence is missing a timestamp or is stale.")
                continue
            group = str(item.get("source_group", "")).strip()
            if not group:
                reasons.append(f"{source} has no independent-source identifier.")
                continue
            groups.add(group)
        return groups, reasons

    def _record_if_changed(
        self, result: Mapping[str, Any], observed_at: datetime | None
    ) -> None:
        zone = str(result["zone"])
        observation = _datetime(observed_at)
        evidence_signature = tuple(
            sorted(
                (
                    str(item.get("source")),
                    str(item.get("source_group")),
                    str(item.get("observed_at")),
                    bool(item.get("supports_risk")),
                )
                for item in result["evidence"]
            )
        )
        signature = (
            result["decision"],
            result["decision_source"],
            result["risk_level"],
            observation.isoformat() if observation else None,
            evidence_signature,
        )
        if self._last_record_signature.get(zone) == signature:
            return
        self._last_record_signature[zone] = signature
        self.history.append({
            "timestamp": result["timestamp"],
            "zone": result["zone"],
            "decision": result["decision"],
            "decision_source": result["decision_source"],
            "risk_score": result["risk_score"],
            "evidence": result["evidence"],
            "reasons": list(result["reasons"]),
            "virtual_suppression": result["virtual_suppression"]["state"],
        })
        self.history = self.history[-1000:]

