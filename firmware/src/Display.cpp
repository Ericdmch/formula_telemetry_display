#include "Display.h"

#include <LiquidCrystal.h>
#include <stdio.h>
#include "HardwareConfig.h"
#include "SerialProtocol.h"

namespace flagsense {
namespace {
LiquidCrystal lcd(LCD_RS_PIN, LCD_ENABLE_PIN, LCD_D4_PIN, LCD_D5_PIN,
                  LCD_D6_PIN, LCD_D7_PIN);
bool available = false;

const char* hazardDisplayText(HazardType hazard) {
  switch (hazard) {
    case HazardType::STOPPED_CAR: return "STOPPED CAR";
    case HazardType::CRASH: return "CRASH";
    case HazardType::TRACK_BLOCKED: return "TRACK BLOCKED";
    case HazardType::DEBRIS: return "DEBRIS";
    case HazardType::SPIN: return "SPIN";
    case HazardType::SLOW_CAR: return "SLOW CAR";
    case HazardType::MULTI_CAR_INCIDENT: return "MULTI CAR";
    case HazardType::OFF_TRACK: return "OFF TRACK";
    case HazardType::UNKNOWN_HAZARD: return "UNKNOWN HAZARD";
    case HazardType::SESSION_STOPPED: return "SESSION STOPPED";
    case HazardType::INVALID: return "UNKNOWN HAZARD";
  }
  return "UNKNOWN HAZARD";
}

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
}  // namespace

bool displayBegin() {
  lcd.begin(LCD_COLUMNS, LCD_ROWS);
  lcd.clear();
  // A parallel LCD has no discovery/status line, so presence cannot be sensed.
  available = true;
  return available;
}

void renderStartup() {
  writeLine(0, "FlagSense");
  writeLine(1, "Starting...");
}

void renderClear() {
  writeLine(0, "CLEAR - TRACK OK");
  writeLine(1, "NO ACTIVE HAZ.");
}

void renderIncident(SystemState state, const FlagMessage& message) {
  char text[32];
  if (state == SystemState::YELLOW) {
    snprintf(text, sizeof(text), "YELLOW S%ld", static_cast<long>(message.sector));
    writeLine(0, text);
    snprintf(text, sizeof(text), "%ldm %s", static_cast<long>(message.distanceMeters),
             hazardDisplayText(message.hazard));
    writeLine(1, text);
  } else {
    snprintf(text, sizeof(text), "RED FLAG S%ld", static_cast<long>(message.sector));
    writeLine(0, text);
    writeLine(1, hazardDisplayText(message.hazard));
  }
}

void renderDeviceTest() {
  writeLine(0, "DEVICE TEST"); writeLine(1, "LED SEQUENCE");
}

void renderDisplayTest() {
  writeLine(0, "DISPLAY TEST OK"); writeLine(1, "");
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
