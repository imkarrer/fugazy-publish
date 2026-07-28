# Fugazy Publish — Windows one-time setup helper
# Run: powershell -ExecutionPolicy Bypass -File setup.ps1

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root

$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("Path", "User")

Write-Host "=== Fugazy Publish Setup ===" -ForegroundColor Cyan

Write-Host "`nInstalling Python packages..."
py -m pip install -r requirements.txt

Write-Host "`nChecking ffmpeg..."
try {
    $ff = ffmpeg -version 2>&1 | Select-Object -First 1
    Write-Host "  OK: $ff" -ForegroundColor Green
} catch {
    Write-Host "  Installing ffmpeg via winget..." -ForegroundColor Yellow
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path", "User")
}

if (-not (Test-Path "$Root\config.yaml")) {
    Copy-Item "$Root\config.example.yaml" "$Root\config.yaml"
    Write-Host "`nCreated config.yaml from example." -ForegroundColor Green
}

New-Item -ItemType Directory -Force -Path "$Root\credentials", "$Root\output" | Out-Null

Write-Host "`n=== Still needed (manual) ===" -ForegroundColor Yellow
Write-Host "1. Social APIs (TikTok, Instagram) — see credentials\README.txt"
Write-Host "   py auth_social.py tiktok"
Write-Host "   py auth_social.py tiktok"
Write-Host "   py auth_social.py instagram"
Write-Host ""
Write-Host "2. YouTube OAuth (for NEW uploads only):"
Write-Host "   - Google Cloud Console -> enable YouTube Data API v3"
Write-Host "   - Save OAuth JSON as credentials\client_secret.json"
Write-Host ""
Write-Host "3. Promote existing videos (no YouTube OAuth needed):"
Write-Host "   Double-click Promote.bat and paste a URL"
Write-Host ""
Write-Host "=== Ready ===" -ForegroundColor Green
Write-Host "Project: $Root"
