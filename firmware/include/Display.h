#pragma once

#include "FlagMessage.h"
#include "StateMachine.h"

namespace flagsense {

bool displayBegin();
void renderStartup();
void renderClear();
void renderIncident(SystemState state, const FlagMessage& message);
void renderDeviceTest();
void renderDisplayTest();
void renderLinkLost(const FlagMessage& lastConfirmed);
void renderError();

}  // namespace flagsense
