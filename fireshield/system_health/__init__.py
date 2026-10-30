"""Lightweight status assessment for existing FireShield AI components."""

from __future__ import annotations

from datetime import datetime, timezone
import importlib
import importlib.util
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from fireshield.database import DEFAULT_DATABASE_PATH, check_database_connection


ONLINE = "ONLINE"
WARNING = "WARNING"
OFFLINE = "OFFLINE"
NOT_CONFIGURED = "NOT CONFIGURED"
STATUS_COLORS = {
    ONLINE: "#34d399",
    WARNING: "#fb923c",
    OFFLINE: "#fb5656",
    NOT_CONFIGURED: "#9aa8b5",
}


def _latest_sensor_records(
    records: Iterable[Mapping[str, Any]], sensor: str, zones: tuple[str, ...]
) -> dict[str, Mapping[str, Any]]:
    latest: dict[str, Mapping[str, Any]] = {}
    for record in records:
        if record.get("sensor") != sensor:
            continue
        zone = str(record.get("zone", ""))
        if zone not in zones:
            continue
        if zone not in latest or _as_datetime(record.get("timestamp")) >= _as_datetime(latest[zone].get("timestamp")):
            latest[zone] = record
    return latest


def _as_datetime(value: Any) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _sensor_component(
    sensor: str,
    label: str,
    records: Iterable[Mapping[str, Any]],
    now: datetime,
    stale_after_seconds: float,
    zones: tuple[str, ...],
) -> dict[str, str]:
    latest = _latest_sensor_records(records, sensor, zones)
    if not latest:
        return {"name": label, "status": NOT_CONFIGURED, "detail": "No recorded readings are available."}
    unavailable = [
        zone for zone, record in latest.items()
        if record.get("value") is None or str(record.get("status", "")).upper() == "OFFLINE"
    ]
    missing_zones = sorted(set(zones) - set(latest))
    stale_zones = [
        zone for zone, record in latest.items()
        if (now - _as_datetime(record.get("timestamp"))).total_seconds() > stale_after_seconds
        or _as_datetime(record.get("timestamp")) > now
    ]
    if len(unavailable) == len(zones):
        status = OFFLINE
        detail = "Readings are unavailable in all configured zones."
    elif unavailable or missing_zones or stale_zones:
        status = WARNING
        issues = []
        if unavailable:
            issues.append("unavailable: " + ", ".join(unavailable))
        if missing_zones:
            issues.append("not yet reported: " + ", ".join(missing_zones))
        if stale_zones:
            issues.append("stale: " + ", ".join(stale_zones))
        detail = "; ".join(issues)
    elif all(record.get("simulated") is True for record in latest.values()):
        status = WARNING
        detail = "Fresh simulated readings are available; physical sensor connectivity is not established."
    else:
        status = ONLINE
        detail = "Fresh non-simulated readings are available in all configured zones."
    return {"name": label, "status": status, "detail": detail}


def _module_status(name: str, module_name: str, symbol: str) -> dict[str, str]:
    try:
        module = importlib.import_module(module_name)
        available = callable(getattr(module, symbol))
    except Exception as exc:
        return {"name": name, "status": OFFLINE, "detail": f"Module initialization failed: {exc}"}
    if not available:
        return {"name": name, "status": OFFLINE, "detail": f"Required module interface {symbol} is unavailable."}
    return {"name": name, "status": ONLINE, "detail": "Module loaded and required interface is available."}


def collect_system_health(
    *,
    sensor_history: Iterable[Mapping[str, Any]] = (),
    camera_capture_available: bool = False,
    model_status: Mapping[str, Any] | None = None,
    model_path: str | Path | None = None,
    database_check: Callable[[], bool] | None = None,
    database_path: str | Path | None = None,
    risk_engine_ready: bool | None = None,
    decision_engine_ready: bool = False,
    suppression_controller_ready: bool = False,
    now: datetime | None = None,
    stale_after_seconds: float = 60.0,
) -> dict[str, Any]:
    """Assess actual module and data availability without loading models or polling hardware."""
    current = _as_datetime(now or datetime.now(timezone.utc))
    history = list(sensor_history or [])
    components = []

    if camera_capture_available:
        camera = {
            "name": "Camera input",
            "status": WARNING,
            "detail": "A browser frame is available; continuous camera or hardware connectivity is not verified.",
        }
    else:
        camera = {
            "name": "Camera input",
            "status": NOT_CONFIGURED,
            "detail": "No browser camera frame is present; upload and one-shot browser capture are supported.",
        }
    components.append(camera)

    model_module_error = None
    try:
        if model_path is not None:
            resolved_model_path = Path(model_path)
        else:
            from fireshield.camera_monitoring.model import resolve_model_path

            resolved_model_path = resolve_model_path()
    except Exception as exc:
        resolved_model_path = Path()
        model_module_error = str(exc)
        model_status = {"available": False, "path": "", "message": f"Camera/model module initialization failed: {exc}"}
    known_model_status = model_status
    if model_module_error:
        model_component = {"name": "YOLO fire/smoke model", "status": OFFLINE, "detail": f"Camera/model module initialization failed: {model_module_error}"}
    elif known_model_status is not None:
        checked_path = Path(known_model_status.get("path", resolved_model_path))
        if not checked_path.is_file():
            model_component = {"name": "YOLO fire/smoke model", "status": NOT_CONFIGURED, "detail": str(known_model_status.get("message", "Model weights are missing."))}
        elif known_model_status.get("available") is True:
            model_component = {"name": "YOLO fire/smoke model", "status": ONLINE, "detail": "Compatible model was validated by the camera module."}
        else:
            model_component = {"name": "YOLO fire/smoke model", "status": OFFLINE, "detail": str(known_model_status.get("message", "Configured model failed validation."))}
    elif not resolved_model_path.is_file():
        model_component = {"name": "YOLO fire/smoke model", "status": NOT_CONFIGURED, "detail": f"No trained weights found at {resolved_model_path}."}
    else:
        try:
            ultralytics_available = importlib.util.find_spec("ultralytics") is not None
        except (ImportError, ValueError):
            ultralytics_available = False
        if not ultralytics_available:
            model_component = {"name": "YOLO fire/smoke model", "status": OFFLINE, "detail": "Weights exist, but the Ultralytics dependency is unavailable."}
        else:
            model_component = {"name": "YOLO fire/smoke model", "status": WARNING, "detail": "Weights and Ultralytics are present; compatibility has not been checked in this session."}
    components.append(model_component)

    try:
        from fireshield.sensor_monitoring.data import ZONES
    except Exception as exc:
        ZONES = ()
        zone_import_error = str(exc)
    else:
        zone_import_error = None
    for sensor, label in (
        ("temperature", "Temperature sensor readings"),
        ("smoke", "Smoke sensor readings"),
        ("gas", "Gas sensor readings"),
    ):
        if zone_import_error:
            components.append({"name": label, "status": OFFLINE, "detail": f"Sensor module initialization failed: {zone_import_error}"})
        else:
            components.append(_sensor_component(sensor, label, history, current, stale_after_seconds, tuple(ZONES)))

    db_path = Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH
    if not db_path.exists() and database_check is None:
        db_component = {"name": "SQLite database", "status": NOT_CONFIGURED, "detail": f"Database file is not present at {db_path}."}
    else:
        try:
            database_ready = (database_check or check_database_connection)()
        except Exception as exc:
            database_ready = False
            error_detail = str(exc)
        else:
            error_detail = "SQLite connection check failed."
        db_component = {
            "name": "SQLite database",
            "status": ONLINE if database_ready else OFFLINE,
            "detail": "SQLite connection and event table are available." if database_ready else error_detail,
        }
    components.append(db_component)

    if risk_engine_ready is None:
        risk_module = _module_status("Risk prediction engine", "fireshield.risk_prediction.engine", "calculate_facility_risk")
    else:
        risk_module = {
            "name": "Risk prediction engine",
            "status": ONLINE if risk_engine_ready else OFFLINE,
            "detail": "Risk calculation interface is available." if risk_engine_ready else "Risk prediction module did not initialize.",
        }
    components.append(risk_module)
    components.append({
        "name": "Decision engine",
        "status": ONLINE if decision_engine_ready else OFFLINE,
        "detail": "Decision engine instance is initialized." if decision_engine_ready else "Decision engine instance is unavailable.",
    })
    components.append({
        "name": "Virtual suppression controller",
        "status": ONLINE if suppression_controller_ready else OFFLINE,
        "detail": "Virtual-only controller instance is initialized; no hardware is connected." if suppression_controller_ready else "Virtual suppression controller instance is unavailable.",
    })

    statuses = {component["status"] for component in components}
    overall = OFFLINE if OFFLINE in statuses else WARNING if WARNING in statuses else NOT_CONFIGURED if NOT_CONFIGURED in statuses else ONLINE
    return {"overall_status": overall, "components": components}


__all__ = ["NOT_CONFIGURED", "OFFLINE", "ONLINE", "STATUS_COLORS", "WARNING", "collect_system_health"]
