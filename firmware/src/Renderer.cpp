#include "Renderer.h"

#include <Arduino.h>

#include "Display.h"
#include "HardwareConfig.h"
#include "LEDs.h"

namespace flagsense {

namespace {

LedPattern patternForState(SystemState state) {
  switch (state) {
    case SystemState::GREEN:
      return LedPattern::SOLID_GREEN;
    case SystemState::YELLOW:
      return LedPattern::SOLID_AMBER;
    case SystemState::DOUBLE_YELLOW:
      return LedPattern::PULSE_AMBER;
    case SystemState::SAFETY_CAR:
      return LedPattern::FLASH_AMBER;
    case SystemState::VSC:
      return LedPattern::STROBE_AMBER;
    case SystemState::RED:
      return LedPattern::FLASH_RED;
    default:
      return LedPattern::OFF;
  }
}

}  // namespace

void Renderer::begin() {
  state_.begin();
  lastState_ = SystemState::STARTING;
  ledsBegin();
  setStartupIndicator();
  displayBegin();
  renderStartup();
}

void Renderer::tick() {
  tickLeds();
  if (testActive_) {
    const unsigned long elapsed = millis() - testStart_;
    if (elapsed >= TEST_DISPLAY_MS) {
      testActive_ = false;
      renderCurrent();
    }
  }
  if (ledTestActive_) {
    const unsigned long elapsed = millis() - ledTestStart_;
    const uint8_t step = elapsed / TEST_LED_STEP_MS;
    if (step != ledTestStep_) {
      ledTestStep_ = step;
      if (step == 0)
        setGreen();
      else if (step == 1)
        setYellow();
      else if (step == 2)
        setRed();
      else {
        ledTestActive_ = false;
        renderCurrent();
      }
    }
  }
}

void Renderer::renderCurrent() {
  const SystemState current = state_.state();
  switch (current) {
    case SystemState::STARTING:
      setStartupIndicator();
      renderStartup();
      break;
    case SystemState::GREEN:
    case SystemState::YELLOW:
    case SystemState::DOUBLE_YELLOW:
    case SystemState::SAFETY_CAR:
    case SystemState::VSC:
    case SystemState::RED:
      setLedPattern(patternForState(current));
      renderFlagState(current, state_.incident());
      break;
    case SystemState::LINK_LOST:
      setLinkLostIndicator();
      renderLinkLost(state_.incident());
      break;
    case SystemState::ERROR:
      setErrorIndicator();
      renderError();
      break;
  }
}

void Renderer::handleMessage(const FlagMessage& message) {
  if (message.type == MessageType::DEVICE_TEST) {
    setStartupIndicator();
    renderDeviceTest();
    return;
  }
  if (message.type == MessageType::DISPLAY_TEST) {
    testActive_ = true;
    testStart_ = millis();
    renderDeviceTest();
    return;
  }
  if (message.type == MessageType::LED_TEST) {
    ledTestActive_ = true;
    ledTestStart_ = millis();
    ledTestStep_ = 0;
    setGreen();
    return;
  }
  if (state_.handleMessage(message)) renderCurrent();
}

void Renderer::setLinkLost(bool linkLost) {
  if (state_.setLinkLost(linkLost)) renderCurrent();
}

void Renderer::setError() {
  if (state_.setError()) renderCurrent();
}

SystemState Renderer::state() const { return state_.state(); }

}  // namespace flagsense
