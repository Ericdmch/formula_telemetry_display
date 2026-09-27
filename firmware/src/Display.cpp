#include "Display.h"

#include <LiquidCrystal.h>
#include <stdio.h>
#include <string.h>

#include "HardwareConfig.h"
#include "SerialProtocol.h"

namespace flagsense {
namespace {
LiquidCrystal lcd(LCD_RS_PIN, LCD_ENABLE_PIN, LCD_D4_PIN, LCD_D5_PIN, LCD_D6_PIN,
                  LCD_D7_PIN);
bool available = false;

void writeLine(uint8_t row, const char* text) {
  if (!available) return;
  lcd.setCursor(0, row);
  uint8_t column = 0;
  while (column < LCD_COLUMNS && text[column] != '\0') {
    lcd.print(text[column]);
    ++column;
  }
  while (column < LCD_COLUMNS) {
    lcd.print(' ');
    ++column;
  }
}

}  // namespace (anonymous)

bool displayBegin() {
  lcd.begin(LCD_COLUMNS, LCD_ROWS);
  lcd.clear();
  available = true;
  return true;
}

void renderStartup() {
  writeLine(0, "FLAGSENSE");
  writeLine(1, "WAITING LINK");
}

void renderDeviceTest() {
  writeLine(0, "DISPLAY TEST");
  writeLine(1, "1234567890123456");
}

namespace {
const char* flagLabel(SystemState state) {
  switch (state) {
    case SystemState::GREEN:
      return "GREEN FLAG";
    case SystemState::YELLOW:
      return "YELLOW FLAG";
    case SystemState::DOUBLE_YELLOW:
      return "DOUBLE YELLOW";
    case SystemState::SAFETY_CAR:
      return "SAFETY CAR";
    case SystemState::VSC:
      return "VSC";
    case SystemState::RED:
      return "RED FLAG";
    default:
      return "";
  }
}

const char* hazardLabel(HazardType hazard) {
  switch (hazard) {
    case HazardType::STOPPED_CAR:
      return "STOPPED CAR";
    case HazardType::CRASH:
      return "CRASH";
    case HazardType::TRACK_BLOCKED:
      return "TRACK BLOCKED";
    case HazardType::DEBRIS:
      return "DEBRIS";
    case HazardType::SPIN:
      return "SPIN";
    case HazardType::SLOW_CAR:
      return "SLOW CAR";
    case HazardType::MULTI_CAR_INCIDENT:
      return "MULTI CAR";
    case HazardType::OFF_TRACK:
      return "OFF TRACK";
    case HazardType::SESSION_STOPPED:
      return "SESSION STOPPED";
    case HazardType::UNKNOWN_HAZARD:
    case HazardType::INVALID:
      return "CAUTION";
  }
  return "CAUTION";
}

}  // namespace (anonymous)

void renderFlagState(SystemState state, const FlagMessage& message) {
  const char* label = flagLabel(state);
  if (label[0] == '\0') return;
  writeLine(0, label);
  // Line 2: prefer the sender's short context (built from real evidence by
  // the dashboard); otherwise derive from the incident evidence; green
  // always reads "Track clear" so no stale context survives a return.
  if (message.context[0] != '\0') {
    writeLine(1, message.context);
    return;
  }
  if (state == SystemState::GREEN) {
    writeLine(1, "Track clear");
    return;
  }
  char line[LCD_COLUMNS + 1];
  if (message.sector > 0 && message.distanceMeters > 0) {
    snprintf(line, sizeof(line), "S%ld %ldm", (long)message.sector,
             (long)message.distanceMeters);
  } else if (message.sector > 0) {
    snprintf(line, sizeof(line), "S%ld %s", (long)message.sector,
             hazardLabel(message.hazard));
  } else if (message.distanceMeters > 0) {
    snprintf(line, sizeof(line), "%ldm %s", (long)message.distanceMeters,
             hazardLabel(message.hazard));
  } else {
    snprintf(line, sizeof(line), "%s", hazardLabel(message.hazard));
  }
  writeLine(1, line);
}

void renderLinkLost(const FlagMessage& lastConfirmed) {
  writeLine(0, "LINK LOST");
  char text[17];
  snprintf(text, sizeof(text), "LAST: %s",
           lastConfirmed.valid ? messageTypeName(lastConfirmed.type) : "UNKNOWN");
  writeLine(1, text);
}

void renderError() {
  writeLine(0, "DEVICE ERROR"); writeLine(1, "CHECK SYSTEM");
}

}  // namespace flagsense
