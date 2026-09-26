#include "LEDs.h"
#include <Arduino.h>
#include <Adafruit_NeoPixel.h>
#include "HardwareConfig.h"

namespace flagsense {
namespace {
Adafruit_NeoPixel ring(NEOPIXEL_COUNT, NEOPIXEL_DATA_PIN, NEO_GRB + NEO_KHZ800);
void setRingColor(uint32_t color) {
  ring.fill(color);
  ring.show();
}
}  // namespace

void ledsBegin() {
  ring.begin();
  ring.setBrightness(NEOPIXEL_BRIGHTNESS);
  allOff();
}

void allOff() { setRingColor(0); }

void setGreen() { setRingColor(ring.Color(0, 180, 0)); }
void setYellow() { setRingColor(ring.Color(255, 90, 0)); }
void setRed() { setRingColor(ring.Color(180, 0, 0)); }

}  // namespace flagsense
