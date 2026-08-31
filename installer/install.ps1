# =====================================================================
#  Bale Bot - Windows installer
#  Run on the customer server (PowerShell as Administrator):
#    irm https://raw.githubusercontent.com/<OWNER>/<REPO>/main/installer/install.ps1 | iex
#  or download this file and run:  powershell -ExecutionPolicy Bypass -File install.ps1
# =====================================================================
$ErrorActionPreference = "Stop"

# ------------- settings (filled in by the release script) -------------
$Repo       = "__UPDATE_REPO__"        # e.g. "someuser/bale-bot"
$InstallDir = "C:\BaleBot"
$AppDir     = Join-Path $InstallDir "app"
$DataDir    = Join-Path $InstallDir "data"
$TaskName   = "BaleBot"

Write-Host ""
Write-Host "=== نصب بات بله ===" -ForegroundColor Green
Write-Host "Install dir: $InstallDir"

# ------------- admin check -------------
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "این اسکریپت باید با دسترسی Administrator اجرا شود." -ForegroundColor Red
    exit 1
}

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
    Write-Host "Python یافت نشد؛ در حال نصب Python 3.12 ..." -ForegroundColor Yellow
    $pyUrl = "https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe"
    $pyExe = Join-Path $env:TEMP "python-installer.exe"
    Invoke-WebRequest -Uri $pyUrl -OutFile $pyExe -UseBasicParsing
    Start-Process $pyExe -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0" -Wait
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
    $py = Find-Python
    if (-not $py) { Write-Host "نصب Python ناموفق بود." -ForegroundColor Red; exit 1 }
}
Write-Host "Python: $py" -ForegroundColor Green

# ------------- download latest release -------------
New-Item -ItemType Directory -Force -Path $AppDir, $DataDir | Out-Null

Write-Host "دریافت آخرین نسخه از گیت‌هاب ..." -ForegroundColor Yellow
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
Write-Host "نسخه $($rel.tag_name) نصب شد." -ForegroundColor Green

# ------------- create venv + install requirements -------------
Write-Host "ساخت محیط پایتون و نصب وابستگی‌ها ..." -ForegroundColor Yellow
$venv = Join-Path $InstallDir "venv"
& cmd /c "$py -m venv `"$venv`""
$venvPy = Join-Path $venv "Scripts\python.exe"
& $venvPy -m pip install --upgrade pip -q
& $venvPy -m pip install -r (Join-Path $AppDir "requirements.txt") -q

# ------------- initial config -------------
$cfgPath = Join-Path $DataDir "config.json"
if (-not (Test-Path $cfgPath)) {
    $botToken  = Read-Host "توکن بات بله را وارد کنید (می‌توانید بعداً در داشبورد وارد کنید، Enter برای رد شدن)"
    $adminPass = Read-Host "رمز عبور مدیر داشبورد را تعیین کنید"
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

# ------------- copy supervisor + register scheduled task -------------
$runner = Join-Path $InstallDir "run_bot.ps1"
Copy-Item (Join-Path $AppDir "installer\run_bot.ps1") $runner -Force

schtasks /Delete /TN $TaskName /F 2>$null | Out-Null
$action = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$runner`""
schtasks /Create /TN $TaskName /TR $action /SC ONSTART /RU SYSTEM /RL HIGHEST /F | Out-Null
schtasks /Run /TN $TaskName | Out-Null

# ------------- firewall -------------
netsh advfirewall firewall delete rule name="BaleBot Dashboard" 2>$null | Out-Null
netsh advfirewall firewall add rule name="BaleBot Dashboard" dir=in action=allow protocol=TCP localport=8585 | Out-Null

Write-Host ""
Write-Host "=== نصب کامل شد ===" -ForegroundColor Green
Write-Host "داشبورد مدیریت:  http://localhost:8585" -ForegroundColor Cyan
Write-Host "نام کاربری: admin"
Write-Host ""
