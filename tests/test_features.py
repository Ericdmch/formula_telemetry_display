import pandas as pd

from config import Config
from src.features import FEATURE_COLUMNS, extract_features
from src.incident_detection import IncidentDetector
from src.track import load_track


def test_feature_vector_has_exact_order_and_no_car_identity(tmp_path) -> None:
    path = tmp_path / "track.json"
    path.write_text('{"points": [[0,0],[1200,0],[1200,400],[0,400],[0,0]]}')
    track = load_track(path)
    detector = IncidentDetector(Config())
    frame = pd.DataFrame(
        [
            {
                "timestamp_s": 0.0,
                "car_id": 12,
                "x_m": 0,
                "y_m": 100,
                "speed_kmh": 0,
                "longitudinal_accel_g": -4.0,
                "sector": 4,
            }
        ]
    )

    detected = detector.update(frame, track)[0]
    features = extract_features(detected)
    vector = features.model_vector()

    assert list(vector) == list(FEATURE_COLUMNS)
    assert "car_id" not in vector
    assert vector["peak_decel_g"] == -4.0
