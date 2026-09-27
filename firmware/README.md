# FlagSense ESP32 firmware

## Hardware

The renderer targets an ESP32-S3-DevKitC-1 N16R8 board and uses a bare
16-pin HD44780-compatible LCD1602A in 4-bit mode, plus a 24-pixel
WS2812/NeoPixel ring:

| Signal | ESP32 GPIO |
|---|---:|
| LCD RS | 4 |
| LCD Enable | 5 |
| LCD D4, D5, D6, D7 | 6, 7, 8, 9 |
| NeoPixel data | 18 |
| Onboard RGB NeoPixel | 48 by default (38 on DevKitC-1 v1.1) |

Tie the LCD RW pin to GND. Connect LCD power, ground, and contrast according
to the module markings. The ring count, data pin, brightness, and LCD pins are
configurable in `include/HardwareConfig.h`. The ring shows a non-blocking
LED pattern per flag state — solid green for GREEN, solid amber for YELLOW, a
slow amber brightness pulse for DOUBLE YELLOW, a 500 ms amber flash for
SAFETY CAR, an amber double-blink strobe for VSC, and a 400 ms red flash for
RED. All animation is driven by `tickLeds()` (no `delay()` anywhere), and a
new recommendation interrupts the previous pattern immediately. STARTING and
ERROR turn the ring off. LINK_LOST freezes the ring on its last frame and sets
the onboard RGB NeoPixel to magenta; the onboard pixel otherwise stays off.
Brightness defaults to a low level.
Check the board revision printed on the PCB: DevKitC-1 v1.0 uses
GPIO48 for its onboard pixel and v1.1 uses GPIO38. Change
`ONBOARD_NEOPIXEL_DATA_PIN` in `include/HardwareConfig.h` if your board uses
GPIO38.

Power the NeoPixel ring from a suitable 5V supply, with its ground tied to ESP32
ground. For reliable 3.3V ESP32-to-5V pixel signaling, use a 74AHCT125 or
74HCT245 level shifter on the data line. The NeoPixel library and parallel LCD
library are declared in `platformio.ini`; the LCD library targets HD44780
compatible character displays, and Adafruit's NeoPixel library supports ESP32
pixels. [Arduino LiquidCrystal](https://github.com/arduino-libraries/LiquidCrystal),
[Adafruit NeoPixel](https://github.com/adafruit/Adafruit_NeoPixel).

If the LCD1602A has an I2C backpack attached, these parallel LCD connections do
not apply; the LCD driver and pin configuration need to be changed for I2C.

## Message flow

USB serial bytes enter a fixed 128-character line framer. Newline completes a
message; CRLF is accepted and blank lines are ignored. An overlong line is
discarded through its newline and reported as `MESSAGE_TOO_LONG`. The pure
parser tokenizes and validates the line, then returns a typed `ParseResult`.
Only valid flag messages reach the state machine; test commands exercise
outputs without changing the safety state. The
renderer reads the current state and incident and updates the ring and LCD.
The parser has no hardware dependencies.

## Supported messages

The firmware implements protocol v2 (see the
[serial protocol](../FLAGSENSE_SERIAL_PROTOCOL.md), section 25): `GREEN`,
`YELLOW`, `DOUBLE_YELLOW`, `SAFETY_CAR`, `VSC`, and `RED` in the classic
`FLAG,SECTOR,DISTANCE,HAZARD` shape, the legacy `CLEAR` alias (treated exactly
like `GREEN`), and the extended 7-field shape
`FLAG,SECTOR,DISTANCE,HAZARD,CAR_ID,SEQ,CONTEXT`. It also handles the
protocol's `DEVICE_TEST`, `LED_TEST`, and `DISPLAY_TEST` commands. Hazard
names match the fixed list in the serial protocol; sector, distance, and car
ID use 0 for "unknown".

The device emits `STATUS,READY` once per second. Completed input lines are
echoed as `RX,<line>`; state changes report `STATUS,STATE,<state>`; rejected
lines report `STATUS,REJECTED,<reason>`; link loss and recovery report
`STATUS,LINK_LOST` and `STATUS,RECOVERED,<state>`.

The display states are `STARTING`, `GREEN`, `YELLOW`, `DOUBLE_YELLOW`,
`SAFETY_CAR`, `VSC`, `RED`, `LINK_LOST`, and `ERROR`. Test commands temporarily
exercise outputs and leave the safety state unchanged; a later valid flag
message cancels the test. Invalid lines are reported to serial and never
change the state or outputs.

The LCD shows the flag label on line 1 and the sender's short context on line
2 (`C27 S2 STOPPED`, `DEBRIS REPORTED`); when the sender provides no context,
line 2 is derived from the real evidence (sector / distance / hazard), and
GREEN always reads "Track clear" so no stale context survives a return to
green.

Link supervision is enabled: every valid message restarts a 10 s watchdog
(`LINK_LOSS_TIMEOUT_MS` in `include/HardwareConfig.h`). If it expires, the
device enters `LINK_LOST` — the ring freezes on its last frame, the LCD shows
`LINK LOST` with the last confirmed flag, and the onboard pixel turns magenta.
The next valid message recovers automatically with `STATUS,RECOVERED,<state>`;
no reboot is needed.

The protocol does not specify a sector range. By default the parser accepts
sector 0 ("unknown") through the full 32-bit range; set `SectorRange` at the
call site if the chosen circuit has known limits. The parallel LCD has no presence-detection
line, so its connection cannot be reported automatically. NeoPixels likewise
provide no feedback path for detecting a failed pixel.

## Build and manual check

Install PlatformIO, connect the LCD and ring using the wiring table above, and
adjust `include/HardwareConfig.h` if needed. The build enables the ESP32-S3
Hardware CDC/JTAG serial interface on boot, so use the board's native USB port
for serial monitoring. From `firmware/`, run
`pio run -t upload`, then `pio device monitor -b 115200`. Send each line below
with a newline:

```text
GREEN
YELLOW,2,120,STOPPED_CAR,27,1,C27 S2 STOPPED
VSC,2,0,DEBRIS,0,2,DEBRIS REPORTED
SAFETY_CAR,3,0,DEBRIS,0,3,
RED,3,0,SESSION_STOPPED,81,4,C81 S3 SESSION
CLEAR
DEVICE_TEST
LED_TEST
DISPLAY_TEST
```

`STATUS,READY` is printed on boot and every second. Received lines and their
parse result are printed to the serial monitor.

The hardware-independent parser/framer/state test can be run from the
repository root with:

```sh
c++ -std=c++11 -Wall -Wextra -Werror -Ifirmware/include \
  firmware/src/SerialProtocol.cpp firmware/src/StateMachine.cpp \
  firmware/test/native/test_parser.cpp -o /tmp/flagsense_parser_test
/tmp/flagsense_parser_test
```
