"""Common WebSocket message type constants.

The string values should match docs/protocol/protocol.md and
robot/firmware/src/protocol.h.
"""

DEVICE_HELLO = "device.hello"
DEVICE_HEARTBEAT = "device.heartbeat"
SENSOR_BUTTON = "sensor.button"
SENSOR_DOCK_STATUS = "sensor.dock_status"
MOTION_EXECUTE = "motion.execute"
MOTION_COMPLETED = "motion.completed"
DISPLAY_EXPRESSION = "display.expression"
ERROR_REPORT = "error.report"
SYSTEM_WELCOME = "system.welcome"
AUDIO_PLAY_TTS = "audio.play_tts"
AUDIO_PLAY_LOCAL = "audio.play_local"
CONFIG_UPDATE = "config.update"
SYSTEM_SHUTDOWN = "system.shutdown"
