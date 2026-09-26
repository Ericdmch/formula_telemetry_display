#include <Arduino.h>

#include "Display.h"
#include "FlagMessage.h"
#include "LEDs.h"
#include "Renderer.h"
#include "SerialProtocol.h"
#include "StateMachine.h"

#ifndef FLAGSENSE_DEBUG
#define FLAGSENSE_DEBUG 1
#endif

namespace {
flagsense::LineFramer framer;
flagsense::StateMachine stateMachine;
flagsense::Renderer renderer;
unsigned long lastValidInput = 0;
bool linkLost = false;
constexpr unsigned long LINK_LOSS_TIMEOUT_MS = 5000;  // Protocol suggests 5 s.

void logParseError(flagsense::ParseError error) {
#if FLAGSENSE_DEBUG
  Serial.print("DEBUG PARSE ERROR: ");
  Serial.println(flagsense::parseErrorName(error));
#else
  (void)error;
#endif
}

void handleLine(const char* line) {
#if FLAGSENSE_DEBUG
  Serial.print("DEBUG RX: ");
  Serial.println(line);
#endif
  const flagsense::ParseResult result = flagsense::parseMessage(line);
  if (!result.success) {
    logParseError(result.error);
    return;
  }
  lastValidInput = millis();
  const bool recovered = stateMachine.setLinkLost(false);
  linkLost = false;
  if (result.message.type == flagsense::MessageType::DEVICE_TEST ||
      result.message.type == flagsense::MessageType::LED_TEST ||
      result.message.type == flagsense::MessageType::DISPLAY_TEST) {
    renderer.startTest(result.message.type, millis());
    return;
  }
  const bool stateChanged = stateMachine.handleMessage(result.message);
  if (stateChanged || recovered) {
#if FLAGSENSE_DEBUG
    Serial.print("DEBUG STATE -> ");
    Serial.println(flagsense::systemStateName(stateMachine.state()));
#endif
    renderer.applyState(stateMachine.state(), stateMachine.incident());
  }
}
}  // namespace

void setup() {
  Serial.begin(115200);
  flagsense::ledsBegin();
  const bool displayReady = flagsense::displayBegin();
  stateMachine.begin();
  renderer.begin();
  if (!displayReady) {
    Serial.println("STATUS,ERROR,DEVICE_ERROR");
  }
  lastValidInput = millis();
  Serial.println("STATUS,READY");
}

void loop() {
  char line[flagsense::MAX_MESSAGE_LENGTH + 1];
  while (Serial.available() > 0) {
    flagsense::ParseError framingError = flagsense::ParseError::NONE;
    const char byte = static_cast<char>(Serial.read());
    if (framer.push(byte, line, sizeof(line), framingError)) {
      if (framingError != flagsense::ParseError::NONE) logParseError(framingError);
      else handleLine(line);
    }
  }

  const unsigned long now = millis();
  if (!linkLost && now - lastValidInput >= LINK_LOSS_TIMEOUT_MS) {
    linkLost = true;
    stateMachine.setLinkLost(true);
    renderer.applyState(stateMachine.state(), stateMachine.incident());
  }
  if (renderer.tick(now)) renderer.applyState(stateMachine.state(), stateMachine.incident());
}
