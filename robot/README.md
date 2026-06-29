# Robot Firmware Areas

This directory has two firmware lines. Keep them separate.

## Main Integration Line

`robot/mergetesting` is the DK-2500/base-station integration firmware.

Use it for:

- WebSocket `/control`, `/video`, and `/audio`
- DK-2500/OpenClaw demo burns
- face expression + motion + speaker integration
- copying proven robot-body modules into the integration path

Start here:

- [mergetesting/README.md](mergetesting/README.md)
- [mergetesting/MAIN_DEMO.md](mergetesting/MAIN_DEMO.md)
- [../docs/current_status.md](../docs/current_status.md)
- [../docs/agents/03_mergetesting_registry.md](../docs/agents/03_mergetesting_registry.md)

## Bring-Up Lab

`robot/firmware` is the robot-body bring-up and reusable-module lab.

Use it for:

- single-peripheral tests
- motor, display, camera, mic, and speaker validation
- reusable module development before copying the minimum proven code into `robot/mergetesting`
- isolated PlatformIO envs selected by `build_src_filter`

Start here:

- [firmware/README.md](firmware/README.md)
- [firmware/platformio.ini](firmware/platformio.ini)
- [../docs/agents/02_firmware_registry.md](../docs/agents/02_firmware_registry.md)

## Boundary Rule

Do not add new DK-2500 `/control`, `/video`, or `/audio` integration entrypoints to `robot/firmware`.

If integration needs a robot feature:

1. Validate the feature in `robot/firmware`.
2. Copy or sync the minimal proven module into `robot/mergetesting`.
3. Keep the DK-2500 loop in `robot/mergetesting`.

Historical firmware-side integration code remains legacy only.
