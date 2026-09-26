from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Config:
    sample_interval_s: float = 0.1
    history_window_s: float = 8.0
    stopped_speed_kmh: float = 5.0
    stopped_time_s: float = 2.0
    severe_decel_g: float = -2.5
    decel_lookback_s: float = 2.0
    racing_line_tolerance_m: float = 3.0
    approach_search_m: float = 250.0
    approach_min_speed_kmh: float = 80.0
    close_distance_m: float = 150.0
    high_closing_speed_kmh: float = 120.0
    nearby_distance_m: float = 150.0
    multicar_radius_m: float = 35.0
    yellow_risk_threshold: float = 0.35
    red_risk_threshold: float = 0.75
    max_interpolation_gap_s: float = 0.3
    data_unavailable_gap_s: float = 1.0
    track_path: Path = ROOT / "data" / "track.json"
    demo_path: Path = ROOT / "data" / "demo_race.csv"
    model_path: Path = ROOT / "models" / "risk_model.joblib"
