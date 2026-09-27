"""Dashboard -> ESP32 driver-display link (FlagSense hardware boundary).

This module is the ONE translation layer between the Python recommendation
engine and the ESP32 marshal display. It owns:

- flag/hazard vocabulary translation (pipeline -> wire protocol v2),
- short LCD-safe context strings (<= 16 chars, never a long AI explanation),
- the 3 s heartbeat cadence and reconnect handling.

The firmware holds no flag logic: it renders whatever valid state arrives and
enters LINK_LOST on its own 10 s watchdog when the heartbeats stop.

Wire contract (see FLAGSENSE_SERIAL_PROTOCOL.md):
    GREEN
    FLAG,SECTOR,DISTANCE,HAZARD,CAR_ID,SEQ,CONTEXT
e.g. ``YELLOW,2,0,STOPPED_CAR,27,142,C27 S2 STOPPED``

Zero means "unknown" for sector/distance/car. SEQ is a per-message counter
for ordering/audit; staleness is decided by the firmware timeout, not by SEQ,
so the counter may reset when the laptop restarts.
"""

from __future__ import annotations

import glob
import os
import threading
import time
from typing import Any, Callable, Optional

HEARTBEAT_S = 3.0
DEVICE_TIMEOUT_S = 12.0
BAUDRATE = 115200
MAX_CONTEXT_CHARS = 16

# Pipeline flag vocabulary (src/risk_engine.py FLAG_SEVERITY keys) -> wire
# tokens. RED_RECOMMENDED is the pipeline's red state; the wire calls it RED.
WIRE_FLAG = {
    "GREEN": "GREEN",
    "CLEAR": "GREEN",
    "YELLOW": "YELLOW",
    "DOUBLE_YELLOW": "DOUBLE_YELLOW",
    "VSC": "VSC",
    "SAFETY_CAR": "SAFETY_CAR",
    "SC": "SAFETY_CAR",
    "RED": "RED",
    "RED_RECOMMENDED": "RED",
}

# Pipeline rule_id (src/risk_engine.py) -> wire hazard token. Evidence-based:
# only rules whose evidence implies the hazard map to it; anything else is
# UNKNOWN_HAZARD rather than an invented detail.
RULE_HAZARD = {
    "DEBRIS_REPORTED_ON_TRACK": "DEBRIS",
    "ON_LINE_CLOSE_FAST_TRAFFIC": "STOPPED_CAR",
    "STOPPED_WITH_FAST_TRAFFIC": "STOPPED_CAR",
    "STOPPED_IN_HIGH_RISK_LOCATION": "STOPPED_CAR",
    "SUSTAINED_STOP_VSC": "STOPPED_CAR",
    "STOPPED_WITH_TRAFFIC": "STOPPED_CAR",
    "STOPPED_CAR_YELLOW": "STOPPED_CAR",
    "STOPPED_ON_LINE": "STOPPED_CAR",
    "MULTI_CAR_HIGH_RISK": "MULTI_CAR_INCIDENT",
    "MULTI_CAR_STREET_CIRCUIT": "MULTI_CAR_INCIDENT",
    "VISUAL_BLOCKAGE_WITH_STOP": "TRACK_BLOCKED",
    "RECOVERY_WET_POOR_VISIBILITY": "SESSION_STOPPED",
    "PROLONGED_STREET_CIRCUIT_STOP": "SESSION_STOPPED",
    "MODEL_RISK_HIGH_REVIEW": "UNKNOWN_HAZARD",
    "MODEL_RISK_YELLOW": "UNKNOWN_HAZARD",
}

# Wire hazard -> short LCD token. Car/sector numbers come first so a
# truncation to 16 chars never eats them.
HAZARD_SHORT = {
    "STOPPED_CAR": "STOPPED",
    "CRASH": "CRASH",
    "TRACK_BLOCKED": "BLOCKED",
    "DEBRIS": "DEBRIS",
    "SPIN": "SPIN",
    "SLOW_CAR": "SLOW CAR",
    "MULTI_CAR_INCIDENT": "MULTI-CAR",
    "OFF_TRACK": "OFF TRACK",
    "UNKNOWN_HAZARD": "CAUTION",
    "SESSION_STOPPED": "SESSION",
}

KNOWN_HAZARDS = set(HAZARD_SHORT.keys())


def resolve_hazard(rule_id: Optional[str]) -> str:
    if not rule_id:
        return "UNKNOWN_HAZARD"
    if rule_id in KNOWN_HAZARDS:
        return rule_id
    return RULE_HAZARD.get(rule_id, "UNKNOWN_HAZARD")


def _clean_context(text: str) -> str:
    """Make a string LCD/CSV-safe: no commas, capped at 16 chars."""
    return text.replace(",", " ").strip()[:MAX_CONTEXT_CHARS]


def build_context(flag: Optional[str], rule_id: Optional[str], incident: Optional[dict]) -> str:
    """Build the short LCD line-2 string from real evidence only.

    Never invents details: without an incident car it falls back to generic
    words ("Track clear", "DEBRIS REPORTED", "CAUTION").
    """
    if flag in ("GREEN", "CLEAR"):
        return "Track clear"
    incident = incident or {}
    car_id = incident.get("car_id") or 0
    sector = incident.get("sector") or 0
    hazard = resolve_hazard(rule_id)
    short = HAZARD_SHORT.get(hazard, "CAUTION")
    if car_id:
        text = f"C{car_id} S{sector} {short}" if sector else f"C{car_id} {short}"
        return _clean_context(text)
    if rule_id == "DEBRIS_REPORTED_ON_TRACK":
        return "DEBRIS REPORTED"
    return _clean_context(short)


def build_wire_message(
    flag: Optional[str],
    rule_id: Optional[str],
    incident: Optional[dict],
    seq: int,
) -> Optional[str]:
    """Serialize one recommendation to a protocol-v2 wire line.

    Returns None for a None/unknown flag — the caller keeps heartbeating the
    last valid recommendation instead of claiming a state it doesn't have.
    """
    wire = WIRE_FLAG.get(flag)  # type: ignore[arg-type]
    if wire is None:
        return None
    if wire == "GREEN":
        return "GREEN"
    incident = incident or {}
    car_id = int(incident.get("car_id") or 0)
    sector = int(incident.get("sector") or 0)
    # Distance-to-incident is not computed by the pipeline; 0 = unknown.
    hazard = resolve_hazard(rule_id)
    context = build_context(flag, rule_id, incident)
    return f"{wire},{sector},0,{hazard},{car_id},{seq},{context}"


def build_wire_message_v1(
    flag: Optional[str],
    rule_id: Optional[str],
    incident: Optional[dict],
) -> Optional[str]:
    """Serialize recommendation to legacy protocol-v1 wire line (CLEAR or 4 fields)."""
    wire = WIRE_FLAG.get(flag)  # type: ignore[arg-type]
    if wire is None:
        return None
    if wire == "GREEN":
        return "CLEAR"
    incident = incident or {}
    sector = max(1, int(incident.get("sector") or 1))
    hazard = resolve_hazard(rule_id)
    if hazard == "UNKNOWN_HAZARD":
        hazard = "STOPPED_CAR" if wire in ("YELLOW", "DOUBLE_YELLOW", "VSC", "SAFETY_CAR") else "SESSION_STOPPED"
    v1_wire = "RED" if wire == "RED" else "YELLOW"
    return f"{v1_wire},{sector},0,{hazard}"


def is_pyserial_available() -> bool:
    """Return True if pyserial is importable and functional."""
    try:
        import serial
        import serial.tools.list_ports
        return True
    except ImportError:
        return False


def list_serial_ports() -> list[str]:
    """Return candidate serial device names (for the port picker).

    Prioritizes real USB serial microcontrollers (ESP32, FTDI, CP210x, CH340, etc.)
    and excludes non-serial macOS internal debug/Bluetooth ports.
    Includes filesystem scanning fallback if pyserial is not available.
    """
    ports: list[tuple[int, str]] = []
    seen: set[str] = set()

    try:
        from serial.tools import list_ports
        for p in list_ports.comports():
            dev = p.device
            dev_lower = dev.lower()
            desc_lower = (p.description or "").lower()
            hwid_lower = (p.hwid or "").lower()

            # Ignore macOS internal debug and bluetooth ports
            if any(skip in dev_lower for skip in ["wlan-debug", "debug-console", "bluetooth"]):
                continue

            score = 0
            # Espressif USB vendor ID: 0x303A
            if getattr(p, "vid", None) == 0x303A:
                score += 100
            if "espressif" in desc_lower or "espressif" in hwid_lower:
                score += 80
            if "jtag/serial" in desc_lower or "usbmodem" in dev_lower:
                score += 50
            if any(sub in dev_lower for sub in ["usbserial", "wch", "slab"]):
                score += 40
            if getattr(p, "vid", None) is not None or "usb" in desc_lower or "usb" in hwid_lower:
                score += 20

            ports.append((score, dev))
            seen.add(dev)
    except ImportError:
        pass

    # Fallback / augment with glob patterns (e.g. on macOS / Linux)
    fallback_patterns = [
        "/dev/cu.usbmodem*",
        "/dev/cu.usbserial*",
        "/dev/cu.wchusbserial*",
        "/dev/cu.SLAB_USBtoUART*",
        "/dev/ttyUSB*",
        "/dev/ttyACM*",
    ]
    for pat in fallback_patterns:
        for match in glob.glob(pat):
            if match not in seen:
                score = 50 if ("usbmodem" in match or "usbserial" in match) else 10
                ports.append((score, match))
                seen.add(match)

    ports.sort(key=lambda x: -x[0])
    return [dev for score, dev in ports]


class SerialTransport:
    """Thin pyserial wrapper; pyserial is imported lazily so the module
    (and its tests) load without it until a real connection is opened."""

    def __init__(self) -> None:
        self._ser = None

    def open(self, port: str, baudrate: int = BAUDRATE) -> None:
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError(
                "pyserial is not installed (run 'pip install pyserial' in your python environment)"
            ) from exc

        # On macOS, convert /dev/tty.* to /dev/cu.* to prevent blocking on carrier detect (DCD)
        if port.startswith("/dev/tty."):
            cu_candidate = "/dev/cu." + port[len("/dev/tty."):]
            if os.path.exists(cu_candidate):
                port = cu_candidate

        self._ser = serial.Serial(port, baudrate, timeout=0.1)
        try:
            self._ser.dtr = True
            self._ser.rts = True
        except Exception:
            pass

    def write_line(self, line: str) -> None:
        assert self._ser is not None, "transport not open"
        self._ser.write((line + "\n").encode("ascii", errors="replace"))
        self._ser.flush()

    def read_available(self) -> list[str]:
        assert self._ser is not None, "transport not open"
        lines = []
        while True:
            raw = self._ser.readline()
            if not raw:
                break
            lines.append(raw.decode("ascii", errors="replace").strip())
        return lines

    def close(self) -> None:
        ser, self._ser = self._ser, None
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass


class HardwareLink:
    """Streams the dashboard's current recommendation to the ESP32.

    Owns its own sender cadence on a daemon thread: every HEARTBEAT_S the
    latest valid recommendation goes out even when unchanged, and a changed
    recommendation goes out immediately. A reader thread drains the device's
    STATUS lines for the online indicator. Reconnects are attempted
    automatically; the firmware's 10 s watchdog is the stale detector.
    """

    def __init__(
        self,
        transport_factory: Callable[[], Any] = SerialTransport,
        heartbeat_s: float = HEARTBEAT_S,
    ) -> None:
        self._transport_factory = transport_factory
        self._heartbeat_s = heartbeat_s
        self._lock = threading.Lock()
        self._transport: Optional[Any] = None
        self._port: Optional[str] = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._sender: Optional[threading.Thread] = None
        self._reader: Optional[threading.Thread] = None
        self._seq = 0
        self._proto_version = 2
        self._snapshot: Optional[dict] = None
        self._last_sent: Optional[str] = None
        self._last_sent_at = 0.0
        self._device_last_seen = 0.0
        self._device_state: Optional[str] = None
        self._last_echo: Optional[str] = None
        self._link_error: Optional[str] = None

    # ---- lifecycle ----
    def connect(self, port: str) -> None:
        self.disconnect()
        transport = self._transport_factory()
        transport.open(port, BAUDRATE)
        with self._lock:
            self._transport = transport
            self._port = port
            self._proto_version = 2
            self._link_error = None
        self._stop.clear()
        self._wake.clear()
        self._sender = threading.Thread(
            target=self._sender_loop, daemon=True, name="flagsense-hw-tx"
        )
        self._reader = threading.Thread(
            target=self._reader_loop, daemon=True, name="flagsense-hw-rx"
        )
        self._sender.start()
        self._reader.start()
        self._wake.set()  # send the current snapshot immediately, if any

    def disconnect(self) -> None:
        self._stop.set()
        self._wake.set()
        for thread in (self._sender, self._reader):
            if thread is not None and thread.is_alive():
                thread.join(timeout=1.0)
        self._sender = self._reader = None
        transport, self._transport = self._transport, None
        if transport is not None:
            try:
                transport.close()
            except Exception:
                pass
        with self._lock:
            self._port = None

    def is_connected(self) -> bool:
        return self._transport is not None

    # ---- data in ----
    def update(self, result: Any) -> bool:
        """Offer the latest AnalysisResult. Returns True if it became (or
        stayed) the live snapshot. A None/unknown flag keeps the previous
        valid recommendation — never claims GREEN on no data."""
        flag = getattr(result, "flag", None)
        if flag not in WIRE_FLAG:
            return self._snapshot is not None
        incident = getattr(result, "incident", None) or {}
        snapshot = {
            "flag": flag,
            "rule_id": getattr(result, "rule_id", None),
            "car_id": incident.get("car_id") or 0,
            "sector": incident.get("sector") or 0,
        }
        with self._lock:
            if snapshot == self._snapshot:
                return True  # unchanged; the heartbeat repeats it
            self._snapshot = snapshot
        self._wake.set()  # changed -> send immediately
        return True

    # ---- status out (thread-safe, plain values for Streamlit) ----
    def status(self) -> dict:
        now = time.monotonic()
        with self._lock:
            last_sent_at = self._last_sent_at
            device_last_seen = self._device_last_seen
            return {
                "port": self._port,
                "connected": self._transport is not None,
                "seq": self._seq,
                "proto_version": self._proto_version,
                "last_message": self._last_sent,
                "last_sent_age_s": (now - last_sent_at) if self._last_sent else None,
                "device_online": (now - device_last_seen) < DEVICE_TIMEOUT_S,
                "device_last_seen_age_s": (now - device_last_seen)
                if device_last_seen
                else None,
                "device_state": self._device_state,
                "last_echo": self._last_echo,
                "link_error": self._link_error,
            }

    # ---- internals ----
    def _note_error(self, message: str) -> None:
        with self._lock:
            self._link_error = message

    def _next_message(self) -> Optional[str]:
        with self._lock:
            snapshot = self._snapshot
            if snapshot is None:
                return None
            self._seq += 1
            seq = self._seq
            proto = self._proto_version
        if proto == 1:
            return build_wire_message_v1(
                snapshot["flag"],
                snapshot["rule_id"],
                {"car_id": snapshot["car_id"], "sector": snapshot["sector"]},
            )
        return build_wire_message(
            snapshot["flag"],
            snapshot["rule_id"],
            {"car_id": snapshot["car_id"], "sector": snapshot["sector"]},
            seq,
        )

    def _send_once(self, message: str) -> bool:
        transport = self._transport
        if transport is None:
            return False
        try:
            transport.write_line(message)
        except Exception:
            # One reopen attempt; failure just means we retry next cycle and
            # the firmware shows LINK_LOST after its 10 s watchdog.
            try:
                transport.close()
                transport.open(self._port, BAUDRATE)
                transport.write_line(message)
            except Exception as exc:
                self._note_error(f"{type(exc).__name__}: {exc}")
                return False
        with self._lock:
            self._last_sent = message
            self._last_sent_at = time.monotonic()
            self._link_error = None
        return True

    def _sender_loop(self) -> None:
        while not self._stop.is_set():
            message = self._next_message()
            if message is not None and not self._send_once(message):
                self._wake.wait(2.0)  # link down: back off instead of spinning
                self._wake.clear()
                continue
            self._wake.wait(self._heartbeat_s)
            self._wake.clear()

    def _handle_device_line(self, line: str) -> None:
        now = time.monotonic()
        with self._lock:
            if line == "STATUS,READY":
                self._device_last_seen = now
            elif line.startswith("STATUS,STATE,"):
                self._device_state = line.split(",", 2)[2]
                self._device_last_seen = now
            elif line == "STATUS,LINK_LOST":
                self._device_state = "LINK_LOST"
                self._device_last_seen = now
            elif line.startswith("STATUS,RECOVERED,"):
                self._device_state = line.split(",", 2)[2]
                self._device_last_seen = now
            elif line.startswith("RX,"):
                self._last_echo = line[3:]
                self._device_last_seen = now
            elif line.startswith("STATUS,REJECTED,"):
                self._device_last_seen = now
                parts = line.split(",", 2)
                reason = parts[2] if len(parts) >= 3 else "UNKNOWN"
                if reason in ("WRONG_FIELD_COUNT", "UNKNOWN_COMMAND") and self._proto_version != 1:
                    # Device runs v1 firmware; adapt immediately to v1 shape
                    self._proto_version = 1
                    self._wake.set()

    def _reader_loop(self) -> None:
        while not self._stop.is_set():
            try:
                transport = self._transport
                if transport is not None:
                    for line in transport.read_available():
                        if line:
                            self._handle_device_line(line)
            except Exception:
                pass
            time.sleep(0.05)
