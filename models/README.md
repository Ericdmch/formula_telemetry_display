# Local model artifacts

The planned trusted `risk_model.joblib` and `evaluation.txt` should be generated locally and committed if needed for a reliable offline demo. The model bundle must record schema version, the seven ordered v1 columns, class map, and seed. Only load model artifacts created by this project; `joblib` files can execute code when loaded. Missing or incompatible artifacts select a visibly labeled deterministic fallback. See [ML](../docs/ML.md). No artifact exists yet.
