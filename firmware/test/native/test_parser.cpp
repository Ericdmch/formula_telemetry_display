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
  // ---- v1 messages (backward compatibility) ----
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

  // ---- v2: new flag keywords, v1 shape ----
  result = parseMessage("GREEN");
  assert(result.success && result.message.type == MessageType::GREEN);
  result = parseMessage("DOUBLE_YELLOW,2,100,DEBRIS");
  assert(result.success && result.message.type == MessageType::DOUBLE_YELLOW);
  assert(result.message.sector == 2 && result.message.hazard == HazardType::DEBRIS);
  result = parseMessage("SAFETY_CAR,3,0,DEBRIS");
  assert(result.success && result.message.type == MessageType::SAFETY_CAR);
  result = parseMessage("VSC,2,0,DEBRIS");
  assert(result.success && result.message.type == MessageType::VSC);

  // ---- v2: extended 7-field shape ----
  result = parseMessage("YELLOW,2,120,STOPPED_CAR,27,142,C27 S2 STOPPED");
  assert(result.success);
  assert(result.message.type == MessageType::YELLOW);
  assert(result.message.carId == 27);
  assert(result.message.seq == 142);
  assert(strcmp(result.message.context, "C27 S2 STOPPED") == 0);
  // Extended form with unknown/empty fields.
  result = parseMessage("RED,0,0,SESSION_STOPPED,0,7,");
  assert(result.success);
  assert(result.message.sector == 0 && result.message.carId == 0);
  assert(result.message.seq == 7);
  assert(result.message.context[0] == '\0');
  // Sector 0 ("unknown") is accepted by the default range.
  result = parseMessage("YELLOW,0,120,STOPPED_CAR");
  assert(result.success && result.message.sector == 0);
  // Context longer than the LCD budget is truncated to 16 chars.
  result = parseMessage("YELLOW,2,0,DEBRIS,0,9,ABCDEFGHIJKLMNOPQRST");
  assert(result.success);
  assert(strlen(result.message.context) == CONTEXT_MAX_CHARS);
  assert(strncmp(result.message.context, "ABCDEFGHIJKLMNOP", CONTEXT_MAX_CHARS) == 0);
  // GREEN stays bare; CLEAR stays a 1-field alias.
  expectError("GREEN,1", ParseError::WRONG_FIELD_COUNT);
  expectError("CLEAR,1", ParseError::WRONG_FIELD_COUNT);

  // ---- v2: new error cases ----
  expectError("", ParseError::EMPTY_MESSAGE);
  expectError("PURPLE,4,120,STOPPED_CAR", ParseError::UNKNOWN_COMMAND);
  expectError("YELLOW,4", ParseError::WRONG_FIELD_COUNT);
  expectError("YELLOW,4,120,STOPPED_CAR,EXTRA", ParseError::WRONG_FIELD_COUNT);
  expectError("YELLOW,4,120,STOPPED_CAR,27,142,CTX,EXTRA", ParseError::WRONG_FIELD_COUNT);
  expectError("YELLOW,ABC,120,STOPPED_CAR", ParseError::INVALID_SECTOR);
  expectError("YELLOW,-1,120,STOPPED_CAR", ParseError::INVALID_SECTOR);
  expectError("YELLOW,4,ABC,STOPPED_CAR", ParseError::INVALID_DISTANCE);
  expectError("YELLOW,4,-20,STOPPED_CAR", ParseError::INVALID_DISTANCE);
  expectError("YELLOW,4,12.5,STOPPED_CAR", ParseError::INVALID_DISTANCE);
  expectError("YELLOW,4,120,BANANA", ParseError::INVALID_HAZARD);
  expectError("YELLOW,2,120,STOPPED_CAR,ABC,1,CTX", ParseError::INVALID_CAR_ID);
  expectError("YELLOW,2,120,STOPPED_CAR,99999,1,CTX", ParseError::INVALID_CAR_ID);
  expectError("YELLOW,2,120,STOPPED_CAR,27,ABC,CTX", ParseError::INVALID_SEQ);
  expectError("DOUBLE_YELLOW,2,100,BANANA", ParseError::INVALID_HAZARD);
  char oversized[MAX_MESSAGE_LENGTH + 2];
  memset(oversized, 'A', sizeof(oversized) - 1);
  oversized[sizeof(oversized) - 1] = '\0';
  expectError(oversized, ParseError::MESSAGE_TOO_LONG);

  result = parseMessage("CLEAR\r");
  assert(result.success);

  // ---- framer (unchanged behavior) ----
  LineFramer framer;
  char output[MAX_MESSAGE_LENGTH + 1];
  ParseError framingError;
  assert(!framer.push('\n', output, sizeof(output), framingError));  // empty ignored
  const char* sequence = "CLEAR\r\nVSC,2,0,DEBRIS,0,3,DEBRIS REPORTED\nRED,4,0,SESSION_STOPPED\n";
  int lines = 0;
  for (const char* p = sequence; *p; ++p) {
    if (framer.push(*p, output, sizeof(output), framingError)) {
      assert(framingError == ParseError::NONE);
      ++lines;
      if (lines == 1) assert(strcmp(output, "CLEAR") == 0);
      if (lines == 2) assert(strcmp(output, "VSC,2,0,DEBRIS,0,3,DEBRIS REPORTED") == 0);
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

  // ---- state machine: new states ----
  StateMachine state;
  state.begin();
  assert(state.state() == SystemState::STARTING);
  assert(state.handleMessage(parseMessage("GREEN").message));
  assert(state.state() == SystemState::GREEN);
  assert(state.handleMessage(parseMessage("CLEAR").message));  // alias -> GREEN
  assert(state.state() == SystemState::GREEN);
  assert(state.handleMessage(parseMessage("DOUBLE_YELLOW,2,100,DEBRIS").message));
  assert(state.state() == SystemState::DOUBLE_YELLOW);
  assert(state.handleMessage(parseMessage("SAFETY_CAR,3,0,DEBRIS").message));
  assert(state.state() == SystemState::SAFETY_CAR);
  assert(state.handleMessage(parseMessage("VSC,2,0,DEBRIS").message));
  assert(state.state() == SystemState::VSC);
  assert(state.handleMessage(parseMessage("RED,4,0,SESSION_STOPPED").message));
  assert(state.state() == SystemState::RED);

  // ---- state machine: change detection ignores seq ----
  state.handleMessage(parseMessage("YELLOW,2,120,STOPPED_CAR,27,142,C27 S2 STOPPED").message);
  assert(state.state() == SystemState::YELLOW);
  // Identical re-send (heartbeat with bumped seq) is not a change.
  assert(!state.handleMessage(parseMessage("YELLOW,2,120,STOPPED_CAR,27,143,C27 S2 STOPPED").message));
  // New context IS a change (drives LCD refresh).
  assert(state.handleMessage(parseMessage("YELLOW,2,120,STOPPED_CAR,27,144,C28 S2 STOPPED").message));
  assert(strcmp(state.incident().context, "C28 S2 STOPPED") == 0);

  // ---- state machine: invalid input never mutates confirmed state ----
  const FlagMessage before = state.incident();
  const char* invalidMessages[] = {
      "PURPLE,4,120,STOPPED_CAR", "YELLOW,4", "YELLOW,4,120,STOPPED_CAR,EXTRA",
      "YELLOW,ABC,120,STOPPED_CAR", "YELLOW,-1,120,STOPPED_CAR",
      "YELLOW,4,ABC,STOPPED_CAR", "YELLOW,4,-20,STOPPED_CAR",
      "YELLOW,4,12.5,STOPPED_CAR", "YELLOW,4,120,BANANA",
      "YELLOW,2,120,STOPPED_CAR,XX,1,CTX", "",
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
  assert(state.handleMessage(parseMessage("YELLOW,2,120,STOPPED_CAR,27,144,C28 S2 STOPPED").message) == false);
  assert(state.setError());
  assert(state.state() == SystemState::ERROR);
  assert(!state.setLinkLost(true));
  return 0;
}
