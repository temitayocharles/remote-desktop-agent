[CmdletBinding()]
param(
  [string]$RepositoryPath = (Get-Location).Path,
  [string]$ControlPlaneUrl = "",
  [switch]$NoStart
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($env:OS -ne 'Windows_NT') { throw 'This installer must run on Windows.' }
$Repo = (Resolve-Path $RepositoryPath).Path
if (-not (Test-Path (Join-Path $Repo 'pyproject.toml'))) { throw 'RepositoryPath must point to remote-desktop-agent.' }

$PythonExe = $null
$PythonPrefixArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
  & py -3.11 -c "import sys; assert sys.version_info >= (3,11)" 2>$null
  if ($LASTEXITCODE -eq 0) { $PythonExe = 'py'; $PythonPrefixArgs = @('-3.11') }
}
if (-not $PythonExe -and (Get-Command python -ErrorAction SilentlyContinue)) {
  & python -c "import sys; assert sys.version_info >= (3,11)" 2>$null
  if ($LASTEXITCODE -eq 0) { $PythonExe = 'python' }
}
if (-not $PythonExe) { throw 'Python 3.11 or newer is required. Install it, reopen PowerShell, then rerun this script.' }

$RuntimeRoot = Join-Path $env:LOCALAPPDATA 'TelegramOperatorAgent'
$ConfigDir = Join-Path $RuntimeRoot 'config'
$BinDir = Join-Path $RuntimeRoot 'bin'
$LogDir = Join-Path $RuntimeRoot 'logs'
$RunnerEnv = Join-Path $ConfigDir 'runner.env'
$RepositoryEnv = Join-Path $ConfigDir 'repository.env'
$Launcher = Join-Path $BinDir 'run-runner.cmd'
New-Item -ItemType Directory -Force -Path $ConfigDir,$BinDir,$LogDir | Out-Null

if (-not (Test-Path $RunnerEnv)) {
  Copy-Item (Join-Path $Repo 'scripts\runner.env.example') $RunnerEnv
}

function Set-RunnerValue([string]$Name, [string]$Value) {
  $values = [ordered]@{}
  Get-Content $RunnerEnv | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { $values[$matches[1]] = $matches[2] }
  }
  $values[$Name] = $Value
  $values.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" } | Set-Content -Encoding utf8 $RunnerEnv
}

if ($ControlPlaneUrl) { Set-RunnerValue 'CONTROL_PLANE_URL' $ControlPlaneUrl }
Set-RunnerValue 'RUNNER_OS' 'windows'
Set-RunnerValue 'RUNNER_ARTIFACT_DIR' (Join-Path $RuntimeRoot 'artifacts')
Set-RunnerValue 'RUNNER_PID_FILE' (Join-Path $RuntimeRoot 'runner.pid')
Set-RunnerValue 'BROWSER_PROFILE_DIR' (Join-Path $RuntimeRoot 'browser-profile')
Set-Content -Encoding utf8 $RepositoryEnv "REPO_DIR=$Repo"

$Required = @('RUNNER_ID','RUNNER_TOKEN')
$Missing = @()
$ConfigText = Get-Content $RunnerEnv -Raw
foreach ($Name in $Required) {
  if ($ConfigText -notmatch "(?m)^$Name=(?!replace-with)[^\r\n]+$") { $Missing += $Name }
}
if ($Missing.Count -gt 0) {
  throw "Configure $RunnerEnv with unique $($Missing -join ', ') values. The Windows runner intentionally does not copy Telegram or control-plane bot credentials."
}

& $PythonExe @PythonPrefixArgs -m venv (Join-Path $Repo '.venv')
$VenvPython = Join-Path $Repo '.venv\Scripts\python.exe'
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -e $Repo
& $VenvPython -m playwright install chromium

@'
@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "RUNTIME_ROOT=%LOCALAPPDATA%\TelegramOperatorAgent"
for /f "usebackq tokens=1,* delims==" %%A in ("%RUNTIME_ROOT%\config\repository.env") do set "%%A=%%B"
for /f "usebackq tokens=1,* delims==" %%A in ("%RUNTIME_ROOT%\config\runner.env") do set "%%A=%%B"
set "PYTHONPATH=%REPO_DIR%\apps\runner"
cd /d "%REPO_DIR%"
:run
"%REPO_DIR%\.venv\Scripts\python.exe" -m agent_runner.main 1>>"%RUNTIME_ROOT%\logs\runner.out.log" 2>>"%RUNTIME_ROOT%\logs\runner.err.log"
timeout /t 10 /nobreak >nul
goto run
'@ | Set-Content -Encoding ascii $Launcher

$Startup = [Environment]::GetFolderPath('Startup')
$ShortcutPath = Join-Path $Startup 'Telegram Operator Runner.lnk'
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $env:ComSpec
$Shortcut.Arguments = '/c ""' + $Launcher + '""'
$Shortcut.WorkingDirectory = $Repo
$Shortcut.WindowStyle = 7
$Shortcut.Save()

$PidFile = Join-Path $RuntimeRoot 'runner.pid'
$AlreadyRunning = $false
if (Test-Path $PidFile) {
  try { $AlreadyRunning = [bool](Get-Process -Id ([int](Get-Content $PidFile -Raw)) -ErrorAction Stop) } catch { }
}
if (-not $NoStart -and -not $AlreadyRunning) {
  Start-Process -FilePath $env:ComSpec -ArgumentList '/c', ('"' + $Launcher + '"') -WorkingDirectory $Repo -WindowStyle Hidden
}

Write-Host "Windows runner installed."
Write-Host "Runner configuration: $RunnerEnv"
Write-Host "Logs: $LogDir"
Write-Host "The runner starts at user sign-in through a Startup shortcut and restarts after crashes."
