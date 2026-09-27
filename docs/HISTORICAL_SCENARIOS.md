# Historical scenario replay

FlagSense replays four documented Formula 1 incidents to ask whether a multimodal decision-support system can surface useful safety evidence promptly. These examples are **not proof that FlagSense outperforms race control**. They do not establish that any incident would have been prevented, or that an FIA decision was wrong. `RED_RECOMMENDED` is a prototype recommendation state; it is not a translation of VSC, Safety Car, or an FIA red flag.

## Run offline

From the repository root, install `requirements.txt`, then run `streamlit run app.py` and choose **Historical Scenario**. The committed `reconstruction.csv` files let every scenario run with no internet. The headless loader is `src.historical.load_scenario(id)`; use `scenario.replay()` for ordinary `SafetyPipeline` results. The synthetic demo remains the default.

The first measured-data milestone was run with:

```bash
python -m pip install -r requirements-historical.txt
python scripts/fetch_historical_scenarios.py --scenario 2024_azerbaijan_perez_sainz
streamlit run app.py
```

For the other supported measured feed, run the same command with `2021_azerbaijan_verstappen`. The script verifies the event name and session against the installed FastF1 3.8.3 event schedule, loads laps, car speed, position, weather, track status, and race-control messages, and writes a **local, ignored** cache. The dashboard never calls FastF1. `python scripts/build_scenario_cache.py --scenario all` regenerates the committed simulated fallbacks; Canada and Qatar remain offline reconstructions.

`python scripts/run_historical.py --scenario 2024_azerbaijan_perez_sainz --write-derived` prints both timelines and writes an ignored `derived_features.csv` computed from the normal pipeline, with no prescribed recommendation sequence.

## Data contract and provenance

Each `data/scenarios/<id>/` directory contains `scenario.json`, `reconstruction.csv`, and `SOURCES.md`. The Canada and Qatar fallbacks also commit `track.json`, because their simulated positions use those circuit centerlines. Online preparation for measured sessions adds ignored `telemetry.csv`, `track.json`, `weather.csv`, `race_control.csv`, and `scenario-cache.json`; the loader uses that measured cache only when telemetry and matching metadata are both present. Otherwise it loads the committed reconstruction. `scenario.json` records fallback quality; `scenario-cache.json` records measured-data quality.

The replay CSV preserves the existing telemetry input columns: `timestamp_s`, `car_id`, `x_m`, `y_m`, `speed_kmh`, `longitudinal_accel_g`, `sector`. `timestamp_s` begins at zero to satisfy the v1 loader. `relative_time_s = timestamp_s - incident_offset_s` places the interpreted incident onset at **T=0**, including a five-second pre-roll. For measured sessions, `source_time_utc`, `speed_source_time_utc`, and `position_source_time_utc` preserve the original feed times. The `*_origin` columns mark individual values. Source speed values are real FastF1 samples carried forward at most 0.5 seconds to a causal 0.2-second grid. Position is a FastF1 coordinate converted by 1/10 to approximate metres; acceleration is a trailing speed difference in g, saturated at the existing -8 to +5 input range. Replay zones 1–4 and the reference-lap centerline are **derived proxies**, not official race sectors or surveyed racing lines. Every continuous motion value in `reconstruction.csv` is `SIMULATED`.

All resampling takes the most recent sample **at or before** the replay instant. The stateful detector sees only frames up to that instant. Context events enter the pipeline at their listed availability time. Historical control actions are rendered separately and never enter the model or rule engine. The Random Forest continues to receive its original seven telemetry fields; typed weather/visual facts are available to explicit deterministic rules and explanations only. The model was trained on synthetic examples, so its severity index is neither calibrated accident probability nor validated real-world accuracy.

## The four cases

| Case | Historical facts and source | Measured local cache | Committed fallback | Control timing |
| --- | --- | --- | --- | --- |
| 2022 Canada Tsunoda | Tsunoda stopped at pit exit; roughly one lap under yellows before the Safety Car (RaceFans; Ferrari's Mattia Binotto: "it took very long to decide for the Safety Car") | No measured feed | Simulated delayed-Safety-Car reconstruction | YELLOW ≈ T+5, SAFETY CAR ≈ T+75; approximate, single source |
| 2024 Qatar mirror debris | Mirror on the main straight; no VSC ever deployed, Safety Car only after punctures several laps later (RaceFans, Autosport) | No measured feed | Simulated debris-report reconstruction | DOUBLE YELLOW ≈ T+5, SAFETY CAR ≈ T+160; approximate, real gap was about four laps, compressed for demo |
| 2024 Azerbaijan Pérez/Sainz | [F1 race report](https://www.formula1.com/en/latest/article/its-very-disappointing-sainz-and-perez-give-their-views-on-dramatic-late.33pViZ5hLOZkAQcePX3WnC), [FIA messages](https://www.fia.com/sites/default/files/2024_17_aze_f1_r0_timing_raceracecontrolmessages_v01.pdf), [RaceFans](https://www.racefans.net/2024/09/16/f1-drivers-surprised-race-control-waited-before-deploying-vsc-after-sainz-perez-crash/) | PER/SAI and selected traffic speed/position, weather, yellow/VSC messages | Simulated two-car crash and traffic | Feed messages at approximately T+10 double yellow, T+12 yellow, T+87 VSC; T=0 interpreted from speed trace |
| 2021 Azerbaijan Verstappen | [F1 race report](https://www.formula1.com/en/latest/article/perez-beats-vettel-to-baku-victory-after-verstappen-crashes-out-from-lead.aLIxuNGxwBFgZ4Z8OhuRw), [RaceFans radios](https://www.racefans.net/2021/06/08/whos-next-why-are-they-waiting-concern-and-confusion-on-drivers-radios-after-baku-crashes/) | VER and selected traffic speed/position, weather, yellow/SC/red messages | Simulated tyre-failure motion and traffic | Feed messages approximately T+21 double yellow, T+24 yellow, T+90 Safety Car, T+286 red; T=0 approximate |

Each case's `SOURCES.md` states which source supports each field and whether it is real, derived, reconstructed, or simulated. The actual-message timestamp is a feed record, not necessarily the instant a marshal light was seen by a particular driver. The T=0 anchor is interpreted from speed samples, so relative differences carry onset uncertainty.

The recommendation ladder treats a stopped car as at least a local yellow warning. A sustained stop can escalate to VSC; a street-circuit or no-runoff stop, or close fast traffic, can justify an earlier Safety Car. RED is reserved for corroborating high-consequence evidence, such as a multi-car incident with a stopped car on a street circuit. In the replay examples, that makes Pérez/Sainz a RED recommendation, Verstappen at least a Safety Car, and Tsunoda a faster Safety Car recommendation. These are prototype recommendations; the historical control actions shown in the table remain separate facts.

## Images and offline limits

The four historical replays include user-provided recorded incident stills. At T=0 the matching image and description appear in the compact Incident camera card while replay continues. Each scenario's `visual_features.json` holds reviewed observations and cached `VisualFeatures`; the image hash must match before the UI displays its caption. The pipeline receives those facts only at or after `available_at_relative_s`. `VisionAnalyzer` remains an optional adapter for future images; no general automated image provider is bundled. Vision returns evidence, never a flag.

Because upstream Formula 1 timing-data redistribution rights have not been established, the processed FastF1 files stay ignored locally. A fresh clone still runs offline using clearly marked reconstructions. To demonstrate measured feeds offline, prepare the two Baku caches on that machine before the judge session. Actual control actions stay display-only and never enter the risk engine or ML labels. Historical cases inform the qualitative distinction between local caution, Safety Car neutralization, and red-level corroborating evidence; reconstructed motion is not calibration truth, and recommendations are not judged against exact action times.
