#pragma once

#include <stdint.h>

namespace flagsense {

enum class MessageType : uint8_t {
  CLEAR,
  YELLOW,
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

struct FlagMessage {
  MessageType type = MessageType::CLEAR;
  int32_t sector = 0;
  int32_t distanceMeters = 0;
  HazardType hazard = HazardType::INVALID;
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
};

struct ParseResult {
  bool success = false;
  FlagMessage message{};
  ParseError error = ParseError::EMPTY_MESSAGE;
};

}  // namespace flagsense
