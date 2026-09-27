#pragma once

#include <stdint.h>
#include "FlagMessage.h"
#include "StateMachine.h"

namespace flagsense {
bool displayBegin();
void renderStartup();
void renderDeviceTest();
// Unified flag renderer: line 1 is the flag label, line 2 is the sender's
// context when present, otherwise a derivation from the real evidence
// (sector / distance / hazard) or "Track clear" for green.
void renderFlagState(SystemState state, const FlagMessage& message);
void renderLinkLost(const FlagMessage& lastConfirmed);
void renderError();
}  // namespace flagsense
