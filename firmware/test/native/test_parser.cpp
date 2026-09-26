#include <assert.h>
#include <string.h>

#include "SerialProtocol.h"
#include "StateMachine.h"

using namespace flagsense;

void expectError(const char* input, ParseError error) {
  const ParseResult result = parseMessage(input);
  assert(!result.success);
  assert(result.error == error);
}

int main() {
  ParseResult result = parseMessage("CLEAR");
  assert(result.success && result.message.type == MessageType::CLEAR);
  result = parseMessage("YELLOW,4,120,STOPPED_CAR");
  assert(result.success && result.message.sector == 4 && result.message.distanceMeters == 120);
  assert(result.message.hazard == HazardType::STOPPED_CAR);
  result = parseMessage("RED,4,0,SESSION_STOPPED");
  assert(result.success && result.message.type == MessageType::RED);
  assert(parseMessage("DEVICE_TEST").success);
  assert(parseMessage("LED_TEST").success);
  assert(parseMessage("DISPLAY_TEST").success);

  expectError("", ParseError::EMPTY_MESSAGE);
  expectError("PURPLE,4,120,STOPPED_CAR", ParseError::UNKNOWN_COMMAND);
  expectError("YELLOW,4", ParseError::WRONG_FIELD_COUNT);
  expectError("YELLOW,4,120,STOPPED_CAR,EXTRA", ParseError::WRONG_FIELD_COUNT);
  expectError("YELLOW,ABC,120,STOPPED_CAR", ParseError::INVALID_SECTOR);
  expectError("YELLOW,-1,120,STOPPED_CAR", ParseError::INVALID_SECTOR);
  expectError("YELLOW,0,120,STOPPED_CAR", ParseError::INVALID_SECTOR);
  expectError("YELLOW,4,ABC,STOPPED_CAR", ParseError::INVALID_DISTANCE);
  expectError("YELLOW,4,-20,STOPPED_CAR", ParseError::INVALID_DISTANCE);
  expectError("YELLOW,4,12.5,STOPPED_CAR", ParseError::INVALID_DISTANCE);
  expectError("YELLOW,4,120,BANANA", ParseError::INVALID_HAZARD);
  char oversized[MAX_MESSAGE_LENGTH + 2];
  memset(oversized, 'A', sizeof(oversized) - 1);
  oversized[sizeof(oversized) - 1] = '\0';
  expectError(oversized, ParseError::MESSAGE_TOO_LONG);

  result = parseMessage("CLEAR\r");
  assert(result.success);

  LineFramer framer;
  char output[MAX_MESSAGE_LENGTH + 1];
  ParseError framingError;
  assert(!framer.push('\n', output, sizeof(output), framingError));  // empty ignored
  const char* sequence = "CLEAR\r\nYELLOW,4,120,STOPPED_CAR\nRED,4,0,SESSION_STOPPED\n";
  int lines = 0;
  for (const char* p = sequence; *p; ++p) {
    if (framer.push(*p, output, sizeof(output), framingError)) {
      assert(framingError == ParseError::NONE);
      ++lines;
      if (lines == 1) assert(strcmp(output, "CLEAR") == 0);
    }
  }
  assert(lines == 3);

  // An oversized line is discarded through newline; the following line works.
  for (size_t i = 0; i < MAX_MESSAGE_LENGTH + 10; ++i)
    assert(!framer.push('X', output, sizeof(output), framingError));
  assert(framer.push('\n', output, sizeof(output), framingError));
  assert(framingError == ParseError::MESSAGE_TOO_LONG);
  for (const char* p = "CLEAR\n"; *p; ++p) {
    if (framer.push(*p, output, sizeof(output), framingError)) {
      assert(framingError == ParseError::NONE);
      assert(strcmp(output, "CLEAR") == 0);
    }
  }

  StateMachine state;
  state.begin();
  assert(state.state() == SystemState::STARTING);
  state.handleMessage(parseMessage("YELLOW,4,120,STOPPED_CAR").message);
  assert(state.state() == SystemState::YELLOW);
  const FlagMessage before = state.incident();
  const char* invalidMessages[] = {
      "PURPLE,4,120,STOPPED_CAR", "YELLOW,4", "YELLOW,4,120,STOPPED_CAR,EXTRA",
      "YELLOW,ABC,120,STOPPED_CAR", "YELLOW,-1,120,STOPPED_CAR",
      "YELLOW,4,ABC,STOPPED_CAR", "YELLOW,4,-20,STOPPED_CAR",
      "YELLOW,4,12.5,STOPPED_CAR", "YELLOW,4,120,BANANA", "",
  };
  for (const char* invalid : invalidMessages) {
    result = parseMessage(invalid);
    assert(!result.success);
    assert(!state.handleMessage(result.message));
    assert(state.state() == SystemState::YELLOW);
    assert(state.incident().sector == before.sector);
    assert(state.incident().distanceMeters == before.distanceMeters);
  }
  state.handleMessage(parseMessage("LED_TEST").message);
  assert(state.state() == SystemState::YELLOW);
  state.setLinkLost(true);
  assert(state.state() == SystemState::LINK_LOST);
  assert(state.incident().sector == before.sector);
  state.setLinkLost(false);
  assert(state.state() == SystemState::YELLOW);
  assert(state.handleMessage(parseMessage("YELLOW,4,120,STOPPED_CAR").message) == false);
  assert(state.setError());
  assert(state.state() == SystemState::ERROR);
  assert(!state.setLinkLost(true));
  return 0;
}
