import json
from pathlib import Path

import pytest

from src.track import forward_gap_m, load_track, project_to_track


def make_track(tmp_path: Path) -> Path:
    path = tmp_path / "track.json"
    path.write_text(
        json.dumps({"points": [[0, 0], [1200, 0], [1200, 400], [0, 400], [0, 0]]})
    )
    return path


def test_projection_and_forward_gap_follow_track_not_straight_line(tmp_path: Path) -> None:
    track = load_track(make_track(tmp_path))

    incident = project_to_track(0, 100, track)
    approaching = project_to_track(0, 225, track)

    assert track.length_m == pytest.approx(3200)
    assert incident.s_m == pytest.approx(3100)
    assert incident.offset_m == pytest.approx(0)
    assert forward_gap_m(incident.s_m, approaching.s_m, track.length_m) == pytest.approx(125)


def test_forward_gap_handles_start_finish_wrap() -> None:
    assert forward_gap_m(20, 3180, 3200) == pytest.approx(40)


def test_catmull_rom_closed_loop_is_smooth_and_closed() -> None:
    from src.track import _build_track, catmull_rom_closed

    corners = [(0, 0), (1200, 0), (1200, 400), (0, 400)]
    sampled = catmull_rom_closed(corners, samples_per_segment=10)

    assert len(sampled) == 41  # 4*10 + closing repeat
    assert sampled[0] == sampled[-1]
    track = _build_track(tuple(sampled))
    assert track.length_m > 0
    # no wild overshoot: smoothed loop stays within 10% of the polygon length
    assert abs(track.length_m - 3200.0) / 3200.0 < 0.10


def test_catmull_rom_rejects_bad_input() -> None:
    import pytest

    from src.track import catmull_rom_closed

    with pytest.raises(ValueError):
        catmull_rom_closed([(0, 0), (1, 1), (2, 0)], 10)
    with pytest.raises(ValueError):
        catmull_rom_closed([(0, 0), (1, 0), (1, 1), (0, 1)], 0)
