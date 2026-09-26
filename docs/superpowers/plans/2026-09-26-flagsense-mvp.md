# FlagSense Software MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task by task. Steps use checkbox syntax for tracking. Keep the software MVP stable before dashboard polish or hardware integration.

**Goal:** Build an offline, explainable race-control decision-support demo that replays multiple cars, detects a developing incident, estimates severity with a small Random Forest, and recommends GREEN, YELLOW, then RED FLAG RECOMMENDED.

**Architecture:** A stateful Python pipeline consumes one timestamp of telemetry at a time. Deterministic code validates samples, detects incidents, extracts features, and recommends flags; a Random Forest estimates severity from those features. Streamlit only controls replay and renders a structured pipeline result. Hardware is an optional output adapter behind an explicit operator action.

**Tech stack:** Python 3.11, pandas, NumPy, scikit-learn, joblib, Streamlit, Plotly, pytest. No network service, database, or LLM.

**Spec:** The user-provided FlagSense brief at /Users/ericchen/.codex/attachments/7dfae25e-ff75-462b-bd7b-7dbb98ccce01/Pasted text.txt. This plan restates its implementation requirements.

## Global constraints

- Decision support only. Display RED FLAG RECOMMENDED, never an activated race flag.
- The ML model estimates severity; deterministic rules own every flag recommendation.
- The complete default demo runs offline from committed telemetry and a committed trusted model artifact.
- If the model artifact cannot load, a labeled deterministic scoring fallback keeps the software demo usable.
- All distances, times, speeds, accelerations, and thresholds below are prototype assumptions, not official motorsport or FIA limits.
- The eight-hour software schedule is a target inside a 12-hour two-person hackathon. Reserve the remaining time for teammate integration and judge rehearsal.

## Review focus

1. Duplicate or out-of-order car samples must be rejected rather than silently changing stop durations.
2. A missing speed sample must never be interpreted as a stopped car.
3. Approaching traffic across the start/finish wrap must use forward track distance, not raw Euclidean distance.
4. A missing or incompatible model artifact must visibly switch to deterministic fallback and preserve the result schema.
5. Replaying, pausing, resetting, and replaying again must produce the same GREEN → YELLOW → RED_RECOMMENDED sequence.

---

## 1. Architecture overview

Build one in-process Python application. There are three boundaries:

| Boundary | Responsibility | Output |
| --- | --- | --- |
| Telemetry and track | Load/validate CSV, group timestamp frames, project positions onto a bundled closed track centerline | Validated frames and track coordinates |
| Safety pipeline | Maintain short car histories, extract deterministic features, call model, apply flag rules, generate reasons | One AnalysisResult per frame |
| Streamlit | Playback controls and read-only presentation of AnalysisResult | Judge-facing dashboard |

Each module is importable without Streamlit. A command-line replay script must use the same pipeline as the UI. The pipeline considers all cars each frame, picks one focus incident by flag priority then risk score, and still returns every car position for the track view.

## 2. Data flow

    data/demo_race.csv
      → load_telemetry()
      → validated frames at 10 Hz
      → SafetyPipeline.update(frame)
      → incident detectors and seven model features per car
      → RiskEstimator.predict(features)
      → recommend_flag(features, model_result)
      → build_reasons(features, decision)
      → AnalysisResult
      → Streamlit track/status/incident/risk/telemetry panels
      → optional operator-triggered hardware adapter

The model receives one seven-column feature row, never raw timestamp sequences or car identity. The UI calls update() and contains no safety thresholds. The pipeline performs inference for all visible cars; only a confirmed candidate becomes the focus incident.

## 3. Exact telemetry schema

One CSV row is one car at one timestamp. All cars share the same time base. Four custom sectors are used in the synthetic course; these are demo zones, not the three official F1 sectors.

| Column | Type | Unit | Required | Rule |
| --- | --- | --- | --- | --- |
| timestamp_s | float | seconds since replay start | Yes | Finite, >= 0, 0.1 s target cadence |
| car_id | int | car number | Yes | Positive; unique with timestamp_s |
| x_m | float | local track x in metres | Yes | Finite |
| y_m | float | local track y in metres | Yes | Finite |
| speed_kmh | float | km/h | Yes | Finite, 0–400 |
| longitudinal_accel_g | float | signed g; negative is deceleration | Yes | Finite, -8 to +5 |
| sector | int | custom zone 1–4 | Yes | One of 1, 2, 3, 4 |
| throttle_pct | float | 0–100% | No | Plot only if present |
| brake_on | bool | applied/not applied | No | Plot only if present |
| heading_deg | float | degrees | No | Reserved for stretch work |
| lateral_accel_g | float | signed g | No | Reserved for stretch work |

Normalize column names when loading. Reject missing identifiers, duplicate timestamp/car pairs, invalid units/ranges, and nonfinite coordinates. Check that timestamps are nondecreasing in the source CSV and strictly increasing within each car's original row order; reject an out-of-order file, then sort by timestamp_s and car_id for frame grouping. Permit a single missing speed or acceleration sample only when the same car has valid neighbors within 0.3 s: interpolate speed linearly and acceleration linearly, and add a data-quality note. A longer gap is excluded from detector continuity, so it cannot accumulate stationary time or create a deceleration event. Do not replace missing speed with zero. The committed demo CSV must contain no missing required values. Optional columns may be absent entirely.

The loader yields a list of DataFrames, each containing one timestamp and one row per observed car. One absent car is omitted from that frame; if the entire frame is absent for over 1.0 s, the pipeline returns DATA_UNAVAILABLE with no flag recommendation.

## 4. Exact engineered feature set

The Random Forest receives exactly these seven fields, in this fixed order:

| Feature | Definition | No-evidence value |
| --- | --- | --- |
| stationary_time_s | Continuous time with speed < 5 km/h, reset on a gap > 0.3 s | 0 |
| peak_decel_g | Minimum signed longitudinal acceleration in trailing 2.0 s | 0 |
| on_racing_line | 1 if car is within 3 m of the track centerline; the flag rules combine this with stopped status | 0 |
| closing_speed_kmh | Maximum of 0 and approaching car speed minus incident car speed | 0 |
| closest_car_distance_m | Forward along-track distance to closest valid approaching car | 500 |
| nearby_cars | Other cars within 150 m along track in either direction | 0 |
| multiple_cars_affected | 1 if at least two cars within 35 m are stopped >= 1 s or had severe deceleration in 2 s | 0 |

Feature metadata retained outside the ML vector: car_id, timestamp_s, sector, current speed, x/y, track_s_m, incident_detected, closest_approaching_car_id, closest_approaching_car_speed_kmh, and data-quality notes. Use 500 m as a documented finite sentinel because the approaching search window is 250 m. Model training uses the same sentinel and column order.

## 5. Incident detection logic

Use one bundled closed centerline polyline with cumulative metre distances and four labeled zones. Project each car's x/y position onto the nearest line segment, storing track_s_m and perpendicular offset. This gives a cheap racing-line proxy and avoids mistaking cars on nearby but separate track sections for approaching traffic. The synthetic course and vehicle positions must use the same geometry.

| Detector | Rule | Feature/result effect |
| --- | --- | --- |
| Severe deceleration | Trailing 2 s minimum acceleration <= -2.5 g | peak_decel_g and candidate event |
| Stopped vehicle | Speed < 5 km/h continuously for >= 2.0 s | stationary_time_s and confirmed incident |
| On/near racing line | Car within 3.0 m of centerline; an obstruction claim also requires a confirmed stop | on_racing_line |
| Approaching traffic | Other car is 0–250 m behind incident along track, speed >= 80 km/h, positive closing speed, and forward gap decreased over consecutive frames | Closest car ID, distance, speed, closing speed |
| Multiple affected cars | At least two stopped/anomalous cars within 35 m along track | multiple_cars_affected |

Forward gap is (incident_track_s - other_track_s) modulo track_length. Count a car as approaching only after two valid frames show a decreasing gap; this prevents a car already past the incident from being called approaching. The first valid frame can still show positions, but no approach claim. Abnormal trajectory detection is excluded from the MVP.

Peak deceleration is an observed telemetry value, not an inferred crash diagnosis. A severe deceleration candidate may be shown as an observation before a confirmed stop. Never claim an obstruction when position data or geometry is unavailable.

## 6. Synthetic training-data strategy

Generate 3,600 independent feature rows with NumPy Generator seed 42: 1,200 per class. Sample correlated ranges within several scenario families, with overlapping boundaries and small random noise:

- NORMAL: ordinary moving/on-line racing, routine braking, no prolonged stop, no closing traffic; include on_racing_line=1 so that field alone cannot imply danger.
- MODERATE_RISK: slowdown or moderate deceleration; off-line stop; brief on-line stop with distant or slow traffic.
- HIGH_RISK: prolonged on-line stop with close high-speed traffic; severe deceleration plus stopped vehicle; multi-car obstruction.

Enforce physical consistency after sampling: closing_speed_kmh=0 when no approaching vehicle; closest_car_distance_m=500 in that case; multiple_cars_affected only when the sampled scenario contains two anomalous cars. Labels describe simulated scenario severity and are never presented as real-world ground truth. Exclude label, scenario family, car_id, timestamp, and sector from model inputs. Save synthetic_training.csv for reproducibility and regenerate only through the script.

## 7. ML model design

Use RandomForestClassifier with n_estimators=150, max_depth=8, min_samples_leaf=4, class_weight="balanced_subsample", random_state=42, n_jobs=-1. The seven engineered features are the entire input. The three stored class IDs are 0=NORMAL, 1=MODERATE_RISK, 2=HIGH_RISK.

Save a trusted local joblib bundle containing estimator, ordered feature column list, class map, schema version 1, and seed. On load, check schema version, exact feature names/order, and classes {0,1,2}. Treat a mismatch as model failure and switch to deterministic fallback.

## 8. Training and evaluation

Split synthetic rows 75/25 with stratification and random_state=42. Fit only on the training subset. Report confusion matrix with class order 0,1,2; per-class precision/recall/F1 via classification_report; and feature_importances_ sorted descending. Save these reports under models/evaluation.txt and the model under models/risk_model.joblib.

Keep the prerecorded demo scenario out of synthetic training and evaluation. A strong held-out synthetic score only shows consistency with the generator's assumptions; the README and dashboard must say the model is a hackathon prototype trained on simulated scenarios. No production safety claim or probability calibration claim is allowed.

## 9. Risk-score definition

Map predict_proba values by model.classes_, never by assumed column position. Define:

    risk_score = 0.5 * P(MODERATE_RISK) + 1.0 * P(HIGH_RISK)

This is a 0–1 severity index, not the probability of a real accident. Predicted class is the largest model class probability. Display both the index and the three class probabilities. If the model fails, compute a fallback score by adding 0.25 for a confirmed stop, 0.20 for a confirmed on-line stop, 0.30 for traffic within 150 m closing at >= 120 km/h, 0.15 for severe deceleration, and 0.30 for multiple affected cars; cap at 1.0. Convert fallback score s into display-only pseudo-probabilities: when s <= 0.5, use (NORMAL=1-2s, MODERATE=2s, HIGH=0); otherwise use (NORMAL=0, MODERATE=2-2s, HIGH=2s-1). This preserves the same severity-index formula and output schema. Set model_source to "rules_fallback", visibly label that mode, and never describe its pseudo-probabilities as ML output.

## 10. Deterministic flag rules

Compute a per-car recommendation, then choose the most urgent across cars using GREEN < YELLOW < RED_RECOMMENDED. Ties go to higher risk_score, then lower car_id. The order below is explicit:

1. No confirmed stop, no severe-deceleration candidate, and no multiple-car anomaly: GREEN.
2. Base model mapping: risk_score < 0.35 → GREEN; 0.35–0.749... → YELLOW; >= 0.75 → RED_RECOMMENDED.
3. Override to at least YELLOW when stationary_time_s >= 2.0 and on_racing_line=1, or when any stopped car has approaching traffic within 200 m at closing speed >= 80 km/h.
4. Override to RED_RECOMMENDED when stationary_time_s >= 4.0, on_racing_line=1, approaching car distance <= 150 m, and closing speed >= 120 km/h.
5. Override to RED_RECOMMENDED when multiple_cars_affected=1 and risk_score >= 0.60.

For severe deceleration without a stop, require current speed < 30 km/h or another confirmed hazard before RED_RECOMMENDED. This prevents one noisy acceleration sample from prompting the highest recommendation. Show the chosen rule ID in the result for auditability. A flag is a recommendation for race control, never an actuation command.

## 11. Deterministic explanation rules

Build reasons from the actual feature values and the rule that fired, in a stable order: stopped duration, line proximity, approaching traffic, severe deceleration, multiple cars. Include a reason only when its detector is true. Use measured values with one decimal place for time and g, integer km/h and metres. Example:

    Car #12 stationary for 6.1 s
    Car #12 is within 3 m of the racing-line proxy
    Car #7 approaching at 192 km/h, 118 m behind
    Peak deceleration was -4.3 g

The recommendation panel shows the rule ID in small print and "Race control must decide" under the status. No LLM is used.

## 12. Dashboard layout

One screen, desktop width:

- Header: FlagSense, "AI-assisted motorsport safety", and persistent "Prototype: simulated data; recommendations only".
- Top left (about two-thirds width): 2D track with all cars, incident car red outline, approaching car amber arrow/label, hover data.
- Top right: large current recommendation, severity, 0–1 risk score, three class probability bars, model source.
- Middle left: incident car/sector/current speed/stationary duration/peak deceleration/closest approaching car.
- Middle right: ordered WHY reasons and race-control decision-support note.
- Bottom: synchronized speed-over-time traces for incident and approaching car, plus playback controls.

At GREEN, show "No active incident" instead of stale incident details. A DATA_UNAVAILABLE state is separate from GREEN and displays a telemetry warning.

## 13. Dashboard state management

Store only playback_index, running, speed_multiplier, SafetyPipeline instance, latest_result, and a short result_history in st.session_state. On Reset, create a new pipeline and set index to zero; do not reuse a prior pipeline history. Keep all playback controls and changing panels inside one Streamlit fragment running every 0.2 s. Each 0.2 s tick feeds two 0.1 s frames at 1x or four at 2x, sequentially; a paused tick feeds zero. Disable Start after the final frame until Reset.

All processing is synchronous and local. Avoid background threads and sleep loops. A fragment timer is supported by Streamlit's run_every behavior; use the same session-state result for every panel so charts and status refer to the same timestamp.

## 14. Plotly visualizations

1. Track: line trace for the bundled centerline; scatter markers for every car; contrasting incident and approaching markers; hover with car ID, sector, and speed. Set equal x/y scale.
2. Speed: line traces over the trailing 8 s for focus car and closest approaching car, with a vertical marker at current replay time. Use one legend and km/h axis.
3. Risk probabilities: three horizontal bars in fixed NORMAL/MODERATE/HIGH order. A simple Streamlit bar or Plotly bar is sufficient.

No 3D track, live map tiles, or dashboard animation beyond updated Plotly frames.

## 15. Simulation and playback

Commit one 20 s, 10 Hz CSV containing at least four cars. Generate trajectories along the bundled centerline, not arbitrary coordinates. Car #12 is the incident; car #7 follows the same sector and approaches. Distinct stages:

| Time | Source data | Expected visible result |
| --- | --- | --- |
| 0–10 s | All cars moving normally | GREEN |
| 10–13 s | Car #12 slows from about 210 to 0 km/h; negative acceleration reaches <= -2.5 g | Candidate event and rising risk |
| 13–16 s | Car #12 stays below 5 km/h on the centerline | YELLOW by 15 s |
| 16–20 s | Car #7 approaches at roughly 190–210 km/h; gap falls below 150 m; car #12 remains stopped | RED_RECOMMENDED by 19 s |

Tune the generator to satisfy these timeline assertions without hard-coding timestamp-specific flag results. Save the generated CSV; the runtime never needs to run the generator or access the internet. The CLI replay prints each state transition and can run when Streamlit is unavailable.

## 16. Minimal file layout and responsibilities

    app.py                         Streamlit presentation and playback controls only
    config.py                      Dataclass of prototype thresholds and paths
    data/demo_race.csv             Committed offline replay
    data/track.json               Closed centerline and four sector labels
    data/synthetic_training.csv   Reproducible generated training table
    models/risk_model.joblib       Trusted serialized model bundle
    models/evaluation.txt         Synthetic holdout report
    src/telemetry.py              CSV schema, validation, frame grouping
    src/track.py                  Projection, along-track distance, line proxy
    src/incident_detection.py     Stateful car history and detector events
    src/features.py               Seven-column model vector and metadata
    src/model.py                  Model load/inference and deterministic fallback
    src/risk_engine.py            Ordered flag rules
    src/explain.py                Evidence-based reason strings
    src/pipeline.py               Single backend interface/result assembly
    src/hardware_output.py        Optional operator-triggered output adapter
    scripts/generate_training_data.py
    scripts/train_model.py
    scripts/generate_demo_race.py
    scripts/run_demo.py           Headless replay/status transitions
    tests/test_telemetry.py
    tests/test_detection.py
    tests/test_model.py
    tests/test_risk_engine.py
    tests/test_pipeline.py
    tests/test_demo.py
    requirements.txt
    README.md

The hardware adapter file can wait until after MVP. Keep the package flat; do not add a service layer or plugin system.

## 17. Function signatures and ownership

    load_telemetry(path: Path) -> list[pd.DataFrame]
    load_track(path: Path) -> Track
    project_to_track(x_m: float, y_m: float, track: Track) -> TrackPosition
    IncidentDetector.update(frame: pd.DataFrame, track: Track) -> list[DetectedCar]
    extract_features(car: DetectedCar, frame: pd.DataFrame, track: Track, history: History) -> SafetyFeatures
    generate_training_data(seed: int, per_class: int) -> pd.DataFrame
    train_model(table: pd.DataFrame, model_path: Path) -> EvaluationReport
    RiskEstimator.load_or_fallback(path: Path) -> RiskEstimator
    RiskEstimator.predict(features: SafetyFeatures) -> ModelResult
    recommend_flag(features: SafetyFeatures, model_result: ModelResult, config: Config) -> FlagDecision
    build_reasons(features: SafetyFeatures, decision: FlagDecision, config: Config) -> list[str]
    SafetyPipeline.update(frame: pd.DataFrame) -> AnalysisResult
    replay(csv_path: Path, pipeline: SafetyPipeline) -> list[AnalysisResult]
    send_recommendation(flag: str, risk_score: float, sector: int) -> None

Use small dataclasses for Track, TrackPosition, History, DetectedCar, SafetyFeatures, ModelResult, FlagDecision, EvaluationReport, and AnalysisResult. Track stores polyline points and cumulative distances; History stores the last 8 s of one car's valid samples; DetectedCar stores the latest sample plus detector booleans; EvaluationReport stores the confusion matrix, classification report, and feature importances. Their JSON forms use the exact names in section 19. Do not pass DataFrames through the model, flag, or explainability interfaces.

## 18. Example input

One frame by itself cannot establish stationary duration or approach direction; the example at 18.4 s assumes prior frames were processed.

    timestamp_s,car_id,x_m,y_m,speed_kmh,longitudinal_accel_g,sector
    18.4,12,0,100,0,0.0,4
    18.4,7,0,225,192,0.1,4
    18.4,3,500,0,205,0.2,1
    18.4,21,1200,200,198,0.1,2

For the bundled rectangular example centerline, car #7 is 125 m behind car #12 along the same straight. The synthetic generator may use rounded corners, but it must preserve this along-track relationship.

## 19. Example backend output

    {
      "timestamp_s": 18.4,
      "status": "OK",
      "flag": "RED_RECOMMENDED",
      "severity": "HIGH_RISK",
      "risk_score": 0.91,
      "probabilities": {"NORMAL": 0.02, "MODERATE_RISK": 0.14, "HIGH_RISK": 0.84},
      "model_source": "random_forest",
      "rule_id": "ON_LINE_CLOSE_FAST_TRAFFIC",
      "incident": {
        "car_id": 12, "sector": 4, "speed_kmh": 0,
        "stationary_time_s": 5.4, "peak_decel_g": -4.1,
        "x_m": 0, "y_m": 100
      },
      "closest_approaching_car": {
        "car_id": 7, "distance_m": 125,
        "speed_kmh": 192, "closing_speed_kmh": 192
      },
      "features": {
        "stationary_time_s": 5.4, "peak_decel_g": -4.1,
        "on_racing_line": true, "closing_speed_kmh": 192,
        "closest_car_distance_m": 125, "nearby_cars": 1,
        "multiple_cars_affected": false
      },
      "reasons": [
        "Car #12 stationary for 5.4 s",
        "Car #12 is within 3 m of the racing-line proxy",
        "Car #7 approaching at 192 km/h, 125 m behind",
        "Peak deceleration was -4.1 g"
      ],
      "vehicles": [
        {"car_id": 12, "x_m": 0, "y_m": 100, "speed_kmh": 0, "sector": 4},
        {"car_id": 7, "x_m": 0, "y_m": 225, "speed_kmh": 192, "sector": 4}
      ],
      "quality_notes": []
    }

The probabilities sum to 1.0 and yield risk_score = 0.5 × 0.14 + 0.84 = 0.91. In normal frames, incident and closest_approaching_car are null, reasons is empty, and vehicles still contains all cars. For DATA_UNAVAILABLE, flag is null and quality_notes describes the problem.

## 20. Config values

| Name | Initial value | Meaning |
| --- | ---: | --- |
| SAMPLE_INTERVAL_S | 0.1 | Demo CSV cadence |
| HISTORY_WINDOW_S | 8.0 | Detector/chart history |
| STOPPED_SPEED_KMH | 5 | Below this counts toward stationary time |
| STOPPED_TIME_S | 2.0 | Confirmed stopped vehicle |
| SEVERE_DECEL_G | -2.5 | Candidate event threshold |
| DECEL_LOOKBACK_S | 2.0 | Peak deceleration window |
| RACING_LINE_TOLERANCE_M | 3.0 | Centerline proxy |
| APPROACH_SEARCH_M | 250 | Maximum backward along-track search |
| APPROACH_MIN_SPEED_KMH | 80 | Minimum approaching speed |
| CLOSE_DISTANCE_M | 150 | RED override distance |
| HIGH_CLOSING_SPEED_KMH | 120 | RED override closing speed |
| NEARBY_DISTANCE_M | 150 | Nearby car count |
| MULTICAR_RADIUS_M | 35 | Shared incident region |
| YELLOW_RISK_THRESHOLD | 0.35 | Model severity-index rule |
| RED_RISK_THRESHOLD | 0.75 | Model severity-index rule |
| MAX_INTERPOLATION_GAP_S | 0.3 | Required-sample repair limit |
| DATA_UNAVAILABLE_GAP_S | 1.0 | No valid frame limit |

Use one immutable Config dataclass passed into detector, pipeline, and flag engine. Thresholds are demo assumptions; the README should say they require validation before any real-world use.

## 21. Focused test plan

- Telemetry: schema/units, sort order, duplicate key rejection, missing speed repair within 0.3 s, longer gap without false stop.
- Detection: severe decel at -2.5 g boundary; 1.9 s stop is false and 2.0 s stop true; line offset inside/outside 3 m; approaching car moving closer, receding car, track wrap; two affected cars within 35 m.
- Model: seven features in fixed order, probabilities sum to 1, risk-score formula, bundled artifact classes/schema, missing artifact fallback.
- Rules: GREEN for ordinary racing, YELLOW for stopped on-line car, RED for on-line stop plus close fast traffic, RED multi-car override, no RED from one decel sample alone.
- Explanations: only true evidence appears, correct car and rounded values, no stale reason after Reset.
- Pipeline: stable JSON keys in normal and incident states, multi-car focus priority, DATA_UNAVAILABLE is distinct from GREEN.
- Demo: full prerecorded replay has ordered GREEN → YELLOW → RED_RECOMMENDED transitions, reaches YELLOW by 15 s and RED by 19 s, and replay after Reset gives identical transitions.

Run focused tests at each module boundary; run the full suite and headless replay before dashboard work and again at the final software freeze. These tests check meaningful safety and demo behavior, not duplicate internal implementation.

## 22. Failure and fallback strategy

| Failure | Behavior |
| --- | --- |
| Model missing/incompatible | Deterministic score with model_source="rules_fallback"; visible dashboard notice; same flag/reason schema |
| Streamlit unavailable | scripts/run_demo.py replays offline and prints transitions |
| Hardware unavailable | No change to software; hardware adapter is never required by pipeline |
| Internet unavailable | No runtime network calls; committed CSV/model/track assets |
| Training never run locally | Committed trusted model bundle loads; otherwise scoring fallback |
| Track asset unreadable | Use bundled coarse oval centerline; if projection still fails, suppress line/approach claims and show data-quality notice |
| Missing telemetry frame > 1 s | DATA_UNAVAILABLE; do not silently infer GREEN |
| Invalid CSV | Clear validation error naming column and timestamp/car key; offer the committed demo CSV |

## 23. Hardware integration interface

The software emits a recommendation object, not an actuation instruction. After the MVP, an explicit operator button may call send_recommendation() with one line:

    RECOMMENDATION:RED;RISK:0.91;SECTOR:4

Equivalent GREEN and YELLOW lines are allowed. The adapter maps RED_RECOMMENDED to RED only in this demo protocol, and the physical display must be labeled "recommended". It must not write to serial automatically on model or flag changes. Serial port errors become a UI notice and do not affect analysis. Teammate owns firmware and wiring; agree on baud rate and newline termination during the integration hour.

## 24. Development sequence: independently reviewable tasks

- [ ] **Task 1 — Canonical data and track:** Create config.py, src/telemetry.py, src/track.py, the track asset, and telemetry tests. Deliverable: validated multi-car frames and correct projection/wrap geometry.
- [ ] **Task 2 — Deterministic detection and features:** Create src/incident_detection.py and src/features.py with history and detector tests. Deliverable: the seven stable features for a moving, stopped, and approached car.
- [ ] **Task 3 — Synthetic ML:** Create generation/training scripts, src/model.py, artifact, evaluation report, and model tests. Deliverable: reproducible Random Forest inference and visible fallback.
- [ ] **Task 4 — Flag engine and explanations:** Create src/risk_engine.py and src/explain.py with rule/explanation tests. Deliverable: every recommendation has a rule ID and evidence-backed reasons.
- [ ] **Task 5 — Stable backend and demo:** Create src/pipeline.py, demo generator/CSV, headless replay, and pipeline/demo tests. Deliverable: repeatable GREEN → YELLOW → RED_RECOMMENDED transitions offline.
- [ ] **Task 6 — Dashboard MVP:** Create app.py with playback state, status, incident details, reasons, vehicle plot, speed traces, and model/prototype labels. Deliverable: 2–3 minute judge demo from one command.
- [ ] **Task 7 — Freeze and rehearse:** Final focused test suite, headless replay, offline Streamlit rehearsal, README commands and limitations. Deliverable: stable software before visual polish.
- [ ] **Task 8 — Optional hardware/polish:** Only after Task 7, add explicit send button/adapter, timeline, or layout refinements. Deliverable: no regression in the software-only demo.

Each task should be reviewed against its deliverable before the next. The pipeline and demo must be complete before visual polishing.

## 25. Eight-hour software schedule

| Time | Work | Exit milestone |
| --- | --- | --- |
| 0:00–0:45 | Schema, config, track centerline, file skeleton | One valid multi-car frame loads |
| 0:45–2:00 | Detectors and feature extraction | Stop, decel, approach, and multi-car unit cases pass |
| 2:00–3:00 | Synthetic generator, model training, evaluation, artifact | Seven-feature inference and fallback work |
| 3:00–4:00 | Deterministic flag rules, reasons, pipeline | Backend emits complete AnalysisResult |
| 4:00–5:00 | Prerecorded race generator, CSV, headless replay | GREEN → YELLOW → RED passes offline |
| 5:00–6:15 | Streamlit status, details, controls, track points | Clickable judge demo works |
| 6:15–7:00 | Speed traces, risk bars, concise copy | Judges can see why recommendation changed |
| 7:00–8:00 | Test/fallback pass, README, offline rehearsal, software freeze | Software-only MVP stable |

Hours 8–12 of the hackathon are for teammate hardware integration, one optional stretch item, and repeated 2–3 minute demo rehearsals. If the schedule slips, preserve the backend and simple dashboard before adding any hardware or polish.

## 26. MVP definition of done

The default offline replay loads at least four cars; car #12 decelerates and stops; car #7 approaches; the pipeline produces seven features, Random Forest probabilities, a severity index, deterministic flag and reasons; Streamlit shows all vehicle positions, incident details, probabilities, and two speed traces; the status visibly moves GREEN → YELLOW → RED FLAG RECOMMENDED; Reset reproduces the sequence; the CLI and dashboard run without internet; README states simulated-data and decision-support limits.

## 27. Stretch goals, in order

1. Explicit operator-triggered hardware recommendation display.
2. Two additional prerecorded scenarios selected from the UI.
3. Incident event timeline.
4. Global model feature-importance plot, labeled as synthetic-model behavior.
5. Manual race-control acknowledgement.
6. Better track drawing.
7. Abnormal trajectory detector.
8. Multiple simultaneous incident cards.

Start each only after the preceding software MVP is demonstrably stable.

## 28. Deliberate exclusions

No authentication, accounts, database, cloud backend, React, mobile app, live CAN bus, real race-control integration, neural network, computer vision, LLM flag decision, distributed system, automatic flag activation, production deployment, perfect vehicle physics, or real-world safety validation. This prototype demonstrates an explainable decision pipeline over simulated telemetry.

## References for implementation

- Streamlit fragments and session state: https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment
- RandomForestClassifier probabilities and feature importances: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html
- Stratified train/test splitting: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.train_test_split.html
- Confusion matrix: https://scikit-learn.org/stable/modules/generated/sklearn.metrics.confusion_matrix.html
