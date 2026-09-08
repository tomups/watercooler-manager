$ErrorActionPreference = "Stop"

$version = "0.9.6"
$expectedHash = "086D9F1B5A99E643EDC2CFAAAC16051685B551E4C5AC0B32A57C58C0E529C001"
$url = "https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/download/v$version/LibreHardwareMonitor.zip"
$destination = Join-Path $PSScriptRoot "vendor\librehardwaremonitor"
$archive = Join-Path $env:TEMP "LibreHardwareMonitor-$version.zip"
$extractPath = Join-Path $env:TEMP "LibreHardwareMonitor-$version"

Invoke-WebRequest -Uri $url -OutFile $archive
$actualHash = (Get-FileHash $archive -Algorithm SHA256).Hash
if ($actualHash -ne $expectedHash) {
    throw "LibreHardwareMonitor archive checksum mismatch"
}

if (Test-Path $extractPath) {
    Remove-Item $extractPath -Recurse -Force
}
Expand-Archive $archive -DestinationPath $extractPath
New-Item -ItemType Directory -Force -Path $destination | Out-Null
Get-ChildItem $destination -File | Remove-Item -Force
Copy-Item (Join-Path $extractPath "*.dll") $destination

Remove-Item $archive -Force
Remove-Item $extractPath -Recurse -Force
Write-Host "LibreHardwareMonitor $version libraries prepared in $destination"
