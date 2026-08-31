# Remove the Bale bot from the customer server (keeps C:\BaleBot\data unless -Purge).
param([switch]$Purge)
$ErrorActionPreference = "SilentlyContinue"

schtasks /End /TN "BaleBot" /F | Out-Null
schtasks /Delete /TN "BaleBot" /F | Out-Null
Get-Process python* | Where-Object { $_.Path -like "C:\BaleBot\*" } | Stop-Process -Force
netsh advfirewall firewall delete rule name="BaleBot Dashboard" | Out-Null

Remove-Item -Recurse -Force "C:\BaleBot\app", "C:\BaleBot\venv", "C:\BaleBot\run_bot.ps1"
if ($Purge) { Remove-Item -Recurse -Force "C:\BaleBot" }

Write-Host "حذف نصب انجام شد." -ForegroundColor Green
