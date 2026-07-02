param(
    [string]$Port,
    [int]$Baud = 921600,
    [int]$TimeoutMs = 500,
    [int]$StartupDelayMs = 2500,
    [int]$TrackEvery = 4,
    [int]$TrackSampleStep = 8,
    [ValidateSet("QR", "Red", "None")]
    [string]$Mode = "QR",
    [switch]$NoTracking,
    [switch]$VerboseLog,
    [switch]$ResetOnOpen
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$Magic = [byte[]][char[]]"XAN1"
$MaxFrameBytes = 262144
$FrameRequest = [byte][char]'F'
$SampleStep = [Math]::Max(2, $TrackSampleStep)
$MinRedPixels = 70
$MinBoxSizePx = 10
$MaxBoxWidthPx = 150
$MaxBoxHeightPx = 150
$BoxPadPx = 2
$MinQrDarkPixels = 80
$MinQrSizePx = 36
$MaxQrSizePx = 220
$QrAspectTolerance = 0.45

function Select-SerialPort {
    param([string]$RequestedPort)

    if ($RequestedPort) {
        return $RequestedPort
    }

    $ports = [System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object
    if ($ports.Count -eq 0) {
        throw "No serial ports found. Check the ESP32 USB cable."
    }

    if ($ports.Count -eq 1) {
        Write-Host "Using $($ports[0])"
        return $ports[0]
    }

    Write-Host "Available serial ports:"
    for ($i = 0; $i -lt $ports.Count; $i++) {
        Write-Host ("  [{0}] {1}" -f ($i + 1), $ports[$i])
    }

    while ($true) {
        $choice = (Read-Host "Select index or COM port, e.g. 2 or COM19").Trim()
        $index = 0
        if ([int]::TryParse($choice, [ref]$index) -and $index -ge 1 -and $index -le $ports.Count) {
            return $ports[$index - 1]
        }

        $normalized = $choice.ToUpperInvariant()
        if ($normalized -match '^\d+$') {
            $normalized = "COM$normalized"
        }
        foreach ($port in $ports) {
            if ($port.ToUpperInvariant() -eq $normalized) {
                return $port
            }
        }
        Write-Host "Invalid choice."
    }
}

function Read-Exact {
    param(
        [System.IO.Ports.SerialPort]$Serial,
        [int]$Count
    )

    $buffer = New-Object byte[] $Count
    $offset = 0
    while ($offset -lt $Count) {
        $read = $Serial.Read($buffer, $offset, $Count - $offset)
        if ($read -le 0) {
            throw "Serial read timeout"
        }
        $offset += $read
    }
    return $buffer
}

function Read-Frame {
    param([System.IO.Ports.SerialPort]$Serial)

    $matched = 0
    while ($matched -lt $Magic.Length) {
        $b = $Serial.ReadByte()
        if ($b -lt 0) {
            throw "Waiting for frame magic"
        }

        if ([byte]$b -eq $Magic[$matched]) {
            $matched++
        } else {
            $matched = 0
            if ([byte]$b -eq $Magic[0]) {
                $matched = 1
            }
        }
    }

    $lenBytes = Read-Exact -Serial $Serial -Count 4
    $length = [BitConverter]::ToUInt32($lenBytes, 0)
    if ($length -le 0 -or $length -gt $MaxFrameBytes) {
        throw "Invalid frame length: $length"
    }

    return Read-Exact -Serial $Serial -Count ([int]$length)
}

function Request-Frame {
    param([System.IO.Ports.SerialPort]$Serial)

    $Serial.Write([byte[]]@($FrameRequest), 0, 1)
}

function Test-RedPixel {
    param([System.Drawing.Color]$Color)

    $r = [int]$Color.R
    $g = [int]$Color.G
    $b = [int]$Color.B
    $max = [Math]::Max($r, [Math]::Max($g, $b))
    $min = [Math]::Min($r, [Math]::Min($g, $b))

    return $r -gt 145 -and
           $g -lt 95 -and
           $b -lt 95 -and
           ($max - $min) -gt 80 -and
           $r -gt ($g + 70) -and
           $r -gt ($b + 65)
}

function Find-RedBox {
    param([System.Drawing.Bitmap]$Bitmap)

    $xMin = $Bitmap.Width
    $yMin = $Bitmap.Height
    $xMax = 0
    $yMax = 0
    $pixels = 0

    for ($y = 0; $y -lt $Bitmap.Height; $y += $SampleStep) {
        for ($x = 0; $x -lt $Bitmap.Width; $x += $SampleStep) {
            if (Test-RedPixel -Color $Bitmap.GetPixel($x, $y)) {
                if ($x -lt $xMin) { $xMin = $x }
                if ($y -lt $yMin) { $yMin = $y }
                if ($x -gt $xMax) { $xMax = $x }
                if ($y -gt $yMax) { $yMax = $y }
                $pixels++
            }
        }
    }

    $width = $xMax - $xMin + 1
    $height = $yMax - $yMin + 1
    if ($pixels -lt $MinRedPixels -or
        $width -lt $MinBoxSizePx -or
        $height -lt $MinBoxSizePx -or
        $width -gt $MaxBoxWidthPx -or
        $height -gt $MaxBoxHeightPx) {
        return $null
    }

    $xMin = [Math]::Max(0, $xMin - $BoxPadPx)
    $yMin = [Math]::Max(0, $yMin - $BoxPadPx)
    $xMax = [Math]::Min($Bitmap.Width - 1, $xMax + $BoxPadPx)
    $yMax = [Math]::Min($Bitmap.Height - 1, $yMax + $BoxPadPx)
    $centerX = [int](($xMin + $xMax) / 2)
    $centerY = [int](($yMin + $yMax) / 2)

    [pscustomobject]@{
        X = $xMin
        Y = $yMin
        Width = $xMax - $xMin + 1
        Height = $yMax - $yMin + 1
        CenterX = $centerX
        CenterY = $centerY
        Dx = $centerX - [int]($Bitmap.Width / 2)
        Dy = $centerY - [int]($Bitmap.Height / 2)
        Pixels = $pixels
    }
}

function Test-DarkPixel {
    param([System.Drawing.Color]$Color)

    $r = [int]$Color.R
    $g = [int]$Color.G
    $b = [int]$Color.B
    $max = [Math]::Max($r, [Math]::Max($g, $b))
    $min = [Math]::Min($r, [Math]::Min($g, $b))
    $brightness = ($r + $g + $b) / 3

    return $brightness -lt 85 -and ($max - $min) -lt 55
}

function Test-WhitePixel {
    param([System.Drawing.Color]$Color)

    return ([int]$Color.R + [int]$Color.G + [int]$Color.B) / 3 -gt 150
}

function Find-QrBox {
    param([System.Drawing.Bitmap]$Bitmap)

    $xMin = $Bitmap.Width
    $yMin = $Bitmap.Height
    $xMax = 0
    $yMax = 0
    $darkPixels = 0

    # First pass: find the bounding box of dark, neutral pixels. This is a
    # lightweight QR target tracker, not a QR decoder.
    for ($y = 0; $y -lt $Bitmap.Height; $y += $SampleStep) {
        for ($x = 0; $x -lt $Bitmap.Width; $x += $SampleStep) {
            if (Test-DarkPixel -Color $Bitmap.GetPixel($x, $y)) {
                if ($x -lt $xMin) { $xMin = $x }
                if ($y -lt $yMin) { $yMin = $y }
                if ($x -gt $xMax) { $xMax = $x }
                if ($y -gt $yMax) { $yMax = $y }
                $darkPixels++
            }
        }
    }

    $width = $xMax - $xMin + 1
    $height = $yMax - $yMin + 1
    if ($darkPixels -lt $MinQrDarkPixels -or
        $width -lt $MinQrSizePx -or
        $height -lt $MinQrSizePx -or
        $width -gt $MaxQrSizePx -or
        $height -gt $MaxQrSizePx) {
        return $null
    }

    $ratio = $width / [double]$height
    if ([Math]::Abs($ratio - 1.0) -gt $QrAspectTolerance) {
        return $null
    }

    # Confirm that the candidate contains both black modules and white gaps.
    $whitePixels = 0
    $insideSamples = 0
    for ($y = $yMin; $y -le $yMax; $y += $SampleStep) {
        for ($x = $xMin; $x -le $xMax; $x += $SampleStep) {
            $insideSamples++
            if (Test-WhitePixel -Color $Bitmap.GetPixel($x, $y)) {
                $whitePixels++
            }
        }
    }
    if ($insideSamples -le 0 -or $whitePixels -lt [Math]::Max(20, [int]($insideSamples * 0.15))) {
        return $null
    }

    $xMin = [Math]::Max(0, $xMin - $BoxPadPx)
    $yMin = [Math]::Max(0, $yMin - $BoxPadPx)
    $xMax = [Math]::Min($Bitmap.Width - 1, $xMax + $BoxPadPx)
    $yMax = [Math]::Min($Bitmap.Height - 1, $yMax + $BoxPadPx)
    $centerX = [int](($xMin + $xMax) / 2)
    $centerY = [int](($yMin + $yMax) / 2)

    [pscustomobject]@{
        X = $xMin
        Y = $yMin
        Width = $xMax - $xMin + 1
        Height = $yMax - $yMin + 1
        CenterX = $centerX
        CenterY = $centerY
        Dx = $centerX - [int]($Bitmap.Width / 2)
        Dy = $centerY - [int]($Bitmap.Height / 2)
        Pixels = $darkPixels
    }
}

function Draw-TrackingOverlay {
    param(
        [System.Drawing.Bitmap]$Bitmap,
        $Box,
        [string]$Label
    )

    $graphics = [System.Drawing.Graphics]::FromImage($Bitmap)
    $font = [System.Drawing.Font]::new("Consolas", 12, [System.Drawing.FontStyle]::Bold)
    $greenPen = [System.Drawing.Pen]::new([System.Drawing.Color]::Lime, 3)
    $whitePen = [System.Drawing.Pen]::new([System.Drawing.Color]::White, 2)
    $blackBrush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::Black)
    $whiteBrush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::White)

    try {
        $graphics.FillRectangle($blackBrush, 4, 4, 210, 46)
        if ($Box) {
            $graphics.DrawRectangle($greenPen, $Box.X, $Box.Y, $Box.Width, $Box.Height)
            $graphics.DrawLine($whitePen, $Box.CenterX - 8, $Box.CenterY, $Box.CenterX + 8, $Box.CenterY)
            $graphics.DrawLine($whitePen, $Box.CenterX, $Box.CenterY - 8, $Box.CenterX, $Box.CenterY + 8)
            $graphics.DrawString(("X:{0:D3} Y:{1:D3}" -f $Box.CenterX, $Box.CenterY), $font, $whiteBrush, 10, 7)
            $graphics.DrawString(("DX:{0:+000;-000;+000} DY:{1:+000;-000;+000}" -f $Box.Dx, $Box.Dy), $font, $whiteBrush, 10, 27)
        } else {
            $graphics.DrawString("NO $Label", $font, $whiteBrush, 10, 14)
        }
    } finally {
        $greenPen.Dispose()
        $whitePen.Dispose()
        $blackBrush.Dispose()
        $whiteBrush.Dispose()
        $font.Dispose()
        $graphics.Dispose()
    }
}

function Draw-StatusFrame {
    param(
        [System.Windows.Forms.PictureBox]$Picture,
        [string]$Text
    )

    $bitmap = [System.Drawing.Bitmap]::new(640, 360)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $font = [System.Drawing.Font]::new("Consolas", 16, [System.Drawing.FontStyle]::Bold)
    $brush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::White)
    try {
        $graphics.Clear([System.Drawing.Color]::Black)
        $graphics.DrawString($Text, $font, $brush, 20, 20)
    } finally {
        $brush.Dispose()
        $font.Dispose()
        $graphics.Dispose()
    }

    $old = $Picture.Image
    $Picture.Image = $bitmap
    if ($old) {
        $old.Dispose()
    }
}

$selectedPort = Select-SerialPort -RequestedPort $Port
Write-Host "Opening $selectedPort at $Baud baud"
Write-Host "Close the image window to quit."
if ($NoTracking -or $Mode -eq "None") {
    Write-Host "Tracking overlay disabled."
} else {
    Write-Host "$Mode tracking every $TrackEvery frame(s), sample step $SampleStep."
}

$serial = [System.IO.Ports.SerialPort]::new($selectedPort, $Baud)
$serial.ReadBufferSize = 1048576
$serial.WriteBufferSize = 4096
$serial.ReadTimeout = $TimeoutMs
$serial.WriteTimeout = $TimeoutMs
$serial.Open()
if ($ResetOnOpen) {
    $serial.DtrEnable = $true
    $serial.RtsEnable = $false
}
try {
    $serial.DiscardInBuffer()
    $serial.DiscardOutBuffer()
} catch {
    Write-Host "Serial buffer clear skipped: $($_.Exception.Message)"
}

$form = [System.Windows.Forms.Form]::new()
$form.Text = "Xiao-An Serial Camera"
$form.Width = 720
$form.Height = 560
$form.StartPosition = "CenterScreen"

$picture = [System.Windows.Forms.PictureBox]::new()
$picture.Dock = "Fill"
$picture.SizeMode = "Zoom"
$picture.BackColor = [System.Drawing.Color]::Black
$form.Controls.Add($picture)
$form.Show()
Draw-StatusFrame -Picture $picture -Text "Opening $selectedPort...`nWaiting for ESP32 camera..."

$frames = 0
$totalFrames = 0
$lastBox = $null
$timeouts = 0
$receivedAnyFrame = $false
$lastMessage = ""
$fpsStart = [DateTime]::UtcNow

try {
    Start-Sleep -Milliseconds $StartupDelayMs
    try {
        if ($serial.IsOpen) {
            $serial.DiscardInBuffer()
            $serial.DiscardOutBuffer()
        }
    } catch {
        Write-Host "Serial buffer clear skipped: $($_.Exception.Message)"
    }
    Request-Frame -Serial $serial

    while ($form.Visible) {
        [System.Windows.Forms.Application]::DoEvents()

        try {
            $jpeg = Read-Frame -Serial $serial
        } catch [System.TimeoutException] {
            $timeouts++
            $lastMessage = "No frame yet (timeout $timeouts).`nCheck firmware, camera wiring, and COM port."
            if (-not $receivedAnyFrame) {
                Draw-StatusFrame -Picture $picture -Text $lastMessage
            }
            if ($VerboseLog) {
                Write-Host $lastMessage
            }
            Request-Frame -Serial $serial
            continue
        } catch [System.InvalidOperationException] {
            $lastMessage = "Serial port closed or reset.`nClose this window, wait 2 seconds, then reopen viewer."
            Draw-StatusFrame -Picture $picture -Text $lastMessage
            Write-Host $lastMessage
            Start-Sleep -Milliseconds 500
            continue
        } catch [System.IO.IOException] {
            $lastMessage = "Serial I/O reset or disconnect.`nClose this window, wait 2 seconds, then reopen viewer."
            Draw-StatusFrame -Picture $picture -Text $lastMessage
            Write-Host $lastMessage
            Start-Sleep -Milliseconds 500
            continue
        } catch {
            $lastMessage = $_.Exception.Message
            Write-Host $lastMessage
            try {
                if ($serial.IsOpen) {
                    $serial.DiscardInBuffer()
                    Request-Frame -Serial $serial
                }
            } catch {
                Write-Host "Serial recovery skipped: $($_.Exception.Message)"
            }
            continue
        }
        $timeouts = 0
        $receivedAnyFrame = $true

        $ms = [System.IO.MemoryStream]::new($jpeg)
        try {
            try {
                $img = [System.Drawing.Image]::FromStream($ms)
                $bitmap = [System.Drawing.Bitmap]::new($img)
                $img.Dispose()
            } catch {
                Write-Host "Skipped corrupt JPEG frame ($($jpeg.Length) bytes)"
                Request-Frame -Serial $serial
                continue
            }
        } finally {
            $ms.Dispose()
        }

        $totalFrames++
        if (-not $NoTracking -and $Mode -ne "None") {
            if ($TrackEvery -le 1 -or ($totalFrames % $TrackEvery) -eq 1 -or $null -eq $lastBox) {
                if ($Mode -eq "QR") {
                    $lastBox = Find-QrBox -Bitmap $bitmap
                } else {
                    $lastBox = Find-RedBox -Bitmap $bitmap
                }
            }
            Draw-TrackingOverlay -Bitmap $bitmap -Box $lastBox -Label $Mode
        }

        $old = $picture.Image
        $picture.Image = $bitmap
        if ($old) {
            $old.Dispose()
        }

        $frames++
        $elapsed = ([DateTime]::UtcNow - $fpsStart).TotalSeconds
        if ($elapsed -ge 1.0) {
            $fps = $frames / $elapsed
            $form.Text = "Xiao-An Serial Camera  {0:N1} FPS" -f $fps
            $frames = 0
            $fpsStart = [DateTime]::UtcNow
        }

        Request-Frame -Serial $serial
    }
} finally {
    if ($picture.Image) {
        $picture.Image.Dispose()
    }
    try {
        if ($serial.IsOpen) {
            $serial.Close()
        }
    } catch {
        Write-Host "Serial close skipped: $($_.Exception.Message)"
    }
    $serial.Dispose()
}
