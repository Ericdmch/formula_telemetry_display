"""FlagSense prototype/demo settings; safety thresholds are not official FIA rules."""

from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Config:
    sample_interval_s: float = 0.1
    # Retain enough speed history to distinguish a brief stop from a
    # prolonged street-circuit blockage (up to the prototype red threshold).
    history_window_s: float = 300.0
    stopped_speed_kmh: float = 5.0
    stopped_time_s: float = 2.0
    vsc_stationary_time_s: float = 5.0
    safety_car_stationary_s: float = 4.0
    red_stationary_time_s: float = 180.0
    # Prototype/demo hysteresis: a stopped episode ends only when the car is
    # clearly moving again, so brief low-speed blips (recovery handling, sensor
    # noise) do not reset the stationary timer.
    recovered_speed_kmh: float = 25.0
    stopped_blip_tolerance_s: float = 1.5
    # Prototype/demo relative-speed detection: "stopped" is judged against the
    # normal speed profile for that point on track, so a slow corner does not
    # read as an incident. A car counts as anomalously slow below
    # max(stopped_speed_kmh, stopped_speed_ratio * expected_kmh), and is
    # recovered above max(recovered_speed_kmh, recovered_speed_ratio *
    # expected_kmh). Absolute floors keep a parked car flagged anywhere.
    stopped_speed_ratio: float = 0.30
    recovered_speed_ratio: float = 0.60
    severe_decel_g: float = -2.5
    decel_lookback_s: float = 2.0
    racing_line_tolerance_m: float = 3.0
    approach_search_m: float = 250.0
    approach_min_speed_kmh: float = 80.0
    close_distance_m: float = 150.0
    high_closing_speed_kmh: float = 120.0
    nearby_distance_m: float = 150.0
    multicar_radius_m: float = 35.0
    multi_car_risk_threshold: float = 0.60
    yellow_risk_threshold: float = 0.35
    high_risk_review_threshold: float = 0.75
    vision_min_confidence: float = 0.7
    vision_blockage_threshold: float = 0.5
    max_interpolation_gap_s: float = 0.3
    data_unavailable_gap_s: float = 1.0
    track_path: Path = ROOT / "data" / "track.json"
    demo_path: Path = ROOT / "data" / "demo_race.csv"
    training_path: Path = ROOT / "data" / "synthetic_training.csv"
    model_path: Path = ROOT / "models" / "risk_model.joblib"
    evaluation_path: Path = ROOT / "models" / "evaluation.txt"
