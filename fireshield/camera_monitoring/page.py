"""Camera Monitoring page for optional, validated fire/smoke model inference."""

from __future__ import annotations

import hashlib
import time
from datetime import datetime

import pandas as pd
import streamlit as st

from fireshield.camera_monitoring.contracts import make_detection_event
from fireshield.camera_monitoring.image_processing import decode_image, to_rgb
from fireshield.camera_monitoring.model import infer_fire_smoke, inspect_model
from fireshield.camera_monitoring.live import render_live_monitor
from fireshield.dashboard.components import inject_theme
from fireshield.database import safe_record_event
from fireshield.sensor_monitoring.data import ZONES


@st.cache_data(max_entries=16, show_spinner=False)
def _decode_cached(image_bytes: bytes):
    """Decode and prepare display pixels once for an identical image."""
    frame_bgr = decode_image(image_bytes)
    return frame_bgr, to_rgb(frame_bgr)


def _record_events(
    detections: list[dict], *, timestamp: datetime, zone: str, source: str, image_key: str
) -> None:
    logged = st.session_state.setdefault("camera_logged_images", set())
    if image_key in logged:
        return
    history = st.session_state.setdefault("camera_detection_history", [])
    for detection in detections:
        event = make_detection_event(
            timestamp=timestamp,
            zone=zone,
            class_name=detection["class_name"],
            confidence=detection["confidence"],
            source=source,
            event_id=hashlib.sha256(
                f"{image_key}:{detection['class_name']}:{detection['confidence']:.6f}".encode()
            ).hexdigest()[:16],
        )
        history.append(event)
        safe_record_event(
            "camera_detection",
            timestamp=event["timestamp"],
            zone_id=event["zone"],
            details=event,
            event_key=f"camera:{event['event_id']}",
        )
    st.session_state.camera_detection_history = history[-500:]
    logged.add(image_key)
    st.session_state.camera_logged_images = logged


def _render_history() -> None:
    st.markdown('<div class="section-heading">Detection history</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-note">Only actual Fire/Smoke model detections are recorded and restored from local history. Upload previews and unavailable-model states do not create events.</div>', unsafe_allow_html=True)
    history = pd.DataFrame(st.session_state.get("camera_detection_history", []))
    if history.empty:
        st.info("No model detection events recorded in this session.")
        return
    history["timestamp"] = pd.to_datetime(history["timestamp"], utc=True).dt.strftime("%d %b %Y · %H:%M:%S %Z")
    history = history.rename(columns={
        "timestamp": "Timestamp",
        "zone": "Zone",
        "detection_class": "Detection",
        "confidence": "Confidence",
        "source": "Source",
    })
    st.dataframe(
        history[["Timestamp", "Zone", "Detection", "Confidence", "Source"]].iloc[::-1],
        use_container_width=True,
        hide_index=True,
        column_config={"Confidence": st.column_config.NumberColumn("Confidence", format="%.1%%")},
    )


def render_camera_monitoring() -> None:
    """Render image capture, transparent model status, and real event history."""
    inject_theme()
    st.markdown('<div class="eyebrow">Industrial safety monitoring</div>', unsafe_allow_html=True)
    st.markdown('<div class="main-title">Camera Monitoring</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Image capture and optional fire/smoke object detection</div>', unsafe_allow_html=True)

    model_status = inspect_model()
    st.session_state.camera_model_status = model_status
    if model_status["available"]:
        st.success("MODEL READY · " + str(model_status["message"]))
    else:
        st.warning("DETECTION UNAVAILABLE · " + str(model_status["message"]))
    st.markdown(
        '<div class="notice">Camera processing does not control suppression equipment. Inference is real only when compatible trained weights are loaded; otherwise the page shows an image preview without detections or confidence scores.</div>',
        unsafe_allow_html=True,
    )

    source_col, zone_col, confidence_col, size_col = st.columns([1.3, 1.3, 1, 1])
    with source_col:
        source_mode = st.radio("Image source", ["Upload Image", "Webcam Capture"], horizontal=True, key="camera_source_mode")
    with zone_col:
        zone = st.selectbox("Facility zone", ZONES, key="camera_zone")
    with confidence_col:
        confidence_threshold = st.slider("Model confidence filter", 0.05, 0.95, 0.25, 0.05, help="YOLO inference filtering only; not a fire-safety threshold.")
    with size_col:
        image_size = st.select_slider(
            "Inference image size",
            options=[320, 416, 512, 640, 768, 960, 1280],
            value=640,
            help="Ultralytics preserves aspect ratio while resizing/letterboxing. Larger sizes can improve small-object detail at higher CPU cost.",
        )

    if model_status["available"]:
        render_live_monitor(zone, confidence_threshold, image_size)
    else:
        st.markdown('<div class="section-heading">Continuous live monitoring</div>', unsafe_allow_html=True)
        st.info("Start Monitoring is unavailable until compatible Fire and Smoke YOLO weights are loaded.")

    input_col, result_col = st.columns([1.1, 1])
    image_file = None
    source_label = "Uploaded image"
    with input_col:
        if source_mode == "Upload Image":
            st.markdown('<div class="section-heading">Image input</div>', unsafe_allow_html=True)
            image_file = st.file_uploader("Choose an image", type=["jpg", "jpeg", "png"], key="camera_upload")
            st.caption("Supported formats: JPG, JPEG, PNG. Uploads are analyzed only if a compatible model is configured.")
            st.info("Connection status: upload mode · no camera hardware connection required.")
        else:
            st.markdown('<div class="section-heading">Webcam input</div>', unsafe_allow_html=True)
            image_file = st.camera_input("Capture a frame", key="camera_capture")
            source_label = "Webcam"
            if image_file is None:
                st.info("Camera status: waiting for a browser webcam capture. Browser permission and device access are managed by Streamlit.")
            else:
                st.success("Camera status: image captured by the browser.")

    frame_bgr = None
    frame_rgb = None
    if image_file is not None:
        try:
            image_bytes = image_file.getvalue()
            frame_bgr, frame_rgb = _decode_cached(image_bytes)
        except (RuntimeError, ValueError) as exc:
            st.error(f"Image processing unavailable: {exc}")
        else:
            with input_col:
                st.image(frame_rgb, caption=f"{source_label} · OpenCV image decode", use_container_width=True)
                st.caption("OpenCV image decoding only; no fire/smoke inference is implied.")

    with result_col:
        st.markdown('<div class="section-heading">Detection results</div>', unsafe_allow_html=True)
        if not model_status["available"]:
            st.error("No detection results are available. Configure a compatible fire/smoke-trained YOLO model to enable inference.")
            st.button("Run Detection", disabled=True, help="Detection is unavailable until compatible model weights are configured.")
            st.caption("No bounding boxes or confidence scores were fabricated.")
        elif frame_bgr is None:
            st.info("Provide an image to run model inference.")
        else:
            image_bytes = image_file.getvalue()
            image_digest = hashlib.sha256(image_bytes).hexdigest()
            inference_key = (image_digest, float(confidence_threshold), int(image_size))
            cached_result = st.session_state.get("camera_last_inference")
            if st.button("Run Detection", type="primary", key="run_camera_detection"):
                if cached_result and cached_result["key"] == inference_key:
                    st.info("This image already has results for the selected settings; reusing them.")
                else:
                    try:
                        started = time.perf_counter()
                        annotated_bgr, detections = infer_fire_smoke(
                            frame_bgr,
                            confidence_threshold,
                            device="cpu",
                            image_size=image_size,
                        )
                        elapsed_ms = (time.perf_counter() - started) * 1000
                    except Exception as exc:
                        st.error(f"Inference failed; no detection result was recorded. {exc}")
                    else:
                        cached_result = {
                            "key": inference_key,
                            "annotated_rgb": to_rgb(annotated_bgr),
                            "detections": detections,
                            "elapsed_ms": elapsed_ms,
                        }
                        st.session_state.camera_last_inference = cached_result
                        if detections:
                            detection_timestamp = datetime.now().astimezone()
                            history_key = hashlib.sha256(
                                source_label.encode() + zone.encode() + image_bytes
                            ).hexdigest()
                            _record_events(
                                detections,
                                timestamp=detection_timestamp,
                                zone=zone,
                                source=source_label,
                                image_key=history_key,
                            )

            cached_result = st.session_state.get("camera_last_inference")
            if cached_result and cached_result["key"] == inference_key:
                st.image(cached_result["annotated_rgb"], caption="OpenCV frame with actual model output", use_container_width=True)
                st.caption(f"CPU inference time: {cached_result['elapsed_ms']:.1f} ms · inference size: {image_size}px")
                detections = cached_result["detections"]
                if detections:
                    st.success(f"Model inference complete · {len(detections)} Fire/Smoke detection(s)")
                    st.dataframe(
                        pd.DataFrame(detections).rename(columns={"class_name": "Class", "confidence": "Confidence"}),
                        hide_index=True,
                        use_container_width=True,
                        column_config={"Confidence": st.column_config.NumberColumn("Confidence", format="%.1%%")},
                    )
                else:
                    st.info("Model inference complete · no Fire or Smoke objects detected in this image.")
            else:
                st.info("Image ready. Click **Run Detection** to start CPU inference.")

    _render_history()

