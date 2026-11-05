# Write the full SARAH merged image so the chip matches a factory board.
# That includes blank NVS at 0x9000, blank OTA slots, and the image's own otadata.
param(
    [string]$Port = "COM5",
    [string]$MergedBin = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $MergedBin) {
    $MergedBin = Join-Path $Root "FACTORY_BINARIES\SARAH_toilet_kat_change.ino.merged.bin"
}
if (-not (Test-Path $MergedBin)) {
    throw "Missing merged image: $MergedBin"
}
$MergedBin = (Resolve-Path $MergedBin).Path
$size = (Get-Item $MergedBin).Length
if ($size -ne 0x1000000) {
    throw "SARAH merged image must be 16MB (16777216 bytes), got $size"
}

Write-Host "Flashing full SARAH factory image ($size bytes) on $Port..."
python -m esptool --chip esp32s3 --port $Port --baud 921600 write-flash `
    --flash-size 16MB --erase-all 0x0 $MergedBin
if ($LASTEXITCODE -ne 0) {
    throw "esptool write-flash failed with exit code $LASTEXITCODE"
}

python -m esptool --chip esp32s3 --port $Port run
if ($LASTEXITCODE -ne 0) {
    throw "esptool run failed with exit code $LASTEXITCODE"
}

Write-Host "Done. Verifying partition table..."
python (Join-Path $Root "read_partitions.py") --port $Port
if ($LASTEXITCODE -ne 0) {
    throw "read_partitions.py failed with exit code $LASTEXITCODE"
}

Write-Host "SARAH factory flashed."
