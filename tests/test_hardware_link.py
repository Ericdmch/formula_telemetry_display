"""Tests for src/hardware_link.py — the dashboard -> ESP32 translation layer.

Covers the exact wire strings the firmware parser (protocol v2) accepts, so
these tests and the firmware native tests cross-check the same contract.
"""

import time
from types import SimpleNamespace

import pytest

from src.hardware_link import (
    HardwareLink,
    build_context,
    build_wire_message,
    list_serial_ports,
)


def result(flag, rule_id=None, car_id=None, sector=None):
    incident = None
    if car_id is not None:
        incident = {"car_id": car_id, "sector": sector or 0}
    return SimpleNamespace(flag=flag, rule_id=rule_id, incident=incident)


class FakeTransport:
    def __init__(self):
        self.written = []
        self.incoming = []
        self.opened = []
        self.fail_writes = 0

    def open(self, port, baudrate=115200):
        if port == "BAD":
            raise OSError("no such port")
        self.opened.append((port, baudrate))

    def write_line(self, line):
        if self.fail_writes:
            self.fail_writes -= 1
            raise OSError("unplugged")
        self.written.append(line)

    def read_available(self):
        out, self.incoming = self.incoming, []
        return out

    def close(self):
        pass

    def inject(self, line):
        self.incoming.append(line)


# ---- serialization: exact wire strings ----
def test_green_is_bare():
    assert build_wire_message("GREEN", "NO_INCIDENT", None, 1) == "GREEN"


def test_wire_format_per_flag():
    cases = [
        ("YELLOW", "STOPPED_CAR_YELLOW", "YELLOW,2,0,STOPPED_CAR,27,7,C27 S2 STOPPED"),
        ("DOUBLE_YELLOW", "STOPPED_ON_LINE", "DOUBLE_YELLOW,2,0,STOPPED_CAR,27,7,C27 S2 STOPPED"),
        ("VSC", "SUSTAINED_STOP_VSC", "VSC,2,0,STOPPED_CAR,27,7,C27 S2 STOPPED"),
        ("SAFETY_CAR", "ON_LINE_CLOSE_FAST_TRAFFIC", "SAFETY_CAR,2,0,STOPPED_CAR,27,7,C27 S2 STOPPED"),
        ("RED_RECOMMENDED", "RECOVERY_WET_POOR_VISIBILITY", "RED,2,0,SESSION_STOPPED,27,7,C27 S2 SESSION"),
    ]
    for flag, rule, expected in cases:
        incident = {"car_id": 27, "sector": 2}
        assert build_wire_message(flag, rule, incident, 7) == expected, flag


def test_rule_to_hazard_mapping():
    assert "MULTI_CAR_INCIDENT" in build_wire_message(
        "SAFETY_CAR", "MULTI_CAR_HIGH_RISK", {"car_id": 1, "sector": 1}, 1
    )
    assert ",TRACK_BLOCKED," in build_wire_message(
        "RED_RECOMMENDED", "VISUAL_BLOCKAGE_WITH_STOP", {"car_id": 1, "sector": 1}, 1
    )
    assert ",DEBRIS," in build_wire_message(
        "VSC", "DEBRIS_REPORTED_ON_TRACK", None, 1
    )
    # Unknown rule -> honest UNKNOWN_HAZARD, never an invented hazard.
    assert ",UNKNOWN_HAZARD," in build_wire_message(
        "YELLOW", "SOME_FUTURE_RULE", {"car_id": 1, "sector": 1}, 1
    )


def test_unknown_flag_returns_none():
    assert build_wire_message("PURPLE", "X", None, 1) is None
    assert build_wire_message(None, "X", None, 1) is None


def test_debris_vsc_without_incident():
    assert build_wire_message("VSC", "DEBRIS_REPORTED_ON_TRACK", None, 3) == (
        "VSC,0,0,DEBRIS,0,3,DEBRIS REPORTED"
    )


def test_context_never_exceeds_lcd_budget_and_has_no_commas():
    assert build_context("GREEN", "NO_INCIDENT", None) == "Track clear"
    assert build_context("VSC", "DEBRIS_REPORTED_ON_TRACK", None) == "DEBRIS REPORTED"
    ctx = build_context("YELLOW", "STOPPED_CAR_YELLOW", {"car_id": 99, "sector": 3})
    assert len(ctx) <= 16 and "," not in ctx
    # No incident, no debris -> generic, honest fallback.
    assert build_context("YELLOW", "MODEL_RISK_YELLOW", None) == "CAUTION"


# ---- link behavior ----
def make_link(**kwargs):
    kwargs.setdefault("heartbeat_s", 0.05)
    factory = kwargs.pop("factory", FakeTransport)
    link = HardwareLink(transport_factory=factory, **kwargs)
    link.connect("/dev/fake")
    return link


def test_heartbeat_repeats_unchanged_recommendation_with_bumped_seq():
    link = make_link()
    try:
        link.update(result("YELLOW", "STOPPED_CAR_YELLOW", car_id=27, sector=2))
        time.sleep(0.3)
        transport = link._transport
        assert len(transport.written) >= 3
        seqs = [int(w.split(",")[5]) for w in transport.written]
        assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
        bodies = {",".join(w.split(",")[:5] + w.split(",")[6:]) for w in transport.written}
        assert len(bodies) == 1  # same recommendation, only seq differs
    finally:
        link.disconnect()


def test_changed_recommendation_sends_immediately():
    link = make_link()
    try:
        link.update(result("YELLOW", "STOPPED_CAR_YELLOW", car_id=27, sector=2))
        time.sleep(0.15)
        link.update(result("RED_RECOMMENDED", "RECOVERY_WET_POOR_VISIBILITY",
                           car_id=27, sector=2))
        time.sleep(0.15)
        written = link._transport.written
        assert written[0].startswith("YELLOW,")
        assert any(w.startswith("RED,") for w in written[1:4])
    finally:
        link.disconnect()


def test_none_flag_keeps_last_valid_recommendation():
    link = make_link()
    try:
        assert link.update(result("YELLOW", "STOPPED_CAR_YELLOW", car_id=27, sector=2))
        assert link.update(result(None))  # DATA UNAVAILABLE: keep last valid
        time.sleep(0.15)
        assert all(w.startswith("YELLOW,") for w in link._transport.written)
        assert all("GREEN" not in w.split(",")[0] for w in link._transport.written)
    finally:
        link.disconnect()


def test_nothing_sent_before_first_valid_result():
    link = make_link()
    try:
        link.update(result(None))
        time.sleep(0.15)
        assert link._transport.written == []
    finally:
        link.disconnect()


def test_device_heartbeat_drives_online_status():
    link = make_link()
    try:
        link._transport.inject("STATUS,READY")
        link._transport.inject("STATUS,STATE,YELLOW")
        time.sleep(0.15)
        status = link.status()
        assert status["device_online"] is True
        assert status["device_state"] == "YELLOW"
        assert status["connected"] is True
        assert status["port"] == "/dev/fake"
        assert status["last_echo"] is None
        link._transport.inject("RX,YELLOW,2,0,STOPPED_CAR,27,9,C27 S2 STOPPED")
        time.sleep(0.15)
        assert link.status()["last_echo"] == "YELLOW,2,0,STOPPED_CAR,27,9,C27 S2 STOPPED"
    finally:
        link.disconnect()


def test_status_values_are_plain_and_json_safe():
    link = make_link()
    try:
        link.update(result("GREEN", "NO_INCIDENT"))
        time.sleep(0.15)
        status = link.status()
        assert status["last_message"] == "GREEN"
        assert isinstance(status["seq"], int)
        import json
        json.dumps(status)  # must not raise
    finally:
        link.disconnect()


def test_connect_failure_raises_and_leaves_link_down():
    link = HardwareLink(transport_factory=FakeTransport)
    with pytest.raises(OSError):
        link.connect("BAD")
    assert not link.is_connected()


def test_list_serial_ports_smoke():
    ports = list_serial_ports()
    assert isinstance(ports, list)
