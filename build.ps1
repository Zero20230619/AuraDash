# AuraDash build script (Windows PowerShell)
# Usage: powershell -ExecutionPolicy Bypass -File build.ps1          # onedir mode (fast startup)
#        powershell -ExecutionPolicy Bypass -File build.ps1 -OneFile # single-file EXE for release
param([switch]$OneFile)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

# 1. virtualenv
$Venv = Join-Path $Root ".venv"
if (-not (Test-Path $Venv)) {
    Write-Host "==> create venv .venv"
    python -m venv $Venv
}
$Py = Join-Path $Venv "Scripts\python.exe"
& $Py -m pip install --upgrade pip --quiet
Write-Host "==> install deps"
& $Py -m pip install -r requirements.txt pyinstaller --quiet

# 2. generate assets (icon / sounds)
Write-Host "==> generate assets"
& $Py tools\make_assets.py

# 3. PyInstaller (--onefile when -OneFile, otherwise onedir)
Write-Host "==> PyInstaller packaging"
if ($OneFile) {
    & $Py -m PyInstaller --noconfirm --clean --windowed --onefile `
        --name AuraDash --icon assets\aura.ico `
        --add-data "assets;assets" `
        main.py
    Write-Host ""
    Write-Host "DONE: dist\AuraDash.exe (single file)"
} else {
    & $Py -m PyInstaller --noconfirm --clean --windowed `
        --name AuraDash --icon assets\aura.ico `
        --add-data "assets;assets" `
        main.py
    Write-Host ""
    Write-Host "DONE: dist\AuraDash\AuraDash.exe"
}
