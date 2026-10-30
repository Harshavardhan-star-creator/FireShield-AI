"""Dashboard page for the FireShield AI prototype."""

from datetime import datetime
from html import escape
import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from fireshield.dashboard.components import inject_theme, render_zone_card
from fireshield.dashboard.risk_data import get_dashboard_risk_data
from fireshield.database import check_database_connection, safe_record_event
from fireshield.decision_engine import DecisionEngine
from fireshield.suppression_control import (
    ACTIVATED,
    ARMED,
    STANDBY,
    VirtualSuppressionController,
)
from fireshield.system_health import STATUS_COLORS, collect_system_health


RISK_COLORS = {"WATCH": "#34d399", "ALERT": "#fb923c", "ACT": "#fb5656"}


def _cached_database_health() -> bool:
    cached = st.session_state.get("_database_health_check")
    if cached and time.monotonic() - cached[0] < 15:
        return cached[1]
    result = check_database_connection()
    st.session_state["_database_health_check"] = (time.monotonic(), result)
    return result


def render_dashboard() -> None:
    """Render the industrial dashboard with explainable rule-based zone risk."""
    inject_theme()
    now = datetime.now().astimezone()
    zone_rows, risk_results = get_dashboard_risk_data(
        st.session_state.get("sensor_history"),
        st.session_state.get("camera_detection_history"),
        now,
    )
    zones = pd.DataFrame(zone_rows)
    decision_engine = st.session_state.get("decision_engine")
    if not isinstance(decision_engine, DecisionEngine):
        decision_engine = DecisionEngine()
        st.session_state.decision_engine = decision_engine
    decisions_by_zone = {}
    for zone_row, risk_result in zip(zone_rows, risk_results):
        decisions_by_zone[risk_result["zone"]] = decision_engine.evaluate(
            risk_result,
            zone_row["decision_evidence"],
            now=now,
            observed_at=zone_row["observed_at"],
        )
        risk_timestamp = zone_row.get("observed_at") or now
        risk_details = {
            "score": risk_result.get("score"),
            "level": risk_result.get("level"),
            "complete": risk_result.get("complete"),
            "missing_evidence": risk_result.get("missing_evidence", []),
            "factors": risk_result.get("factors", []),
            "reason": risk_result.get("reason"),
            "scenario": zone_row.get("scenario"),
            "sensor_evidence": zone_row.get("decision_evidence", []),
        }
        safe_record_event(
            "risk_assessment", timestamp=risk_timestamp,
            zone_id=risk_result["zone"], details=risk_details,
        )
    suppression_controller = st.session_state.get("suppression_controller")
    if not isinstance(suppression_controller, VirtualSuppressionController):
        suppression_controller = VirtualSuppressionController()
        st.session_state.suppression_controller = suppression_controller
    for decision in decisions_by_zone.values():
        suppression_controller.update(decision, now=now)
    for record in decision_engine.history:
        safe_record_event(
            "decision_history", timestamp=record.get("timestamp"),
            zone_id=record.get("zone", "Unknown zone"), details=record,
        )
        if record.get("decision_source") == "OPERATOR_OVERRIDE":
            safe_record_event(
                "operator_override", timestamp=record.get("timestamp"),
                zone_id=record.get("zone", "Unknown zone"), details=record,
                event_key=(
                    f"decision-override:{record.get('zone')}:{record.get('timestamp')}:{record.get('decision')}"
                ),
            )
    for record in suppression_controller.event_history:
        safe_record_event(
            "suppression_event", timestamp=record.get("timestamp"),
            zone_id=record.get("zone", "Unknown zone"), details=record,
        )
    sensor_health_data = list(st.session_state.get("sensor_history", []))
    if not sensor_health_data:
        # Dashboard fallback values come from the existing simulated sensor generator.
        for row in zone_rows:
            for key in ("temperature", "smoke", "gas"):
                value = row.get(key)
                if value is not None:
                    sensor_health_data.append({
                        "zone": row["zone"], "sensor": key, "value": value,
                        "timestamp": row.get("observed_at") or now,
                        "status": "ONLINE", "simulated": True,
                    })
    health = collect_system_health(
        sensor_history=sensor_health_data,
        camera_capture_available=st.session_state.get("camera_capture") is not None,
        model_status=st.session_state.get("camera_model_status"),
        database_check=_cached_database_health,
        risk_engine_ready=True,
        decision_engine_ready=isinstance(decision_engine, DecisionEngine),
        suppression_controller_ready=isinstance(suppression_controller, VirtualSuppressionController),
        now=now,
    )
    active_alerts = sum(result["level"] in {"ALERT", "ACT"} for result in risk_results)
    available_scores = [result["score"] for result in risk_results if result["score"] is not None]
    average_risk = sum(available_scores) / len(available_scores) if available_scores else None

    left, right = st.columns([3, 1])
    with left:
        st.markdown('<div class="eyebrow">Industrial safety monitoring</div>', unsafe_allow_html=True)
        st.markdown('<div class="main-title">🔥 FireShield AI</div>', unsafe_allow_html=True)
        st.markdown('<div class="sub-title">Facility monitoring control centre</div>', unsafe_allow_html=True)
    with right:
        st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
        st.markdown('<div class="system-badge"><span></span> SIMULATION MODE</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="time-stamp" style="margin-top:9px">{now.strftime("%A, %d %B %Y · %H:%M:%S %Z")}</div>', unsafe_allow_html=True)

    st.markdown('<div class="notice">SIMULATED SENSOR DATA · Risk scores are calculated by a deterministic, explainable rules engine from available sensor readings and recent actual camera model detections. Missing camera or sensor evidence is shown as incomplete, never assumed normal. Demo breakpoints are illustrative and are not certified safety limits. No physical control is active.</div>', unsafe_allow_html=True)

    _render_system_health(health)

    st.markdown('<div class="section-heading">Facility overview</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-note">Current summary across the monitored example zones</div>', unsafe_allow_html=True)
    metrics = st.columns(3)
    metric_items = [
        ("TOTAL ZONES", f"{len(zones):02d}", "Configured example areas"),
        ("ACTIVE ALERTS", f"{active_alerts:02d}", "Zones in ALERT or ACT state"),
        ("AVERAGE RISK", f"{average_risk:.1f}%" if average_risk is not None else "Unavailable", "Mean of available rule-based scores"),
    ]
    for column, (label, value, subtext) in zip(metrics, metric_items):
        with column:
            st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div><div class="metric-sub">{subtext}</div></div>', unsafe_allow_html=True)

    st.markdown('<div class="section-heading">Zone status</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-note">Simulated sensor readings · actual recent model detections when available · rule-based risk score</div>', unsafe_allow_html=True)
    zone_columns = st.columns(2)
    for index, zone in zones.iterrows():
        with zone_columns[index % 2]:
            render_zone_card(zone.to_dict())

    st.markdown('<div class="section-heading">Risk factors and classification reasons</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-note">Each score is the sum of configured demo contributions, capped at 100. Incomplete evidence is called out and is not an all-clear.</div>', unsafe_allow_html=True)
    detail_columns = st.columns(2)
    for index, result in enumerate(risk_results):
        with detail_columns[index % 2]:
            score_label = "Unavailable" if result["score"] is None else f"{result['score']}/100"
            with st.expander(f"{result['zone']} · {result['level']} · {score_label}"):
                st.write(result["reason"])
                factor_rows = []
                for factor in result["factors"]:
                    value = factor["value"]
                    if value is not None and factor["unit"] == "confidence":
                        shown_value = f"{value:.3f}"
                    elif value is not None:
                        shown_value = f"{value:g} {factor['unit']}"
                    else:
                        shown_value = "Unavailable"
                    factor_rows.append({
                        "Factor": factor["label"],
                        "Reading": shown_value,
                        "Risk points": factor["contribution"],
                        "Evidence": factor["detail"],
                    })
                st.dataframe(pd.DataFrame(factor_rows), hide_index=True, use_container_width=True)

    st.markdown('<div class="section-heading">Intelligent Decision Engine</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-note">Automatic policy decisions from the risk engine · ACT requires complete, reliable, independent fresh sources and sustained confirmation</div>', unsafe_allow_html=True)
    for result in risk_results:
        decision = decisions_by_zone[result["zone"]]
        if decision["notification"]:
            st.error(
                f"HIGH PRIORITY OPERATOR NOTIFICATION · {decision['zone']} · "
                + " ".join(decision["reasons"])
            )
        decision_col, control_col = st.columns([4, 1])
        with decision_col:
            st.markdown(
                f"**{decision['zone']} · {decision['decision']}**  "
                f"`{decision['decision_source']}` · {decision['action']}"
            )
            for reason in decision["reasons"]:
                st.caption(f"• {reason}")
            st.caption(
                f"Virtual suppression: {decision['virtual_suppression']['state']} · "
                "hardware control: disabled"
            )
        with control_col:
            if decision["operator_hold"]:
                if st.button("Release operator hold", key=f"release_decision_hold_{result['zone']}"):
                    decisions_by_zone[result["zone"]] = decision_engine.evaluate(
                        result,
                        next(row["decision_evidence"] for row in zone_rows if row["zone"] == result["zone"]),
                        now=datetime.now().astimezone(),
                        observed_at=next(row["observed_at"] for row in zone_rows if row["zone"] == result["zone"]),
                        operator_override="RELEASE_HOLD",
                    )
                    suppression_controller.release_cancellation(result["zone"])
                    safe_record_event(
                        "operator_override", timestamp=datetime.now().astimezone(),
                        zone_id=result["zone"],
                        details={"action": "RELEASE_HOLD", "source": "decision_engine"},
                    )
                    st.rerun()
            elif result["level"] == "ACT":
                if st.button("Cancel ACT / hold ALERT", key=f"cancel_decision_act_{result['zone']}"):
                    suppression_controller.cancel(
                        result["zone"], decision, now=datetime.now().astimezone()
                    )
                    safe_record_event(
                        "operator_override", timestamp=datetime.now().astimezone(),
                        zone_id=result["zone"],
                        details={"action": "HOLD_ALERT", "source": "decision_engine"},
                    )
                    decisions_by_zone[result["zone"]] = decision_engine.evaluate(
                        result,
                        next(row["decision_evidence"] for row in zone_rows if row["zone"] == result["zone"]),
                        now=datetime.now().astimezone(),
                        observed_at=next(row["observed_at"] for row in zone_rows if row["zone"] == result["zone"]),
                        operator_override="HOLD_ALERT",
                    )
                    st.rerun()

    st.markdown('<div class="section-heading">Virtual Suppression Control</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-note">Virtual interface only · activation requires explicit authorization from the decision engine · no physical equipment is connected</div>', unsafe_allow_html=True)
    status_colors = {STANDBY: "#9aa8b5", ARMED: "#fb923c", ACTIVATED: "#fb5656"}
    suppression_columns = st.columns(2)
    for index, zone in enumerate(zone_rows):
        name = zone["zone"]
        suppression_state = suppression_controller.get_state(name)
        decision = decisions_by_zone[name]
        with suppression_columns[index % 2]:
            state_color = status_colors.get(suppression_state["status"], "#9aa8b5")
            st.markdown(
                f'<div class="metric-card"><div class="metric-label">{name}</div>'
                f'<div class="metric-value" style="font-size:23px;color:{state_color}">{suppression_state["status"]}</div>'
                f'<div class="metric-sub">Triggering decision: {suppression_state["triggering_decision"]}</div>'
                f'<div class="metric-sub">Activation timestamp: {suppression_state["activation_timestamp"].strftime("%d %b %Y · %H:%M:%S %Z") if suppression_state["activation_timestamp"] else "—"}</div>'
                f'<div class="metric-sub">Operator override: {suppression_state["operator_override_status"]}</div>'
                f'<div class="metric-sub">{suppression_state["reason"]}</div></div>',
                unsafe_allow_html=True,
            )
            if suppression_controller.cancellation_active(name):
                if st.button("Release suppression cancel", key=f"release_suppression_cancel_{name}"):
                    suppression_controller.release_cancellation(name)
                    safe_record_event(
                        "operator_override", timestamp=datetime.now().astimezone(),
                        zone_id=name,
                        details={"action": "RELEASE_SUPPRESSION_CANCEL", "source": "operator"},
                    )
                    st.rerun()
            elif suppression_state["status"] != STANDBY or decision["decision"] in {"ALERT", "ACT"}:
                if st.button("Cancel virtual suppression", key=f"cancel_suppression_{name}"):
                    suppression_controller.cancel(name, decision, now=datetime.now().astimezone())
                    safe_record_event(
                        "operator_override", timestamp=datetime.now().astimezone(),
                        zone_id=name,
                        details={"action": "CANCEL_SUPPRESSION", "source": "operator"},
                    )
                    st.rerun()

    persisted_suppression = st.session_state.get("suppression_event_history", [])
    suppression_records = _merge_recent(
        persisted_suppression, suppression_controller.event_history, "timestamp", "zone", "status", "decision"
    )
    suppression_history = pd.DataFrame(suppression_records[-30:])
    st.markdown('<div class="section-heading">Suppression event history</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-note">Virtual state changes restored from local history, including operator cancellation and authorization denials</div>', unsafe_allow_html=True)
    if suppression_history.empty:
        st.info("No virtual suppression state changes have been recorded yet.")
    else:
        suppression_history["timestamp"] = pd.to_datetime(suppression_history["timestamp"], utc=True).dt.strftime("%d %b %Y · %H:%M:%S %Z")
        suppression_history = suppression_history.rename(columns={
            "timestamp": "Timestamp", "zone": "Zone", "status": "Status",
            "decision": "Triggering decision", "reason": "Reason",
            "operator_override_status": "Operator override", "evidence": "Evidence",
        })
        st.dataframe(
            suppression_history[["Timestamp", "Zone", "Status", "Triggering decision", "Reason", "Operator override", "Evidence"]].iloc[::-1],
            use_container_width=True,
            hide_index=True,
        )

    override_history = pd.DataFrame(st.session_state.get("operator_override_history", [])[-30:])
    st.markdown('<div class="section-heading">Operator override history</div>', unsafe_allow_html=True)
    if override_history.empty:
        st.info("No operator overrides have been recorded.")
    else:
        if "timestamp" in override_history:
            override_history["timestamp"] = pd.to_datetime(override_history["timestamp"], utc=True).dt.strftime("%d %b %Y · %H:%M:%S %Z")
        if "action" not in override_history:
            override_history["action"] = override_history.get("decision", "Operator override")
        if "source" not in override_history:
            override_history["source"] = override_history.get("decision_source", "operator")
        override_history = override_history.rename(columns={
            "timestamp": "Timestamp", "zone": "Zone", "action": "Action", "source": "Source",
        })
        st.dataframe(
            override_history[[column for column in ("Timestamp", "Zone", "Action", "Source") if column in override_history]],
            use_container_width=True,
            hide_index=True,
        )

    persisted_decisions = st.session_state.get("decision_history", [])
    decision_records = _merge_recent(
        persisted_decisions, decision_engine.history, "timestamp", "zone", "decision", "decision_source"
    )
    decision_history = pd.DataFrame(decision_records[-30:])
    st.markdown('<div class="section-heading">Decision history</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-note">Recent persistent records · automatic decisions and operator overrides are distinguished</div>', unsafe_allow_html=True)
    if decision_history.empty:
        st.info("No decision evaluations have been recorded yet.")
    else:
        decision_history["evidence"] = decision_history["evidence"].map(
            lambda items: "; ".join(
                f"{item.get('source')}: {item.get('value', item.get('confidence', '—'))}"
                for item in items
                if item.get("supports_risk")
            ) or "No contributing evidence recorded"
        )
        decision_history["timestamp"] = pd.to_datetime(decision_history["timestamp"], utc=True).dt.strftime("%d %b %Y · %H:%M:%S %Z")
        decision_history = decision_history.rename(columns={
            "timestamp": "Timestamp",
            "zone": "Zone",
            "decision": "Decision",
            "decision_source": "Decision source",
            "risk_score": "Risk score",
            "evidence": "Contributing evidence",
        })
        st.dataframe(
            decision_history[["Timestamp", "Zone", "Decision", "Decision source", "Risk score", "Contributing evidence"]].iloc[::-1],
            use_container_width=True,
            hide_index=True,
        )

    st.markdown('<div class="section-heading">Risk comparison</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-note">Rule-based risk from available evidence · WATCH 0–39 · ALERT 40–69 · ACT 70–100</div>', unsafe_allow_html=True)
    chart_col, legend_col = st.columns([3, 1])
    with chart_col:
        states = zones["risk_level"]
        figure = go.Figure(go.Bar(
            x=zones["zone"], y=zones["risk"],
            marker={"color": [RISK_COLORS.get(state, "#718096") for state in states], "line": {"width": 0}},
            text=["—" if pd.isna(value) else f"{value:.1f}%" for value in zones["risk"]], textposition="outside",
            hovertemplate="%{x}<br>Rule-based score: %{y}%<extra></extra>",
        ))
        figure.update_layout(
            height=310, margin={"l": 12, "r": 18, "t": 28, "b": 18},
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font={"color": "#c0cbd4", "family": "Segoe UI, Arial, sans-serif", "size": 11},
            yaxis={"range": [0, 108], "title": None, "gridcolor": "#293b49", "ticksuffix": "%", "tickvals": [0, 20, 40, 60, 80, 100], "zeroline": False},
            xaxis={"title": None, "tickfont": {"size": 11}, "gridcolor": "rgba(0,0,0,0)"},
            showlegend=False,
        )
        for threshold in (40, 70):
            figure.add_hline(
                y=threshold,
                line_width=1,
                line_dash="dot",
                line_color="#536573",
                opacity=.7,
            )
        st.plotly_chart(figure, use_container_width=True, config={"displayModeBar": False})
    with legend_col:
        for state, color in RISK_COLORS.items():
            st.markdown(f'<div style="display:flex;align-items:center;gap:9px;margin:12px 0;color:#b6c3ce"><span style="width:9px;height:9px;border-radius:50%;background:{color}"></span><b>{state}</b></div>', unsafe_allow_html=True)
        st.markdown('<div class="section-note" style="margin-top:20px">Thresholds are demo labels only; they are not safety guidance.</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-heading">Recent alert history</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-note">Current and recent persisted risk classifications</div>', unsafe_allow_html=True)
    alert_rows = [
        {
            "Timestamp": now,
            "Zone": result["zone"],
            "Severity": result["level"],
            "Risk": result["score"],
            "Event": result["reason"],
        }
        for result in risk_results
        if result["level"] in {"ALERT", "ACT"}
    ]
    for record in st.session_state.get("risk_history", []):
        if record.get("level") in {"ALERT", "ACT"}:
            alert_rows.append({
                "Timestamp": record.get("timestamp"),
                "Zone": record.get("zone", "Unknown zone"),
                "Severity": record.get("level"),
                "Risk": record.get("score"),
                "Event": record.get("reason", "Persisted risk assessment"),
            })
    if alert_rows:
        unique_alerts = {}
        for row in alert_rows:
            identity = (str(row["Timestamp"]), row["Zone"], row["Severity"], row["Risk"])
            unique_alerts[identity] = row
        alert_rows = sorted(unique_alerts.values(), key=lambda row: str(row["Timestamp"]))[-100:]
    if alert_rows:
        alert_frame = pd.DataFrame(alert_rows)
        st.dataframe(
            alert_frame.style.map(lambda value: f"color: {RISK_COLORS.get(value, '#dce5ec')}; font-weight: 700" if value in RISK_COLORS else "", subset=["Severity"]),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Timestamp": st.column_config.DatetimeColumn("Timestamp", format="DD MMM YYYY, HH:mm:ss"),
                "Risk": st.column_config.NumberColumn("Risk", format="%.1f/100"),
                "Event": st.column_config.TextColumn("Event", width="large"),
            },
        )
    else:
        st.info("No zones currently classify as ALERT or ACT from available evidence.")
    st.caption("FireShield AI is a college project prototype. Risk outputs are illustrative rules, not certified limits or operational fire-safety decisions.")


def _render_system_health(health: dict) -> None:
    """Render compact health indicators without probing devices or loading models."""
    status = health["overall_status"]
    color = STATUS_COLORS[status]
    st.markdown('<div class="section-heading">System Health</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="metric-card" style="margin-bottom:10px"><div class="metric-label">OVERALL SYSTEM HEALTH</div>'
        f'<div class="metric-value" style="font-size:22px;color:{color}">{escape(status)}</div>'
        '<div class="metric-sub">Sensor statuses describe data availability. Simulated readings do not indicate physical connectivity.</div></div>',
        unsafe_allow_html=True,
    )
    columns = st.columns(3)
    grouped_components = [health["components"][index::3] for index in range(3)]
    for column, components in zip(columns, grouped_components):
        rows = []
        for component in components:
            component_color = STATUS_COLORS[component["status"]]
            rows.append(
                '<div class="health-row">'
                '<div class="health-row-top">'
                f'<span class="health-name">{escape(component["name"])}</span>'
                f'<span class="health-status" style="color:{component_color}">{escape(component["status"])}</span>'
                '</div>'
                f'<div class="health-detail">{escape(component["detail"])}</div>'
                '</div>'
            )
        with column:
            st.markdown(
                f'<div class="health-list">{"".join(rows)}</div>',
                unsafe_allow_html=True,
            )


def _merge_recent(persisted, current, *identity_fields):
    """Combine restored SQLite rows and live session records without rerun duplicates."""
    merged = {}
    for record in list(persisted or []) + list(current or []):
        if not isinstance(record, dict):
            continue
        key = tuple(str(record.get(field)) for field in identity_fields)
        merged[key] = record
    return sorted(
        merged.values(),
        key=lambda record: str(record.get("timestamp", "")),
    )
