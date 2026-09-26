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
