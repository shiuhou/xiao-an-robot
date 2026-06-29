# OpenFace OV Runtime

This directory is a bundled OpenFace/OpenVINO runtime, not normal Xiao-An
application code.

It contains:

- `ov_perceive.py` and `ov_runner.py`, the local OpenVINO perception bridge.
- `Pytorch_Retinaface/`, vendored RetinaFace decode utilities.
- `STAR/`, vendored STAR landmark utilities.

## Do Not Move Casually

`base_station/perception/openface_ov_adapter.py` expects this directory at:

```text
base_station/perception/openface_ov_runtime
```

At runtime, `ov_perceive.py` also inserts this directory, `Pytorch_Retinaface/`,
and `STAR/` into `sys.path`, then imports modules such as:

```text
ov_runner
Pytorch_Retinaface.*
STAR.demo
```

Moving or renaming this directory requires an import-path audit and OpenFace
verification. Keep it in place during ordinary repo cleanup.

## Models

The OpenVINO IR model files live outside this runtime under:

```text
base_station/models/openface_ov/
```

See `base_station/models/README.md` and `docs/setup/device_setup.md` for model
placement and setup notes.
