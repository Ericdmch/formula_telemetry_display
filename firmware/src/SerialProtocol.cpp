#include "SerialProtocol.h"

#include <limits.h>
#include <stdint.h>
#include <string.h>

namespace flagsense {

namespace {

struct Keyword {
  const char* name;
  MessageType type;
};

constexpr Keyword MESSAGE_KEYWORDS[] = {
    {"CLEAR", MessageType::CLEAR},        // legacy alias -> GREEN
    {"GREEN", MessageType::GREEN},
    {"YELLOW", MessageType::YELLOW},
    {"DOUBLE_YELLOW", MessageType::DOUBLE_YELLOW},
    {"SAFETY_CAR", MessageType::SAFETY_CAR},
    {"VSC", MessageType::VSC},
    {"RED", MessageType::RED},
    {"DEVICE_TEST", MessageType::DEVICE_TEST},
    {"DISPLAY_TEST", MessageType::DISPLAY_TEST},
    {"LED_TEST", MessageType::LED_TEST},
};

struct HazardKeyword {
  const char* name;
  HazardType type;
};

constexpr HazardKeyword HAZARD_KEYWORDS[] = {
    {"STOPPED_CAR", HazardType::STOPPED_CAR},
    {"CRASH", HazardType::CRASH},
    {"TRACK_BLOCKED", HazardType::TRACK_BLOCKED},
    {"DEBRIS", HazardType::DEBRIS},
    {"SPIN", HazardType::SPIN},
    {"SLOW_CAR", HazardType::SLOW_CAR},
    {"MULTI_CAR_INCIDENT", HazardType::MULTI_CAR_INCIDENT},
    {"OFF_TRACK", HazardType::OFF_TRACK},
    {"UNKNOWN_HAZARD", HazardType::UNKNOWN_HAZARD},
    {"SESSION_STOPPED", HazardType::SESSION_STOPPED},
};

bool parseInteger(const char* text, int32_t& value) {
  if (text[0] == '\0') return false;
  size_t start = 0;
  if (text[0] == '-') start = 1;
  if (text[start] == '\0') return false;
  for (size_t i = start; text[i] != '\0'; ++i) {
    if (text[i] < '0' || text[i] > '9') return false;
  }
  long parsed = strtol(text, nullptr, 10);
  if (parsed < INT32_MIN || parsed > INT32_MAX) return false;
  value = static_cast<int32_t>(parsed);
  return true;
}

bool parseUnsigned(const char* text, uint32_t& value) {
  if (text[0] == '\0') return false;
  for (size_t i = 0; text[i] != '\0'; ++i) {
    if (text[i] < '0' || text[i] > '9') return false;
  }
  unsigned long parsed = strtoul(text, nullptr, 10);
  if (parsed > UINT32_MAX) return false;
  value = static_cast<uint32_t>(parsed);
  return true;
}

// Splits `input` on commas into fields, keeping the extended tail (context)
// verbatim as fields[6]. Returns the field count, or 0 when the line has
// more than 7 comma-separated fields.
size_t splitFields(char* input, char* fields[7]) {
  size_t count = 0;
  fields[count++] = input;
  for (char* p = input; *p != '\0'; ++p) {
    if (*p == ',') {
      *p = '\0';
      if (count >= 7) return 0;
      fields[count++] = p + 1;
    }
  }
  return count;
}

}  // namespace

const char* parseErrorName(ParseError error) {
  switch (error) {
    case ParseError::NONE:
      return "NONE";
    case ParseError::EMPTY_MESSAGE:
      return "EMPTY_MESSAGE";
    case ParseError::MESSAGE_TOO_LONG:
      return "MESSAGE_TOO_LONG";
    case ParseError::UNKNOWN_COMMAND:
      return "UNKNOWN_COMMAND";
    case ParseError::WRONG_FIELD_COUNT:
      return "WRONG_FIELD_COUNT";
    case ParseError::INVALID_SECTOR:
      return "INVALID_SECTOR";
    case ParseError::INVALID_DISTANCE:
      return "INVALID_DISTANCE";
    case ParseError::INVALID_HAZARD:
      return "INVALID_HAZARD";
    case ParseError::INVALID_CAR_ID:
      return "INVALID_CAR_ID";
    case ParseError::INVALID_SEQ:
      return "INVALID_SEQ";
  }
  return "UNKNOWN";
}

const char* messageTypeName(MessageType type) {
  switch (type) {
    case MessageType::CLEAR:
      return "CLEAR";
    case MessageType::GREEN:
      return "GREEN";
    case MessageType::YELLOW:
      return "YELLOW";
    case MessageType::DOUBLE_YELLOW:
      return "DOUBLE_YELLOW";
    case MessageType::SAFETY_CAR:
      return "SAFETY_CAR";
    case MessageType::VSC:
      return "VSC";
    case MessageType::RED:
      return "RED";
    case MessageType::DEVICE_TEST:
      return "DEVICE_TEST";
    case MessageType::DISPLAY_TEST:
      return "DISPLAY_TEST";
    case MessageType::LED_TEST:
      return "LED_TEST";
  }
  return "UNKNOWN";
}

ParseResult parseMessage(const char* input, SectorRange sectors) {
  ParseResult result;
  if (input == nullptr || input[0] == '\0') {
    result.error = ParseError::EMPTY_MESSAGE;
    return result;
  }
  if (strlen(input) > MAX_MESSAGE_LENGTH) {
    result.error = ParseError::MESSAGE_TOO_LONG;
    return result;
  }

  char working[MAX_MESSAGE_LENGTH + 1];
  strncpy(working, input, sizeof(working));
  working[sizeof(working) - 1] = '\0';
  char* fields[7] = {};
  const size_t fieldCount = splitFields(working, fields);
  if (fieldCount == 0) {
    result.error = ParseError::WRONG_FIELD_COUNT;
    return result;
  }

  bool isTestCommand = false;
  for (const Keyword& keyword : MESSAGE_KEYWORDS) {
    if (strcmp(fields[0], keyword.name) == 0) {
      result.message.type = keyword.type;
      if (keyword.type == MessageType::DEVICE_TEST ||
          keyword.type == MessageType::DISPLAY_TEST ||
          keyword.type == MessageType::LED_TEST) {
        isTestCommand = true;
      }
      break;
    }
  }
  bool keywordMatched = (result.message.type != MessageType::CLEAR) ||
                        strcmp(fields[0], "CLEAR") == 0;
  if (!keywordMatched) {
    result.error = ParseError::UNKNOWN_COMMAND;
    return result;
  }

  const bool singleField = (fieldCount == 1);
  const bool extended = (fieldCount == 7);
  if (singleField) {
    result.success = true;
    result.message.valid = true;
    result.error = ParseError::NONE;
    return result;
  }
  if (isTestCommand) {
    result.error = ParseError::WRONG_FIELD_COUNT;
    return result;
  }
  if (fieldCount != 4 && !extended) {
    result.error = ParseError::WRONG_FIELD_COUNT;
    return result;
  }

  int32_t sector = 0;
  if (!parseInteger(fields[1], sector) || sector < sectors.min ||
      sector > sectors.max) {
    result.error = ParseError::INVALID_SECTOR;
    return result;
  }
  int32_t distance = 0;
  if (!parseInteger(fields[2], distance) || distance < 0) {
    result.error = ParseError::INVALID_DISTANCE;
    return result;
  }
  HazardType hazard = HazardType::INVALID;
  for (const HazardKeyword& keyword : HAZARD_KEYWORDS) {
    if (strcmp(fields[3], keyword.name) == 0) {
      hazard = keyword.type;
      break;
    }
  }
  if (hazard == HazardType::INVALID) {
    result.error = ParseError::INVALID_HAZARD;
    return result;
  }

  result.message.sector = sector;
  result.message.distanceMeters = distance;
  result.message.hazard = hazard;

  if (extended) {
    uint32_t carId = 0;
    if (!parseUnsigned(fields[4], carId) || carId > 9999) {
      result.error = ParseError::INVALID_CAR_ID;
      return result;
    }
    uint32_t seq = 0;
    if (!parseUnsigned(fields[5], seq)) {
      result.error = ParseError::INVALID_SEQ;
      return result;
    }
    result.message.carId = static_cast<uint16_t>(carId);
    result.message.seq = seq;
    strncpy(result.message.context, fields[6], CONTEXT_MAX_CHARS);
    result.message.context[CONTEXT_MAX_CHARS] = '\0';
  }

  result.success = true;
  result.message.valid = true;
  result.error = ParseError::NONE;
  return result;
}

bool LineFramer::push(char byte, char* output, size_t outputCapacity,
                      ParseError& error) {
  error = ParseError::NONE;
  if (byte == '\r' || byte == '\n') {
    if (discarding_) {
      discarding_ = false;
      length_ = 0;
      error = ParseError::MESSAGE_TOO_LONG;
      return true;
    }
    if (length_ == 0) return false;
    if (outputCapacity < length_ + 1) {
      length_ = 0;
      error = ParseError::MESSAGE_TOO_LONG;
      return true;
    }
    memcpy(output, buffer_, length_);
    output[length_] = '\0';
    length_ = 0;
    return true;
  }
  if (discarding_) return false;
  if (length_ < MAX_MESSAGE_LENGTH) {
    buffer_[length_++] = byte;
    return false;
  }
  discarding_ = true;
  return false;
}

}  // namespace flagsense
