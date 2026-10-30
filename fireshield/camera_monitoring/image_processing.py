"""OpenCV image decoding and display helpers for camera monitoring."""

from __future__ import annotations

import numpy as np


def decode_image(image_bytes: bytes) -> np.ndarray:
    """Decode an uploaded image into an OpenCV BGR frame."""
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is not installed. Install the project requirements first.") from exc

    encoded = np.frombuffer(image_bytes, dtype=np.uint8)
    frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if frame is None or frame.size == 0:
        raise ValueError("The selected file could not be decoded as an image.")
    return frame


def to_rgb(frame_bgr: np.ndarray) -> np.ndarray:
    """Convert an OpenCV BGR frame to RGB for Streamlit display."""
    import cv2

    return cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
