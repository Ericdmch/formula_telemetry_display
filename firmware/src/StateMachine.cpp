#include "StateMachine.h"

#include <string.h>

namespace flagsense {

namespace {

SystemState messageToState(MessageType type) {
  switch (type) {
    case MessageType::CLEAR:
    case MessageType::GREEN:
      return SystemState::GREEN;
    case MessageType::YELLOW:
      return SystemState::YELLOW;
    case MessageType::DOUBLE_YELLOW:
      return SystemState::DOUBLE_YELLOW;
    case MessageType::SAFETY_CAR:
      return SystemState::SAFETY_CAR;
    case MessageType::VSC:
      return SystemState::VSC;
    case MessageType::RED:
      return SystemState::RED;
    default:
      return SystemState::STARTING;
  }
}

}  // namespace

void StateMachine::begin() {
  state_ = SystemState::STARTING;
  confirmedState_ = SystemState::STARTING;
  incident_ = FlagMessage{};
}

bool StateMachine::handleMessage(const FlagMessage& message) {
  if (!message.valid) return false;
  switch (message.type) {
    case MessageType::DEVICE_TEST:
    case MessageType::DISPLAY_TEST:
    case MessageType::LED_TEST:
      return false;
    default:
      break;
  }
  const SystemState newState = messageToState(message.type);
  const SystemState oldState = state_;
  // A changed flag, or new evidence for the same flag, is a real change.
  // The sender's seq counter increments every heartbeat, so it is
  // deliberately excluded: counting it would restart the LED pattern and
  // re-render the LCD every ~3 s.
  const bool changed =
      newState != oldState || incident_.type != message.type ||
      incident_.sector != message.sector ||
      incident_.distanceMeters != message.distanceMeters ||
      incident_.hazard != message.hazard || incident_.carId != message.carId ||
      strcmp(incident_.context, message.context) != 0;
  confirmedState_ = newState;
  state_ = newState;
  incident_ = message;
  return changed;
}

bool StateMachine::setLinkLost(bool linkLost) {
  if (linkLost) {
    if (state_ == SystemState::LINK_LOST || state_ == SystemState::ERROR) {
      return false;
    }
    state_ = SystemState::LINK_LOST;
    return true;
  }
  if (state_ != SystemState::LINK_LOST) return false;
  state_ = confirmedState_;
  return true;
}

bool StateMachine::setError() {
  if (state_ == SystemState::ERROR) return false;
  state_ = SystemState::ERROR;
  return true;
}

const char* systemStateName(SystemState state) {
  switch (state) {
    case SystemState::STARTING:
      return "STARTING";
    case SystemState::GREEN:
      return "GREEN";
    case SystemState::YELLOW:
      return "YELLOW";
    case SystemState::DOUBLE_YELLOW:
      return "DOUBLE_YELLOW";
    case SystemState::SAFETY_CAR:
      return "SAFETY_CAR";
    case SystemState::VSC:
      return "VSC";
    case SystemState::RED:
      return "RED";
    case SystemState::LINK_LOST:
      return "LINK_LOST";
    case SystemState::ERROR:
      return "ERROR";
  }
  return "UNKNOWN";
}

}  // namespace flagsense
