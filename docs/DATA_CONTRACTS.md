# Shared data contracts

**Status key:** **implemented** means a Python type or function exists now; **planned** is the exact target interface for the next implementation tasks. Do not import planned names until their modules exist. This document governs producers and consumers; update it with code and tests when a shared schema changes. All distances use metres, speeds km/h, time seconds, acceleration signed `g` (negative means deceleration), and scores `[0,1]`. `None` means unavailable evidence, never false or zero.

## TelemetrySample — planned typed row; CSV contract implemented

`src/telemetry.py` currently validates a `pandas.DataFrame` rather than exposing a dataclass. One CSV row represents one car at one timestamp. The typed target is `TelemetrySample` with these fields:

| Field | Python type | Required | Meaning and validation |
| --- | --- | --- | --- |
| `timestamp_s` | `float` | Yes | Replay seconds, finite and `>=0`; source rows nondecreasing. |
| `car_id` | `int` | Yes | Positive; unique with `timestamp_s`. |
| `x_m`, `y_m` | `float` | Yes | Finite local track coordinates, metres. |
| `speed_kmh` | `float` | Yes | 0–400 km/h. A missing sample may be interpolated only between valid neighbors within 0.3 s; never fill with zero. |
| `longitudinal_accel_g` | `float` | Yes | Signed -8 to +5 g, same repair rule. |
| `sector` | `int` | Yes | Demo zone 1–4; these are not official race sectors. |
| `throttle_pct` | `float | None` | No | 0–100%, display only. |
| `brake_on` | `bool | None` | No | Braking indicator, display only; use this current-plan name, not `brake_pct`. |
| `heading_deg`, `lateral_accel_g` | `float | None` | No | Reserved telemetry. |

`load_telemetry(path: Path) -> list[pd.DataFrame]` is the **implemented** API. Frames are sorted by time and car ID. Existing loader adds `speed_imputed` and `accel_imputed` booleans to accepted rows; an unrepaired required value is dropped. Duplicate keys, invalid units, and out-of-order source rows are rejected. Current code does not expose a `TelemetrySample` class, so adding one must not break this loader contract.

## IncidentFeatures — implemented as `DetectedCar` plus `SafetyFeatures`

`IncidentDetector.update(frame, track) -> list[DetectedCar]` owns state. `extract_features(car) -> SafetyFeatures` is the public model-facing conversion. The canonical incident feature names are:

| Field | Python type | Unit | Required | Description |
| --- | --- | --- | --- | --- |
| `car_id`, `sector` | `int` | none | Yes | Focus car and demo zone. |
| `timestamp_s` | `float` | s | Yes | Current frame time. |
| `x_m`, `y_m` | `float` | m | Yes | Latest local position. |
| `speed_kmh` | `float` | km/h | Yes | Current measured or narrowly interpolated speed. |
| `stationary_time_s` | `float` | s | Yes | Time since the car last ran at normal pace for its track position: below the stopped-speed threshold, which is relative to the scenario's normal speed profile when one is available (see SpeedProfile); zero otherwise. |
| `peak_decel_g` | `float` | g | Yes | Minimum signed acceleration in trailing configured window. |
| `on_racing_line` | `bool` | none | Yes | Proximity to centerline proxy, not a camera judgment. |
| `closing_speed_kmh` | `float` | km/h | Yes | Positive relative speed for confirmed approaching traffic; zero if absent. |
| `closest_car_distance_m` | `float` | m | Yes | Forward along-track gap to closest confirmed approach; **500.0 sentinel** if none. |
| `nearby_cars` | `int` | count | Yes | Other cars within configured along-track radius. |
| `multiple_cars_affected` | `bool` | none | Yes | Two or more anomalous cars in configured incident radius. |
| `closest_approaching_car_id` | `int | None` | none | Yes | `None` if no confirmed approach. |
| `closest_approaching_car_speed_kmh` | `float` | km/h | Yes | Approaching car speed; zero if absent. |
| `incident_detected`, `severe_decel` | `bool` | none | Yes | Detector facts. |

`DetectedCar` additionally carries `track_s_m`, `line_offset_m`, and `stopped`. The implemented `SafetyFeatures` omits those intermediate fields and is the v1 handoff. Keep the exact `FEATURE_COLUMNS` order shown in [ML](ML.md); only those seven values reach the v1 Random Forest. This type corresponds to the brief's `IncidentFeatures` concept; do not create a second incompatible implementation with that name.

## SpeedProfile — implemented normal-pace reference

`src.speed_profile.build_speed_profile(frames, track, bin_m=25.0) -> SpeedProfile | None` builds a per-scenario normal speed profile from the scenario's own telemetry: the track is binned every 25 m along its length and each bin stores the maximum observed speed (smoothed, gaps filled from nearest non-empty bins), so incident cars going slowly do not drag the reference down. `SpeedProfile.expected_speed_kmh(s_m)` linearly interpolates the reference, wrapping around the closed loop. Returns `None` when the frames carry no usable speed samples.

`HistoricalScenario.speed_profile()` builds the profile from the scenario's telemetry; `replay()` and the dashboard pass it into `SafetyPipeline(..., speed_profile=...)`, which forwards it to `IncidentDetector`. With a profile, "slow" means below `max(stopped_speed_kmh, stopped_speed_ratio × expected)` and "recovered" means at or above `max(recovered_speed_kmh, recovered_speed_ratio × expected)` — prototype/demo ratios 0.30/0.60 in `config.py`. A car circulating a slow corner at its normal pace never counts as stationary; a car far below normal pace for its position does, even above the absolute 5 km/h floor. Without a profile the detector falls back to the absolute thresholds. A scenario-local `data/scenarios/<id>/track.json` takes precedence over the bundled track asset whenever present.

## EnvironmentalContext — implemented

`src.sensor_fusion.EnvironmentalContext` is an immutable dataclass. Values come from local scenario configuration or manual input; no live weather call is required. It also carries `visibility_condition: str | None`, `recovery_vehicle_present: bool | None`, `debris_reported: bool | None`, `source: str | None`, and `quality: str | None`. A scenario's recovery vehicle and debris reports become available only at their labelled `context_events` replay times.

| Field | Python type | Unit | Required | Description |
| --- | --- | --- | --- | --- |
| `sector` | `int` | none | Yes | Demo zone 1–4 to which context applies. |
| `track_type` | `str | None` | none | No | e.g. permanent circuit/street course; descriptive only. |
| `corner_type` | `str | None` | none | No | e.g. straight/slow corner; descriptive only. |
| `runoff_available` | `bool | None` | none | No | Local scenario fact, not image inference. |
| `rain_intensity` | `float | None` | `[0,1]` | No | Local normalized rain setting. |
| `track_wet` | `bool | None` | none | No | Scenario/manual condition. |
| `visibility_m` | `float | None` | m | No | Nonnegative visibility range. |
| `temperature_c` | `float | None` | °C | No | Ambient temperature; display only for MVP. |
| `debris_reported` | `bool | None` | none | No | Debris reported on track (marshal/race-control report via `context_events`), not a camera judgment. |

Unknown values remain `None`. `track_wet=False` is an explicit dry observation, not a fallback for a missing value.

## VisualFeatures — implemented evidence type; provider optional

`VisionAnalyzer.analyze(image: bytes) -> VisualFeatures | None` is the provider-agnostic interface for one still image. Without a configured provider it returns `None`, so an uploaded image creates no visual claim. A local cached/manual provider must satisfy the same output schema. `source` is `provider`, `cached`, or `manual`. No field contains a flag recommendation or raw image bytes.

| Field | Python type | Unit | Required | Description |
| --- | --- | --- | --- | --- |
| `vehicle_stopped_visible` | `bool | None` | none | Yes | Apparent stationary vehicle; `None` when not assessable. |
| `vehicle_on_track` | `bool | None` | none | Yes | Apparent vehicle on racing surface. |
| `track_blockage_fraction` | `float | None` | `[0,1]` | Yes | Approximate visible obstruction fraction, if assessable. |
| `multiple_vehicles_involved` | `bool | None` | none | Yes | Multiple involved vehicles visible. |
| `debris_visible`, `smoke_visible`, `fire_visible` | `bool | None` | none | Yes | Observable image facts. |
| `wet_surface_visible`, `poor_visibility_visible` | `bool | None` | none | Yes | Observable image facts, separate from environment source. |
| `visual_severity` | `float | None` | `[0,1]` | Yes | Image-only descriptive estimate; never a flag decision. |
| `confidence` | `float` | `[0,1]` | Yes | Overall visual extraction confidence. |
| `source` | `Literal["provider", "cached", "manual"]` | none | Yes | Evidence provenance. |

The image model may leave ambiguous observations `None`; confidence and source must be shown. No uploaded image or API response containing private content should be committed.

## FusedFeatures — implemented subset

One immutable object per focus car, constructed by `src/sensor_fusion.py` from `SafetyFeatures`, an optional `EnvironmentalContext`, and optional `VisualFeatures`. It subclasses `SafetyFeatures`, preserving telemetry names and the exact seven-field model vector. Implemented additional fields are `track_wet`, `visibility_condition`, `recovery_vehicle_present`, `debris_reported`, `context_source`, `context_quality`, `vision_vehicle_on_track`, `vision_track_blockage_fraction`, `vision_debris_visible`, `vision_multiple_vehicles`, `vision_confidence`, and `vision_source`. The table below remains a wider future target; its other fields are **not yet implemented**.

| Field | Python type | Unit | Required | Description |
| --- | --- | --- | --- | --- |
| `track_type`, `corner_type` | `str | None` | none | Yes | Copied context, `None` if absent. |
| `runoff_available`, `track_wet` | `bool | None` | none | Yes | Copied context. |
| `rain_intensity` | `float | None` | `[0,1]` | Yes | Copied context. |
| `visibility_m` | `float | None` | m | Yes | Copied context. |
| `vision_vehicle_on_track` | `bool | None` | none | Yes | Camera observation only. |
| `vision_track_blockage_fraction` | `float | None` | `[0,1]` | Yes | Camera observation only. |
| `vision_debris_visible`, `vision_smoke_visible`, `vision_fire_visible` | `bool | None` | none | Yes | Camera observations. |
| `vision_multiple_vehicles` | `bool | None` | none | Yes | Camera observation. |
| `vision_confidence` | `float | None` | `[0,1]` | Yes | `None` when no image evidence. |
| `vision_source` | `str | None` | none | Yes | `provider`, `cached`, `manual`, or `None`. |

The seven v1 ML fields retain their existing finite sentinel/zero conventions **only when building the v1 model vector**. Missing environment/vision stays `None` in fused and result objects. Fused fields may affect deterministic rules and explanation; they do **not** affect v1 ML inference. A model v2 migration must version the ordered vector and artifact.

## MLResult — implemented as `src.model.ModelResult`

| Field | Python type | Unit | Required | Description |
| --- | --- | --- | --- | --- |
| `predicted_class` | `Literal["NORMAL", "MODERATE_RISK", "HIGH_RISK"]` | none | Yes | Largest class probability. |
| `probabilities` | `dict[str, float]` | `[0,1]` | Yes | Exactly those three uppercase keys; sums to 1 within numeric tolerance. Fallback values are display-only pseudo-probabilities. |
| `risk_score` | `float` | `[0,1]` | Yes | `0.5*P(MODERATE_RISK)+P(HIGH_RISK)` severity index. |
| `model_source` | `Literal["random_forest", "rules_fallback"]` | none | Yes | Show this provenance. |

The brief's `MLResult` concept is named `ModelResult` in existing Python. Preserve that name unless every import and contract is migrated together.

## SafetyRecommendation — implemented as `src.risk_engine.FlagDecision`

`recommend_flag(features: SafetyFeatures | FusedFeatures, model_result: ModelResult, config: Config) -> FlagDecision` is the **implemented** sole flag-decision API. The brief's `SafetyRecommendation` concept is named `FlagDecision` in Python. Do not return plain strings from multiple modules.

| Field | Python type | Required | Description |
| --- | --- | --- | --- |
| `flag` | `Literal["GREEN", "YELLOW", "DOUBLE_YELLOW", "VSC", "SAFETY_CAR", "RED_RECOMMENDED"]` | Yes | Human-facing labels: `DOUBLE_YELLOW` renders “DOUBLE YELLOW”, `VSC` “VIRTUAL SAFETY CAR”, `SAFETY_CAR` “SAFETY CAR”, `RED_RECOMMENDED` “RED FLAG RECOMMENDED”. |
| `rule_id` | `str` | Yes | Stable identifier for the decisive rule/override. |

Rules should map low/moderate/high risk bands, then apply evidence guardrails. Existing `config.py` already centralizes `yellow_risk_threshold=0.35`, `red_risk_threshold=0.75`, stop/deceleration/traffic distances and times. Add visual blockage threshold there only when visual guardrails are implemented. **All are prototype/demo values, not official FIA thresholds.** `DATA_UNAVAILABLE` is a pipeline status with `flag=None`, not a recommendation value.

Deterministic geometric overrides run **before** the model band and can escalate to `SAFETY_CAR` regardless of model score:

| `rule_id` | Flag | Trigger |
| --- | --- | --- |
| `ON_LINE_CLOSE_FAST_TRAFFIC` | `SAFETY_CAR` | Stopped car on the racing-line proxy, stationary ≥ `safety_car_stationary_s` (4.0 s), traffic closing within 150 m at ≥ 120 km/h. |
| `MULTI_CAR_HIGH_RISK` | `SAFETY_CAR` | Multiple cars affected and `risk_score` ≥ `multi_car_risk_threshold` (0.60). |
| `DEBRIS_REPORTED_ON_TRACK` | `VSC` | Debris reported on the racing line (marshal/race-control report) with the field circulating; fires after the deterministic Safety Car rules and before the model band, so it beats `MODEL_RISK_YELLOW` but never overrides a Safety Car or red. Prototype/demo rule. |

When the model band is GREEN, weaker geometric evidence still escalates: `STOPPED_WITH_TRAFFIC` → `VSC` (stopped, traffic within 200 m closing ≥ 80 km/h) and `STOPPED_ON_LINE` → `DOUBLE_YELLOW` (stopped on the racing-line proxy). Fused visual evidence can force RED: `FUSED_RED_EVIDENCE` (severe blockage + debris/fire, or blockage + multiple vehicles) and `SEVERE_MULTICAR_BLOCKAGE`.

**Prototype latch:** `src.risk_engine.latch_flag(previous, new)` orders flags by severity GREEN < YELLOW < DOUBLE_YELLOW < VSC < SAFETY_CAR < RED_RECOMMENDED. Once the pipeline's latched recommendation reaches `VSC` or above, it never downgrades within the same run — a later GREEN/DOUBLE_YELLOW fresh read keeps the earlier flag and rule ID, appending a “no downgrade after escalation” reason. Escalations still stick. `SafetyPipeline.reset()` clears the latch; switching scenarios in the dashboard resets playback. Below `VSC` the fresh read always wins.

**Stationary-time hysteresis (blip tolerance):** `IncidentDetector` computes `stationary_time_s` by walking speed history backward and tolerating excursions above the slow threshold that stay below the recovered threshold and total ≤ `stopped_blip_tolerance_s` (1.5 s) — so a crashed car nudged at walking pace (recovery vehicle contact, sensor noise) stays `stopped`. Without a speed profile the thresholds are the absolute `stopped_speed_kmh` (5 km/h) / `recovered_speed_kmh` (25 km/h); with a profile they scale with the normal pace at each sample's track position (see SpeedProfile). **Prototype/demo values, not official thresholds.**

## AnalysisResult — implemented telemetry-only JSON-facing pipeline output

`SafetyPipeline.update(frame: pd.DataFrame, environment: EnvironmentalContext | None = None, visual: VisualFeatures | None = None) -> AnalysisResult` is the **implemented** stateful interface. `AnalysisResult.to_dict()` serializes it. The UI and hardware should consume its serialized form, not internal DataFrames or detector objects. Each frame must represent the same timestamp across all panels. The pipeline chooses the highest-priority incident across cars, then rounded risk score and car ID as tie breakers; rounding only stabilizes machine-precision ties.

| Field | Python/JSON type | Required | Description |
| --- | --- | --- | --- |
| `timestamp_s` | `float` | Yes | Frame replay time. |
| `status` | `Literal["OK", "DATA_UNAVAILABLE"]` | Yes | No valid input is not GREEN. |
| `flag` | `str | None` | Yes | Recommendation code, or `None` for data unavailable. |
| `severity` | `str` | Yes | Model class; `"UNKNOWN"` when unavailable. |
| `risk_score` | `float` | Yes | Severity index; 0.0 placeholder when unavailable. |
| `probabilities` | `dict[str, float]` | Yes | Model/fallback values; all three values are 0.0 when unavailable. |
| `model_source` | `str` | Yes | Inference source; still reports selected estimator on unavailable data. |
| `rule_id` | `str | None` | Yes | Fired decision rule. |
| `incident` | `dict | None` | Yes | Focus car ID, sector, speed, stationary time, peak deceleration, x/y. `None` with no incident. |
| `closest_approaching_car` | `dict | None` | Yes | Car ID, along-track distance, speed, closing speed. |
| `features` | `dict | None` | Yes | Current seven-field v1 model vector for focus car; `FusedFeatures` serialization is planned. |
| `reasons` | `list[str]` | Yes | Ordered evidence strings; empty when none. |
| `vehicles` | `list[dict]` | Yes | All visible car IDs, x/y, speed, sector for track display. |
| `quality_notes` | `list[str]` | Yes | Missing/interpolated source, fallback, or validation notices. |
| `context_evidence` | `dict | None` | No | Structured environmental/visual facts for the chosen incident, with source/quality labels; no raw image. |

For ordinary GREEN frames, `incident` and `closest_approaching_car` are `None`, `reasons=[]`, and `vehicles` still lists cars. For DATA_UNAVAILABLE, `flag`, `rule_id`, `incident`, `closest_approaching_car`, and `features` are `None`; `severity="UNKNOWN"`, `risk_score=0.0`, and all three probability values are 0.0 placeholders. Explain the failure in `quality_notes`. Consumers must branch on `status` before displaying a score or attempting hardware output. A future schema revision may replace these placeholders with nulls, but must update all producers/consumers/tests together. Neither UI nor hardware may infer a flag from `risk_score` without the rule engine.

## Change control

## HistoricalScenario — implemented local replay adapter

`load_scenario(scenario_id: str) -> HistoricalScenario` validates `data/scenarios/<id>/scenario.json` and loads `telemetry.csv` with matching `scenario-cache.json` when present; otherwise it loads `reconstruction.csv`. Its metadata includes a stable ID, title, season, event, session, incident car IDs, `data_quality`, `incident_offset_s`, field-level provenance, actual control actions with timing quality and source, context, notes, and limitations. `relative_time_s = timestamp_s - incident_offset_s`; exactly one frame must be T=0. Actual actions use `relative_time_s: null` when only order is documented. The adapter can pass only context available by the current frame into `SafetyPipeline`; actual control actions are presentation data and never pipeline input. See [historical methods](HISTORICAL_SCENARIOS.md).

The existing [MVP plan](superpowers/plans/2026-09-26-flagsense-mvp.md) is a work sequence, while this page is the shared interface source. The v1 Random Forest remains telemetry-only even when environment or visual facts affect explicit deterministic rules. When altering a schema, update this document, code, tests, and any model artifact in one focused change.
