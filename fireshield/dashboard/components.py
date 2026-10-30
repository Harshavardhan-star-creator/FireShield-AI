"""Reusable dashboard presentation components."""

import streamlit as st


RISK_STYLES = {
    "WATCH": ("#34d399", "rgba(52, 211, 153, .12)"),
    "ALERT": ("#fb923c", "rgba(251, 146, 60, .13)"),
    "ACT": ("#fb5656", "rgba(251, 86, 86, .14)"),
    "UNAVAILABLE": ("#94a3b8", "rgba(148, 163, 184, .12)"),
}


def risk_state(risk: float) -> str:
    if risk >= 70:
        return "ACT"
    if risk >= 40:
        return "ALERT"
    return "WATCH"


def render_zone_card(zone: dict[str, object]) -> None:
    risk = zone.get("risk")
    status = str(zone.get("risk_level") or (risk_state(float(risk)) if risk is not None else "UNAVAILABLE"))
    color, tint = RISK_STYLES[status]
    risk_text = "—" if risk is None else f"{float(risk):g}<small>%</small>"
    risk_width = 0 if risk is None else max(0, min(100, float(risk)))

    def metric(key: str, unit: str, precision: int = 1) -> str:
        value = zone.get(key)
        shown = "Unavailable" if value is None else f"{float(value):.{precision}f}"
        return f"{shown} <small>{unit}</small>" if value is not None else shown

    st.markdown(
        f"""
        <section class="zone-card" style="--risk:{color}; --risk-tint:{tint}">
          <div class="zone-top"><span class="zone-dot"></span>
            <span class="zone-name">{zone['zone']}</span>
            <span class="risk-pill">{status}</span></div>
          <div class="risk-number">{risk_text}
            <span class="risk-caption">RULE-BASED RISK</span></div>
          <div class="risk-track"><span style="width:{risk_width}%"></span></div>
          <div class="sensor-grid">
            <div><span>TEMPERATURE</span><strong>{metric('temperature', '°C')}</strong></div>
            <div><span>SMOKE</span><strong>{metric('smoke', 'SU')}</strong></div>
            <div><span>GAS</span><strong>{metric('gas', 'ppm')}</strong></div>
            <div><span>HUMIDITY</span><strong>{metric('humidity', '%RH')}</strong></div>
          </div>
          <div class="card-foot">{('Evidence incomplete · ' + ', '.join(zone.get('missing_evidence', []))) if not zone.get('risk_complete', True) else 'Evidence complete for current inputs'} · readings simulated where labelled</div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def inject_theme() -> None:
    st.markdown(
        """
        <style>
        :root { color-scheme:dark; --page:#0b1219; --surface:#131e28; --surface-raised:#172430; --line:#293b49; --muted:#91a2b1; --text:#e8eef4; }
        .stApp { background:radial-gradient(ellipse at 52% -18%,#1a2c3b 0%,var(--page) 55%); color:var(--text); }
        html,body,[class*="css"] { font-family:Inter,"Segoe UI",Arial,sans-serif; }
        [data-testid="stSidebar"] { background:#0d151d; border-right:1px solid #20303c; }
        [data-testid="stSidebar"] [data-testid="stRadio"] label { padding:.2rem 0; }
        [data-testid="stHeader"] { background:transparent; }
        .block-container { max-width:1440px; padding:1.25rem 2rem 2.5rem; }
        [data-testid="stVerticalBlock"] { gap:.8rem; }
        h1,h2,h3,.main-title,.metric-value,.risk-number,.section-heading { font-family:"Segoe UI",Arial,sans-serif !important; letter-spacing:-.025em; }
        h1,h2,h3 { color:var(--text); }
        .eyebrow { color:#91a6b7; text-transform:uppercase; font-size:.69rem; letter-spacing:.14em; font-weight:700; }
        .main-title { font-weight:700; font-size:2rem; line-height:1.12; color:#f4f7fb; margin:.15rem 0; }
        .sub-title { color:#9aaab8; font-size:.9rem; }
        .system-badge { display:inline-flex; align-items:center; gap:8px; padding:8px 12px; background:#15251f; border:1px solid #31513f; border-radius:999px; color:#a9e7c2; font-weight:650; font-size:.76rem; white-space:nowrap; }
        .system-badge span { width:7px;height:7px;border-radius:50%;background:#49d58c; }
        .time-stamp { color:#b2c0cc; font-size:.78rem; text-align:right; line-height:1.55; }
        .section-heading { color:#edf2f6; font-size:1.05rem;font-weight:650;margin:1rem 0 .1rem; }
        .section-note { color:#8294a3;font-size:.77rem;margin-bottom:.65rem; line-height:1.45; }
        .metric-card { background:linear-gradient(145deg,#182632,#121c26); border:1px solid var(--line); padding:16px 18px; border-radius:13px; min-height:100px; }
        .metric-label { color:#9aabba;font-size:.69rem;text-transform:uppercase;letter-spacing:.085em;font-weight:650; }
        .metric-value { color:#f1f5f9;font-size:1.7rem;font-weight:700;margin-top:6px; }
        .metric-sub { color:#8293a1;font-size:.73rem;margin-top:3px;line-height:1.45; }
        .health-list { background:rgba(19,30,40,.75);border:1px solid #293b49;border-radius:11px;padding:4px 12px; }
        .health-row { padding:8px 0;border-bottom:1px solid #263642; }
        .health-row:last-child { border-bottom:0; }
        .health-row-top { display:flex;align-items:center;justify-content:space-between;gap:8px; }
        .health-name { color:#dfe7ed;font-size:.75rem;font-weight:600; }
        .health-status { font-size:.64rem;font-weight:750;letter-spacing:.045em;white-space:nowrap; }
        .health-detail { color:#8293a1;font-size:.67rem;line-height:1.35;margin-top:3px; }
        .zone-card { background:linear-gradient(150deg,#182632,#121c25);border:1px solid #2a3d4b;border-radius:14px;padding:17px 18px 13px;margin-bottom:10px;box-shadow:0 8px 20px rgba(0,0,0,.12); }
        .zone-top { display:flex;align-items:center;gap:9px;min-width:0; }
        .zone-dot { flex:0 0 8px;width:8px;height:8px;border-radius:50%;background:var(--risk); }
        .zone-name { color:#edf2f6;font-weight:650;font-size:.9rem;flex:1;overflow:hidden;text-overflow:ellipsis; }
        .risk-pill { color:var(--risk);background:var(--risk-tint);padding:4px 9px;border-radius:999px;font-size:.63rem;letter-spacing:.075em;font-weight:750; }
        .risk-number { color:#f5f8fa;font-size:1.9rem;font-weight:700;margin-top:15px;line-height:1; }
        .risk-number small { font-size:.95rem;color:#a6b4c0; }
        .risk-caption { color:#8293a1;font-size:.6rem;letter-spacing:.09em;margin-left:8px;font-weight:650; }
        .risk-track { background:#293945;height:5px;border-radius:5px;margin:11px 0 15px;overflow:hidden; }
        .risk-track span { display:block;height:100%;background:var(--risk);border-radius:5px; }
        .sensor-grid { display:grid;grid-template-columns:1fr 1fr;gap:13px 12px; }
        .sensor-grid div { display:flex;flex-direction:column;gap:4px;min-width:0; }
        .sensor-grid span { color:#8395a4;font-size:.59rem;letter-spacing:.09em;font-weight:700; }
        .sensor-grid strong { color:#e0e8ee;font-size:.88rem;font-weight:650; }
        .sensor-grid small { color:#93a4b1;font-size:.67rem;font-weight:500; }
        .card-foot { border-top:1px solid #2a3a46;margin-top:13px;padding-top:9px;color:#8293a1;font-size:.66rem;line-height:1.4; }
        .notice { background:#15222d;border:1px solid #304554;border-radius:10px;padding:10px 13px;color:#b0bfca;font-size:.75rem;line-height:1.5; }
        div[data-testid="stDataFrame"],div[data-testid="stPlotlyChart"] { border:1px solid #293b49;border-radius:11px;overflow:hidden;background:rgba(18,28,38,.42); }
        div[data-testid="stDataFrame"] { padding:3px; }
        div[data-testid="stExpander"] { border-color:#2b3d4a;border-radius:10px;background:rgba(19,30,40,.55); }
        div[data-testid="stButton"] button { border-radius:8px; min-height:2.35rem; font-weight:600; }
        div[data-testid="stSelectbox"] [data-baseweb="select"] > div { border-color:#334755; }
        hr { border-color:#293a46 !important; }
        .sensor-zone-card { min-height:260px; }
        .sensor-readings { display:grid; grid-template-columns:1fr 1fr; gap:11px 13px; margin-top:17px; }
        .sensor-reading { display:flex; justify-content:space-between; align-items:center; gap:7px; padding:9px 10px; background:rgba(255,255,255,.025); border:1px solid #2a3a46; border-radius:9px; min-width:0; }
        .sensor-reading div { display:flex; flex-direction:column; gap:5px; min-width:0; }
        .sensor-reading span { color:#8395a4; font-size:.58rem; letter-spacing:.075em; font-weight:700; }
        .sensor-reading strong { color:#e0e8ee; font-size:.81rem; font-weight:650; white-space:nowrap; }
        .sensor-status { display:inline-flex; align-items:center; gap:5px; color:var(--status-color); font-size:.57rem; letter-spacing:.035em; font-weight:750; white-space:nowrap; }
        .sensor-status i { width:6px; height:6px; border-radius:50%; background:var(--status-color); }
        @media (max-width:1000px) {
          .block-container { padding:1rem 1.1rem 2rem; }
          .main-title { font-size:1.75rem; }
          .metric-card { padding:14px; }
        }
        @media (max-width:700px) {
          .block-container { padding:.8rem .75rem 1.5rem; }
          .main-title { font-size:1.55rem; }
          .zone-card { padding:14px; }
          .sensor-reading { padding:8px; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

