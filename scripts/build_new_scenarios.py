"""Build the 2022 Canada and 2024 Qatar historical scenarios.

Fetches official circuit centerlines from the MultiViewer API once ("bake"),
then generates historically-grounded reconstructions with SIMULATED motion
plus scenario metadata. Deterministic: no randomness involved.

Outputs (per scenario): track.json, reconstruction.csv, scenario.json under
data/scenarios/<scenario_id>/.

Usage: python scripts/build_new_scenarios.py [--no-download]
  --no-download rebuilds from cached centerlines in scripts/.cache/
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.track import Track, load_track  # noqa: E402

CACHE = Path(__file__).resolve().parent / ".cache"
DT = 0.2
OFFSET = 5.0  # incident T=0 sits at timestamp 5.0 s
ORIGIN = "SIMULATED"

# (scenario_id, circuit key, year, official length m)
TRACKS = {
    "canada": ("2022_canada_tsunoda", 23, 2022, 4361.0),
    "qatar": ("2024_qatar_mirror_debris", 150, 2023, 5380.0),
}


def fetch_centerline(circuit_key: int, year: int) -> list[tuple[float, float]]:
    """Official MultiViewer circuit centerline; x/y arrive in decimetres."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"circuit_{circuit_key}_{year}.json"
    if cached.is_file():
        raw = json.loads(cached.read_text())
    else:
        url = f"https://api.multiviewer.app/api/v1/circuits/{circuit_key}/{year}"
        request = urllib.request.Request(
            url, headers={"User-Agent": "FlagSense-demo/1.0 (prototype)"})
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = json.loads(response.read().decode())
        cached.write_text(json.dumps(raw))
    points = [(float(x) / 10.0, float(y) / 10.0)
              for x, y in zip(raw["x"], raw["y"])]
    if points[0] != points[-1]:
        points.append(points[0])
    return points


def scale_to_length(points: list[tuple[float, float]],
                    target_m: float) -> list[tuple[float, float]]:
    total = sum(math.dist(a, b) for a, b in zip(points, points[1:]))
    factor = target_m / total
    return [(x * factor, y * factor) for x, y in points]


def smooth_centerline(points: list[tuple[float, float]],
                      radius: int = 4) -> list[tuple[float, float]]:
    """Light moving-average smoothing on the closed loop (keeps closure)."""
    ring = points[:-1]
    n = len(ring)
    out = []
    for i in range(n):
        sx = sy = 0.0
        for k in range(-radius, radius + 1):
            x, y = ring[(i + k) % n]
            sx += x
            sy += y
        out.append((sx / (2 * radius + 1), sy / (2 * radius + 1)))
    out.append(out[0])
    return out


def target_speeds(track: Track, lat_accel: float = 38.0,
                  vmax_mps: float = 89.0) -> list[float]:
    """Per-point target speed from curvature (smooth, braking-agnostic)."""
    pts = track.points
    n = len(pts) - 1
    raw: list[float] = []
    for i in range(n):
        p0, p1, p2 = pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        a1 = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
        a2 = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
        dtheta = abs((a2 - a1 + math.pi) % (2 * math.pi) - math.pi)
        ds = math.dist(p0, p1) or 1e-6
        kappa = dtheta / ds
        raw.append(min(vmax_mps, math.sqrt(lat_accel / max(kappa, 1e-9))))
    # Smooth aggressively so scripted cars never exceed the profile mid-corner.
    radius = 25
    out = []
    for i in range(n):
        window = [raw[(i + k) % n] for k in range(-radius, radius + 1)]
        out.append(sum(window) / len(window))
    return out


def make_profiler(track: Track, speeds: list[float]):
    cum = track.cumulative_m
    n = len(speeds)

    def at(s_m: float) -> float:
        s = s_m % track.length_m
        # segment lookup
        lo, hi = 0, n
        while lo < hi:
            mid = (lo + hi) // 2
            if cum[mid + 1] < s:
                lo = mid + 1
            else:
                hi = mid
        i = min(lo, n - 1)
        frac = (s - cum[i]) / ((cum[i + 1] - cum[i]) or 1e-9)
        return speeds[i] * (1 - frac) + speeds[(i + 1) % n] * frac

    def point(s_m: float, offset_m: float) -> tuple[float, float]:
        s = s_m % track.length_m
        lo, hi = 0, n
        while lo < hi:
            mid = (lo + hi) // 2
            if cum[mid + 1] < s:
                lo = mid + 1
            else:
                hi = mid
        i = min(lo, n - 1)
        p0, p1 = track.points[i], track.points[i + 1]
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        seg = math.hypot(dx, dy) or 1e-9
        frac = (s - cum[i]) / seg
        # left-hand normal
        nx, ny = -dy / seg, dx / seg
        return (p0[0] + frac * dx + offset_m * nx,
                p0[1] + frac * dy + offset_m * ny)

    return at, point


class Car:
    def __init__(self, car_id: int, s0: float, offset_m: float,
                 speed_fn):
        self.car_id = car_id
        self.s = s0
        self.offset_m = offset_m
        self.speed_fn = speed_fn  # (t, s, v_target) -> v_mps
        self.v = 0.0


def simulate(track: Track, cars: list[Car], t_end: float,
             profiler) -> list[dict]:
    v_target_at, point_at = profiler
    rows: list[dict] = []
    t = 0.0
    # settle initial speeds
    for car in cars:
        car.v = v_target_at(car.s)
    steps = int(round(t_end / DT)) + 1
    for step in range(steps):
        t = round(step * DT, 10)
        for car in cars:
            v_prev = car.v
            v = car.speed_fn(t, car.s, v_target_at(car.s))
            v = max(0.0, v)
            car.v = v
            car.s = (car.s + v * DT) % track.length_m
            x, y = point_at(car.s, car.offset_m)
            accel_g = (v - v_prev) / DT / 9.81 if step else 0.0
            accel_g = min(5.0, max(-8.0, accel_g))
            sector = int(car.s / track.length_m * 4) + 1
            rows.append({
                "timestamp_s": t,
                "relative_time_s": t - OFFSET,
                "car_id": car.car_id,
                "x_m": round(x, 4),
                "y_m": round(y, 4),
                "speed_kmh": round(v * 3.6, 4),
                "longitudinal_accel_g": round(accel_g, 4),
                "sector": min(4, max(1, sector)),
                "speed_origin": ORIGIN,
                "position_origin": ORIGIN,
                "accel_origin": ORIGIN,
                "timing_origin": ORIGIN,
            })
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    columns = ["timestamp_s", "relative_time_s", "car_id", "x_m", "y_m",
               "speed_kmh", "longitudinal_accel_g", "sector", "speed_origin",
               "position_origin", "accel_origin", "timing_origin"]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------- Canada ---
def build_canada(track: Track, profiler) -> tuple[list[dict], dict]:
    L = track.length_m
    # Incident: Tsunoda (#22) emergency-brakes at T=0 (timestamp OFFSET)
    # and stops.
    def v_22(t, s, vt):
        if t < OFFSET:
            return vt
        v0 = 72.0  # ~260 km/h at brake application
        return max(0.0, v0 - 38.0 * (t - OFFSET))

    def v_cruise(t, s, vt):
        return vt

    # Car 22 starts so the stop lands just past start/finish (pit-exit area).
    stop_dist = 72.0 ** 2 / (2 * 38.0)
    s_inc = 0.10 * L
    # distance covered in the 5 s lead-in at ~profile speed
    lead = 5.0 * 72.0
    cars = [
        Car(22, (s_inc - stop_dist - lead) % L, 1.5, v_22),
        Car(55, (s_inc - stop_dist - lead - 320) % L, -1.0, v_cruise),
        Car(16, (s_inc - stop_dist - lead - 640) % L, 1.0, v_cruise),
        Car(63, (s_inc - stop_dist - lead - 980) % L, -1.5, v_cruise),
        Car(44, (s_inc - stop_dist - lead - 1400) % L, 0.5, v_cruise),
        Car(11, (s_inc - stop_dist - lead - 1900) % L, -0.5, v_cruise),
        Car(4, (s_inc - stop_dist - lead - 2500) % L, 1.2, v_cruise),
        Car(77, (s_inc - stop_dist - lead - 3100) % L, -1.2, v_cruise),
    ]
    rows = simulate(track, cars, 100.0, profiler)
    metadata = {
        "scenario_id": "2022_canada_tsunoda",
        "title": "2022 Canada — Tsunoda",
        "season": 2022,
        "event": "Canadian Grand Prix",
        "session": "Race",
        "description": (
            "Yuki Tsunoda crashed at the pit-lane exit late in the race. "
            "The incident was covered by yellow flags for roughly a full lap "
            "before race control deployed the Safety Car — "
            "a documented delayed Safety Car example."
        ),
        "incident_cars": [22],
        "approaching_cars": [55, 16],
        "data_quality": "HISTORICALLY_GROUNDED_RECONSTRUCTION",
        "incident_offset_s": OFFSET,
        "incident_start_time_utc": "2022-06-19T19:15:00",
        "incident_time_quality": "REPORTED_APPROXIMATE",
        "field_provenance": {
            "relative_time_s": "DERIVED",
            "speed_kmh": ORIGIN,
            "x_m": ORIGIN,
            "y_m": ORIGIN,
            "longitudinal_accel_g": ORIGIN,
            "sector": ORIGIN,
        },
        "actual_control_actions": [
            {"relative_time_s": 5.0, "action": "YELLOW",
             "source": "RACEFANS",
             "timing_quality": "REPORTED_APPROXIMATE"},
            {"relative_time_s": 75.0, "action": "SAFETY CAR",
             "source": "RACEFANS",
             "timing_quality": "REPORTED_APPROXIMATE"},
        ],
        "presentation_note": (
            "Documented: roughly one lap under yellow flags before the Safety "
            "Car (Ferrari's Mattia Binotto: 'it took very long to decide for "
            "the Safety Car')."
        ),
        "weather_context": {
            "rainfall": False,
            "source": "REPORTED",
            "quality": "REPORTED",
        },
        "track_context": {
            "location": "Pit-lane exit",
            "source": "RACEFANS",
            "quality": "REPORTED",
        },
        "notes": [
            "Historical control actions and FlagSense recommendations are separate outputs.",
            "The prototype RED_RECOMMENDED state is not an FIA red-flag rule.",
        ],
        "limitations": [
            "No licensed incident photograph is bundled.",
            "Fallback motion is simulated and illustrates documented conditions, not measured car motion.",
            "Control-action timings are approximate, derived from contemporary reporting (single source).",
        ],
    }
    return rows, metadata


# ----------------------------------------------------------------- Qatar ---
def build_qatar(track: Track, profiler) -> tuple[list[dict], dict]:
    L = track.length_m
    v_target_at, _ = profiler
    # Debris location: midpoint of the longest fast stretch (main straight).
    speeds = [v_target_at(i * 5.0) for i in range(int(L / 5.0))]
    best, best_run = 0, 0
    i = 0
    while i < len(speeds):
        if speeds[i] > 80.0:
            j = i
            while j < len(speeds) and speeds[j] > 80.0:
                j += 1
            if j - i > best_run:
                best_run, best = j - i, (i + j) // 2
            i = j
        else:
            i += 1
    s_debris = (best * 5.0) % L

    def strike(t, t0, vmin, recover_s):
        # sharp slowdown at t0, hold vmin, then recover toward profile
        def fn(tt, s, vt):
            if tt < t0:
                return vt
            if tt < t0 + 1.5:
                return vmin + (vt - vmin) * max(0.0, 1 - (tt - t0) / 1.5)
            if tt < t0 + recover_s:
                return vmin
            blend = min(1.0, (tt - t0 - recover_s) / 3.0)
            return vmin + (vt - vmin) * blend
        return fn

    def v_cruise(t, s, vt):
        return vt

    # Strike times below are relative seconds; the sim clock starts at
    # timestamp 0 = T-5, so add OFFSET to get timestamps.
    def strike_rel(t_rel, vmin, recover_s):
        return strike(0, t_rel + OFFSET, vmin, recover_s)

    # Bottas strikes the mirror at T+150 and limps on (puncture); Hamilton
    # and Sainz hit the debris field shortly after, then recover.
    cars = [
        Car(77, (s_debris - 150 * 82.0) % L, 1.0, strike_rel(150.0, 25.0, 1e9)),
        Car(44, (s_debris - 156 * 82.0 - 400) % L, -1.0, strike_rel(156.0, 30.0, 8.0)),
        Car(55, (s_debris - 162 * 82.0 - 800) % L, 1.2, strike_rel(162.0, 30.0, 8.0)),
        Car(4, (s_debris - 1200) % L, -1.2, v_cruise),
        Car(23, (s_debris - 2000) % L, 0.5, v_cruise),
        Car(16, (s_debris - 2900) % L, -0.5, v_cruise),
    ]
    rows = simulate(track, cars, 185.0, profiler)
    metadata = {
        "scenario_id": "2024_qatar_mirror_debris",
        "title": "2024 Qatar — Mirror debris",
        "season": 2024,
        "event": "Qatar Grand Prix",
        "session": "Race",
        "description": (
            "Alex Albon's mirror detached on the main straight and lay on the "
            "circuit under double yellows. No VSC was ever deployed; the "
            "Safety Car came only after Bottas shattered the mirror and "
            "punctures followed — a documented delayed-VSC example."
        ),
        "incident_cars": [77],
        "approaching_cars": [44, 55],
        "data_quality": "HISTORICALLY_GROUNDED_RECONSTRUCTION",
        "incident_offset_s": OFFSET,
        "incident_start_time_utc": "2024-12-01T16:40:00",
        "incident_time_quality": "REPORTED_APPROXIMATE",
        "field_provenance": {
            "relative_time_s": "DERIVED",
            "speed_kmh": ORIGIN,
            "x_m": ORIGIN,
            "y_m": ORIGIN,
            "longitudinal_accel_g": ORIGIN,
            "sector": ORIGIN,
        },
        "actual_control_actions": [
            {"relative_time_s": 5.0, "action": "DOUBLE YELLOW",
             "source": "RACEFANS",
             "timing_quality": "REPORTED_APPROXIMATE"},
            {"relative_time_s": 160.0, "action": "SAFETY CAR",
             "source": "AUTOSPORT",
             "timing_quality": "REPORTED_APPROXIMATE"},
        ],
        "context_events": [
            {"event": "Debris reported on track",
             "relative_time_s": 0.0,
             "quality": "REPORTED",
             "detail": "Mirror on main straight"},
        ],
        "presentation_note": (
            "Documented: no VSC was ever deployed for the mirror; the Safety "
            "Car came only after punctures, several laps later. The-Race "
            "called it a 'bafflingly slow decision'; the FIA defended it as "
            "'normal practice' — genuinely disputed."
        ),
        "weather_context": {
            "rainfall": False,
            "source": "REPORTED",
            "quality": "REPORTED",
        },
        "track_context": {
            "location": "Main straight",
            "source": "THE_RACE",
            "quality": "REPORTED",
        },
        "notes": [
            "Historical control actions and FlagSense recommendations are separate outputs.",
            "The prototype RED_RECOMMENDED state is not an FIA red-flag rule.",
            "The debris hazard is a documented marshal/race-control report; FlagSense treats it as reported context, not a telemetry detection.",
        ],
        "limitations": [
            "No licensed incident photograph is bundled.",
            "Fallback motion is simulated and illustrates documented conditions, not measured car motion.",
            "The real mirror-to-Safety-Car gap was about four laps; the timeline is compressed for demo length.",
            "Control-action timings are approximate, derived from contemporary reporting.",
        ],
    }
    return rows, metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-download", action="store_true")
    args = parser.parse_args()

    builders = {"canada": build_canada, "qatar": build_qatar}
    for key, (scenario_id, circuit_key, year, length_m) in TRACKS.items():
        if args.no_download and not (CACHE / f"circuit_{circuit_key}_{year}.json").is_file():
            raise SystemExit(f"no cached centerline for {key}; run without --no-download")
        points = fetch_centerline(circuit_key, year)
        # Smooth first (smoothing shortens the loop slightly), then scale to
        # the official lap length so the asset matches its description.
        points = scale_to_length(smooth_centerline(points), length_m)
        track_dir = ROOT / "data" / "scenarios" / scenario_id
        track_dir.mkdir(parents=True, exist_ok=True)
        track_path = track_dir / "track.json"
        track_path.write_text(json.dumps({
            "description": (
                f"Official circuit centerline via MultiViewer "
                f"(api.multiviewer.app/api/v1/circuits/{circuit_key}/{year}), "
                f"x/y decimetres to metres, scaled to {length_m:.0f} m. "
                "Prototype demo asset."
            ),
            "source": "MultiViewer official circuit geometry",
            "points": [[round(x, 2), round(y, 2)] for x, y in points],
        }))
        track = load_track(track_path)
        speeds = target_speeds(track)
        profiler = make_profiler(track, speeds)
        rows, metadata = builders[key](track, profiler)
        write_csv(track_dir / "reconstruction.csv", rows)
        (track_dir / "scenario.json").write_text(
            json.dumps(metadata, indent=2) + "\n")
        print(f"{scenario_id}: {len(rows)} rows, track {len(points)} pts, "
              f"{track.length_m:.0f} m")


if __name__ == "__main__":
    main()
