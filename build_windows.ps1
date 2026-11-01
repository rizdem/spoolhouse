# Build a Spoolhouse installer on this Windows PC for testing (no GitHub release involved).
#   powershell -ExecutionPolicy Bypass -File build_windows.ps1 [-Ref <branch or commit>]
# Gets the latest code from GitHub, makes the Python environment the first time (and refreshes its packages),
# then runs build_windows.py: tests, app, self-test, installer -> dist\Spoolhouse-<version>-windows-setup.exe
param([string]$Ref = "main")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

git fetch --quiet origin
git checkout --quiet --detach "origin/$Ref" 2>$null
if ($LASTEXITCODE -ne 0) { git checkout --quiet --detach $Ref }
if ($LASTEXITCODE -ne 0) { throw "Couldn't find '$Ref' to build." }
Write-Host "Building $(git log -1 --format='%h %s')"

$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) { throw "Inno Setup 6 isn't installed: winget install JRSoftware.InnoSetup" }

if (-not (Test-Path .venv\Scripts\python.exe)) {
    uv venv --python 3.12 --python-preference only-managed .venv
}
uv pip install --quiet --python .venv\Scripts\python.exe -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "Installing the Python packages failed." }

.venv\Scripts\python.exe build_windows.py
if ($LASTEXITCODE -ne 0) { throw "The build failed." }
Get-ChildItem dist\Spoolhouse-*-windows-setup.exe | Sort-Object LastWriteTime | Select-Object -Last 1 | ForEach-Object { "Installer: $($_.FullName)" }
