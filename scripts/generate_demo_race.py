from pathlib import Path

import numpy as np
import pandas as pd

from config import Config
from src.track import Track, load_track, point_at_distance


def generate_demo_race(path: Path, track: Track) -> pd.DataFrame:
    """Generate a 20 s, four-car, 10 Hz race-control demonstration."""
    rows: list[dict] = []
    speed_breakpoints_s = [0, 10, 10.8, 11.5, 12.2, 13, 20]
    speed_breakpoints_kmh = [210, 210, 140, 70, 20, 0, 0]
    incident_s = 2447.0
    previous_speed = 210.0
    for tick in range(201):
        timestamp_s = round(tick / 10, 1)
        speed_12 = float(
            np.interp(
                timestamp_s, speed_breakpoints_s, speed_breakpoints_kmh
            )
        )
        if tick:
            incident_s += (previous_speed + speed_12) / 2 / 3.6 * 0.1
        accel_12 = (
            0.0
            if tick == 0
            else (speed_12 - previous_speed) / 3.6 / 0.1 / 9.80665
        )
        previous_speed = speed_12
        cars = (
            (3, 200 + 205 / 3.6 * timestamp_s, 205.0, 0.0),
            (7, 1911.1 + 200 / 3.6 * timestamp_s, 200.0, 0.0),
            (12, incident_s, speed_12, accel_12),
            (21, 1000 + 195 / 3.6 * timestamp_s, 195.0, 0.0),
        )
        for car_id, unwrapped_s, speed, accel in cars:
            s_m = unwrapped_s % track.length_m
            x_m, y_m = point_at_distance(track, s_m)
            rows.append(
                {
                    "timestamp_s": timestamp_s,
                    "car_id": car_id,
                    "x_m": x_m,
                    "y_m": y_m,
                    "speed_kmh": speed,
                    "longitudinal_accel_g": accel,
                    "sector": min(4, int(4 * s_m / track.length_m) + 1),
                }
            )
    table = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(path, index=False, float_format="%.4f")
    return table


if __name__ == "__main__":
    config = Config()
    table = generate_demo_race(config.demo_path, load_track(config.track_path))
    print(f"Wrote {len(table)} telemetry rows to {config.demo_path}")
