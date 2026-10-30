from fireshield.dashboard import render_dashboard
from fireshield.sensor_monitoring import render_sensor_monitoring
from fireshield.camera_monitoring import render_camera_monitoring

import streamlit as st

from fireshield.database import DatabaseError, initialize_database, load_recent_session_data

st.set_page_config(
    page_title="FireShield AI",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Restore persisted histories once per browser session. If local SQLite is
# unavailable, empty session histories remain valid and the app continues.
try:
    initialize_database()
    restored_histories = load_recent_session_data()
except (DatabaseError, OSError):
    restored_histories = {}
for history_name in (
    "sensor_history",
    "camera_detection_history",
    "risk_history",
    "decision_history",
    "suppression_event_history",
    "operator_override_history",
):
    st.session_state.setdefault(history_name, restored_histories.get(history_name, []))

PAGES = {
    "Dashboard": render_dashboard,
    "Sensor Monitoring": render_sensor_monitoring,
    "Camera Monitoring": render_camera_monitoring,
}

st.sidebar.title("FireShield AI")
st.sidebar.caption("Industrial fire safety project prototype")
page = st.sidebar.radio("Navigation", list(PAGES))
PAGES[page]()

