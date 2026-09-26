from pathlib import Path

from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parents[1] / "app.py"


def test_dashboard_loads_offline_demo_and_controls_playback() -> None:
    at = AppTest.from_file(APP, default_timeout=30).run()

    assert not at.exception
    assert at.title[0].value == "FlagSense"
    assert at.session_state["latest_result"].flag == "GREEN"
    assert at.session_state["playback_index"] == 0

    at.get_by_key("start_demo").click().run()
    assert at.session_state["running"] is True

    at.get_by_key("pause_demo").click().run()
    assert at.session_state["running"] is False

    at.get_by_key("reset_demo").click().run()
    assert at.session_state["playback_index"] == 0
    assert at.session_state["latest_result"].flag == "GREEN"


def test_dashboard_can_select_historical_case_without_network() -> None:
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.get_by_key("scenario_choice").set_value("2014_japan_sutil_bianchi").run()

    assert not at.exception
    assert at.session_state["active_scenario"] == "2014_japan_sutil_bianchi"
    assert at.session_state["latest_result"].status == "OK"
    assert any("historical sensor-fusion case study" in item.value for item in at.warning)
    assert any("Actual race control vs FlagSense" in item.value for item in at.subheader)
    assert at.session_state["playback_index"] == 0


def test_dashboard_displays_first_measured_or_fallback_replay() -> None:
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.get_by_key("scenario_choice").set_value("2024_azerbaijan_perez_sainz").run()

    assert not at.exception
    assert at.session_state["active_scenario"] == "2024_azerbaijan_perez_sainz"
    assert at.session_state["latest_result"].flag == "GREEN"
    assert any("Actual race control vs FlagSense" in item.value for item in at.subheader)
    assert any("Data quality" in item.value for item in at.info)
