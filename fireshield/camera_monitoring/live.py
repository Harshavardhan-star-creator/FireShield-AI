"""Continuous browser webcam inference using Streamlit WebRTC."""

from __future__ import annotations

from datetime import datetime
import threading
import time
from typing import Any

import streamlit as st

from fireshield.camera_monitoring.image_processing import to_rgb
from fireshield.camera_monitoring.model import infer_fire_smoke


class FireSmokeVideoProcessor:
    """Run the configured YOLO model on a sampled stream of webcam frames."""

    def __init__(self, confidence: float, image_size: int) -> None:
        self.confidence = confidence
        self.image_size = image_size
        self.lock = threading.Lock()
        self.latest: dict[str, Any] = {"detections": [], "timestamp": None, "error": None}
        self._last_seen: dict[str, float] = {}
        self._pending_alerts: list[dict[str, Any]] = []

    def recv(self, frame):
        import av

        image = frame.to_ndarray(format="bgr24")
        try:
            annotated, detections = infer_fire_smoke(
                image, self.confidence, device="cpu", image_size=self.image_size
            )
            image = annotated
            now = time.monotonic()
            timestamp = datetime.now().astimezone()
            alerts = []
            best_by_class = {}
            for detection in detections:
                label = detection["class_name"]
                best_by_class[label] = max(
                    float(detection["confidence"]), best_by_class.get(label, 0.0)
                )
            for label, confidence in best_by_class.items():
                previously_seen = self._last_seen.get(label)
                self._last_seen[label] = now
                if previously_seen is None or now - previously_seen >= 5:
                    alerts.append({"class_name": label, "confidence": confidence})
            # A class clears after five seconds without a positive inference;
            # the same persistent object does not create an alert per frame.
            self._last_seen = {
                label: seen for label, seen in self._last_seen.items() if now - seen < 5
            }
            with self.lock:
                self.latest = {
                    "frame_rgb": to_rgb(annotated),
                    "detections": detections,
                    "timestamp": timestamp,
                    "alerts": [],
                    "error": None,
                }
                self._pending_alerts.extend({**item, "timestamp": timestamp} for item in alerts)
        except Exception as exc:
            with self.lock:
                self.latest = {**self.latest, "error": str(exc)}
        return av.VideoFrame.from_ndarray(image, format="bgr24")

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            result = dict(self.latest)
            result["alerts"] = self._pending_alerts
            self._pending_alerts = []
            return result


@st.fragment(run_every=1)
def render_live_monitor(zone: str, confidence: float, image_size: int) -> None:
    """Live UI fragment: independent reruns keep stop controls responsive."""
    try:
        from streamlit_webrtc import RTCConfiguration, WebRtcMode, webrtc_streamer
    except ImportError:
        st.error("Continuous webcam monitoring needs streamlit-webrtc. Install requirements.txt and restart the app.")
        return

    st.markdown('<div class="section-heading">Continuous live monitoring</div>', unsafe_allow_html=True)
    st.caption("The browser sends webcam frames for CPU YOLO inference. Camera access requires browser permission and localhost or HTTPS.")
    state_key = "camera_live_requested"
    start_col, stop_col, status_col = st.columns([1, 1, 2])
    with start_col:
        if st.button("Start Monitoring", type="primary", disabled=st.session_state.get(state_key, False), key="live_start"):
            st.session_state[state_key] = True
    with stop_col:
        if st.button("Stop Monitoring", disabled=not st.session_state.get(state_key, False), key="live_stop"):
            st.session_state[state_key] = False

    active = st.session_state.get(state_key, False)
    with status_col:
        st.success("MONITORING" if active else "STOPPED · webcam released when stream closes") if active else st.info("Monitoring is stopped.")

    context = webrtc_streamer(
        key="fireshield-live-camera",
        mode=WebRtcMode.SENDRECV,
        rtc_configuration=RTCConfiguration({"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}),
        media_stream_constraints={"video": {"frameRate": {"ideal": 5, "max": 8}}, "audio": False},
        video_processor_factory=lambda: FireSmokeVideoProcessor(confidence, image_size),
        async_processing=True,
        desired_playing_state=active,
        video_html_attrs={"autoPlay": True, "controls": False, "muted": True},
    )
    processor = context.video_processor
    if not active or processor is None:
        return
    result = processor.snapshot()
    if result.get("error"):
        st.error(f"Live inference error: {result['error']}")
    detections = result.get("detections", [])
    timestamp = result.get("timestamp")
    frame_rgb = result.get("frame_rgb")
    if frame_rgb is not None:
        st.image(frame_rgb, caption="Live webcam frame · YOLO bounding boxes", use_container_width=True)
    if timestamp:
        st.caption(f"Last inference: {timestamp.strftime('%d %b %Y · %H:%M:%S %Z')}")
    if detections and timestamp:
        st.dataframe(
            [{"Detection time": timestamp.strftime("%d %b %Y · %H:%M:%S %Z"),
              "Class": item["class_name"], "Confidence": item["confidence"]} for item in detections],
            hide_index=True, use_container_width=True,
            column_config={"Confidence": st.column_config.NumberColumn("Confidence", format="%.1%%")},
        )
    else:
        st.caption("No Fire or Smoke detections in the latest inference.")

    for alert in result.get("alerts", []):
        event_time = alert["timestamp"]
        event_id = f"live-{event_time.timestamp()}-{alert['class_name']}"
        from fireshield.camera_monitoring.contracts import make_detection_event
        from fireshield.database import safe_record_event

        event = make_detection_event(
            timestamp=event_time, zone=zone, class_name=alert["class_name"],
            confidence=alert["confidence"], source="Live webcam", event_id=event_id,
        )
        history = st.session_state.setdefault("camera_detection_history", [])
        if not any(item.get("event_id") == event_id for item in history):
            history.append(event)
            st.session_state.camera_detection_history = history[-500:]
            safe_record_event("camera_detection", timestamp=event["timestamp"], zone_id=zone,
                              details=event, event_key=f"camera:{event_id}")
            st.toast(f"{alert['class_name']} detected · {alert['confidence']:.0%} confidence", icon="🚨")
