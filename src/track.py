from dataclasses import dataclass
from bisect import bisect_right
import json
import math
from pathlib import Path


@dataclass(frozen=True)
class Track:
    points: tuple[tuple[float, float], ...]
    cumulative_m: tuple[float, ...]
    length_m: float


@dataclass(frozen=True)
class TrackPosition:
    s_m: float
    offset_m: float
    x_m: float
    y_m: float


def load_track(path: Path) -> Track:
    raw = json.loads(path.read_text())
    points = tuple((float(x), float(y)) for x, y in raw["points"])
    if len(points) < 4 or points[0] != points[-1]:
        raise ValueError("track must be a closed polyline with at least 3 segments")
    cumulative = [0.0]
    for a, b in zip(points, points[1:]):
        length = math.dist(a, b)
        if length == 0:
            raise ValueError("track contains a zero-length segment")
        cumulative.append(cumulative[-1] + length)
    return Track(points, tuple(cumulative), cumulative[-1])


def project_to_track(x_m: float, y_m: float, track: Track) -> TrackPosition:
    best: TrackPosition | None = None
    for index, (start, end) in enumerate(zip(track.points, track.points[1:])):
        dx, dy = end[0] - start[0], end[1] - start[1]
        fraction = ((x_m - start[0]) * dx + (y_m - start[1]) * dy) / (
            dx * dx + dy * dy
        )
        fraction = min(1.0, max(0.0, fraction))
        projected_x = start[0] + fraction * dx
        projected_y = start[1] + fraction * dy
        offset = math.hypot(x_m - projected_x, y_m - projected_y)
        s_m = (track.cumulative_m[index] + fraction * math.hypot(dx, dy)) % track.length_m
        position = TrackPosition(s_m, offset, projected_x, projected_y)
        if best is None or offset < best.offset_m:
            best = position
    assert best is not None
    return best


def forward_gap_m(incident_s_m: float, other_s_m: float, length_m: float) -> float:
    if length_m <= 0:
        raise ValueError("track length must be positive")
    return (incident_s_m - other_s_m) % length_m


def distance_along_track_m(a_s_m: float, b_s_m: float, length_m: float) -> float:
    forward = (a_s_m - b_s_m) % length_m
    return min(forward, length_m - forward)


def point_at_distance(track: Track, distance_m: float) -> tuple[float, float]:
    """Interpolate a position on the bundled centerline."""
    s_m = distance_m % track.length_m
    segment = bisect_right(track.cumulative_m, s_m) - 1
    start = track.points[segment]
    end = track.points[segment + 1]
    fraction = (s_m - track.cumulative_m[segment]) / (
        track.cumulative_m[segment + 1] - track.cumulative_m[segment]
    )
    return (
        start[0] + fraction * (end[0] - start[0]),
        start[1] + fraction * (end[1] - start[1]),
    )
