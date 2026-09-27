"""Online preparation: convert FastF1 sessions into local, offline replay files.

The output stays in data/cache and data/scenarios/*/telemetry.csv, both ignored.
Run from the repository root after installing the optional fastf1 dependency.
"""

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PRE_ROLL_S = 5.0
sys.path.insert(0, str(ROOT))

from src.historical import SCENARIO_ROOT
from src.track import load_track, project_to_track
EVENTS = {
    "2024_azerbaijan_perez_sainz": {
        "year": 2024, "event": "Azerbaijan Grand Prix", "session": "Race",
        "anchor": "2024-09-15T12:33:11", "drivers": ("11", "55", "77", "27", "63", "14"),
        "reference_driver": "81", "reference_lap": 49, "seconds_after": 92,
        "sectors": (3, 4),
    },
    "2021_azerbaijan_verstappen": {
        "year": 2021, "event": "Azerbaijan Grand Prix", "session": "Race",
        "anchor": "2021-06-06T13:31:17", "drivers": ("33", "11", "44", "5", "16", "10"),
        "reference_driver": "11", "reference_lap": 44, "seconds_after": 290,
        "sectors": (20, 21),
    },
}


def _verified_session(fastf1, event: dict):
    schedule = fastf1.get_event_schedule(event["year"], include_testing=False)
    match = schedule[schedule["EventName"] == event["event"]]
    if len(match) != 1:
        raise ValueError(f"event not found uniquely: {event['event']}")
    sessions = [match.iloc[0][f"Session{i}"] for i in range(1, 6)]
    if event["session"] not in sessions:
        raise ValueError(f"session unavailable: {event['session']}")
    return fastf1.get_session(event["year"], event["event"], event["session"])


def _reference_track(session, event: dict) -> dict:
    laps = session.laps.pick_drivers(event["reference_driver"])
    if event["reference_lap"] is not None:
        laps = laps[laps["LapNumber"] == event["reference_lap"]]
    else:
        laps = laps[laps["LapTime"].notna()].sort_values("LapTime")
    if laps.empty:
        raise ValueError("no reference lap for track projection")
    lap = laps.iloc[0]
    start, end = session.t0_date + lap["LapStartTime"], session.t0_date + lap["Time"]
    pos = session.pos_data[event["reference_driver"]]
    pos = pos[(pos["Date"] >= start) & (pos["Date"] <= end) & (pos["Status"] == "OnTrack")]
    points = [(round(float(x) / 10, 2), round(float(y) / 10, 2))
              for x, y in pos[["X", "Y"]].iloc[::4].itertuples(index=False, name=None)]
    if len(points) < 20:
        raise ValueError("insufficient reference position samples")
    points.append(points[0])
    return {"description": "FastF1 position proxy from one reference lap; coordinates divided by 10 to metres", "points": points}


def _derive_anchor(session, driver: str, event: dict) -> pd.Timestamp:
    """Find a severe late-session speed collapse, then require a sustained stop."""
    data = session.car_data[driver]
    moving = data[(data["Speed"] > 100) & (data["Date"] > data["Date"].max() - pd.Timedelta(minutes=35))]
    stopped = data[(data["Speed"] <= 5) & (data["Date"] > moving["Date"].min())]
    for row in stopped.itertuples(index=False):
        t = row.Date
        prior = moving[(moving["Date"] >= t - pd.Timedelta(seconds=4)) & (moving["Date"] < t)]
        after = data[(data["Date"] >= t) & (data["Date"] < t + pd.Timedelta(seconds=2))]
        if not prior.empty and len(after) >= 4 and (after["Speed"] <= 10).all():
            return pd.Timestamp(prior.iloc[-1]["Date"])
    raise ValueError("could not identify incident onset from telemetry; inspect feed manually")


def _asof_row(table: pd.DataFrame, when: pd.Timestamp, max_age_s: float = 0.5):
    indices = table["Date"].searchsorted(when, side="right")
    if indices == 0:
        return None
    row = table.iloc[indices - 1]
    if (when - row["Date"]).total_seconds() > max_age_s:
        return None
    return row


def _telemetry(session, event: dict, anchor: pd.Timestamp, track) -> pd.DataFrame:
    rows = []
    previous_speed: dict[int, tuple[float, float]] = {}
    drivers = [d for d in event["drivers"] if d in session.car_data and d in session.pos_data]
    for tick in np.arange(-PRE_ROLL_S, event["seconds_after"] + 0.001, 0.2):
        relative = round(float(tick), 1)
        when = anchor + pd.Timedelta(seconds=relative)
        timestamp = round(relative + PRE_ROLL_S, 1)
        for driver in drivers:
            car = _asof_row(session.car_data[driver], when)
            pos = _asof_row(session.pos_data[driver], when)
            if car is None or pos is None:
                continue
            car_id = int(driver)
            speed = float(car["Speed"])
            last = previous_speed.get(car_id)
            accel = 0.0 if last is None or timestamp - last[1] > 0.3 else (speed - last[0]) / 3.6 / 0.2 / 9.80665
            previous_speed[car_id] = (speed, timestamp)
            x_m, y_m = float(pos["X"]) / 10, float(pos["Y"]) / 10
            projected = project_to_track(x_m, y_m, track)
            rows.append({
                "timestamp_s": timestamp, "relative_time_s": relative,
                "source_time_utc": when.isoformat(), "car_id": car_id,
                "x_m": round(x_m, 2),
                "y_m": round(y_m, 2),
                "speed_kmh": speed,
                "longitudinal_accel_g": round(float(np.clip(accel, -8, 5)), 3),
                "accel_saturated": accel < -8 or accel > 5,
                "sector": min(4, 1 + int(4 * projected.s_m / track.length_m)),
                "speed_origin": "REAL", "position_origin": "DERIVED",
                "accel_origin": "DERIVED",
                "speed_source_time_utc": car["Date"].isoformat(),
                "position_source_time_utc": pos["Date"].isoformat(),
            })
    table = pd.DataFrame(rows).sort_values(["timestamp_s", "car_id"])
    if table.empty or not (table["relative_time_s"] == 0).any():
        raise ValueError("incident T=0 missing from telemetry")
    return table


def _actions(session, event: dict, anchor: pd.Timestamp) -> list[dict]:
    messages = session.race_control_messages
    window = messages[(messages["Time"] >= anchor) &
                      (messages["Time"] <= anchor + pd.Timedelta(seconds=event["seconds_after"]))]
    actions = []
    for row in window.itertuples(index=False):
        action = None
        if row.Category == "Flag" and row.Flag in ("YELLOW", "DOUBLE YELLOW"):
            if event["sectors"] and row.Sector not in event["sectors"]:
                continue
            action = row.Flag
        elif row.Category == "SafetyCar" and "VIRTUAL SAFETY CAR DEPLOYED" in row.Message:
            action = "VSC"
        elif row.Category == "SafetyCar" and "SAFETY CAR DEPLOYED" in row.Message:
            action = "SAFETY CAR"
        elif row.Category == "Flag" and row.Flag == "RED":
            action = "RED FLAG"
        if action:
            actions.append({
                "relative_time_s": round((row.Time - anchor).total_seconds(), 1),
                "action": action, "source": "FASTF1_RACE_CONTROL",
                "original_time_utc": row.Time.isoformat(),
                "timing_quality": "FEED_TIMESTAMP", "detail": row.Message,
            })
    return actions


def fetch(scenario_id: str) -> Path:
    import fastf1  # optional online-preparation dependency

    event = EVENTS[scenario_id]
    cache = ROOT / "data" / "cache" / "fastf1"
    cache.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(cache))
    session = _verified_session(fastf1, event)
    session.load(laps=True, telemetry=True, weather=True, messages=True)
    anchor = pd.Timestamp(event["anchor"]) if event["anchor"] else _derive_anchor(session, event["drivers"][0], event)
    destination = SCENARIO_ROOT / scenario_id
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "track.json").write_text(json.dumps(_reference_track(session, event), indent=2) + "\n")
    telemetry = _telemetry(session, event, anchor, load_track(destination / "track.json"))
    telemetry.to_csv(destination / "telemetry.csv", index=False)
    weather = session.weather_data.copy()
    weather["source_time_utc"] = (session.t0_date + weather["Time"]).dt.strftime("%Y-%m-%dT%H:%M:%S.%f")
    weather["relative_time_s"] = ((session.t0_date + weather["Time"]) - anchor).dt.total_seconds()
    weather = weather[weather["relative_time_s"].between(-120, event["seconds_after"])]
    weather.to_csv(destination / "weather.csv", index=False)
    actions = _actions(session, event, anchor)
    pd.DataFrame(actions).to_csv(destination / "race_control.csv", index=False)
    metadata_path = destination / "scenario.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["incident_start_time_utc"] = anchor.isoformat()
    metadata["incident_offset_s"] = PRE_ROLL_S
    metadata["actual_control_actions"] = actions
    metadata["active_data_quality"] = "REAL_TELEMETRY_WITH_DERIVED_FEATURES"
    metadata["data_quality"] = "REAL_TELEMETRY_WITH_DERIVED_FEATURES"
    metadata["field_provenance"] = {
        "source_time_utc": "REAL", "relative_time_s": "DERIVED",
        "speed_kmh": "REAL", "x_m": "DERIVED", "y_m": "DERIVED",
        "longitudinal_accel_g": "DERIVED", "sector": "DERIVED",
    }
    (destination / "scenario-cache.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
    print(f"{scenario_id}: {len(telemetry)} samples; T=0 {anchor}; {len(actions)} control actions")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=sorted(EVENTS), required=True)
    args = parser.parse_args()
    fetch(args.scenario)


if __name__ == "__main__":
    main()
