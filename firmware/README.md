# FlagSense ESP32 firmware

## Hardware

The renderer targets an ESP32-S3-DevKitC-1 N16R8 board and uses a bare
16-pin HD44780-compatible LCD1602A in 4-bit mode, plus a 24-pixel
WS2812/NeoPixel ring:

| Signal | ESP32-S3 GPIO |
|---|---:|
| LCD RS | 13 |
| LCD Enable | 12 |
| LCD D4, D5, D6, D7 | 4, 5, 6, 7 |
| NeoPixel data | 18 |
| Onboard RGB NeoPixel | 48 by default (38 on DevKitC-1 v1.1) |

Tie the LCD RW pin to GND. Connect LCD power, ground, and contrast according
to the module markings. The ring count, data pin, brightness, and LCD pins are
configurable in `include/HardwareConfig.h`. The ring shows solid green for
CLEAR, amber for YELLOW, and red for RED; STARTING and ERROR turn it off. The
onboard RGB NeoPixel mirrors the flag colors; it shows blue before the first
valid flag and magenta on a device error. Brightness defaults to a low level.
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
Only valid `CLEAR`, `YELLOW`, and `RED` messages reach the state machine. The
renderer reads the current state and incident and updates the ring and LCD.
The parser has no hardware dependencies.

## Supported messages

The MVP implements `CLEAR`, `YELLOW,<SECTOR>,<DISTANCE>,<HAZARD>`,
`RED,<SECTOR>,<DISTANCE>,<HAZARD>`, and the protocol's `DEVICE_TEST`,
`LED_TEST`, and `DISPLAY_TEST` commands. Hazard names match the fixed list in
the [serial protocol](../FLAGSENSE_SERIAL_PROTOCOL.md). Commands with car IDs
and `CAUTION` are documented optional extensions and are not enabled in this
MVP. The device emits `STATUS,READY` at startup and once per second. Completed
input lines are echoed as `RX,<line>`; accepted test commands report
`STATUS,TEST,<name>`, state changes report `STATUS,STATE,<state>`, and rejected
lines report `STATUS,REJECTED,<reason>`.

The display states are `STARTING`, `CLEAR`, `YELLOW`, `RED`, `LINK_LOST`, and
`ERROR`. Test commands temporarily exercise outputs and leave the safety state
unchanged; a later valid flag message cancels the test. Invalid lines are
reported to serial and never change the state or outputs. Automatic link-loss
detection is disabled: the most recent valid flag remains displayed until a
new valid flag arrives or the device is reset.

The protocol does not specify a sector range. By default the parser accepts
positive 32-bit sector numbers; set `SectorRange` at the call site if the
chosen circuit has known limits. The parallel LCD has no presence-detection
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
CLEAR
YELLOW,4,120,STOPPED_CAR
RED,4,0,SESSION_STOPPED
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
