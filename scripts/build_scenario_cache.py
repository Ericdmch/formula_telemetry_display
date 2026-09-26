"""Build portable, explicitly simulated fallback motion for offline demos.

Only historical event order and labelled control facts come from sources.
Continuous vehicle motion here is illustrative; never describe it as telemetry.
"""

import argparse
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import Config
from src.historical import SCENARIO_ROOT
from src.track import load_track, point_at_distance


PROFILES = {
    "2024_azerbaijan_perez_sainz": {
        "end": 92, "cars": [(11, 2200, 195, 0, 1.8), (55, 2210, 190, 0, 2.2), (77, 1900, 215, None, None)],
    },
    "2021_azerbaijan_verstappen": {
        "end": 100, "cars": [(33, 2200, 310, 0, 1.8), (11, 1850, 300, None, None), (44, 1550, 295, None, None)],
    },
    "2024_sao_paulo_stroll": {
        "end": 60, "cars": [(18, 2200, 165, 0, 0.8), (1, 1750, 205, None, None), (16, 1450, 210, None, None)],
    },
    "2014_japan_sutil_bianchi": {
        "end": 110, "cars": [(99, 2200, 170, 0, 1.5), (17, 1600, 175, 103, 105)],
    },
}


def speed_at(t: float, base: float, onset: float | None, stopped_at: float | None) -> float:
    if onset is None or t < onset:
        return base
    assert stopped_at is not None
    return round(base * max(0.0, 1.0 - (t - onset) / (stopped_at - onset)), 2)


def build(scenario_id: str) -> Path:
    if scenario_id not in PROFILES:
        raise ValueError("unknown scenario")
    track = load_track(Config().track_path)
    profile = PROFILES[scenario_id]
    cars = {car_id: {"s": float(start_s), "last_speed": float(speed)}
            for car_id, start_s, speed, _, _ in profile["cars"]}
    rows = []
    for tick in range(int((profile["end"] + 5) / 0.2) + 1):
        relative = round(-5 + tick * 0.2, 1)
        for car_id, _, base, onset, stopped_at in profile["cars"]:
            if scenario_id == "2014_japan_sutil_bianchi" and car_id == 17 and relative < 90:
                continue
            state = cars[car_id]
            speed = speed_at(relative, base, onset, stopped_at)
            if tick:
                state["s"] += speed / 3.6 * 0.2
            accel = 0.0 if tick == 0 else (speed - state["last_speed"]) / 3.6 / 0.2 / 9.80665
            state["last_speed"] = speed
            s_m = state["s"] % track.length_m
            x, y = point_at_distance(track, s_m)
            if scenario_id == "2014_japan_sutil_bianchi" and (
                (car_id == 99 and relative >= 0) or (car_id == 17 and relative >= 103)
            ):
                y += 20  # simulated runoff offset from the synthetic centerline
            rows.append({
                "timestamp_s": round(relative + 5, 1), "relative_time_s": relative,
                "car_id": car_id, "x_m": round(x, 2), "y_m": round(y, 2),
                "speed_kmh": speed, "longitudinal_accel_g": round(max(-8, min(5, accel)), 3),
                "sector": min(4, 1 + int(4 * s_m / track.length_m)),
                "speed_origin": "SIMULATED", "position_origin": "SIMULATED",
                "accel_origin": "SIMULATED", "timing_origin": "SIMULATED",
            })
    destination = SCENARIO_ROOT / scenario_id / "reconstruction.csv"
    pd.DataFrame(rows).to_csv(destination, index=False)
    print(f"{scenario_id}: {len(rows)} simulated rows -> {destination}")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=[*sorted(PROFILES), "all"], default="all")
    args = parser.parse_args()
    for scenario_id in (PROFILES if args.scenario == "all" else [args.scenario]):
        build(scenario_id)


if __name__ == "__main__":
    main()
