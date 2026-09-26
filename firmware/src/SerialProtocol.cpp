#include "SerialProtocol.h"

#include <limits.h>
#include <string.h>

namespace flagsense {
namespace {

bool parseInteger(const char* text, int32_t& value) {
  if (text == nullptr || *text == '\0') return false;
  int32_t parsed = 0;
  for (const char* p = text; *p; ++p) {
    if (*p < '0' || *p > '9') return false;
    const int digit = *p - '0';
    if (parsed > (INT32_MAX - digit) / 10) return false;
    parsed = parsed * 10 + digit;
  }
  value = parsed;
  return true;
}

bool lookupHazard(const char* text, HazardType& hazard) {
  static const struct { const char* name; HazardType type; } values[] = {
      {"STOPPED_CAR", HazardType::STOPPED_CAR}, {"CRASH", HazardType::CRASH},
      {"TRACK_BLOCKED", HazardType::TRACK_BLOCKED}, {"DEBRIS", HazardType::DEBRIS},
      {"SPIN", HazardType::SPIN}, {"SLOW_CAR", HazardType::SLOW_CAR},
      {"MULTI_CAR_INCIDENT", HazardType::MULTI_CAR_INCIDENT},
      {"OFF_TRACK", HazardType::OFF_TRACK}, {"UNKNOWN_HAZARD", HazardType::UNKNOWN_HAZARD},
      {"SESSION_STOPPED", HazardType::SESSION_STOPPED},
  };
  for (const auto& value : values) {
    if (strcmp(text, value.name) == 0) { hazard = value.type; return true; }
  }
  return false;
}

ParseResult failure(ParseError error) {
  ParseResult result;
  result.error = error;
  return result;
}

}  // namespace

ParseResult parseMessage(const char* input, SectorRange sectors) {
  if (input == nullptr || *input == '\0') return failure(ParseError::EMPTY_MESSAGE);
  char copy[MAX_MESSAGE_LENGTH + 1];
  const size_t length = strlen(input);
  if (length > MAX_MESSAGE_LENGTH) return failure(ParseError::MESSAGE_TOO_LONG);
  memcpy(copy, input, length + 1);
  if (length && copy[length - 1] == '\r') copy[length - 1] = '\0';
  if (*copy == '\0') return failure(ParseError::EMPTY_MESSAGE);

  char* tokens[5] = {};
  size_t count = 1;
  tokens[0] = copy;
  for (char* p = copy; *p; ++p) {
    if (*p == ',') {
      if (count == 5) return failure(ParseError::WRONG_FIELD_COUNT);
      *p = '\0';
      tokens[count++] = p + 1;
    }
  }

  FlagMessage message;
  if (strcmp(tokens[0], "CLEAR") == 0) {
    if (count != 1) return failure(ParseError::WRONG_FIELD_COUNT);
    message.type = MessageType::CLEAR;
  } else if (strcmp(tokens[0], "DEVICE_TEST") == 0 ||
             strcmp(tokens[0], "DISPLAY_TEST") == 0 ||
             strcmp(tokens[0], "LED_TEST") == 0) {
    if (count != 1) return failure(ParseError::WRONG_FIELD_COUNT);
    message.type = strcmp(tokens[0], "DEVICE_TEST") == 0 ? MessageType::DEVICE_TEST :
                   strcmp(tokens[0], "DISPLAY_TEST") == 0 ? MessageType::DISPLAY_TEST : MessageType::LED_TEST;
  } else if (strcmp(tokens[0], "YELLOW") == 0 || strcmp(tokens[0], "RED") == 0) {
    if (count != 4) return failure(ParseError::WRONG_FIELD_COUNT);
    message.type = strcmp(tokens[0], "YELLOW") == 0 ? MessageType::YELLOW : MessageType::RED;
    int32_t sector = 0, distance = 0;
    if (!parseInteger(tokens[1], sector) || sector < sectors.min || sector > sectors.max)
      return failure(ParseError::INVALID_SECTOR);
    if (!parseInteger(tokens[2], distance)) return failure(ParseError::INVALID_DISTANCE);
    if (!lookupHazard(tokens[3], message.hazard)) return failure(ParseError::INVALID_HAZARD);
    message.sector = sector;
    message.distanceMeters = distance;
  } else {
    return failure(ParseError::UNKNOWN_COMMAND);
  }
  message.valid = true;
  ParseResult result;
  result.success = true;
  result.message = message;
  result.error = ParseError::NONE;
  return result;
}

bool LineFramer::push(char byte, char* output, size_t capacity, ParseError& error) {
  error = ParseError::NONE;
  if (byte == '\n') {
    if (discarding_) { discarding_ = false; length_ = 0; error = ParseError::MESSAGE_TOO_LONG; return true; }
    if (length_ && buffer_[length_ - 1] == '\r') --length_;
    buffer_[length_] = '\0';
    const bool nonempty = length_ != 0;
    if (!nonempty) { length_ = 0; return false; }
    if (capacity <= length_) { length_ = 0; error = ParseError::MESSAGE_TOO_LONG; return true; }
    memcpy(output, buffer_, length_ + 1);
    length_ = 0;
    return true;
  }
  if (discarding_) return false;
  if (length_ >= MAX_MESSAGE_LENGTH) { discarding_ = true; length_ = 0; return false; }
  buffer_[length_++] = byte;
  return false;
}

const char* parseErrorName(ParseError error) {
  switch (error) {
    case ParseError::NONE: return "NONE";
    case ParseError::EMPTY_MESSAGE: return "EMPTY_MESSAGE";
    case ParseError::MESSAGE_TOO_LONG: return "MESSAGE_TOO_LONG";
    case ParseError::UNKNOWN_COMMAND: return "UNKNOWN_COMMAND";
    case ParseError::WRONG_FIELD_COUNT: return "WRONG_FIELD_COUNT";
    case ParseError::INVALID_SECTOR: return "INVALID_SECTOR";
    case ParseError::INVALID_DISTANCE: return "INVALID_DISTANCE";
    case ParseError::INVALID_HAZARD: return "INVALID_HAZARD";
  }
  return "UNKNOWN_ERROR";
}

const char* messageTypeName(MessageType type) {
  switch (type) {
    case MessageType::CLEAR: return "CLEAR";
    case MessageType::YELLOW: return "YELLOW";
    case MessageType::RED: return "RED";
    case MessageType::DEVICE_TEST: return "DEVICE_TEST";
    case MessageType::DISPLAY_TEST: return "DISPLAY_TEST";
    case MessageType::LED_TEST: return "LED_TEST";
  }
  return "UNKNOWN";
}

}  // namespace flagsense
