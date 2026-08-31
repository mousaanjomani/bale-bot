# Supervisor loop: keeps the bot alive and restarts it after upgrades.
# Registered as scheduled task "BaleBot" (runs at system startup).
$InstallDir = "C:\BaleBot"
$AppDir  = Join-Path $InstallDir "app"
$VenvPy  = Join-Path $InstallDir "venv\Scripts\python.exe"

Set-Location $AppDir
while ($true) {
    & $VenvPy (Join-Path $AppDir "main.py")
    # exit code 42 = intentional restart after upgrade; anything else = crash
    Start-Sleep -Seconds 3
}
