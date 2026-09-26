#pragma once

#include "FlagMessage.h"
#include "StateMachine.h"

namespace flagsense {

class Renderer {
 public:
  void begin();
  void applyState(SystemState state, const FlagMessage& incident);
  void startTest(MessageType type, unsigned long now);
  bool tick(unsigned long now);

 private:
  MessageType testType_ = MessageType::CLEAR;
  bool testActive_ = false;
  unsigned long testStarted_ = 0;
  int testPhase_ = -1;
};

}  // namespace flagsense
