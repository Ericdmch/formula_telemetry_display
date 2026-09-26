#pragma once

#include <stdint.h>

namespace flagsense {
// Defaults for a bare 16-pin LCD1602A in 4-bit mode and a 24-pixel ring.
constexpr int LCD_COLUMNS = 16;
constexpr int LCD_ROWS = 2;
constexpr int LCD_RS_PIN = 23;
constexpr int LCD_ENABLE_PIN = 22;
constexpr int LCD_D4_PIN = 21;
constexpr int LCD_D5_PIN = 19;
constexpr int LCD_D6_PIN = 25;
constexpr int LCD_D7_PIN = 26;
constexpr int NEOPIXEL_DATA_PIN = 18;
constexpr int NEOPIXEL_COUNT = 24;
constexpr uint8_t NEOPIXEL_BRIGHTNESS = 32;
constexpr unsigned long TEST_LED_STEP_MS = 400;
constexpr unsigned long TEST_DISPLAY_MS = 800;
}  // namespace flagsense
