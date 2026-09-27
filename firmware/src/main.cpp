#include <Arduino.h>

#include "HardwareConfig.h"
#include "Renderer.h"
#include "SerialProtocol.h"

namespace {
using namespace flagsense;
Renderer renderer;
LineFramer framer;
constexpr unsigned long HEARTBEAT_MS = 1000;
unsigned long lastHeartbeat = 0;
// Link supervision: any valid message restarts the watchdog. Only once a
// valid message has been seen can a timeout mean LINK_LOST.
unsigned long lastValidRx = 0;
bool everValid = false;

void heartbeat() {
  const unsigned long now = millis();
  if (now - lastHeartbeat >= HEARTBEAT_MS) {
    lastHeartbeat = now;
    Serial.println("STATUS,READY");
  }
}

void handleLine(const char* line) {
  Serial.print("RX,");
  Serial.println(line);
  const ParseResult result = parseMessage(line);
  if (!result.success) {
    Serial.print("STATUS,REJECTED,");
    Serial.println(parseErrorName(result.error));
    return;
  }
  lastValidRx = millis();
  everValid = true;
  const SystemState before = renderer.state();
  renderer.setLinkLost(false);  // any valid message recovers the link
  renderer.handleMessage(result.message);
  const SystemState after = renderer.state();
  if (before != after) {
    if (before == SystemState::LINK_LOST) {
      Serial.print("STATUS,RECOVERED,");
      Serial.println(systemStateName(after));
    }
    Serial.print("STATUS,STATE,");
    Serial.println(systemStateName(after));
  }
}

}  // namespace

void setup() {
  Serial.begin(115200);
  renderer.begin();
  Serial.println("STATUS,READY");
}

void loop() {
  renderer.tick();
  while (Serial.available() > 0) {
    const int byte = Serial.read();
    if (byte < 0) break;
    char line[MAX_MESSAGE_LENGTH + 1];
    ParseError error = ParseError::NONE;
    if (framer.push(static_cast<char>(byte), line, sizeof(line), error)) {
      if (error == ParseError::NONE) {
        handleLine(line);
      } else {
        Serial.print("STATUS,REJECTED,");
        Serial.println(parseErrorName(error));
      }
    }
  }
  // Link-loss watchdog: with no valid message for LINK_LOSS_TIMEOUT_MS the
  // link is genuinely down. Normal replay progression always heartbeats, so
  // it never trips falsely.
  if (everValid && renderer.state() != SystemState::LINK_LOST &&
      millis() - lastValidRx > LINK_LOSS_TIMEOUT_MS) {
    renderer.setLinkLost(true);
    Serial.println("STATUS,LINK_LOST");
  }
  heartbeat();
}
