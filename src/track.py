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
    return _build_track(points)


def demo_track_fallback() -> Track:
    """Use the demo course geometry when its JSON asset is unavailable."""
    return _build_track(((0, 0), (1200, 0), (1200, 400), (0, 400), (0, 0)))


def _build_track(points: tuple[tuple[float, float], ...]) -> Track:
    if len(points) < 4 or points[0] != points[-1]:
        raise ValueError("track must be a closed polyline with at least 3 segments")
    if not all(math.isfinite(value) for point in points for value in point):
        raise ValueError("track coordinates must be finite")
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


def _catmull_rom_point(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    """One Catmull-Rom sample between p1 and p2 (uniform, tension 0.5)."""
    t2 = t * t
    t3 = t2 * t
    return (
        0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t
               + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
               + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
        0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t
               + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
               + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3),
    )


def catmull_rom_closed(
    points: list[tuple[float, float]], samples_per_segment: int = 24
) -> list[tuple[float, float]]:
    """Resample a closed control-point loop into a smooth dense polyline.

    Display/geometry helper for turning sparse corner lists (e.g. Fast-F1
    circuit info) into a drivable-looking centerline. Output is closed:
    the last point repeats the first.
    """
    if len(points) < 4:
        raise ValueError("need at least 4 control points for a closed spline")
    if samples_per_segment < 1:
        raise ValueError("samples_per_segment must be positive")
    count = len(points)
    sampled: list[tuple[float, float]] = []
    for i in range(count):
        p0 = points[(i - 1) % count]
        p1 = points[i]
        p2 = points[(i + 1) % count]
        p3 = points[(i + 2) % count]
        for j in range(samples_per_segment):
            sampled.append(_catmull_rom_point(p0, p1, p2, p3, j / samples_per_segment))
    sampled.append(sampled[0])
    return sampled
