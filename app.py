"""Offline race-control demonstration for FlagSense."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import Config
from src.pipeline import AnalysisResult, SafetyPipeline
from src.telemetry import load_telemetry
from src.track import Track, load_track


CONFIG = Config()
FLAG_COLORS = {
    "GREEN": "#29c98b",
    "YELLOW": "#f6c453",
    "RED_RECOMMENDED": "#ff5b62",
}
CLASS_COLORS = {
    "NORMAL": "#29c98b",
    "MODERATE_RISK": "#f6c453",
    "HIGH_RISK": "#ff5b62",
}


@st.cache_data
def demo_frames():
    return load_telemetry(CONFIG.demo_path)


@st.cache_data
def demo_track() -> Track:
    return load_track(CONFIG.track_path)


def reset_playback() -> None:
    frames = demo_frames()
    pipeline = SafetyPipeline(CONFIG, demo_track())
    st.session_state.pipeline = pipeline
    st.session_state.playback_index = 0
    st.session_state.latest_result = pipeline.update(frames[0])
    st.session_state.result_history = [st.session_state.latest_result]
    st.session_state.running = False


def advance_playback() -> None:
    frames = demo_frames()
    steps = 2 * int(st.session_state.speed_multiplier)
    for _ in range(steps):
        next_index = st.session_state.playback_index + 1
        if next_index >= len(frames):
            st.session_state.running = False
            break
        result = st.session_state.pipeline.update(frames[next_index])
        st.session_state.playback_index = next_index
        st.session_state.latest_result = result
        st.session_state.result_history.append(result)


def track_figure(result: AnalysisResult, track: Track) -> go.Figure:
    figure = go.Figure()
    xs, ys = zip(*track.points)
    figure.add_trace(
        go.Scatter(
            x=xs,
            y=ys,
            mode="lines",
            line={"color": "#55718d", "width": 13},
            hoverinfo="skip",
            showlegend=False,
        )
    )
    incident_id = result.incident["car_id"] if result.incident else None
    approaching_id = (
        result.closest_approaching_car["car_id"]
        if result.closest_approaching_car
        else None
    )
    for car in result.vehicles:
        is_incident = car["car_id"] == incident_id
        is_approaching = car["car_id"] == approaching_id
        color = "#ff5b62" if is_incident else "#f6c453" if is_approaching else "#73c7ee"
        size = 19 if is_incident else 16 if is_approaching else 13
        figure.add_trace(
            go.Scatter(
                x=[car["x_m"]],
                y=[car["y_m"]],
                mode="markers+text",
                marker={
                    "size": size,
                    "color": color,
                    "symbol": "diamond" if is_incident else "circle",
                    "line": {"color": "#111d2a", "width": 2},
                },
                text=[f"#{car['car_id']}"],
                textposition="top center",
                name=f"Car #{car['car_id']}",
                hovertemplate=(
                    f"Car #{car['car_id']}<br>"
                    f"{car['speed_kmh']:.0f} km/h<br>"
                    f"Sector {car['sector']}<extra></extra>"
                ),
                showlegend=False,
            )
        )
    figure.update_layout(
        height=380,
        margin={"l": 12, "r": 12, "t": 10, "b": 10},
        paper_bgcolor="#111d2a",
        plot_bgcolor="#111d2a",
        font={"color": "#e7eef5"},
        xaxis={"visible": False},
        yaxis={"visible": False, "scaleanchor": "x", "scaleratio": 1},
    )
    return figure


def speed_figure(result: AnalysisResult, frame_index: int) -> go.Figure:
    frames = demo_frames()
    start = max(0, frame_index - 80)
    history = pd.concat(frames[start : frame_index + 1], ignore_index=True)
    incident_id = result.incident["car_id"] if result.incident else 12
    approach_id = (
        result.closest_approaching_car["car_id"]
        if result.closest_approaching_car
        else 7
    )
    figure = go.Figure()
    for car_id, label, color in (
        (incident_id, f"Car #{incident_id}", "#ff5b62"),
        (approach_id, f"Car #{approach_id}", "#f6c453"),
    ):
        car = history[history["car_id"] == car_id]
        figure.add_trace(
            go.Scatter(
                x=car["timestamp_s"],
                y=car["speed_kmh"],
                mode="lines",
                line={"color": color, "width": 3},
                name=label,
            )
        )
    figure.add_vline(x=result.timestamp_s, line_color="#9bb3c9", line_dash="dot")
    figure.update_layout(
        height=260,
        margin={"l": 15, "r": 15, "t": 15, "b": 25},
        paper_bgcolor="#111d2a",
        plot_bgcolor="#111d2a",
        font={"color": "#e7eef5"},
        xaxis_title="Replay time (s)",
        yaxis_title="Speed (km/h)",
        yaxis={"range": [0, 230], "gridcolor": "#2e4254"},
        xaxis={"gridcolor": "#2e4254"},
        legend={"orientation": "h", "y": 1.15},
    )
    return figure


def render_status(result: AnalysisResult) -> None:
    flag = result.flag
    label = (
        "DATA UNAVAILABLE"
        if flag is None
        else "RED FLAG RECOMMENDED"
        if flag == "RED_RECOMMENDED"
        else flag
    )
    color = FLAG_COLORS.get(flag, "#a5b4c2")
    st.caption("CURRENT RECOMMENDATION")
    st.markdown(
        f"<div style='font-size:2.1rem;font-weight:800;color:{color};"
        f"line-height:1.1;margin-bottom:0.4rem'>{label}</div>",
        unsafe_allow_html=True,
    )
    st.caption("Decision support only · Race control makes the final call")
    st.metric("Severity index", f"{result.risk_score:.0%}")
    st.write(f"**Estimated severity:** {result.severity.replace('_', ' ')}")
    source = (
        "Simulated-data Random Forest"
        if result.model_source == "random_forest"
        else "Deterministic fallback"
    )
    st.caption(f"Model source: {source} · Rule: {result.rule_id or '—'}")
    for name, probability in result.probabilities.items():
        label = name.replace("_", " ").title()
        st.markdown(
            f"<span style='color:{CLASS_COLORS[name]}'>{label}: "
            f"{probability:.0%}</span>",
            unsafe_allow_html=True,
        )
        st.progress(min(1.0, max(0.0, probability)))


def render_incident(result: AnalysisResult) -> None:
    if result.incident is None:
        st.info("No active incident. Monitoring all four cars.")
        return
    incident = result.incident
    st.subheader(f"Car #{incident['car_id']} · Sector {incident['sector']}")
    one, two, three = st.columns(3)
    one.metric("Speed", f"{incident['speed_kmh']:.0f} km/h")
    two.metric("Stationary", f"{incident['stationary_time_s']:.1f} s")
    three.metric("Peak decel", f"{incident['peak_decel_g']:.1f} g")
    if result.closest_approaching_car:
        car = result.closest_approaching_car
        st.write(
            f"**Approaching car #{car['car_id']}** · "
            f"{car['distance_m']:.0f} m behind · "
            f"{car['speed_kmh']:.0f} km/h"
        )
    else:
        st.caption("No closing traffic detected in the current search window")


def render_reasons(result: AnalysisResult) -> None:
    if not result.reasons:
        st.info("No incident evidence requires a flag recommendation.")
        return
    for reason in result.reasons:
        st.markdown(f"- {reason}")
    if result.flag == "GREEN":
        st.caption("Candidate evidence is being monitored; incident not yet confirmed.")


st.set_page_config(page_title="FlagSense", layout="wide")
st.markdown(
    """
    <style>
    .stApp { background: #0b1520; color: #e7eef5; }
    .block-container { padding-top: 1.2rem; max-width: 1400px; }
    h1, h2, h3 { color: #edf4fa; }
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("FlagSense")
st.caption(
    "AI-assisted motorsport safety · Offline simulated race · "
    "Prototype thresholds, not official rules"
)
if "pipeline" not in st.session_state:
    st.session_state.speed_multiplier = 1
    reset_playback()


@st.fragment(run_every=0.2)
def race_control() -> None:
    start, pause, reset, speed = st.columns([1, 1, 1, 2])
    with start:
        if st.button(
            "Start Demo",
            key="start_demo",
            disabled=st.session_state.playback_index >= len(demo_frames()) - 1,
            use_container_width=True,
        ):
            st.session_state.running = True
    with pause:
        if st.button("Pause", key="pause_demo", use_container_width=True):
            st.session_state.running = False
    with reset:
        if st.button("Reset", key="reset_demo", use_container_width=True):
            reset_playback()
    with speed:
        st.selectbox(
            "Playback speed",
            [1, 2],
            format_func=lambda value: f"{value}×",
            key="speed_multiplier",
            label_visibility="collapsed",
        )
    if st.session_state.running:
        advance_playback()

    result = st.session_state.latest_result
    st.caption(f"Replay time {result.timestamp_s:.1f} / 20.0 s")
    track_column, status_column = st.columns([1.65, 1], gap="large")
    with track_column:
        st.subheader("Track view")
        st.plotly_chart(track_figure(result, demo_track()), use_container_width=True)
    with status_column:
        with st.container(border=True):
            render_status(result)

    details_column, why_column = st.columns(2, gap="large")
    with details_column:
        with st.container(border=True):
            st.subheader("Incident details")
            render_incident(result)
    with why_column:
        with st.container(border=True):
            st.subheader("Why?")
            render_reasons(result)

    st.subheader("Speed telemetry")
    st.plotly_chart(
        speed_figure(result, st.session_state.playback_index),
        use_container_width=True,
    )
    if result.quality_notes:
        st.warning(" · ".join(result.quality_notes))
    if st.session_state.playback_index >= len(demo_frames()) - 1:
        st.success("Replay complete. Press Reset to run the same scenario again.")


race_control()
