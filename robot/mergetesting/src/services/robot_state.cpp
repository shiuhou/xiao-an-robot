#include "services/robot_state.h"

namespace {

const char* fallback(const char* value, const char* fallbackValue) {
  return value && value[0] ? value : fallbackValue;
}

}  // namespace

const char* RobotState::expression() const {
  return _expression.c_str();
}

const char* RobotState::motion() const {
  return _motion.c_str();
}

const char* RobotState::camera() const {
  return _camera.c_str();
}

bool RobotState::isBusy() const {
  return _busy;
}

bool RobotState::isDocked() const {
  return _docked;
}

bool RobotState::isWifiConnected() const {
  return _wifiConnected;
}

bool RobotState::isControlConnected() const {
  return _controlConnected;
}

bool RobotState::isVideoConnected() const {
  return _videoConnected;
}

bool RobotState::isAudioConnected() const {
  return _audioConnected;
}

void RobotState::setExpression(const char* expression) {
  _expression = fallback(expression, Expression::NEUTRAL);
}

void RobotState::setMotion(const char* motion) {
  _motion = fallback(motion, "idle");
}

void RobotState::setCamera(const char* camera) {
  _camera = fallback(camera, "cam_off");
}

void RobotState::setCameraReady(bool ready) {
  _camera = ready ? "cam_ok" : "cam_err";
}

void RobotState::setCameraOff() {
  _camera = "cam_off";
}

void RobotState::setBusy(bool busy) {
  _busy = busy;
}

void RobotState::setDocked(bool docked) {
  _docked = docked;
}

void RobotState::setWifiConnected(bool connected) {
  _wifiConnected = connected;
}

void RobotState::setControlConnected(bool connected) {
  _controlConnected = connected;
}

void RobotState::setVideoConnected(bool connected) {
  _videoConnected = connected;
}

void RobotState::setAudioConnected(bool connected) {
  _audioConnected = connected;
}
