"""Offline race-control demonstration for FlagSense — cleaned demo build."""

import hashlib
from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import Config
from src.historical import HistoricalScenario, load_scenario, scenario_ids
from src.pipeline import AnalysisResult, SafetyPipeline
from src.telemetry import load_telemetry
from src.track import Track, load_track
from src.vision import VisionAnalyzer


CONFIG = Config()
FLAG_LABELS = {
    "GREEN": "GREEN",
    "YELLOW": "YELLOW",
    "DOUBLE_YELLOW": "DOUBLE YELLOW",
    "VSC": "VIRTUAL SAFETY CAR",
    "SAFETY_CAR": "SAFETY CAR",
    "RED_RECOMMENDED": "RED FLAG RECOMMENDED",
}
FLAG_COLORS = {
    "GREEN": "#29c98b",
    "YELLOW": "#f6c453",
    "DOUBLE_YELLOW": "#f6c453",
    "VSC": "#ff9f43",
    "SAFETY_CAR": "#ff7a45",
    "RED_RECOMMENDED": "#ff5b62",
}
FLAG_BG = {
    "GREEN": "#10382a",
    "YELLOW": "#4a3a12",
    "DOUBLE_YELLOW": "#4a3a12",
    "VSC": "#3d2a12",
    "SAFETY_CAR": "#40220f",
    "RED_RECOMMENDED": "#4d1a1e",
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
def _speed_history_cached(scenario_key: str) -> pd.DataFrame:
    """Single concatenated history per scenario — avoids pd.concat every frame."""
    if scenario_key == "Synthetic Demo":
        frames = load_telemetry(CONFIG.demo_path)
    else:
        frames = load_scenario(scenario_key).frames
    full = pd.concat(frames, ignore_index=True)
    keep = [c for c in ("timestamp_s", "car_id", "speed_kmh") if c in full.columns]
    return full[keep].sort_values("timestamp_s").reset_index(drop=True)


@st.cache_data
def _sources_md_cached(scenario_id: str) -> str:
    try:
        sc = load_scenario(scenario_id)
        p = sc.path / "SOURCES.md"
        if p.is_file():
            return p.read_text()
    except Exception:
        pass
    return ""


SCENARIO_LABELS = {
    "2024_azerbaijan_perez_sainz": "2024 Azerbaijan — Pérez/Sainz",
    "2021_azerbaijan_verstappen": "2021 Azerbaijan — Verstappen",
    "2024_sao_paulo_stroll": "2024 São Paulo — Stroll",
    "2014_japan_sutil_bianchi": "2014 Japan — Sutil/Bianchi",
    "2022_canada_tsunoda": "2022 Canada — Tsunoda",
    "2024_qatar_mirror_debris": "2024 Qatar — Mirror debris",
}


@st.cache_data
def historical_scenario(scenario_id: str) -> HistoricalScenario:
    return load_scenario(scenario_id)


def selected_scenario() -> HistoricalScenario | None:
    key = st.session_state.get("scenario_choice", "Synthetic Demo")
    return None if key == "Synthetic Demo" else historical_scenario(key)


def current_frames():
    scenario = selected_scenario()
    return demo_frames() if scenario is None else scenario.frames


def visual_for_frame(scenario: HistoricalScenario, frame: pd.DataFrame):
    attached = st.session_state.get("uploaded_visual")
    if attached is None or attached["scenario_id"] != scenario.scenario_id:
        return None
    relative = scenario.relative_time(float(frame["timestamp_s"].iloc[0]))
    return attached["features"] if relative >= attached["available_at_relative_s"] else None


def reset_playback() -> None:
    frames = current_frames()
    scenario = selected_scenario()
    pipeline = SafetyPipeline(
        CONFIG,
        track=load_track(scenario.track_path) if scenario else None,
        speed_profile=scenario.speed_profile() if scenario else None,
    )
    st.session_state.pipeline = pipeline
    st.session_state.playback_index = 0.0
    st.session_state.pipeline_index = 0
    first = (scenario.update_pipeline(pipeline, frames[0], visual_for_frame(scenario, frames[0]))
             if scenario else pipeline.update(frames[0]))
    st.session_state.latest_result = first
    st.session_state.result_cache = {0: first}
    st.session_state.result_history = [first]
    st.session_state.running = False


def _interp_vehicles(vehicles_now: list[dict], vehicles_next: list[dict] | None,
                     alpha: float) -> list[dict]:
    """Linearly interpolate car positions between two pipeline frames.

    Display-only smoothing: the pipeline still sees every frame in order, so
    detection and flag logic are unaffected.
    """
    if not vehicles_next or alpha <= 0:
        return vehicles_now
    if alpha >= 1:
        return vehicles_next
    upcoming = {car["car_id"]: car for car in vehicles_next}
    blended: list[dict] = []
    seen: set[int] = set()
    for car in vehicles_now:
        other = upcoming.get(car["car_id"])
        seen.add(car["car_id"])
        if other is None:
            blended.append(car)
            continue
        merged = dict(car)
        merged["x_m"] = car["x_m"] + (other["x_m"] - car["x_m"]) * alpha
        merged["y_m"] = car["y_m"] + (other["y_m"] - car["y_m"]) * alpha
        merged["speed_kmh"] = car["speed_kmh"] + (other["speed_kmh"] - car["speed_kmh"]) * alpha
        blended.append(merged)
    for car in vehicles_next:
        if car["car_id"] not in seen:
            blended.append(car)
    return blended


def advance_playback() -> None:
    """Advance the render clock smoothly; feed the pipeline whole frames.

    The render position moves in fractional frames (10 ticks/s) while the
    pipeline only ever sees complete frames in order. A one-frame lookahead
    lets the track view interpolate car positions between frames.
    """
    frames = current_frames()
    scenario = selected_scenario()
    last = len(frames) - 1
    speed = int(st.session_state.get("speed_multiplier", 1))
    pos = float(st.session_state.get("playback_index", 0.0)) + 0.5 * speed
    if pos >= last:
        pos = float(last)
        st.session_state.running = False
    st.session_state.playback_index = pos
    need = min(last, int(pos) + 1)
    cache = st.session_state.result_cache
    fed = int(st.session_state.get("pipeline_index", 0))
    while fed < need:
        fed += 1
        result = (scenario.update_pipeline(st.session_state.pipeline, frames[fed], visual_for_frame(scenario, frames[fed]))
                  if scenario else st.session_state.pipeline.update(frames[fed]))
        st.session_state.pipeline_index = fed
        cache[fed] = result
        st.session_state.result_history.append(result)
        for key in [k for k in cache if k < fed - 2]:
            del cache[key]
    st.session_state.latest_result = cache[int(pos)]


def track_figure(result: AnalysisResult, track: Track,
                 scenario: HistoricalScenario | None = None,
                 vehicles: list[dict] | None = None) -> go.Figure:
    figure = go.Figure()
    xs, ys = zip(*track.points)
    # Fixed view: pin the axes to the track geometry (plus padding) so
    # plotly's autorange cannot shift the map as car markers and labels move
    # between frames.
    span_x = max(xs) - min(xs) or 1.0
    span_y = max(ys) - min(ys) or 1.0
    pad_x = span_x * 0.07 + 15.0
    pad_y = span_y * 0.07 + 15.0
    x_range = [min(xs) - pad_x, max(xs) + pad_x]
    y_range = [min(ys) - pad_y, max(ys) + pad_y]
    figure.add_trace(
        go.Scatter(
            x=xs,
            y=ys,
            mode="lines",
            line={"color": "#3a4f66", "width": 12},
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
    for car in vehicles if vehicles is not None else result.vehicles:
        is_incident = car["car_id"] == incident_id or (
            scenario is not None
            and scenario.relative_time(result.timestamp_s) >= 0
            and car["car_id"] in scenario.metadata["incident_cars"]
            and car["speed_kmh"] < 80
        )
        is_approaching = car["car_id"] == approaching_id
        color = "#ff5b62" if is_incident else "#f6c453" if is_approaching else "#73c7ee"
        size = 18 if is_incident else 15 if is_approaching else 12
        figure.add_trace(
            go.Scatter(
                x=[car["x_m"]],
                y=[car["y_m"]],
                mode="markers+text",
                marker={
                    "size": size,
                    "color": color,
                    "symbol": "diamond" if is_incident else "circle",
                    "line": {"color": "#0b1520", "width": 2},
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
        height=360,
        margin={"l": 8, "r": 8, "t": 8, "b": 8},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#e7eef5", "size": 12},
        # Fixed view: pin the axes to the track geometry (plus padding) so
        # plotly's autorange cannot shift the map as car markers and labels
        # move between frames.
        xaxis={"visible": False, "range": x_range},
        yaxis={"visible": False, "scaleanchor": "x", "scaleratio": 1,
               "range": y_range},
    )
    return figure


def speed_figure(result: AnalysisResult, frame_index: int,
                 scenario: HistoricalScenario | None = None,
                 current_t: float | None = None) -> go.Figure:
    scenario_key = st.session_state.get("scenario_choice", "Synthetic Demo")
    history = _speed_history_cached(scenario_key)
    now_t = float(result.timestamp_s) if current_t is None else current_t
    window = history[history["timestamp_s"] >= now_t - 8.0]
    window = window[window["timestamp_s"] <= now_t]
    incident_id = result.incident["car_id"] if result.incident else (scenario.metadata["incident_cars"][0] if scenario else 12)
    approach_id = (
        result.closest_approaching_car["car_id"]
        if result.closest_approaching_car
        else (scenario.metadata.get("approaching_cars", [7])[0] if scenario else 7)
    )
    offset = scenario.incident_offset_s if scenario else 0
    figure = go.Figure()
    for car_id, label, color in (
        (incident_id, f"Car #{incident_id}", "#ff5b62"),
        (approach_id, f"Car #{approach_id}", "#f6c453"),
    ):
        car = window[window["car_id"] == car_id]
        figure.add_trace(
            go.Scatter(
                x=car["timestamp_s"] - offset,
                y=car["speed_kmh"],
                mode="lines",
                line={"color": color, "width": 2.5},
                name=label,
            )
        )
    figure.add_vline(x=now_t - offset, line_color="#9bb3c9", line_dash="dot", line_width=1)
    figure.update_layout(
        height=240,
        margin={"l": 40, "r": 12, "t": 12, "b": 32},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#e7eef5", "size": 11},
        xaxis_title="Seconds from incident" if scenario else "Replay time (s)",
        yaxis_title="Speed (km/h)",
        yaxis={"range": [0, 400 if scenario else 230], "gridcolor": "#1e2f42", "zeroline": False},
        xaxis={"gridcolor": "#1e2f42", "zeroline": False},
        legend={"orientation": "h", "y": 1.08, "x": 0},
    )
    return figure


def render_status(result: AnalysisResult) -> None:
    flag = result.flag
    label = "DATA UNAVAILABLE" if flag is None else FLAG_LABELS.get(flag, flag)
    color = FLAG_COLORS.get(flag, "#a5b4c2")
    bg = FLAG_BG.get(flag, "#1a2634")
    st.markdown(
        f"<div style='background:{bg};border:1px solid {color};border-radius:10px;"
        f"padding:12px 14px;margin-bottom:10px'>"
        f"<div style='font-size:11px;letter-spacing:0.08em;color:#9bb3c9'>CURRENT RECOMMENDATION</div>"
        f"<div style='font-size:1.7rem;font-weight:800;color:{color};line-height:1.15'>{label}</div>"
        f"<div style='font-size:11px;color:#9bb3c9;margin-top:4px'>Decision support only · Race control makes the final call</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    with c1:
        render_metric_card("Severity index", f"{result.risk_score:.0%}")
    with c2:
        render_metric_card("Severity", result.severity.replace("_", " ").title())
    source = (
        "Simulated-data Random Forest"
        if result.model_source == "random_forest"
        else "Deterministic fallback"
    )
    st.caption(f"{source} · Rule {result.rule_id or '—'}")
    for name, probability in result.probabilities.items():
        lbl = name.replace("_", " ").title()
        col = CLASS_COLORS.get(name, "#a5b4c2")
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;font-size:12px;margin-top:6px'>"
            f"<span style='color:{col}'>{lbl}</span><span>{probability:.0%}</span></div>",
            unsafe_allow_html=True,
        )
        st.progress(min(1.0, max(0.0, float(probability))))


def render_incident(result: AnalysisResult) -> None:
    if result.incident is None:
        st.info("No active incident. Monitoring all cars.")
        return
    incident = result.incident
    st.markdown(f"**Car #{incident['car_id']} · Sector {incident['sector']}**")
    one, two, three = st.columns(3)
    with one:
        render_metric_card("Speed", f"{incident['speed_kmh']:.0f} km/h")
    with two:
        render_metric_card("Stationary", f"{incident['stationary_time_s']:.1f} s")
    with three:
        render_metric_card("Peak decel", f"{incident['peak_decel_g']:.1f} g")
    if result.closest_approaching_car:
        car = result.closest_approaching_car
        st.caption(f"Approaching #{car['car_id']} · {car['distance_m']:.0f} m · {car['speed_kmh']:.0f} km/h")
    else:
        st.caption("No closing traffic in window")


def render_metric_card(label: str, value: str) -> None:
    """Render a compact, wrapping metric without Streamlit's value ellipsis."""
    st.markdown(
        "<dl class='metric-card'>"
        f"<dt class='metric-card__label'>{escape(label)}</dt>"
        f"<dd class='metric-card__value'>{escape(value)}</dd>"
        "</dl>",
        unsafe_allow_html=True,
    )


def render_reasons(result: AnalysisResult) -> None:
    if not result.reasons:
        st.info("No incident evidence requires a flag recommendation.")
        return
    for reason in result.reasons:
        st.markdown(f"- {reason}")
    if result.flag == "GREEN":
        st.caption("Monitoring — incident not yet confirmed.")


def historical_timeline_figure(scenario: HistoricalScenario, results: list[AnalysisResult]) -> go.Figure:
    """Presentation only: historical actions never enter SafetyPipeline."""
    figure = go.Figure()
    actual = [a for a in scenario.metadata["actual_control_actions"] if a["relative_time_s"] is not None]
    figure.add_trace(go.Scatter(
        x=[a["relative_time_s"] for a in actual], y=["Actual race control"] * len(actual),
        mode="markers+text", text=[a["action"] for a in actual], textposition="top center",
        marker={"size": 11, "color": "#73c7ee"}, name="Documented control action",
        customdata=[a["timing_quality"] for a in actual],
        hovertemplate="T=%{x:.1f}s · %{text}<br>%{customdata}<extra></extra>",
    ))
    severity_changes = []
    seen_severity = set()
    step = max(1, len(results) // 120)
    for result in results[::step]:
        if result.severity not in seen_severity:
            severity_changes.append((scenario.relative_time(result.timestamp_s), result.severity))
            seen_severity.add(result.severity)
    figure.add_trace(go.Scatter(
        x=[t for t, _ in severity_changes], y=["Estimated severity"] * len(severity_changes),
        mode="markers+text", text=[label.replace("_", " ") for _, label in severity_changes],
        textposition="top center", marker={"size": 8, "color": "#ff5b62"},
        name="Model severity", hovertemplate="T=%{x:.1f}s · %{text}<extra></extra>",
    ))
    transitions = []
    previous = None
    for result in results[::step]:
        label = result.flag or result.status
        if label != previous:
            transitions.append((scenario.relative_time(result.timestamp_s), label))
            previous = label
    figure.add_trace(go.Scatter(
        x=[t for t, _ in transitions], y=["FlagSense recommendation"] * len(transitions),
        mode="lines+markers", marker={"size": 9, "color": "#f6c453"},
        line={"color": "#f6c453"}, name="Pipeline output",
        customdata=[FLAG_LABELS.get(label, label) for _, label in transitions],
        hovertemplate="T=%{x:.1f}s · %{customdata}<extra></extra>",
    ))
    figure.add_vline(x=0, line_color="#ff5b62", line_dash="dash")
    figure.update_layout(
        height=280, margin={"l": 12, "r": 12, "t": 24, "b": 28},
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#e7eef5", "size": 11},
        xaxis_title="Seconds relative to incident",
        xaxis={"gridcolor": "#1e2f42"}, showlegend=False,
    )
    return figure


def render_historical_context(scenario: HistoricalScenario, relative_time_s: float) -> None:
    meta = scenario.metadata
    st.subheader(meta["title"])
    st.caption(f"{meta['event']} · {meta['session']} · {meta['season']}")
    st.write(meta["description"])
    quality = "Real speed samples with derived features" if meta["data_quality"] == "REAL_TELEMETRY_WITH_DERIVED_FEATURES" else "Historically grounded reconstruction — simulated continuous motion"
    st.info(f"Data quality: **{quality}**. T=0: {meta['incident_time_quality'].replace('_', ' ').lower()}.")
    if meta.get("presentation_note"):
        st.warning(meta["presentation_note"])
    try:
        weather = scenario.weather_at(relative_time_s)
        if weather:
            st.caption(f"Weather: {weather.get('source', 'local')} · T+{relative_time_s:.0f}s")
    except Exception:
        pass
    st.caption("Prototype recommendation states and FIA yellow, VSC, Safety Car, and red-flag actions are different mechanisms.")
    with st.expander("Data provenance and limitations"):
        st.json(meta["field_provenance"])
        for limitation in meta.get("limitations", []):
            st.write("• " + limitation)
        sources = _sources_md_cached(scenario.scenario_id)
        if sources:
            st.markdown(sources)


st.set_page_config(page_title="FlagSense", layout="wide")
st.markdown(
    """
    <style>
    .stApp { background: #0b1520; color: #e7eef5; }
    .block-container { padding-top: 1.0rem; max-width: 1380px; }
    h1, h2, h3 { color: #edf4fa; letter-spacing: -0.01em; }
    .metric-card { box-sizing: border-box; display: flex; flex-direction: column; gap: 0.35rem; min-width: 0; height: 5.5rem; margin: 0; padding: 0.75rem 0.85rem; background: #111d2a; border: 1px solid #1e2f42; border-radius: 10px; }
    .metric-card__label { margin: 0; color: #c3d0dc; font-size: 0.95rem; line-height: 1.3; }
    .metric-card__value { min-width: 0; margin: auto 0 0; color: #e7eef5; font-size: clamp(0.9rem, 1.6vw, 1.4rem); font-weight: 500; line-height: 1.15; white-space: nowrap; }
    div[data-testid="stExpander"] { background: #0e1a28; border: 1px solid #1e2f42; border-radius: 10px; }
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("FlagSense")
st.caption("AI-assisted motorsport safety · Offline incident replay · Prototype thresholds, not official rules")
choices = ["Synthetic Demo"] + [key for key in SCENARIO_LABELS if key in scenario_ids()]
st.selectbox("Historical Scenario", choices, format_func=lambda value: SCENARIO_LABELS.get(value, value), key="scenario_choice")
if ("pipeline" not in st.session_state or "result_cache" not in st.session_state
        or st.session_state.get("active_scenario") != st.session_state.scenario_choice):
    st.session_state.speed_multiplier = 1
    st.session_state.active_scenario = st.session_state.scenario_choice
    st.session_state.uploaded_visual = None
    st.session_state.last_image_digest = None
    st.session_state.image_error = None
    reset_playback()
_static_scenario = selected_scenario()
if _static_scenario is not None:
    _rel0 = _static_scenario.relative_time(st.session_state.latest_result.timestamp_s)
    with st.expander("Scenario context & provenance", expanded=False):
        render_historical_context(_static_scenario, _rel0)
if _static_scenario is not None:
    with st.sidebar:
        st.header("Evidence")
        uploaded = st.file_uploader(
            "Optional incident still image (kept local)",
            type=["jpg", "jpeg", "png"],
            key=f"incident_image_{_static_scenario.scenario_id}",
        )
        _rel_now = _static_scenario.relative_time(st.session_state.latest_result.timestamp_s)
        if uploaded is not None and _rel_now < 0:
            st.caption("Imagery enters at or after T=0. Advance the replay first.")
        elif uploaded is not None:
            image_bytes = uploaded.getvalue()
            digest = hashlib.sha256(image_bytes).hexdigest()
            if st.session_state.get("last_image_digest") != digest:
                st.session_state.last_image_digest = digest
                st.session_state.uploaded_visual = None
                st.session_state.image_error = None
                analyzer = st.session_state.get("vision_analyzer") or VisionAnalyzer()
                try:
                    visual = analyzer.analyze(image_bytes)
                except Exception:
                    visual = None
                    st.session_state.image_error = "Image analysis failed; visual evidence was omitted."
                if visual is not None:
                    st.session_state.uploaded_visual = {
                        "scenario_id": _static_scenario.scenario_id,
                        "digest": digest,
                        "available_at_relative_s": _rel_now,
                        "features": visual,
                    }
            if st.session_state.get("uploaded_visual") is None:
                st.caption("Attached — no new structured visual facts from this upload.")
                if st.session_state.image_error:
                    st.warning(st.session_state.image_error)
            else:
                st.caption("Structured image evidence enters from the next frame onward.")


@st.fragment(run_every=0.1)
def race_control() -> None:
    scenario = selected_scenario()
    frames = current_frames()
    last = len(frames) - 1
    pos = float(st.session_state.get("playback_index", 0.0))
    c_start, c_pause, c_reset, c_speed, c_progress = st.columns([1, 1, 1, 1.2, 2.2])
    with c_start:
        if st.button("Start Demo", key="start_demo", disabled=pos >= last, use_container_width=True):
            st.session_state.running = True
    with c_pause:
        if st.button("Pause", key="pause_demo", use_container_width=True):
            st.session_state.running = False
    with c_reset:
        if st.button("Reset", key="reset_demo", use_container_width=True):
            reset_playback()
    with c_speed:
        st.selectbox("Playback speed", [1, 2, 4], format_func=lambda v: f"{v}×", key="speed_multiplier", label_visibility="collapsed")
    with c_progress:
        st.progress(min(1.0, pos / max(1, last)))
        frame_no = int(pos)
        alpha = pos - frame_no
        cache = st.session_state.get("result_cache", {})
        cur = cache.get(frame_no, st.session_state.latest_result)
        nxt = cache.get(frame_no + 1)
        if nxt is not None:
            current_t = cur.timestamp_s + (nxt.timestamp_s - cur.timestamp_s) * alpha
        else:
            current_t = cur.timestamp_s
        if scenario:
            rel = scenario.relative_time(current_t)
            total_rel = scenario.relative_time(float(frames[-1]["timestamp_s"].iloc[0]))
            st.caption(f"T={rel:+.1f}s / +{total_rel:.1f}s · frame {frame_no+1}/{len(frames)}")
        else:
            st.caption(f"{current_t:.1f}s / 20.0s · frame {frame_no+1}/{len(frames)}")
    if st.session_state.running:
        advance_playback()
    result = st.session_state.latest_result
    frame_no = int(float(st.session_state.get("playback_index", 0.0)))
    alpha = float(st.session_state.get("playback_index", 0.0)) - frame_no
    cache = st.session_state.get("result_cache", {})
    cur = cache.get(frame_no, result)
    nxt = cache.get(frame_no + 1)
    vehicles = _interp_vehicles(cur.vehicles, nxt.vehicles if nxt else None, alpha)
    current_t = cur.timestamp_s + ((nxt.timestamp_s - cur.timestamp_s) * alpha if nxt else 0.0)
    left, right = st.columns([1.7, 1], gap="large")
    with left:
        st.subheader("Track view")
        st.plotly_chart(track_figure(result, st.session_state.pipeline.track, scenario, vehicles), use_container_width=True, config={"displayModeBar": False})
        st.subheader("Speed telemetry")
        if scenario:
            src = "FastF1 car samples" if scenario.metadata["data_quality"] == "REAL_TELEMETRY_WITH_DERIVED_FEATURES" else "SIMULATED reconstruction"
            st.caption(f"Speed source: {src}")
        st.plotly_chart(speed_figure(result, frame_no, scenario, current_t), use_container_width=True, config={"displayModeBar": False})
    with right:
        render_status(result)
        with st.container(border=True):
            st.subheader("Incident details")
            render_incident(result)
        with st.container(border=True):
            st.subheader("Why?")
            render_reasons(result)
    if scenario:
        with st.expander("Actual race control vs FlagSense", expanded=False):
            st.subheader("Actual race control vs FlagSense")
            st.caption("FlagSense recommendation from inputs available at each replay point. Actual actions are independently documented — not a judgment of race control.")
            hist = st.session_state.result_history
            st.plotly_chart(historical_timeline_figure(scenario, hist), use_container_width=True, config={"displayModeBar": False})
            rel = scenario.relative_time(result.timestamp_s)
            st.write(f"**Actual:** {scenario.actual_state(rel)}")
            st.write(f"**FlagSense:** {FLAG_LABELS.get(result.flag, result.flag or result.status)} · {result.severity.replace('_', ' ')}")
            untimed = [a for a in scenario.metadata["actual_control_actions"] if a["relative_time_s"] is None]
            if untimed:
                st.caption("Without verified timing: " + " → ".join(a["action"] for a in untimed))
    if result.quality_notes:
        st.warning(" · ".join(result.quality_notes[:3]))
    if float(st.session_state.get("playback_index", 0.0)) >= last:
        st.success("Replay complete — press Reset to run it again.")


race_control()
