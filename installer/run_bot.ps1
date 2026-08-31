# Supervisor loop: keeps the bot alive and restarts it after upgrades.
# NOTE: on customer servers install.ps1 GENERATES this file in the chosen
# install dir with paths baked in; this copy derives them from its location
# (expects to live in <install-dir>\run_bot.ps1 next to app\ and venv\).
$InstallDir = $PSScriptRoot
$AppDir  = Join-Path $InstallDir "app"
$VenvPy  = Join-Path $InstallDir "venv\Scripts\python.exe"

Set-Location $AppDir
while ($true) {
    & $VenvPy (Join-Path $AppDir "main.py")
    # exit code 42 = intentional restart after upgrade; anything else = crash
    Start-Sleep -Seconds 3
}
