# FlagSense ESP32 firmware

## Hardware

The renderer uses a bare 16-pin HD44780-compatible LCD1602A in 4-bit mode,
plus a 24-pixel WS2812/NeoPixel ring. It assumes an ESP32 DevKit pinout:

| Signal | ESP32 GPIO |
|---|---:|
| LCD RS | 23 |
| LCD Enable | 22 |
| LCD D4, D5, D6, D7 | 21, 19, 25, 26 |
| NeoPixel data | 18 |

Tie the LCD RW pin to GND. Connect LCD power, ground, and contrast according
to the module markings. The ring count, data pin, brightness, and LCD pins are
configurable in `include/HardwareConfig.h`. The ring shows solid green for
CLEAR, amber for YELLOW, and red for RED; STARTING and ERROR turn it off.
Brightness defaults to a low level.

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
MVP. The device emits the protocol-defined `STATUS,READY` message at startup.

The display states are `STARTING`, `CLEAR`, `YELLOW`, `RED`, `LINK_LOST`, and
`ERROR`. Test commands temporarily exercise outputs and leave the safety state
unchanged; a later valid flag message cancels the test. Invalid lines only
produce prefixed debug output and never change the state or outputs. Link loss
uses the protocol's suggested five-second interval, preserves the last ring
color, and shows the last flag on the LCD until another valid message arrives.

The protocol does not specify a sector range. By default the parser accepts
positive 32-bit sector numbers; set `SectorRange` at the call site if the
chosen circuit has known limits. The parallel LCD has no presence-detection
line, so its connection cannot be reported automatically. NeoPixels likewise
provide no feedback path for detecting a failed pixel.

## Build and manual check

Install PlatformIO, connect the LCD and ring using the wiring table above, and
adjust `include/HardwareConfig.h` if needed. From `firmware/`, run
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

`STATUS,READY` is printed on boot. Debug messages are enabled by default and
can be disabled by compiling with `FLAGSENSE_DEBUG=0`.

The hardware-independent parser/framer/state test can be run from the
repository root with:

```sh
c++ -std=c++11 -Wall -Wextra -Werror -Ifirmware/include \
  firmware/src/SerialProtocol.cpp firmware/src/StateMachine.cpp \
  firmware/test/native/test_parser.cpp -o /tmp/flagsense_parser_test
/tmp/flagsense_parser_test
```
