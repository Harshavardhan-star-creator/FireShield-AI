"""Camera detection event contract for future risk and decision modules."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def make_detection_event(
    *,
    timestamp: datetime,
    zone: str,
    class_name: str,
    confidence: float,
    source: str,
    event_id: str,
) -> dict[str, Any]:
    """Return a normalized, real-inference event payload for downstream modules."""
    if class_name not in {"Fire", "Smoke"}:
        raise ValueError("Camera events must use a validated Fire or Smoke class.")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("Confidence must be between 0 and 1.")
    return {
        "event_id": event_id,
        "timestamp": timestamp,
        "zone": zone,
        "detection_class": class_name,
        "confidence": confidence,
        "source": source,
        "origin": "camera_model_inference",
        "simulated": False,
    }


def to_risk_signal(event: dict[str, Any]) -> dict[str, Any]:
    """Adapt an event for a future risk engine; this does not actuate hardware."""
    return {
        "signal_type": "camera_detection",
        "observed_at": event["timestamp"],
        "zone": event["zone"],
        "class_name": event["detection_class"],
        "confidence": event["confidence"],
        "source_event_id": event["event_id"],
        "requires_decision_engine_review": True,
    }
