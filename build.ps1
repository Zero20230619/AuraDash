# AuraDash 一键构建脚本（Windows PowerShell）
# 用法：powershell -ExecutionPolicy Bypass -File build.ps1
# 产物：dist\AuraDash.exe（单文件，约 30-40MB）

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

# 1. 虚拟环境
$Venv = Join-Path $Root ".venv"
if (-not (Test-Path $Venv)) {
    Write-Host "==> 创建虚拟环境 .venv"
    python -m venv $Venv
}
$Py = Join-Path $Venv "Scripts\python.exe"
& $Py -m pip install --upgrade pip --quiet
Write-Host "==> 安装依赖"
& $Py -m pip install -r requirements.txt pyinstaller --quiet

# 2. 生成资源（图标 / 提示音）
Write-Host "==> 生成资源"
& $Py tools\make_assets.py

# 3. 打包（--onedir 更快启动；如需单文件改 --onefile）
Write-Host "==> PyInstaller 打包"
& $Py -m PyInstaller --noconfirm --clean --windowed `
    --name AuraDash --icon assets\aura.ico `
    --add-data "assets;assets" `
    main.py

Write-Host ""
Write-Host "完成：dist\AuraDash\AuraDash.exe"
