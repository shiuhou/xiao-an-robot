$ErrorActionPreference = "Stop"
& "$PSScriptRoot\probes\serial_camera_viewer.ps1" @args
exit $LASTEXITCODE