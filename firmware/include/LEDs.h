#pragma once

#include <stdint.h>

namespace flagsense {

// Non-blocking LED patterns. All animation is driven by tickLeds() — never
// with delay() — so serial handling and the link watchdog stay responsive.
// setLedPattern() applies the first frame immediately, so a new
// recommendation interrupts the previous pattern without waiting.
enum class LedPattern : uint8_t {
  OFF,
  SOLID_GREEN,
  SOLID_AMBER,
  PULSE_AMBER,  // double yellow: slow brightness pulse
  FLASH_AMBER,  // safety car: 500 ms on/off
  STROBE_AMBER,  // VSC: double-blink strobe
  FLASH_RED,    // red flag: 400 ms on/off
};

void ledsBegin();
void setLedPattern(LedPattern pattern);
void tickLeds();  // call every loop()

// Legacy solid setters (used by the device self-test). Each one stops any
// active pattern first so tickLeds() cannot fight the test sequence.
void setGreen();
void setYellow();
void setRed();
void setStartupIndicator();
void setLinkLostIndicator();
void setErrorIndicator();
void allOff();
}  // namespace flagsense
