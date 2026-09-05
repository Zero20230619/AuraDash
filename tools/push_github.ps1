# AuraDash one-click GitHub push script (ASCII only, PowerShell 5.1 safe)
# Prereq: GitHub CLI installed with `gh auth login`
# Usage: powershell -ExecutionPolicy Bypass -File tools\push_github.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Test-Path ".git")) {
    git init -b main
}

git add .
git commit -m "feat: AuraDash v1.0.0 - Windows floating hardware monitor dashboard" 2>$null
git branch -M main

# prefer gh CLI (interacts least)
if (Get-Command gh -ErrorAction SilentlyContinue) {
    $exists = gh repo view AuraDash --json name -q .name 2>$null
    if (-not $exists) {
        Write-Host "==> creating remote repo AuraDash via gh..."
        gh repo create AuraDash --public --source . --remote=origin --push
    } else {
        git push -u origin main
    }
} else {
    git push -u origin main 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "git has no stored credentials. Run first:"
        Write-Host "    gh auth login"
        Write-Host "or follow docs\GITHUB_PUSH.md option B / C."
    }
}
Write-Host "DONE."
