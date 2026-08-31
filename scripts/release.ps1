# =====================================================================
#  Release helper (run on the DEV machine, not the customer server)
#  Usage:  .\scripts\release.ps1 -Version 0.2.0 -Notes "توضیح تغییرات"
#  Steps: bump version -> commit -> tag -> zip -> GitHub release
# =====================================================================
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$Notes = ""
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

# 1) bump version
$verFile = Join-Path $Root "app\version.py"
"__version__ = `"$Version`"" | Out-File -FilePath $verFile -Encoding utf8
Write-Host "version.py -> $Version"

# 2) commit + tag
Set-Location $Root
git add -A
git commit -m "release: v$Version"
git tag "v$Version"
git push origin main --tags

# 3) build release zip (app code only - no data, no git)
$zip = Join-Path $env:TEMP "balebot-v$Version.zip"
Remove-Item $zip -ErrorAction SilentlyContinue
$items = @("app", "installer", "main.py", "requirements.txt", "CHANGELOG.md", "README.md")
Compress-Archive -Path ($items | ForEach-Object { Join-Path $Root $_ }) -DestinationPath $zip

# 4) create GitHub release with the zip asset
if (-not $Notes) { $Notes = "نسخه $Version" }
gh release create "v$Version" $zip --title "v$Version" --notes $Notes
Write-Host "Release v$Version published." -ForegroundColor Green
