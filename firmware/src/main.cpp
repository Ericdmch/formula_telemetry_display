#include <Arduino.h>

#include "Display.h"
#include "FlagMessage.h"
#include "LEDs.h"
#include "Renderer.h"
#include "SerialProtocol.h"
#include "StateMachine.h"

namespace {
flagsense::LineFramer framer;
flagsense::StateMachine stateMachine;
flagsense::Renderer renderer;
unsigned long lastStatusOutput = 0;
constexpr unsigned long STATUS_HEARTBEAT_MS = 1000;

void logParseError(flagsense::ParseError error) {
  Serial.print("STATUS,REJECTED,");
  Serial.println(flagsense::parseErrorName(error));
}

void handleLine(const char* line) {
  Serial.print("RX,");
  Serial.println(line);
  const flagsense::ParseResult result = flagsense::parseMessage(line);
  if (!result.success) {
    logParseError(result.error);
    return;
  }
  if (result.message.type == flagsense::MessageType::DEVICE_TEST ||
      result.message.type == flagsense::MessageType::LED_TEST ||
      result.message.type == flagsense::MessageType::DISPLAY_TEST) {
    Serial.print("STATUS,TEST,");
    Serial.println(flagsense::messageTypeName(result.message.type));
    renderer.startTest(result.message.type, millis());
    return;
  }
  const bool stateChanged = stateMachine.handleMessage(result.message);
  if (stateChanged) {
    Serial.print("STATUS,STATE,");
    Serial.println(flagsense::systemStateName(stateMachine.state()));
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
  lastStatusOutput = millis();
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
  if (now - lastStatusOutput >= STATUS_HEARTBEAT_MS) {
    lastStatusOutput = now;
    Serial.println("STATUS,READY");
  }
  if (renderer.tick(now)) renderer.applyState(stateMachine.state(), stateMachine.incident());
}
