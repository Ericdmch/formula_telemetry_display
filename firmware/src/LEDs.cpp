#include "LEDs.h"

#include <Adafruit_NeoPixel.h>

#include "HardwareConfig.h"

namespace flagsense {

namespace {
Adafruit_NeoPixel ring(NEOPIXEL_COUNT, NEOPIXEL_DATA_PIN,
                       NEO_GRB + NEO_KHZ800);
Adafruit_NeoPixel onboard(1, ONBOARD_NEOPIXEL_PIN, NEO_GRB + NEO_KHZ800);

constexpr uint32_t AMBER = 0xFF7A00;
constexpr uint32_t GREEN = 0x00C000;
constexpr uint32_t RED = 0xFF0000;
constexpr uint32_t PURPLE = 0x7A00FF;
constexpr uint32_t OFF = 0x000000;

LedPattern activePattern = LedPattern::OFF;
bool patternOn = false;      // current on/off phase for flash/strobe patterns
unsigned long phaseStart = 0;  // millis() at the current phase start
uint8_t lastBrightness = 0xFF;  // tracks redundant ring.show() calls

uint32_t nowMillis() { return static_cast<uint32_t>(millis()); }

uint32_t amberPulse(uint8_t step) {
  // 32-step triangle wave: ramps up then back down over one cycle.
  const uint8_t level = step < LED_PULSE_STEPS / 2
                            ? step * 2
                            : (LED_PULSE_STEPS - 1 - step) * 2;
  return ring.Color((AMBER >> 16) * level / 31, ((AMBER >> 8) & 0xFF) * level / 31,
                    (AMBER & 0xFF) * level / 31);
}

void applySolid(uint32_t color) {
  ring.fill(color);
  ring.show();
  onboard.fill(color);
  onboard.show();
}

void stopPattern() {
  activePattern = LedPattern::OFF;
  lastBrightness = 0xFF;
}

}  // namespace

void ledsBegin() {
  ring.begin();
  ring.setBrightness(NEOPIXEL_BRIGHTNESS);
  ring.fill(OFF);
  ring.show();
  onboard.begin();
  onboard.setBrightness(NEOPIXEL_BRIGHTNESS);
  onboard.fill(OFF);
  onboard.show();
}

// Applies the first animation frame immediately so a new recommendation
// interrupts the previous pattern without waiting out the old phase.
void setLedPattern(LedPattern pattern) {
  activePattern = pattern;
  phaseStart = nowMillis();
  patternOn = true;
  lastBrightness = 0xFF;
  uint32_t color = OFF;
  switch (pattern) {
    case LedPattern::OFF:
      color = OFF;
      ring.fill(OFF);
      break;
    case LedPattern::SOLID_GREEN:
      color = GREEN;
      ring.fill(GREEN);
      break;
    case LedPattern::SOLID_AMBER:
      color = AMBER;
      ring.fill(AMBER);
      break;
    case LedPattern::PULSE_AMBER:
      color = AMBER;
      ring.fill(amberPulse(0));
      lastBrightness = 0;
      break;
    case LedPattern::FLASH_AMBER:
    case LedPattern::STROBE_AMBER:
      color = AMBER;
      ring.fill(AMBER);
      break;
    case LedPattern::FLASH_RED:
      color = RED;
      ring.fill(RED);
      break;
  }
  ring.show();
  onboard.fill(color);
  onboard.show();
}

void tickLeds() {
  const uint32_t now = nowMillis();
  switch (activePattern) {
    case LedPattern::OFF:
    case LedPattern::SOLID_GREEN:
    case LedPattern::SOLID_AMBER:
      return;
    case LedPattern::PULSE_AMBER: {
      const uint8_t step =
          static_cast<uint8_t>((now - phaseStart) * LED_PULSE_STEPS /
                               LED_PULSE_CYCLE_MS) %
          LED_PULSE_STEPS;
      if (step != lastBrightness) {
        const uint32_t c = amberPulse(step);
        ring.fill(c);
        ring.show();
        onboard.fill(c);
        onboard.show();
        lastBrightness = step;
      }
      return;
    }
    case LedPattern::FLASH_AMBER:
    case LedPattern::FLASH_RED: {
      const unsigned long period = activePattern == LedPattern::FLASH_AMBER
                                       ? LED_FLASH_AMBER_MS
                                       : LED_FLASH_RED_MS;
      const bool on = ((now - phaseStart) / period) % 2 == 0;
      if (on != patternOn) {
        patternOn = on;
        const uint32_t c = on ? (activePattern == LedPattern::FLASH_RED ? RED : AMBER) : OFF;
        ring.fill(c);
        ring.show();
        onboard.fill(c);
        onboard.show();
      }
      return;
    }
    case LedPattern::STROBE_AMBER: {
      // Double-blink strobe: on 120 ms, off 120 ms, on 120 ms, rest off.
      const unsigned long t = (now - phaseStart) % LED_VSC_CYCLE_MS;
      const bool on = t < 120 || (t >= 240 && t < 360);
      if (on != patternOn) {
        patternOn = on;
        const uint32_t c = on ? AMBER : OFF;
        ring.fill(c);
        ring.show();
        onboard.fill(c);
        onboard.show();
      }
      return;
    }
  }
}

void setGreen() {
  stopPattern();
  applySolid(GREEN);
}
void setYellow() {
  stopPattern();
  applySolid(AMBER);
}
void setRed() {
  stopPattern();
  applySolid(RED);
}
void setStartupIndicator() {
  stopPattern();
  ring.fill(OFF);
  ring.show();
  onboard.fill(0x0000C0);  // Blue while waiting for link
  onboard.show();
}
void setLinkLostIndicator() {
  stopPattern();
  ring.fill(OFF);
  ring.show();
  onboard.fill(PURPLE);  // Purple on link lost
  onboard.show();
}
void setErrorIndicator() {
  stopPattern();
  applySolid(RED);
}
void allOff() {
  stopPattern();
  ring.fill(OFF);
  ring.show();
  onboard.fill(OFF);
  onboard.show();
}


}  // namespace flagsense
