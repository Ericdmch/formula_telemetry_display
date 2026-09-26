# Optional marshal display

The physical device is a **recommendation display** for a hackathon demo. It does not operate official flags or make a safety decision. Software analysis continues normally when no device is connected. The hardware adapter and firmware are not implemented yet.

## MVP bill of materials

- One ESP32 **or** Arduino with USB serial support
- Green, yellow, and red LEDs
- Three 220–330 Ω current-limiting resistors
- Breadboard, jumper wires, and USB cable

An I2C OLED, acknowledge/reset button, and buzzer are stretch goals. Use a board-appropriate digital output pin for each LED; connect each pin through a resistor and LED to ground, observe LED polarity, and check the board's output voltage/current limits. Record the actual pin map in firmware before wiring. Do not assume ESP32 and Arduino pin numbers or voltage limits are interchangeable.

## Interface and responsibility

The laptop owns detection, ML, rules, and reasons. An explicit operator action may call `send_flag(flag)` or `send_recommendation(...)` on a serial adapter. The adapter maps software `GREEN`/`YELLOW`/`RED_RECOMMENDED` to simple display tokens `GREEN`/`YELLOW`/`RED`. Firmware parses a single newline-terminated token, lights exactly one LED, and may show the words **RED FLAG RECOMMENDED** if an OLED is available. It must never calculate risk or infer a flag.

Proposed MVP protocol at `SERIAL_BAUD=115200`:

```text
GREEN
YELLOW
RED
```

Each line above is sent separately with a trailing newline (`\n`). The sender should wait for USB serial startup if the chosen board resets on connection, then send only on an explicit user action. An invalid token should be ignored or shown as an error, not interpreted as GREEN. A disconnected port or write failure becomes a visible dashboard notice; it cannot alter analysis. The port is configured via `SERIAL_PORT` in `.env`, never hard-coded. Add `pyserial` to `requirements.txt` only when the adapter is implemented.

The existing [MVP plan](superpowers/plans/2026-09-26-flagsense-mvp.md) sketches a richer `RECOMMENDATION:RED;RISK:...;SECTOR:...` line. Treat that as a stretch protocol requiring both sides to agree; the three plain tokens above are the baseline. Include a physical “recommendation only” label in the judge demo.
