import json
from pathlib import Path
import shutil

import pytest

from src.historical import SCENARIO_ROOT, load_scenario, scenario_ids
from src.pipeline import SafetyPipeline
from src.sensor_fusion import VisualFeatures
from src.track import load_track


@pytest.fixture
def portable_root(tmp_path: Path) -> Path:
    for scenario_id in scenario_ids():
        source = SCENARIO_ROOT / scenario_id
        destination = tmp_path / scenario_id
        destination.mkdir()
        shutil.copy(source / "scenario.json", destination / "scenario.json")
        shutil.copy(source / "reconstruction.csv", destination / "reconstruction.csv")
    return tmp_path


def test_all_portable_scenarios_normalize_incident_and_label_motion(portable_root: Path) -> None:
    assert len(scenario_ids(portable_root)) == 6
    for scenario_id in scenario_ids(portable_root):
        scenario = load_scenario(scenario_id, portable_root)
        assert scenario.relative_time(scenario.frames[0]["timestamp_s"].iloc[0]) == -5
        assert any(scenario.relative_time(frame["timestamp_s"].iloc[0]) == 0 for frame in scenario.frames)
        assert scenario.metadata["data_quality"] == "HISTORICALLY_GROUNDED_RECONSTRUCTION"
        assert scenario.metadata["field_provenance"]["speed_kmh"] == "SIMULATED"
        assert {origin for frame in scenario.frames for origin in frame["speed_origin"]} == {"SIMULATED"}


def test_invalid_schema_and_actual_action_order_rejected(portable_root: Path) -> None:
    path = portable_root / "2024_azerbaijan_perez_sainz" / "scenario.json"
    data = json.loads(path.read_text())
    data["actual_control_actions"] = list(reversed(data["actual_control_actions"]))
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="out of time order"):
        load_scenario("2024_azerbaijan_perez_sainz", portable_root)


def test_incomplete_measured_cache_falls_back_to_labelled_reconstruction(portable_root: Path) -> None:
    folder = portable_root / "2024_azerbaijan_perez_sainz"
    shutil.copy(folder / "reconstruction.csv", folder / "telemetry.csv")
    scenario = load_scenario("2024_azerbaijan_perez_sainz", portable_root)
    assert scenario.metadata["data_quality"] == "HISTORICALLY_GROUNDED_RECONSTRUCTION"
    assert scenario.track_path.parent != folder
    assert scenario.frames[0]["speed_origin"].iloc[0] == "SIMULATED"


def test_actual_state_is_separate_and_untimed_actions_do_not_gain_seconds(portable_root: Path) -> None:
    baku = load_scenario("2024_azerbaijan_perez_sainz", portable_root)
    assert baku.actual_state(9) == "GREEN / SESSION RUNNING"
    assert baku.actual_state(10) == "DOUBLE YELLOW (LOCAL MESSAGE)"
    assert baku.actual_state(12) == "YELLOW (LOCAL MESSAGE)"
    assert baku.actual_state(87) == "VSC"
    japan = load_scenario("2014_japan_sutil_bianchi", portable_root)
    assert all(action["relative_time_s"] is None for action in japan.metadata["actual_control_actions"])
    assert "timing unavailable" in japan.actual_state(10)


def test_missing_optional_weather_and_visual_do_not_change_pipeline_contract(portable_root: Path) -> None:
    path = portable_root / "2024_azerbaijan_perez_sainz" / "scenario.json"
    data = json.loads(path.read_text())
    data.pop("weather_context")
    path.write_text(json.dumps(data))
    scenario = load_scenario("2024_azerbaijan_perez_sainz", portable_root)
    assert scenario.visual_at(scenario.frames[0]) is None
    pipeline = SafetyPipeline(track=load_track(scenario.track_path))
    results = [scenario.update_pipeline(pipeline, frame) for frame in scenario.frames[:55]]
    assert results[0].flag == "GREEN"
    assert all(result.status == "OK" for result in results)
    assert any(result.incident is not None for result in results)
    assert all(result.context_evidence is None or result.context_evidence["vision_source"] is None for result in results)


def test_cached_visual_facts_are_not_visible_before_availability(portable_root: Path) -> None:
    folder = portable_root / "2024_azerbaijan_perez_sainz"
    (folder / "visual_features.json").write_text(json.dumps({
        "available_at_relative_s": 4.0,
        "features": {"debris_visible": True, "confidence": 0.9, "source": "cached"},
    }))
    scenario = load_scenario("2024_azerbaijan_perez_sainz", portable_root)
    before = next(f for f in scenario.frames if abs(scenario.relative_time(f["timestamp_s"].iloc[0]) - 3.8) < 1e-6)
    after = next(f for f in scenario.frames if abs(scenario.relative_time(f["timestamp_s"].iloc[0]) - 4.0) < 1e-6)
    assert scenario.visual_at(before) is None
    assert scenario.visual_at(after).debris_visible is True


def test_attached_still_image_facts_enter_only_subsequent_frames(portable_root: Path) -> None:
    scenario = load_scenario("2024_azerbaijan_perez_sainz", portable_root)
    pipeline = SafetyPipeline(track=load_track(scenario.track_path))
    visual = VisualFeatures(debris_visible=True, confidence=0.8, source="manual")
    before_sources = []
    after_sources = []
    for frame in scenario.frames[:75]:
        relative = scenario.relative_time(float(frame["timestamp_s"].iloc[0]))
        result = scenario.update_pipeline(pipeline, frame, visual if relative >= 4 else None)
        source = result.context_evidence and result.context_evidence["vision_source"]
        (before_sources if relative < 4 else after_sources).append(source)
    assert all(source is None for source in before_sources)
    assert "manual" in after_sources


def test_recovery_evidence_is_available_only_after_reconstructed_event(portable_root: Path) -> None:
    scenario = load_scenario("2014_japan_sutil_bianchi", portable_root)
    at_zero = next(f for f in scenario.frames if scenario.relative_time(f["timestamp_s"].iloc[0]) == 0)
    at_twenty = next(f for f in scenario.frames if scenario.relative_time(f["timestamp_s"].iloc[0]) == 20)
    assert scenario.environment_at(at_zero).recovery_vehicle_present is None
    assert scenario.environment_at(at_twenty).recovery_vehicle_present is True
    assert scenario.environment_at(at_twenty).quality == "SIMULATED_TIMING_DOCUMENTED_EVENT"


def test_debris_report_context_event_reaches_pipeline(portable_root: Path) -> None:
    scenario = load_scenario("2024_qatar_mirror_debris", portable_root)
    assert scenario.metadata["context_events"] == [{
        "event": "Debris reported on track",
        "relative_time_s": 0.0,
        "quality": "REPORTED",
        "detail": "Mirror on main straight",
    }]
    before = next(f for f in scenario.frames
                  if scenario.relative_time(float(f["timestamp_s"].iloc[0])) == -5)
    at_zero = next(f for f in scenario.frames
                   if scenario.relative_time(float(f["timestamp_s"].iloc[0])) == 0)
    assert scenario.environment_at(before).debris_reported is None
    assert scenario.environment_at(at_zero).debris_reported is True


def test_new_scenario_replay_flag_ladders(portable_root: Path) -> None:
    ladders = {
        "2022_canada_tsunoda": [
            (-5.0, "GREEN", "NO_INCIDENT"),
            (2.8, "RED_RECOMMENDED", "MODEL_RISK_RED"),
        ],
        "2024_qatar_mirror_debris": [
            (-5.0, "GREEN", "NO_INCIDENT"),
            (0.0, "VSC", "DEBRIS_REPORTED_ON_TRACK"),
            (172.6, "SAFETY_CAR", "ON_LINE_CLOSE_FAST_TRAFFIC"),
        ],
    }
    for scenario_id, expected in ladders.items():
        folder = portable_root / scenario_id
        shutil.copy(SCENARIO_ROOT / scenario_id / "track.json", folder / "track.json")
        scenario = load_scenario(scenario_id, portable_root)
        results = scenario.replay()
        assert len(results) == len(scenario.frames)
        transitions = []
        previous = None
        for frame, result in zip(scenario.frames, results):
            if result.flag != previous:
                transitions.append((
                    scenario.relative_time(float(frame["timestamp_s"].iloc[0])),
                    result.flag,
                    result.rule_id,
                ))
                previous = result.flag
        assert [flag for _, flag, _ in transitions] == [flag for _, flag, _ in expected]
        assert [rule for _, _, rule in transitions] == [rule for _, _, rule in expected]
        assert [when for when, _, _ in transitions] == pytest.approx(
            [when for when, _, _ in expected])


def test_replay_prefix_is_causal_and_uses_normal_pipeline(portable_root: Path) -> None:
    scenario = load_scenario("2024_azerbaijan_perez_sainz", portable_root)
    frames = scenario.frames[:45]
    first = SafetyPipeline(track=load_track(scenario.track_path))
    second = SafetyPipeline(track=load_track(scenario.track_path))
    first_results = [scenario.update_pipeline(first, frame) for frame in frames]
    second_results = [scenario.update_pipeline(second, frame) for frame in scenario.frames[:80]][:45]
    assert [(result.flag, result.severity, result.incident and result.incident["car_id"])
            for result in first_results] == [
                (result.flag, result.severity, result.incident and result.incident["car_id"])
                for result in second_results]
    assert [result.risk_score for result in first_results] == pytest.approx(
        [result.risk_score for result in second_results])
    assert first_results[0].flag == "GREEN"
    assert any(result.incident for result in first_results)
