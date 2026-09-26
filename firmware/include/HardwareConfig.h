#pragma once

#include <stdint.h>

namespace flagsense {
// ESP32-S3-DevKitC-1 N16R8 with a bare LCD1602A and 24-pixel ring.
constexpr int LCD_COLUMNS = 16;
constexpr int LCD_ROWS = 2;
constexpr int LCD_RS_PIN = 4;
constexpr int LCD_ENABLE_PIN = 5;
constexpr int LCD_D4_PIN = 6;
constexpr int LCD_D5_PIN = 7;
constexpr int LCD_D6_PIN = 8;
constexpr int LCD_D7_PIN = 9;
constexpr int NEOPIXEL_DATA_PIN = 18;
constexpr int NEOPIXEL_COUNT = 24;
constexpr uint8_t NEOPIXEL_BRIGHTNESS = 32;
constexpr unsigned long TEST_LED_STEP_MS = 400;
constexpr unsigned long TEST_DISPLAY_MS = 800;
}  // namespace flagsense
