# ML severity estimate

FlagSense uses `sklearn.ensemble.RandomForestClassifier` because it trains quickly on small tabular, engineered features, supports local inference, and gives a useful global feature-importance view. The model estimates scenario **severity**, not a flag. The deterministic engine owns the recommendation. No neural network, LLM classification, raw-image input, or cloud training is required.

## Current v1 contract

`src/features.py` defines `FEATURE_COLUMNS` in this exact order: `stationary_time_s`, `peak_decel_g`, `on_racing_line`, `closing_speed_kmh`, `closest_car_distance_m`, `nearby_cars`, `multiple_cars_affected`. Booleans become 0/1. No approaching vehicle uses 500 m as a finite distance sentinel, matched by training. Car identity, timestamp, sector, source images, and scenario labels never enter this vector. [Data contracts](DATA_CONTRACTS.md) describe these fields.

Classes are `NORMAL`, `MODERATE_RISK`, and `HIGH_RISK`. The model outputs class probabilities and the class with the largest probability. `risk_score = 0.5 × P(MODERATE_RISK) + P(HIGH_RISK)` is a normalized severity index in `[0,1]`; it is **not** a calibrated probability of injury, crash, or accident. Probability columns must be mapped by `estimator.classes_`, not assumed array position. The model bundle records schema version, ordered fields, class map, seed, and estimator; loading an incompatible artifact selects the labeled fallback.

## Synthetic training and evaluation

The planned generator creates 3,600 balanced examples with seed 42: 1,200 per class, drawn from normal racing, slowdowns/off-line stops, and sustained on-line/traffic/multi-car hazards. Ranges should overlap and contain noise so one field does not perfectly reveal the label. Preserve physical relationships, such as zero closing speed and 500 m distance when there is no approaching car. The prerecorded demo must stay outside model training and test data.

Train with a stratified 75/25 split, fixed seed, and a small Random Forest (the [MVP plan](superpowers/plans/2026-09-26-flagsense-mvp.md) specifies hyperparameters). Report a three-class confusion matrix, precision/recall/F1 classification report, and sorted feature importances. Feature importance describes behavior on synthetic data, not causality. Save the trusted local model and evaluation under `models/`, and commit the small artifact needed for offline playback. Training and generation scripts are not present yet; do not claim a measured score until they run.

## Fusion migration

Vision and environment will first supply structured evidence to the deterministic rule engine and explanation layer. The existing v1 Random Forest remains telemetry-only. A later v2 model may take selected fused fields, but that requires a new explicit field order, synthetic generator, train/test report, artifact schema version, and tests. Never say that v1 ML integrated an image or weather if only the rule engine saw those facts.

## Fallback and limitations

If the model file is missing or incompatible, `RiskEstimator` uses a deterministic score and display-only pseudo-probabilities with `model_source="rules_fallback"`. The dashboard must name that source. Synthetic labels represent scenario assumptions, and even a strong held-out synthetic result cannot demonstrate real-world predictive performance. This prototype is not validated for operational safety use.
