#pragma once

#include "FlagMessage.h"

namespace flagsense {

enum class SystemState : uint8_t { STARTING, CLEAR, YELLOW, RED, LINK_LOST, ERROR };

class StateMachine {
 public:
  void begin();
  bool handleMessage(const FlagMessage& message);
  bool setLinkLost(bool linkLost);
  bool setError();
  SystemState state() const { return state_; }
  const FlagMessage& incident() const { return incident_; }

 private:
  SystemState state_ = SystemState::STARTING;
  SystemState confirmedState_ = SystemState::STARTING;
  FlagMessage incident_{};
};

const char* systemStateName(SystemState state);

}  // namespace flagsense
