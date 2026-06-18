param(
    [string]$Port = "COM19",
    [int]$Baud = 115200
)

$ErrorActionPreference = "Stop"

$serial = [System.IO.Ports.SerialPort]::new($Port, $Baud, [System.IO.Ports.Parity]::None, 8, [System.IO.Ports.StopBits]::One)
$serial.ReadTimeout = 20
$serial.WriteTimeout = 200
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$serial.Open()
$serial.DtrEnable = $false
$serial.RtsEnable = $false

try {
    Write-Host "Motor keyboard control on $Port @ $Baud"
    Write-Host "W/A/S/D drive, X or Space stop, +/- speed, G bench test, ? help, Esc quit."
    Write-Host "Keep wheels lifted until direction is confirmed."

    while ($true) {
        if ($serial.BytesToRead -gt 0) {
            $text = $serial.ReadExisting()
            if ($text.Length -gt 0) {
                Write-Host -NoNewline $text
            }
        }

        if ([Console]::KeyAvailable) {
            $key = [Console]::ReadKey($true)

            if ($key.Key -eq [ConsoleKey]::Escape) {
                $serial.Write("x")
                Write-Host "`nExit requested. Sent stop."
                break
            }

            $ch = $key.KeyChar
            if ("wasdWASDxX +-_=gG?hH".IndexOf($ch) -ge 0) {
                $serial.Write([string]$ch)
                Write-Host "`n[PC] sent '$ch'"
            }
        }

        Start-Sleep -Milliseconds 20
    }
}
finally {
    if ($serial.IsOpen) {
        $serial.Write("x")
        Start-Sleep -Milliseconds 50
        $serial.Close()
    }
}
