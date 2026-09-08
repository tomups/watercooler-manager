$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $root

$venv = Join-Path $root ".venv"
$python = Join-Path $venv "Scripts\python.exe"
$pyinstaller = Join-Path $venv "Scripts\pyinstaller.exe"

if (-not (Test-Path $python)) {
    Write-Host "Creating virtual environment..."
    py -3.11 -m venv $venv
}

Write-Host "Upgrading pip..."
& $python -m pip install --upgrade pip

Write-Host "Installing dependencies..."
& $python -m pip install -r requirements.txt
& $python -m pip install pyinstaller

Write-Host "Running tests..."
& $python -m unittest test_temperature.py

Write-Host "Preparing LibreHardwareMonitor..."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\prepare_librehardwaremonitor.ps1"

Write-Host "Building executable..."
& $pyinstaller `
    --noconfirm `
    --onefile `
    --windowed `
    --noconsole `
    --uac-admin `
    --hidden-import clr `
    --icon "src/icons/connected.png" `
    --add-data "src/icons;icons" `
    --add-data "src/watercooler_manager;watercooler_manager" `
    --add-binary "vendor/librehardwaremonitor/*.dll;librehardwaremonitor" `
    --name "WaterCoolerManager" `
    src/main.py

$exe = Join-Path $root "dist\WaterCoolerManager.exe"
if (Test-Path $exe) {
    $hash = (Get-FileHash $exe -Algorithm SHA256).Hash
    Write-Host "Build complete: $exe"
    Write-Host "SHA-256: $hash"
} else {
    throw "Executable was not created"
}
