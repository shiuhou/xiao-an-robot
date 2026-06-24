# Motor Driver

Current motor driver target: **DRV8833 dual H-bridge** driving two N20 gear motors.

## Wiring

| DRV8833 Side | Driver Pin | ESP32-S3 GPIO | Firmware Constant |
| --- | --- | ---: | --- |
| Left | IN1 | GPIO1 | `PIN_MOTOR_L_IN1` |
| Left | IN2 | GPIO2 | `PIN_MOTOR_L_IN2` |
| Right | IN1 | GPIO3 | `PIN_MOTOR_R_IN1` |
| Right | IN2 | GPIO48 | `PIN_MOTOR_R_IN2` |

Limit switches are intentionally disabled during bench bring-up:

```cpp
PIN_LIMIT_FRONT = -1
PIN_LIMIT_BACK = -1
```

Assign real GPIOs only after motor direction and dock mechanics are verified.

## Firmware Envs

Run from `robot/firmware`:

```powershell
pio run -e motor_bench_once
pio run -e motor_manual
pio run -e motor_wifi_manual
pio run -e motor_cam_wifi_manual
```

## Test Checklist

- Raise the chassis or remove wheels before the first powered test.
- Confirm GPIO1/GPIO2 move the left wheel and GPIO3/GPIO48 move the right wheel.
- Confirm forward and backward direction for both wheels.
- Confirm `stop` cuts all four motor outputs.
- Confirm browser control deadman timeout stops the robot if commands stop arriving.
- Check driver temperature after repeated forward/back/turn pulses.
- Record final motor voltage, battery rail, and measured current in [power.md](power.md).

## Direction Fix Rules

- Correct wheel, wrong direction: flip `MOTOR_LEFT_FORWARD_USES_IN1` or `MOTOR_RIGHT_FORWARD_USES_IN1` in `robot/firmware/src/motor_ctrl.h`.
- Wrong physical wheel: change the `PIN_MOTOR_*` mapping.
- Motor does not stop: disconnect power, then inspect DRV8833 input wiring before another test.
