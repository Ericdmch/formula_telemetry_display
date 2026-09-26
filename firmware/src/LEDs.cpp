#include "LEDs.h"
#include <Arduino.h>
#include <Adafruit_NeoPixel.h>
#include "HardwareConfig.h"

namespace flagsense {
namespace {
Adafruit_NeoPixel ring(NEOPIXEL_COUNT, NEOPIXEL_DATA_PIN, NEO_GRB + NEO_KHZ800);
Adafruit_NeoPixel onboardPixel(1, ONBOARD_NEOPIXEL_PIN, NEO_GRB + NEO_KHZ800);

void setPixels(uint32_t color) {
  ring.fill(color);
  ring.show();
  onboardPixel.setPixelColor(0, color);
  onboardPixel.show();
}
}  // namespace

void ledsBegin() {
  ring.begin();
  onboardPixel.begin();
  ring.setBrightness(NEOPIXEL_BRIGHTNESS);
  onboardPixel.setBrightness(NEOPIXEL_BRIGHTNESS);
  allOff();
}

void allOff() { setPixels(0); }

void setGreen() { setPixels(ring.Color(0, 180, 0)); }
void setYellow() { setPixels(ring.Color(255, 90, 0)); }
void setRed() { setPixels(ring.Color(180, 0, 0)); }

void setStartupIndicator() {
  onboardPixel.setPixelColor(0, onboardPixel.Color(0, 0, 180));
  onboardPixel.show();
}

void setLinkLostIndicator() {
  onboardPixel.setPixelColor(0, onboardPixel.Color(100, 0, 180));
  onboardPixel.show();
}

void setErrorIndicator() {
  onboardPixel.setPixelColor(0, onboardPixel.Color(180, 0, 100));
  onboardPixel.show();
}

}  // namespace flagsense
