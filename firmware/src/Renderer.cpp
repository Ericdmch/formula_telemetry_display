#include "Renderer.h"

#include "Display.h"
#include "HardwareConfig.h"
#include "LEDs.h"

namespace flagsense {

void Renderer::begin() {
  allOff();
  renderStartup();
}

void Renderer::applyState(SystemState state, const FlagMessage& incident) {
  testActive_ = false;
  switch (state) {
    case SystemState::STARTING: allOff(); renderStartup(); break;
    case SystemState::CLEAR: setGreen(); renderClear(); break;
    case SystemState::YELLOW: setYellow(); renderIncident(state, incident); break;
    case SystemState::RED: setRed(); renderIncident(state, incident); break;
    case SystemState::LINK_LOST: renderLinkLost(incident); break;  // Preserve confirmed flag LED.
    case SystemState::ERROR: allOff(); renderError(); break;
  }
}

void Renderer::startTest(MessageType type, unsigned long now) {
  testType_ = type;
  testStarted_ = now;
  testPhase_ = -1;
  testActive_ = true;
  if (type == MessageType::DISPLAY_TEST) renderDisplayTest();
  if (type == MessageType::DEVICE_TEST) renderDeviceTest();
}

bool Renderer::tick(unsigned long now) {
  if (!testActive_) return false;
  if (testType_ == MessageType::DISPLAY_TEST) {
    if (now - testStarted_ >= TEST_DISPLAY_MS) { testActive_ = false; return true; }
    return false;
  }
  if (testType_ == MessageType::DEVICE_TEST) {
    const int phase = static_cast<int>((now - testStarted_) / TEST_LED_STEP_MS);
    if (phase != testPhase_) {
      testPhase_ = phase;
      if (phase == 0) setGreen();
      else if (phase == 1) setYellow();
      else if (phase == 2) setRed();
      else if (phase == 3) renderDisplayTest();
      else { testActive_ = false; return true; }
    }
    return false;
  }
  const int phase = static_cast<int>((now - testStarted_) / TEST_LED_STEP_MS);
  if (phase != testPhase_) {
    testPhase_ = phase;
    if (phase == 0) setGreen();
    else if (phase == 1) setYellow();
    else if (phase == 2) setRed();
    else { testActive_ = false; return true; }
  }
  return false;
}

}  // namespace flagsense
