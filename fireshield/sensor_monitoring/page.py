"""Streamlit Sensor Monitoring page."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from fireshield.dashboard.components import inject_theme
from fireshield.database import safe_record_event
from fireshield.sensor_monitoring.data import (
    SCENARIOS,
    SENSOR_LABELS,
    ZONES,
    flatten_snapshot,
    generate_readings,
)

_STATUS_COLOR = {"ONLINE": "#34d399", "WARNING": "#fb923c", "OFFLINE": "#fb5656"}
_STATUS_ORDER = {"ONLINE": 0, "WARNING": 1, "OFFLINE": 2}


def _append_history(snapshots: list[dict]) -> None:
    records = st.session_state.setdefault("sensor_history", [])
    new_records = flatten_snapshot(snapshots)
    records.extend(new_records)
    st.session_state.sensor_history = records[-1200:]
    for record in new_records:
        stamp = record["timestamp"].isoformat() if hasattr(record["timestamp"], "isoformat") else str(record["timestamp"])
        safe_record_event(
            "sensor_reading",
            timestamp=record["timestamp"],
            zone_id=record["zone"],
            details=record,
            event_key=f"sensor:{record['sensor_id']}:{stamp}",
        )


def _status_badge(status: str) -> str:
    color = _STATUS_COLOR[status]
    return f'<span class="sensor-status" style="--status-color:{color}"><i></i>{status}</span>'


def _render_zone_card(snapshot: dict) -> None:
    statuses = [reading["status"] for reading in snapshot["readings"].values()]
    zone_status = max(statuses, key=lambda status: _STATUS_ORDER[status])
    st.markdown(
        f"""
        <section class="zone-card sensor-zone-card">
          <div class="zone-top"><span class="zone-dot" style="--risk:{_STATUS_COLOR[zone_status]}"></span>
            <span class="zone-name">{snapshot['zone']}</span>{_status_badge(zone_status)}</div>
          <div class="sensor-readings">
            {''.join(_render_sensor_row(key, reading) for key, reading in snapshot['readings'].items())}
          </div>
          <div class="card-foot">SIMULATED · {snapshot['scenario']}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _render_sensor_row(sensor_key: str, reading: dict) -> str:
    value = "Unavailable" if reading["value"] is None else f"{reading['value']:g} {reading['unit']}"
    return (
        '<div class="sensor-reading">'
        f'<div><span>{reading["label"].upper()}</span><strong>{value}</strong></div>'
        f'{_status_badge(reading["status"])}'
        '</div>'
    )


def _render_history(history: pd.DataFrame, zone: str) -> None:
    st.markdown('<div class="section-heading">Historical monitoring</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-note">SIMULATED readings · recent history is restored from local storage when available</div>', unsafe_allow_html=True)
    selected_zone = st.selectbox("Industrial zone", ZONES, key="sensor_history_zone")
    zone_history = history[history["zone"] == selected_zone].copy()

    chart_columns = st.columns(3)
    chart_specs = [
        ("temperature", "Temperature", "°C", "#60a5fa"),
        ("smoke", "Smoke level", "SU", "#fb923c"),
        ("gas", "Gas concentration", "ppm", "#c084fc"),
    ]
    for column, (sensor_key, label, unit, color) in zip(chart_columns, chart_specs):
        chart_data = zone_history[
            (zone_history["sensor"] == sensor_key) & zone_history["value"].notna()
        ].sort_values("timestamp")
        with column:
            st.markdown(f'<div class="section-note">{label} · {unit} · {selected_zone}</div>', unsafe_allow_html=True)
            figure = px.line(
                chart_data,
                x="timestamp",
                y="value",
                markers=True,
                custom_data=["scenario", "status"],
                labels={"timestamp": "Updated", "value": f"{label} ({unit})"},
            )
            figure.update_traces(
                line={"color": color, "width": 2.5},
                marker={"size": 7},
                hovertemplate="%{x|%H:%M:%S}<br>%{y} " + unit + "<br>%{customdata[0]} · %{customdata[1]}<extra></extra>",
            )
            figure.update_layout(
                height=250,
                margin={"l": 8, "r": 8, "t": 18, "b": 8},
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font={"color": "#a9bac8", "family": "DM Sans, sans-serif", "size": 10},
                xaxis={"title": None, "gridcolor": "#233440"},
                yaxis={"title": None, "gridcolor": "#233440"},
                showlegend=False,
            )
            st.plotly_chart(figure, use_container_width=True, config={"displayModeBar": False}, key=f"sensor_chart_{sensor_key}")

    recent = zone_history.sort_values("timestamp", ascending=False).head(24).copy()
    recent["timestamp"] = recent["timestamp"].dt.strftime("%d %b %Y · %H:%M:%S")
    recent["sensor"] = recent["sensor"].map(lambda key: SENSOR_LABELS[key][0])
    recent = recent.rename(columns={
        "timestamp": "Timestamp",
        "zone": "Zone",
        "sensor": "Sensor",
        "value": "Reading",
        "unit": "Unit",
        "status": "Health",
        "scenario": "Scenario",
    })
    st.dataframe(
        recent[["Timestamp", "Zone", "Sensor", "Reading", "Unit", "Health", "Scenario"]],
        use_container_width=True,
        hide_index=True,
        column_config={"Reading": st.column_config.NumberColumn("Reading", format="%.1f")},
    )


@st.fragment(run_every="15s")
def render_sensor_monitoring() -> None:
    """Render sensor readings with a periodic, session-local simulated refresh."""
    inject_theme()
    st.markdown('<div class="eyebrow">Industrial safety monitoring</div>', unsafe_allow_html=True)
    st.markdown('<div class="main-title">Sensor Monitoring</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Zone readings, sensor health and session history</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="notice">SIMULATED DATA — values are generated examples. Smoke uses a demo sensor unit (SU); gas uses illustrative ppm values. No physical sensor connection is active. Display bands are demonstration cues, not certified safety limits.</div>',
        unsafe_allow_html=True,
    )

    scenario_col, refresh_col, time_col = st.columns([2, 1, 2])
    with scenario_col:
        scenario = st.selectbox("Simulation scenario", SCENARIOS, key="sensor_scenario")
    with refresh_col:
        st.markdown('<div style="height:28px"></div>', unsafe_allow_html=True)
        refresh = st.button("↻ Refresh Readings", use_container_width=True)
    timestamp = datetime.now().astimezone()
    previous_update = st.session_state.get("sensor_last_updated")
    cached_snapshots = st.session_state.get("sensor_current_snapshots")
    elapsed = (timestamp - previous_update).total_seconds() if previous_update else None
    refresh_due = (
        not cached_snapshots
        or st.session_state.get("sensor_current_scenario") != scenario
        or refresh
        or elapsed is None
        or elapsed >= 15
    )
    if refresh_due:
        snapshots = generate_readings(scenario, timestamp)
        _append_history(snapshots)
        st.session_state.sensor_last_updated = timestamp
        st.session_state.sensor_current_snapshots = snapshots
        st.session_state.sensor_current_scenario = scenario
    else:
        snapshots = cached_snapshots
        timestamp = previous_update
    with time_col:
        updated_text = timestamp.strftime("%d %b %Y · %H:%M:%S %Z")
        st.markdown('<div style="height:28px"></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="time-stamp">Last updated<br><b>{updated_text}</b> · SIMULATED</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-heading">Zone sensor status</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-note">Per-sensor health is scenario-driven for demonstration; ONLINE · WARNING · OFFLINE</div>', unsafe_allow_html=True)
    zone_columns = st.columns(2)
    for index, snapshot in enumerate(snapshots):
        with zone_columns[index % 2]:
            _render_zone_card(snapshot)

    if scenario == "Sensor Failure":
        st.error("SIMULATED SENSOR FAILURE: the Electrical Room smoke sensor is OFFLINE. Its reading is unavailable.")
    elif scenario != "Normal Conditions":
        st.warning(f"SIMULATED SCENARIO ACTIVE: {scenario}. Highlighted sensors show example changes only.")

    history = pd.DataFrame(st.session_state.sensor_history)
    if not history.empty:
        history["timestamp"] = pd.to_datetime(history["timestamp"], utc=True)
        _render_history(history, ZONES[0])

