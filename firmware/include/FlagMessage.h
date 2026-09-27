#pragma once

#include <stddef.h>
#include <stdint.h>

namespace flagsense {

// Wire vocabulary, protocol v2. CLEAR is kept as a legacy alias and is
// treated exactly like GREEN. New keywords reuse the existing
// FLAG,SECTOR,DISTANCE,HAZARD shape so v1 senders keep working.
enum class MessageType : uint8_t {
  CLEAR,  // legacy alias -> GREEN
  GREEN,
  YELLOW,
  DOUBLE_YELLOW,
  SAFETY_CAR,
  VSC,
  RED,
  DEVICE_TEST,
  DISPLAY_TEST,
  LED_TEST,
};

enum class HazardType : uint8_t {
  STOPPED_CAR,
  CRASH,
  TRACK_BLOCKED,
  DEBRIS,
  SPIN,
  SLOW_CAR,
  MULTI_CAR_INCIDENT,
  OFF_TRACK,
  UNKNOWN_HAZARD,
  SESSION_STOPPED,
  INVALID,
};

// LCD line budget (16x2). Context strings longer than this are truncated.
constexpr size_t CONTEXT_MAX_CHARS = 16;

struct FlagMessage {
  MessageType type = MessageType::CLEAR;
  int32_t sector = 0;          // 0 = unknown
  int32_t distanceMeters = 0;  // 0 = unknown
  HazardType hazard = HazardType::INVALID;
  uint16_t carId = 0;  // involved car number, 0 = unknown
  uint32_t seq = 0;    // per-message counter from the sender (ordering/audit only)
  char context[CONTEXT_MAX_CHARS + 1] = {};  // short LCD line 2, "" = derive
  bool valid = false;
};

enum class ParseError : uint8_t {
  NONE,
  EMPTY_MESSAGE,
  MESSAGE_TOO_LONG,
  UNKNOWN_COMMAND,
  WRONG_FIELD_COUNT,
  INVALID_SECTOR,
  INVALID_DISTANCE,
  INVALID_HAZARD,
  INVALID_CAR_ID,
  INVALID_SEQ,
};

struct ParseResult {
  bool success = false;
  FlagMessage message{};
  ParseError error = ParseError::EMPTY_MESSAGE;
};

}  // namespace flagsense
