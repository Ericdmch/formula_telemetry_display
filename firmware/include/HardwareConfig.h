#pragma once

#include <stdint.h>

namespace flagsense {
// ESP32-S3-DevKitC-1 N16R8 with a bare LCD1602A and 24-pixel ring.
constexpr int LCD_COLUMNS = 16;
constexpr int LCD_ROWS = 2;
constexpr int LCD_RS_PIN = 13;
constexpr int LCD_ENABLE_PIN = 12;
constexpr int LCD_D4_PIN = 4;
constexpr int LCD_D5_PIN = 5;
constexpr int LCD_D6_PIN = 6;
constexpr int LCD_D7_PIN = 7;
constexpr int NEOPIXEL_DATA_PIN = 18;
constexpr int NEOPIXEL_COUNT = 24;
#ifndef ONBOARD_NEOPIXEL_DATA_PIN
// ESP32-S3-DevKitC-1 v1.0 uses GPIO48; v1.1 uses GPIO38.
#define ONBOARD_NEOPIXEL_DATA_PIN 48
#endif
constexpr int ONBOARD_NEOPIXEL_PIN = ONBOARD_NEOPIXEL_DATA_PIN;
constexpr uint8_t NEOPIXEL_BRIGHTNESS = 32;
constexpr unsigned long TEST_LED_STEP_MS = 400;
constexpr unsigned long TEST_DISPLAY_MS = 800;

// Link supervision: the laptop heartbeats every ~3 s, so 10 s without a
// valid message means the link is genuinely down (not a replay transition).
constexpr unsigned long LINK_LOSS_TIMEOUT_MS = 10000;

// Non-blocking LED animation timing (no delay() anywhere).
constexpr unsigned long LED_FLASH_AMBER_MS = 500;  // safety car: on/off period
constexpr unsigned long LED_FLASH_RED_MS = 400;    // red flag: on/off period
constexpr unsigned long LED_VSC_CYCLE_MS = 1000;   // VSC double-blink cycle
constexpr unsigned long LED_PULSE_CYCLE_MS = 1600;  // double-yellow pulse cycle
constexpr unsigned long LED_PULSE_STEPS = 32;
}  // namespace flagsense
