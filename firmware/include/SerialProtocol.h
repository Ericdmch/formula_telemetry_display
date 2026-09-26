#pragma once

#include <stddef.h>
#include "FlagMessage.h"

namespace flagsense {

constexpr size_t MAX_MESSAGE_LENGTH = 128;

// The protocol leaves track sector numbering/range open. Configure these for
// the chosen circuit; the default accepts positive, representable sectors.
struct SectorRange {
  int min = 1;
  int max = 2147483647;
};

ParseResult parseMessage(const char* input, SectorRange sectors = {});
const char* parseErrorName(ParseError error);
const char* messageTypeName(MessageType type);

// Returns one completed non-empty line at a time, without its CR/LF. An
// oversized line is discarded through newline and returned as an error once.
class LineFramer {
 public:
  bool push(char byte, char* output, size_t outputCapacity,
            ParseError& error);

 private:
  char buffer_[MAX_MESSAGE_LENGTH + 1] = {};
  size_t length_ = 0;
  bool discarding_ = false;
};

}  // namespace flagsense
