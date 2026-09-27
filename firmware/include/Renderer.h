#pragma once

#include "FlagMessage.h"
#include "StateMachine.h"

namespace flagsense {

class Renderer {
 public:
  void begin();
  void tick();
  void renderCurrent();
  void handleMessage(const FlagMessage& message);
  void setLinkLost(bool linkLost);
  void setError();
  SystemState state() const;

 private:
  StateMachine state_;
  SystemState lastState_ = SystemState::STARTING;
  bool testActive_ = false;
  unsigned long testStart_ = 0;
  bool ledTestActive_ = false;
  unsigned long ledTestStart_ = 0;
  uint8_t ledTestStep_ = 0;
};

}  // namespace flagsense
