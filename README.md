# FlagSense

FlagSense is an offline, operator-facing race-control prototype for a 12-hour hackathon. It replays four cars on a simple track, detects a stopped car and approaching traffic from telemetry, estimates incident severity with a Random Forest trained on simulated scenarios, and recommends GREEN, YELLOW, or RED. **It does not actuate a flag.** The race-control operator makes the decision.

## Run the demo

Use Python 3.11 or newer from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run app.py
```

Open the local URL printed by Streamlit and select **Start Demo**. The 20-second prerecorded race begins green. Car #12 decelerates and stops on the racing-line proxy; car #7 approaches from behind. The recommendation progresses to yellow and then red. **Pause**, **Reset**, and the 1×/2× selector make the sequence repeatable. All required demo, track, and model files are committed; the dashboard needs no network connection after dependencies are installed.

For a terminal-only replay:

```bash
python -m scripts.run_demo
```

To regenerate the simulated inputs and retrain the model:

```bash
python -m scripts.generate_training_data
python -m scripts.train_model
python -m scripts.generate_demo_race
```

## What is in the repository

| Path | Purpose |
| --- | --- |
| `app.py` | Streamlit track, recommendation, evidence, model output, telemetry, and playback controls |
| `src/telemetry.py` | CSV validation, ordering, and short-gap interpolation |
| `src/track.py` | Track geometry and along-track distances |
| `src/incident_detection.py` | Rolling histories, stops, deceleration, racing-line proxy, and closing traffic |
| `src/features.py` | Seven ordered model features |
| `src/model.py` | Synthetic scenario generator, Random Forest training, inference, and deterministic fallback |
| `src/risk_engine.py` | Transparent rules that convert evidence and model risk into a recommendation |
| `src/pipeline.py` | One-frame integration and a stable output contract |
| `data/demo_race.csv` | Prerecorded four-car, 10 Hz, 20-second scenario |
| `data/track.json` | Closed four-sector track used by the demo |
| `models/evaluation.txt` | Holdout results on simulated data only |

The input CSV requires `timestamp_s`, `car_id`, `x_m`, `y_m`, `speed_kmh`, `longitudinal_accel_g`, and `sector`. Positions and timestamps are numeric; `sector` is 1–4. The pipeline output is an `AnalysisResult` with timestamp, data status, recommendation, severity, risk score, three class probabilities, incident and approaching-car details, reasons, vehicle positions, and quality notes. `AnalysisResult.to_dict()` provides a plain dictionary for another display or adapter.

## Scope and limits

The thresholds in `config.py` are **prototype settings**, not official motorsport rules. The “racing line” is the centerline of the supplied synthetic track. The Random Forest was trained and evaluated only on generated examples; the holdout report must not be read as real-world safety accuracy. Flag recommendations also use deterministic gates, including a confirmed stop, so a brief deceleration alone does not change the displayed flag. If the model file is missing or incompatible, inference falls back to explicit rules and the dashboard labels that source.

FlagSense has no camera analysis, LLM, database, cloud service, or automatic flag control. The prerecorded CSV is the dependable demo input. Hardware integration can consume the pipeline’s output contract later, after the core replay is stable.
