# Source Archive

Files here are excluded from normal firmware builds by `platformio.ini`.

Use this directory only for historical source snapshots that still need a
dedicated legacy env to compile. Fully retired experiments belong in
`robot/firmware/archive/`.

| File | Env | Reason |
|------|-----|--------|
| `integrated_main.cpp` | `esp32-s3-integrated_legacy` | Historical firmware-side DK-2500 integration snapshot; new burns use `robot/mergetesting` |
