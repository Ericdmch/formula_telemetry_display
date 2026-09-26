#include "StateMachine.h"

namespace flagsense {

void StateMachine::begin() {
  state_ = SystemState::STARTING;
  confirmedState_ = SystemState::STARTING;
  incident_ = FlagMessage{};
}

bool StateMachine::handleMessage(const FlagMessage& message) {
  if (!message.valid) return false;
  const SystemState oldState = state_;
  const FlagMessage oldIncident = incident_;
  switch (message.type) {
    case MessageType::CLEAR:
      state_ = SystemState::CLEAR;
      confirmedState_ = state_;
      incident_ = message;
      break;
    case MessageType::YELLOW:
      state_ = SystemState::YELLOW;
      confirmedState_ = state_;
      incident_ = message;
      break;
    case MessageType::RED:
      state_ = SystemState::RED;
      confirmedState_ = state_;
      incident_ = message;
      break;
    case MessageType::DEVICE_TEST:
    case MessageType::DISPLAY_TEST:
    case MessageType::LED_TEST:
      return false;
  }
  return oldState != state_ || oldIncident.type != incident_.type ||
         oldIncident.sector != incident_.sector ||
         oldIncident.distanceMeters != incident_.distanceMeters ||
         oldIncident.hazard != incident_.hazard ||
         oldIncident.valid != incident_.valid;
}

bool StateMachine::setLinkLost(bool linkLost) {
  if (linkLost) {
    if (state_ == SystemState::LINK_LOST || state_ == SystemState::ERROR) return false;
    state_ = SystemState::LINK_LOST;
    return true;
  } else if (state_ == SystemState::LINK_LOST) {
    state_ = confirmedState_;
    return true;
  }
  return false;
}

bool StateMachine::setError() {
  if (state_ == SystemState::ERROR) return false;
  state_ = SystemState::ERROR;
  return true;
}

const char* systemStateName(SystemState state) {
  switch (state) {
    case SystemState::STARTING: return "STARTING";
    case SystemState::CLEAR: return "CLEAR";
    case SystemState::YELLOW: return "YELLOW";
    case SystemState::RED: return "RED";
    case SystemState::LINK_LOST: return "LINK_LOST";
    case SystemState::ERROR: return "ERROR";
  }
  return "UNKNOWN";
}

}  // namespace flagsense
