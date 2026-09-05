# AuraDash 一键推送脚本
# 前置：已安装 GitHub CLI 并完成 `gh auth login`，或本机已有 git 凭据
# 用法：powershell -ExecutionPolicy Bypass -File tools\push_github.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Test-Path ".git")) {
    git init -b main
}

git add .
git commit -m "feat: AuraDash v1.0.0 - Windows 悬浮硬件监控仪表盘" 2>$null
git branch -M main

# 优先使用 gh（交互最少）
if (Get-Command gh -ErrorAction SilentlyContinue) {
    $remote = gh repo view AuraDash --json name -q .name 2>$null
    if (-not $remote) {
        Write-Host "==> 使用 gh 创建远程仓库 AuraDash..."
        gh repo create AuraDash --public --source . --remote=origin --push
    } else {
        git push -u origin main
    }
} else {
    git push -u origin main 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "git 未检测到已登录凭据。请先执行："
        Write-Host "    gh auth login"
        Write-Host "或参考 docs\GITHUB_PUSH.md 方式 B / C 后手动推送。"
    }
}
Write-Host "完成。"
