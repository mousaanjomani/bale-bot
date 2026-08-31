# Remove the Bale bot from the customer server (keeps <install-dir>\data unless -Purge).
# Run from inside the installation (app\installer\uninstall.ps1) or pass -InstallDir.
param(
    [string]$InstallDir = "",
    [switch]$Purge
)
$ErrorActionPreference = "SilentlyContinue"

if (-not $InstallDir) {
    # this script normally lives at <install-dir>\app\installer\uninstall.ps1
    $candidate = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    if (Test-Path (Join-Path $candidate "run_bot.ps1")) { $InstallDir = $candidate }
    else { $InstallDir = "C:\BaleBot" }
}
Write-Host "حذف نصب از: $InstallDir"

schtasks /End /TN "BaleBot" /F | Out-Null
schtasks /Delete /TN "BaleBot" /F | Out-Null
Get-Process python* | Where-Object { $_.Path -like "$InstallDir\*" } | Stop-Process -Force
netsh advfirewall firewall delete rule name="BaleBot Dashboard" | Out-Null

Remove-Item -Recurse -Force (Join-Path $InstallDir "app"), (Join-Path $InstallDir "venv"), (Join-Path $InstallDir "run_bot.ps1")
if ($Purge) { Remove-Item -Recurse -Force $InstallDir }

Write-Host "حذف نصب انجام شد." -ForegroundColor Green
