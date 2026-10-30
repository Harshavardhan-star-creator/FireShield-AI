"""Optional, class-validated Ultralytics YOLO integration."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

import numpy as np
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "fire_smoke_yolo.pt"
FIRE_ALIASES = {"fire", "flame"}
SMOKE_ALIASES = {"smoke"}


class ModelUnavailableError(RuntimeError):
    """Raised when no compatible fire/smoke model can be used."""


def resolve_model_path(model_path: str | Path | None = None) -> Path:
    configured = model_path or os.getenv("FIRESHIELD_FIRE_SMOKE_MODEL")
    if configured:
        path = Path(configured).expanduser()
        return path if path.is_absolute() else PROJECT_ROOT / path
    return DEFAULT_MODEL_PATH


def validate_model_names(names: dict | list | tuple) -> dict[int, str]:
    """Map model-provided class IDs to Fire/Smoke and reject incomplete labels.

    IDs are read from ``model.names`` instead of assumed. A conventional
    two-class export uses 0=fire (or flame), 1=smoke; another ordering is also
    accepted when the class names identify both categories.
    """
    entries = names.items() if isinstance(names, dict) else enumerate(names)
    mapped: dict[int, str] = {}
    found: set[str] = set()
    for class_id, raw_name in entries:
        normalized = str(raw_name).strip().lower()
        if normalized in FIRE_ALIASES:
            mapped[int(class_id)] = "Fire"
            found.add("fire")
        elif normalized in SMOKE_ALIASES:
            mapped[int(class_id)] = "Smoke"
            found.add("smoke")
    missing = {"fire", "smoke"} - found
    if missing:
        raise ModelUnavailableError(
            "The model labels do not include both Fire and Smoke (missing: "
            + ", ".join(sorted(missing))
            + ")."
        )
    return mapped


@st.cache_resource(show_spinner="Loading Fire/Smoke YOLO model…")
def _load_compatible_model(model_path: str) -> tuple[Any, dict[int, str]]:
    path = Path(model_path)
    if not path.is_file():
        raise ModelUnavailableError(f"No model weights found at {path}.")
    if importlib.util.find_spec("ultralytics") is None:
        raise ModelUnavailableError("Ultralytics is not installed. Install the project requirements.")

    try:
        from ultralytics import YOLO

        model = YOLO(str(path))
        class_map = validate_model_names(model.names)
    except ModelUnavailableError:
        raise
    except Exception as exc:
        raise ModelUnavailableError(f"The configured YOLO model could not be loaded: {exc}") from exc
    return model, class_map


def inspect_model(model_path: str | Path | None = None) -> dict[str, str | bool]:
    """Load and validate the configured model, returning a UI-ready status."""
    path = resolve_model_path(model_path)
    try:
        _load_compatible_model(str(path.resolve()))
    except ModelUnavailableError as exc:
        return {"available": False, "path": str(path), "message": str(exc)}
    return {
        "available": True,
        "path": str(path),
        "message": "Compatible YOLO weights loaded; Fire and Smoke labels are available.",
    }


def infer_fire_smoke(
    frame_bgr: np.ndarray,
    confidence_threshold: float = 0.25,
    model_path: str | Path | None = None,
    device: str = "cpu",
    image_size: int = 640,
) -> tuple[np.ndarray, list[dict[str, float | str]]]:
    """Run validated YOLO inference, using CPU and 640px inference by default.

    Ultralytics letterboxes to ``image_size`` while preserving the source
    aspect ratio, and maps detections back onto the original frame.
    """
    try:
        import cv2
    except ImportError as exc:
        raise ModelUnavailableError("OpenCV is not installed.") from exc

    path = resolve_model_path(model_path)
    model, class_map = _load_compatible_model(str(path.resolve()))
    try:
        result = model.predict(
            source=frame_bgr,
            conf=confidence_threshold,
            device=device,
            imgsz=image_size,
            verbose=False,
        )[0]
    except Exception as exc:
        raise RuntimeError(f"YOLO inference failed: {exc}") from exc

    annotated = frame_bgr.copy()
    detections: list[dict[str, float | str]] = []
    boxes = result.boxes
    if boxes is None:
        return annotated, detections
    for box in boxes:
        class_id = int(box.cls[0].item())
        label = class_map.get(class_id)
        if label is None:
            continue
        confidence = float(box.conf[0].item())
        x1, y1, x2, y2 = (int(value) for value in box.xyxy[0].tolist())
        color = (50, 210, 130) if label == "Smoke" else (65, 90, 250)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            annotated,
            f"{label} {confidence:.2f}",
            (x1, max(20, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            color,
            2,
            cv2.LINE_AA,
        )
        detections.append({"class_name": label, "confidence": confidence})
    return annotated, detections

