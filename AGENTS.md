# Agent operating context: FlagSense

FlagSense is a 12-hour, two-person hackathon prototype for **motorsport race-control decision support**. It replays local multi-car telemetry, detects an incident, estimates severity, and explains a GREEN, YELLOW, or RED FLAG RECOMMENDED result to a human. It does not actuate real race flags. Read this file and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) before changing architecture; read [docs/DATA_CONTRACTS.md](docs/DATA_CONTRACTS.md) before changing shared types.

## Current state and priorities

Existing modules: `src/telemetry.py` validates and frames CSV samples; `src/track.py` projects positions onto a closed centerline; `src/incident_detection.py` maintains per-car history and extracts detector facts; `src/features.py` defines the seven-field v1 model vector; `src/model.py` contains synthetic training, Random Forest inference, and a rules fallback. `src/risk_engine.py` owns deterministic recommendation; `src/explain.py` owns reasons; `src/pipeline.py` assembles `AnalysisResult`. `src/sensor_fusion.py` carries typed environment and optional visual facts; `src/historical.py` loads local source-labelled replays. `config.py` centralizes current thresholds. Existing tests cover these modules. The MVP plan is [here](docs/superpowers/plans/2026-09-26-flagsense-mvp.md). An automated still-image provider remains unimplemented.

- **P0:** telemetry, incident detection, sensor fusion, ML model, deterministic risk engine, explanation, pipeline. Finish and test the current v1 core before widening the ML schema.
- **P1:** prerecorded demo, Streamlit dashboard, one-image upload/cached visual result, optional serial output.
- **P2:** UI polish, OLED, extra scenarios, advanced visual evidence.

The fixed architecture is `source adapters → structured features → ML severity estimate → deterministic recommendation → structured explanation/result → read-only UI and optional hardware`. Typed environment/visual fusion and local historical replays now exist; no automated image provider is bundled. Vision extracts evidence only. The core pipeline owns state and recommendation. `AnalysisResult` is the backend/UI/hardware boundary. See the contracts for exact names and extension status.

## Working rules

1. Prefer simple, working code over abstraction. Avoid duplicate implementations and unrelated rewrites.
2. Never put flag-decision logic or safety thresholds in the dashboard. Never put risk calculation or ML in firmware.
3. Never let a vision model choose GREEN, YELLOW, or RED. Use one still image, not live video, for the MVP.
4. Keep safety thresholds in `config.py`; label them **prototype/demo values**, never official FIA rules.
5. Keep the demo offline-capable: local telemetry, local scenarios, local model or explicit rules fallback, and cached/manual visual evidence. No live API may be on the critical path.
6. Do not silently change the v1 seven-feature model order or any shared schema. Update [docs/DATA_CONTRACTS.md](docs/DATA_CONTRACTS.md), producers, consumers, model artifact version, and tests together.
7. Do not claim synthetic-model accuracy predicts real incidents. The risk score is a severity index, not a calibrated accident probability.
8. Use **RED FLAG RECOMMENDED** in prose and `RED_RECOMMENDED` in code. Never claim a flag was “activated” or that the system autonomously controls flags.
9. Never commit API keys, tokens, `.env`, Streamlit secrets, private uploaded images, or sensitive API response caches.
10. Add dependencies only for a concrete implemented need. Run relevant tests before declaring work complete.
11. Preserve another contributor's uncommitted files. Use focused commits and coordinate before changing an actively owned module.
12. Historical control actions never enter `SafetyPipeline`. Keep feed times and simulated/reconstructed motion explicitly labelled; no future context may enter a replay frame. Do not equate prototype `RED_RECOMMENDED` with FIA VSC, Safety Car, or red flag.

## MVP scope

The MVP needs multi-car prerecorded telemetry, stopped/decelerating/approaching detection, local context, optional structured image evidence with fallback, one fused vector, ML severity, deterministic recommendation, evidence reasons, and a repeatable dashboard replay. Serial LEDs are optional. Do not build authentication, a database, cloud backend, React app, mobile app, CAN bus integration, live FIA/track telemetry, live video, custom vision training, neural networks, LLM flag decisions, microservices, or production certification.

If documentation and code disagree, identify the discrepancy explicitly. The existing v1 Python types and tests are the truth for implemented behavior; [docs/DATA_CONTRACTS.md](docs/DATA_CONTRACTS.md) records the intended next contracts. Resolve a difference by updating code, docs, and tests together rather than silently treating a planned type as already implemented.
