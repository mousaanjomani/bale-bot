# =====================================================================
#  Bale Bot - Windows installer
#  Easiest way: give the customer installer/install.bat (double-click).
#  Manual run (PowerShell as Administrator):
#    irm https://raw.githubusercontent.com/mousaanjomani/bale-bot/main/installer/install.ps1 | iex
# =====================================================================
$ErrorActionPreference = "Stop"

# ------------- settings -------------
$Repo     = "mousaanjomani/bale-bot"
$TaskName = "BaleBot"

Write-Host ""
Write-Host "=== Bale Bot Installer ===" -ForegroundColor Green

# ------------- admin check -------------
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "This installer must be run as Administrator." -ForegroundColor Red
    exit 1
}

# ------------- install path (chosen by the customer) -------------
$DefaultDir = "C:\BaleBot"
$InstallDir = Read-Host "Install path (press Enter for $DefaultDir)"
if ([string]::IsNullOrWhiteSpace($InstallDir)) { $InstallDir = $DefaultDir }
$InstallDir = $InstallDir.Trim('"').TrimEnd('\')
try {
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
} catch {
    Write-Host "Cannot create directory '$InstallDir': $_" -ForegroundColor Red
    exit 1
}
$AppDir  = Join-Path $InstallDir "app"
$DataDir = Join-Path $InstallDir "data"
Write-Host "Install dir: $InstallDir" -ForegroundColor Cyan

# ------------- find or install Python -------------
function Find-Python {
    foreach ($cmd in @("py -3", "python")) {
        try {
            $v = & cmd /c "$cmd -c ""import sys;print(sys.version_info[0]*100+sys.version_info[1])""" 2>$null
            if ($LASTEXITCODE -eq 0 -and [int]$v -ge 309) { return $cmd }
        } catch {}
    }
    return $null
}

$py = Find-Python
if (-not $py) {
    Write-Host "Python not found; installing Python 3.12 ..." -ForegroundColor Yellow
    $pyUrl = "https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe"
    $pyExe = Join-Path $env:TEMP "python-installer.exe"
    Invoke-WebRequest -Uri $pyUrl -OutFile $pyExe -UseBasicParsing
    Start-Process $pyExe -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0" -Wait
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
    $py = Find-Python
    if (-not $py) { Write-Host "Python installation failed." -ForegroundColor Red; exit 1 }
}
Write-Host "Python: $py" -ForegroundColor Green

# ------------- download latest release -------------
New-Item -ItemType Directory -Force -Path $AppDir, $DataDir | Out-Null

Write-Host "Downloading the latest release from GitHub ..." -ForegroundColor Yellow
$relApi = "https://api.github.com/repos/$Repo/releases/latest"
$rel = Invoke-RestMethod -Uri $relApi -UseBasicParsing
$asset = $rel.assets | Where-Object { $_.name -like "*.zip" } | Select-Object -First 1
if ($asset) { $zipUrl = $asset.browser_download_url } else { $zipUrl = $rel.zipball_url }

$zipPath = Join-Path $env:TEMP "balebot.zip"
Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing

$tmpDir = Join-Path $env:TEMP "balebot_extract"
Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue
Expand-Archive -Path $zipPath -DestinationPath $tmpDir -Force

# zipball nests content in a single top folder - detect it
$top = Get-ChildItem $tmpDir
if ($top.Count -eq 1 -and $top[0].PSIsContainer) { $src = $top[0].FullName } else { $src = $tmpDir }
Copy-Item -Path (Join-Path $src "*") -Destination $AppDir -Recurse -Force
Write-Host "Version $($rel.tag_name) installed." -ForegroundColor Green

# ------------- create venv + install requirements -------------
Write-Host "Creating Python environment and installing dependencies ..." -ForegroundColor Yellow
$venv = Join-Path $InstallDir "venv"
& cmd /c "$py -m venv `"$venv`""
$venvPy = Join-Path $venv "Scripts\python.exe"
& $venvPy -m pip install --upgrade pip -q
& $venvPy -m pip install -r (Join-Path $AppDir "requirements.txt") -q

# ------------- initial config -------------
$cfgPath = Join-Path $DataDir "config.json"
if (-not (Test-Path $cfgPath)) {
    $botToken  = Read-Host "Enter the Bale bot token (press Enter to skip; you can set it later in the dashboard)"
    $adminPass = Read-Host "Set the dashboard admin password (press Enter for 'admin')"
    if (-not $adminPass) { $adminPass = "admin" }
    $cfg = @{
        bot_token      = "$botToken"
        admin_user     = "admin"
        admin_password = "$adminPass"
        web_port       = 8585
        update_repo    = $Repo
    } | ConvertTo-Json
    [IO.File]::WriteAllText($cfgPath, $cfg, [Text.UTF8Encoding]::new($false))
}

# ------------- write supervisor + register scheduled task -------------
# generated here so the chosen install path is baked in
$runner = Join-Path $InstallDir "run_bot.ps1"
@"
# Supervisor loop: keeps the bot alive and restarts it after upgrades.
# Generated by install.ps1 - registered as scheduled task "$TaskName".
`$AppDir = "$AppDir"
`$VenvPy = "$venvPy"
Set-Location `$AppDir
while (`$true) {
    & `$VenvPy (Join-Path `$AppDir "main.py")
    Start-Sleep -Seconds 3
}
"@ | Out-File -FilePath $runner -Encoding utf8

# delete via cmd so a "task not found" stderr line cannot trip ErrorActionPreference=Stop
cmd /c "schtasks /Delete /TN $TaskName /F >nul 2>&1"
$action = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$runner`""
schtasks /Create /TN $TaskName /TR $action /SC ONSTART /RU SYSTEM /RL HIGHEST /F | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "Failed to register the scheduled task." -ForegroundColor Red; exit 1 }
schtasks /Run /TN $TaskName | Out-Null

# ------------- firewall -------------
cmd /c "netsh advfirewall firewall delete rule name=""BaleBot Dashboard"" >nul 2>&1"
netsh advfirewall firewall add rule name="BaleBot Dashboard" dir=in action=allow protocol=TCP localport=8585 | Out-Null

Write-Host ""
Write-Host "=== Installation complete ===" -ForegroundColor Green
Write-Host "Management dashboard:  http://localhost:8585" -ForegroundColor Cyan
Write-Host "Username: admin"
Write-Host ""
