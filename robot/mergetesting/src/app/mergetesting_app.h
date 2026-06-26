#pragma once

#include "cam_stream.h"
#include "mic_stream.h"
#include "motor_ctrl.h"
#include "services/command_router.h"
#include "services/motion_service.h"
#include "services/robot_state.h"
#include "services/status_service.h"
#include "ws_client.h"

class MergetestingApp {
public:
  MergetestingApp();

  void setup();
  void loop();

private:
  WSClient _wsClient;
  MotorController _motor;
  CamStream _cam;
  MicStream _mic;
  RobotState _state;
  StatusService _status;
  MotionService _motion;
  CommandRouter _router;

#if ENABLE_ARDUINO_OTA
  bool _otaStarted = false;
#endif

  void holdMotorPinsLowBeforeSerial();
  void setupOtaIfReady();
  void pollOta();
  void connectWiFi();
  void maintainWiFi();
  void pollSerialMockAsr();
  void updateTransportState();
};
