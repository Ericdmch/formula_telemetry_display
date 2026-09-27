# FlagSense Serial Message Protocol

## Purpose

This document defines the serial communication protocol between the **FlagSense race-control laptop** and the **ESP32 driver display**.

The goal is to make communication predictable, simple to debug, and easy for both the laptop software and ESP32 firmware to implement.

The driver does **not** need to provide any response. The system is primarily one-way:

**Laptop → ESP32**

Optionally, the ESP32 may send automatic device-status messages back to the laptop so race control can confirm that the hardware is still connected.

---

# 1. Communication Overview

## Laptop responsibilities

The laptop:

- reads race telemetry
- detects incidents
- calculates risk
- generates a recommended safety response
- allows race control to confirm the final state
- sends the confirmed state to the ESP32

## ESP32 responsibilities

The ESP32:

- receives the latest race-control message
- turns on the correct LED
- updates the OLED screen
- optionally reports device health automatically

The ESP32 does **not**:

- calculate risk
- decide which flag should be used
- run the ML model
- require driver acknowledgement

---

# 2. Transport

For the MVP, use:

```text
USB Serial
```

Recommended baud rate:

```text
115200
```

Both sides must use the same baud rate.

ESP32 example:

```cpp
Serial.begin(115200);
```

Python example:

```python
import serial

esp32 = serial.Serial(
    port="/dev/ttyUSB0",
    baudrate=115200,
    timeout=1
)
```

The exact port name depends on the computer.

Examples:

```text
Windows:
COM3
COM4

Linux:
/dev/ttyUSB0
/dev/ttyACM0

macOS:
/dev/cu.usbserial-...
/dev/cu.SLAB_USBtoUART
```

---

# 3. General Message Rules

All messages are plain text.

Each message:

- is one line
- uses commas as separators
- ends with a newline character
- uses uppercase keywords
- uses underscores instead of spaces

Example:

```text
YELLOW,4,120,STOPPED_CAR
```

Internally, the transmitted message is:

```text
YELLOW,4,120,STOPPED_CAR\n
```

The ESP32 should read until `\n`.

---

# 4. Standard Fields

Depending on the message type, a message may contain:

| Field | Description | Example |
|---|---|---|
| `FLAG` | Current confirmed race-control state | `YELLOW` |
| `SECTOR` | Track sector containing the incident | `4` |
| `DISTANCE` | Distance to hazard in metres | `120` |
| `HAZARD` | Type of hazard | `STOPPED_CAR` |
| `CAR_ID` | Vehicle involved in the incident | `12` |
| `MESSAGE` | Simple driver-facing instruction | `CAUTION` |
| `DEVICE_STATE` | ESP32 connection state | `ONLINE` |
| `TIMESTAMP` | Optional time value | `12:31:22` |

The MVP does not need every field in every message.

---

# 5. Required Laptop → ESP32 Messages

These are the messages required for the MVP.

---

## 5.1 CLEAR

### Format

```text
CLEAR
```

### Meaning

The track is clear and there is no active safety alert for the driver.

### ESP32 behavior

- green LED ON
- yellow LED OFF
- red LED OFF
- OLED shows clear status

### OLED example

```text
CLEAR

NO ACTIVE
HAZARDS
```

---

## 5.2 YELLOW

### Format

```text
YELLOW,<SECTOR>,<DISTANCE>,<HAZARD>
```

### Example

```text
YELLOW,4,120,STOPPED_CAR
```

### Meaning

A yellow-flag condition is active.

The message above means:

```text
Flag: YELLOW
Sector: 4
Distance to hazard: 120 m
Hazard: STOPPED CAR
```

### ESP32 behavior

- green LED OFF
- yellow LED ON
- red LED OFF
- OLED shows hazard information

### OLED example

```text
YELLOW

SECTOR 4
HAZARD 120m
STOPPED CAR
```

---

## 5.3 RED

### Format

```text
RED,<SECTOR>,<DISTANCE>,<HAZARD>
```

### Example

```text
RED,4,0,SESSION_STOPPED
```

### Meaning

A red-flag condition is active.

The example means:

```text
Flag: RED
Incident sector: 4
Distance: not relevant
Reason: SESSION STOPPED
```

Use `0` when distance is not relevant.

### ESP32 behavior

- green LED OFF
- yellow LED OFF
- red LED ON
- OLED shows red-flag information

### OLED example

```text
RED FLAG

SESSION
STOPPED

INCIDENT S4
```

---

# 6. Optional Extended Laptop → ESP32 Messages

These are useful if there is time after the MVP works.

---

## 6.1 YELLOW with car ID

### Format

```text
YELLOW,<SECTOR>,<DISTANCE>,<HAZARD>,<CAR_ID>
```

### Example

```text
YELLOW,4,120,STOPPED_CAR,12
```

### Meaning

Car 12 is involved in the hazard.

### Possible OLED

```text
YELLOW

SECTOR 4
120m AHEAD

CAR 12
STOPPED
```

---

## 6.2 RED with car ID

### Format

```text
RED,<SECTOR>,<DISTANCE>,<HAZARD>,<CAR_ID>
```

### Example

```text
RED,4,0,TRACK_BLOCKED,12
```

### Meaning

A severe incident involving Car 12 is blocking the track.

---

## 6.3 CAUTION message

### Format

```text
CAUTION,<SECTOR>,<DISTANCE>,<HAZARD>
```

### Example

```text
CAUTION,2,250,DEBRIS
```

### Meaning

Race control wants to warn the driver about a developing situation without changing the main flag state.

### ESP32 behavior

Suggested behavior:

- preserve current LED state
- show caution information on OLED
- optionally briefly flash yellow

This is optional and should not be implemented before the basic CLEAR/YELLOW/RED messages work.

---

## 6.4 DEVICE_TEST

### Format

```text
DEVICE_TEST
```

### Meaning

Race control is testing the physical driver display.

### ESP32 behavior

A simple test sequence:

```text
Green ON
Yellow ON
Red ON
OLED test text
All OFF
Return to previous state
```

Useful during setup and judging.

---

## 6.5 DISPLAY_TEST

### Format

```text
DISPLAY_TEST
```

### Meaning

Test only the OLED display.

### OLED example

```text
FLAGSENSE

DISPLAY
ONLINE
```

---

## 6.6 LED_TEST

### Format

```text
LED_TEST
```

### Meaning

Test only the LEDs.

Suggested sequence:

```text
GREEN
YELLOW
RED
```

for roughly one second each.

---

# 7. Hazard Types

Use a fixed set of hazard names so the laptop and ESP32 always interpret them the same way.

Recommended MVP hazard types:

```text
STOPPED_CAR
CRASH
TRACK_BLOCKED
DEBRIS
SPIN
SLOW_CAR
MULTI_CAR_INCIDENT
OFF_TRACK
UNKNOWN_HAZARD
SESSION_STOPPED
```

---

## 7.1 STOPPED_CAR

A vehicle has stopped or nearly stopped.

Example:

```text
YELLOW,4,120,STOPPED_CAR
```

---

## 7.2 CRASH

A collision or strong crash event has been detected.

Example:

```text
RED,3,0,CRASH
```

---

## 7.3 TRACK_BLOCKED

The racing surface is substantially blocked.

Example:

```text
RED,2,0,TRACK_BLOCKED
```

---

## 7.4 DEBRIS

Debris or an object is present on or near the racing line.

Example:

```text
YELLOW,1,180,DEBRIS
```

---

## 7.5 SPIN

A vehicle has spun or lost normal orientation.

Example:

```text
YELLOW,3,90,SPIN
```

---

## 7.6 SLOW_CAR

A vehicle is moving significantly slower than surrounding traffic.

Example:

```text
YELLOW,2,150,SLOW_CAR
```

---

## 7.7 MULTI_CAR_INCIDENT

More than one car is involved.

Example:

```text
RED,4,0,MULTI_CAR_INCIDENT
```

---

## 7.8 OFF_TRACK

A vehicle has left the racing surface.

Example:

```text
YELLOW,1,100,OFF_TRACK
```

---

## 7.9 UNKNOWN_HAZARD

An incident has been detected but the system does not have a confident hazard classification.

Example:

```text
YELLOW,3,140,UNKNOWN_HAZARD
```

---

## 7.10 SESSION_STOPPED

The session has been stopped by race control.

Example:

```text
RED,4,0,SESSION_STOPPED
```

---

# 8. Sector Values

Use integers for sectors.

Example:

```text
1
2
3
4
```

If the track uses three sectors:

```text
1
2
3
```

If you later divide the track into more detailed marshal zones, the same field can still be used.

Example:

```text
YELLOW,7,80,STOPPED_CAR
```

would mean Zone/Sector 7.

For the MVP, pick one naming system and use it consistently.

---

# 9. Distance Values

Distance is always expressed in:

```text
metres
```

Examples:

```text
30
75
120
250
```

Do not include `m` inside the serial message.

Correct:

```text
YELLOW,4,120,STOPPED_CAR
```

Avoid:

```text
YELLOW,4,120m,STOPPED_CAR
```

The OLED can add the unit when displaying it.

Example:

```text
HAZARD 120m
```

---

# 10. Message Parsing Example

Laptop sends:

```text
YELLOW,4,120,STOPPED_CAR
```

The ESP32 receives the whole line.

It splits the message by commas:

```text
Field 0 = YELLOW
Field 1 = 4
Field 2 = 120
Field 3 = STOPPED_CAR
```

The firmware converts that into variables:

```text
flag = YELLOW
sector = 4
distance = 120
hazard = STOPPED_CAR
```

Then it updates:

```text
LED = YELLOW
OLED = hazard information
```

---

# 11. Recommended ESP32 State Model

The ESP32 only needs these core display states:

```text
CLEAR
YELLOW
RED
```

Optional device states:

```text
STARTING
LINK_LOST
DEVICE_ERROR
```

The ESP32 should not need complex race logic.

---

# 12. State Transitions

Typical state flow:

```text
CLEAR
  ↓
YELLOW
  ↓
RED
  ↓
CLEAR
```

Other valid transitions include:

```text
CLEAR → RED
YELLOW → CLEAR
RED → YELLOW
RED → CLEAR
```

The newest valid message should replace the previous display state.

---

# 13. Example Full Race Sequence

## Normal racing

Laptop sends:

```text
CLEAR
```

Hardware:

```text
Green LED ON
```

OLED:

```text
CLEAR
NO ACTIVE HAZARDS
```

---

## Incident begins

Car 12 stops in Sector 4.

Laptop sends:

```text
YELLOW,4,150,STOPPED_CAR
```

Hardware:

```text
Yellow LED ON
```

OLED:

```text
YELLOW
SECTOR 4
HAZARD 150m
STOPPED CAR
```

---

## Driver gets closer

Laptop sends:

```text
YELLOW,4,80,STOPPED_CAR
```

OLED becomes:

```text
YELLOW
SECTOR 4
HAZARD 80m
STOPPED CAR
```

---

## Incident becomes severe

Laptop sends:

```text
RED,4,0,TRACK_BLOCKED
```

Hardware:

```text
Red LED ON
```

OLED:

```text
RED FLAG
TRACK BLOCKED
SECTOR 4
```

---

## Incident clears

Laptop sends:

```text
CLEAR
```

Hardware returns to:

```text
Green LED ON
```

---

# 14. Optional ESP32 → Laptop Messages

The driver does not need to respond.

However, the ESP32 may automatically send device-health messages.

These are optional.

---

## 14.1 STATUS ONLINE

### Format

```text
STATUS,ONLINE
```

### Meaning

The ESP32 is operating normally.

This may be sent:

- when the ESP32 boots
- periodically as a heartbeat

Example:

```text
STATUS,ONLINE
```

---

## 14.2 HEARTBEAT

### Format

```text
HEARTBEAT
```

### Meaning

The ESP32 is still connected and running.

Recommended interval:

```text
every 2–5 seconds
```

The laptop can use this to display:

```text
Driver Display: ONLINE
```

---

## 14.3 STATUS ERROR

### Format

```text
STATUS,ERROR,<ERROR_TYPE>
```

### Example

```text
STATUS,ERROR,OLED_FAILURE
```

Possible error values:

```text
OLED_FAILURE
SERIAL_ERROR
DEVICE_ERROR
```

This is optional and can be skipped for the MVP.

---

## 14.4 STATUS READY

### Format

```text
STATUS,READY
```

### Meaning

The ESP32 has completed startup and is ready to receive messages.

Useful after boot.

---

# 15. Link-Loss Behavior

The ESP32 cannot always know whether the laptop has physically disconnected unless you implement a timeout.

A simple approach is:

1. laptop sends a message or heartbeat regularly
2. ESP32 stores the time of the last received message
3. if no message arrives for a chosen timeout, enter `LINK_LOST`

Suggested timeout:

```text
5 seconds
```

Possible OLED:

```text
LINK LOST

WAITING FOR
RACE CONTROL
```

Recommended LED behavior for the demo:

```text
all LEDs OFF
```

or preserve the last confirmed flag state while clearly showing `LINK LOST`.

Choose one behavior and keep it consistent.

For a safety-oriented prototype, preserving the last confirmed flag while showing `LINK LOST` is easier to explain.

---

# 16. Unknown or Invalid Messages

The ESP32 should ignore messages it does not understand rather than crashing.

Example invalid message:

```text
BANANA,4,100,STOPPED_CAR
```

Recommended behavior:

- keep current display state
- optionally print debug information over Serial

Example debug output:

```text
ERROR,UNKNOWN_COMMAND
```

Do not change the LEDs because of an invalid message.

---

# 17. Missing Fields

Example invalid message:

```text
YELLOW,4
```

The ESP32 should detect that expected fields are missing.

Recommended behavior:

```text
ignore message
keep current state
```

Optional debug response:

```text
ERROR,MISSING_FIELDS
```

---

# 18. Invalid Values

Example:

```text
YELLOW,ABC,120,STOPPED_CAR
```

`ABC` is not a valid sector number.

Or:

```text
YELLOW,4,-50,STOPPED_CAR
```

Negative distance is invalid.

The ESP32 should:

- reject the malformed message
- keep the current state

---

# 19. Recommended Command Table

| Command | Direction | Required? | Example |
|---|---|---:|---|
| `CLEAR` | Laptop → ESP32 | Yes | `CLEAR` |
| `YELLOW` | Laptop → ESP32 | Yes | `YELLOW,4,120,STOPPED_CAR` |
| `RED` | Laptop → ESP32 | Yes | `RED,4,0,SESSION_STOPPED` |
| `DEVICE_TEST` | Laptop → ESP32 | Optional | `DEVICE_TEST` |
| `DISPLAY_TEST` | Laptop → ESP32 | Optional | `DISPLAY_TEST` |
| `LED_TEST` | Laptop → ESP32 | Optional | `LED_TEST` |
| `CAUTION` | Laptop → ESP32 | Optional | `CAUTION,2,250,DEBRIS` |
| `STATUS,READY` | ESP32 → Laptop | Optional | `STATUS,READY` |
| `STATUS,ONLINE` | ESP32 → Laptop | Optional | `STATUS,ONLINE` |
| `HEARTBEAT` | ESP32 → Laptop | Optional | `HEARTBEAT` |
| `STATUS,ERROR,...` | ESP32 → Laptop | Optional | `STATUS,ERROR,OLED_FAILURE` |

---

# 20. MVP Protocol

If time is limited, implement only these three laptop commands:

```text
CLEAR
YELLOW,<SECTOR>,<DISTANCE>,<HAZARD>
RED,<SECTOR>,<DISTANCE>,<HAZARD>
```

Example test sequence:

```text
CLEAR
YELLOW,4,120,STOPPED_CAR
RED,4,0,SESSION_STOPPED
CLEAR
```

If all four messages produce the correct LED and OLED output, the hardware communication MVP is working.

---

# 21. Recommended Laptop Data Structure

Internally, the laptop can represent a message like this:

```python
message = {
    "flag": "YELLOW",
    "sector": 4,
    "distance": 120,
    "hazard": "STOPPED_CAR"
}
```

Then convert it to:

```python
serial_message = (
    f"{message['flag']},"
    f"{message['sector']},"
    f"{message['distance']},"
    f"{message['hazard']}\n"
)
```

Result:

```text
YELLOW,4,120,STOPPED_CAR
```

---

# 22. Recommended ESP32 Parsing Logic

Conceptually:

```cpp
if (message == "CLEAR") {
    setClearState();
}
else if (message.startsWith("YELLOW,")) {
    parseYellowMessage(message);
}
else if (message.startsWith("RED,")) {
    parseRedMessage(message);
}
else if (message == "DEVICE_TEST") {
    runDeviceTest();
}
```

The exact implementation can change, but the message format should stay consistent.

---

# 23. Design Principle

The protocol should remain intentionally simple.

The laptop is responsible for intelligence.

The ESP32 is responsible for presentation.

That means:

```text
Laptop:
"What should the driver see?"

ESP32:
"Show exactly what race control sent."
```

Do not put ML logic, safety classification, or complex race-state decisions into the ESP32 for the MVP.

---

# 24. Final MVP Message Set

Use this as the official minimal contract:

```text
CLEAR
YELLOW,<SECTOR>,<DISTANCE>,<HAZARD>
RED,<SECTOR>,<DISTANCE>,<HAZARD>
```

Recommended supported hazards:

```text
STOPPED_CAR
CRASH
TRACK_BLOCKED
DEBRIS
SPIN
SLOW_CAR
MULTI_CAR_INCIDENT
OFF_TRACK
UNKNOWN_HAZARD
SESSION_STOPPED
```

Optional automatic device messages:

```text
STATUS,READY
STATUS,ONLINE
HEARTBEAT
STATUS,ERROR,<ERROR_TYPE>
```

This is enough to support the full FlagSense hardware MVP.

---

# 25. Protocol v2 (implemented)

Protocol v2 is the contract the FlagSense dashboard (`src/hardware_link.py`)
and the ESP32 firmware implement. It extends v1 — every v1 message parses
byte-identically under v2, so v1 senders keep working.

## 25.1 New flag keywords

```text
GREEN
DOUBLE_YELLOW
SAFETY_CAR
VSC
```

`CLEAR` is kept as a legacy alias and is treated exactly like `GREEN`. The
firmware has no separate CLEAR display state: green is the normal state.

## 25.2 Extended message shape

```text
FLAG,SECTOR,DISTANCE,HAZARD,CAR_ID,SEQ,CONTEXT
```

Example:

```text
YELLOW,2,0,STOPPED_CAR,27,142,C27 S2 STOPPED
```

Field rules:

- `SECTOR`, `DISTANCE`, `CAR_ID`: `0` means "unknown". The parser accepts
  sector 0 by default so a sender can be honest when it has no sector data.
  (The pipeline does not currently compute distance; it sends `0`.)
- `SEQ`: a per-message counter from the sender, used for ordering and audit.
  It may reset when the laptop restarts. It is NOT a staleness signal —
  staleness is decided by the firmware link watchdog (§25.4).
- `CONTEXT`: a short line for LCD line 2, at most 16 characters, no commas.
  It may be empty — then the firmware derives line 2 from the real evidence
  (sector / distance / hazard), and green always reads `Track clear` so no
  stale context survives a return to green. The dashboard builds it from real
  evidence only (`C27 S2 STOPPED`, `DEBRIS REPORTED`); long AI explanations
  are never sent to the LCD.

The 1-field and 4-field shapes from v1 remain valid. Test commands
(`DEVICE_TEST`, `DISPLAY_TEST`, `LED_TEST`) remain 1-field only.

## 25.3 Heartbeat

The laptop sends the current recommendation every ~3 s even when it has not
changed, and immediately when it changes. A `None`/unknown recommendation is
never sent as `GREEN`: the laptop keeps heartbeating the last valid
recommendation, and sends nothing until it has one.

## 25.4 Link-loss behavior (implemented)

The firmware restarts a 10 s watchdog (`LINK_LOSS_TIMEOUT_MS`) on every valid
message. The 3 s heartbeat means normal replay progression never trips it —
only a genuine comms failure does. On timeout the device enters `LINK_LOST`:
the ring freezes on its last frame, the LCD shows `LINK LOST` with the last
confirmed flag, and the onboard pixel turns magenta. The next valid message
recovers automatically (`STATUS,RECOVERED,<state>`); no reboot is needed.

## 25.5 ESP32 → laptop status lines

```text
STATUS,READY            (every 1 s)
RX,<line>               (every completed input line)
STATUS,REJECTED,<reason>
STATUS,STATE,<state>    (on state change)
STATUS,LINK_LOST
STATUS,RECOVERED,<state>
```

The dashboard drains these on a reader thread and shows device-online status
(device seen within the last 12 s), the last echoed line, and link errors in
the "Driver display (ESP32)" panel.

## 25.6 LCD layout (16x2)

Line 1: flag label — `GREEN FLAG`, `YELLOW FLAG`, `DOUBLE YELLOW`,
`SAFETY CAR`, `VSC`, `RED FLAG`.

Line 2: the sender's `CONTEXT` when present; otherwise derived from evidence
(`S2 STOPPED CAR`, `120m DEBRIS`, `DEBRIS`); `Track clear` for green.

## 25.7 LED patterns

All animation is non-blocking (`tickLeds()`, no `delay()`); a new message
interrupts the previous pattern immediately.

```text
GREEN:         solid green
YELLOW:        solid amber
DOUBLE_YELLOW: slow amber brightness pulse
SAFETY_CAR:    amber flash, 500 ms on/off
VSC:           amber double-blink strobe
RED:           red flash, 400 ms on/off
```

## 25.8 Translation layer

`src/hardware_link.py` is the ONE explicit translation layer between the
pipeline vocabulary and the wire. It owns the flag map (`WIRE_FLAG`:
`RED_RECOMMENDED` → `RED`, rest identity), the rule-to-hazard map
(`RULE_HAZARD`, evidence-based; unknown rules → `UNKNOWN_HAZARD` rather than
an invented hazard), and the ≤16-char context builder (`build_context`). No
flag logic lives in the firmware — it renders whatever valid state arrives.
