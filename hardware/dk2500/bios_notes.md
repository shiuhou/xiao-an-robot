# DK2500 BIOS Notes

Record BIOS and firmware settings that affect deployment. Current values are not yet captured on the target device; fill this table during the DK-2500 setup pass.

| Setting | Current Value | Why It Matters | Check / Decision |
| --- | --- | --- | --- |
| Boot mode | Not recorded yet | Needed for predictable startup. | Confirm UEFI boot and target disk before installing demo image. |
| Secure Boot | Not recorded yet | May affect drivers, OpenVINO/NPU stack, or unsigned kernel modules. | Record whether it is enabled before troubleshooting driver load failures. |
| USB devices | Not recorded yet | Camera, microphone, keyboard, and debug peripherals. | Record which ports are stable for camera/mic during demo. |
| Power restore | Not recorded yet | Useful for unattended demos. | Decide whether auto power-on after AC restore is needed. |
| Virtualization / NPU related options | Not recorded yet | May affect model runtime or system diagnostics. | Record only after checking actual BIOS menus. |
