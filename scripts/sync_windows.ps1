[CmdletBinding()]
param([string]$RepositoryPath = (Get-Location).Path)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$Repo = (Resolve-Path $RepositoryPath).Path
$RuntimeRoot = Join-Path $env:LOCALAPPDATA 'TelegramOperatorAgent'
$RunnerEnv = Join-Path $RuntimeRoot 'config\runner.env'
$PidFile = Join-Path $RuntimeRoot 'runner.pid'
$Launcher = Join-Path $RuntimeRoot 'bin\run-runner.cmd'
if (-not (Test-Path (Join-Path $Repo 'pyproject.toml'))) { throw 'RepositoryPath must point to remote-desktop-agent.' }
if (-not (Test-Path $RunnerEnv)) { throw 'Runner configuration is missing. Run .\scripts\bootstrap_windows.ps1 once first.' }
if ((git -C $Repo status --porcelain)) { throw 'Refusing to update because the checkout has uncommitted changes.' }
git -C $Repo fetch --prune origin
git -C $Repo pull --ff-only
$VenvPython = Join-Path $Repo '.venv\Scripts\python.exe'
if (-not (Test-Path $VenvPython)) { throw 'Virtual environment is missing. Run .\scripts\bootstrap_windows.ps1 first.' }
& $VenvPython -m pip install -e $Repo
& $VenvPython -m playwright install chromium
if (Test-Path $PidFile) {
  try { Stop-Process -Id ([int](Get-Content $PidFile -Raw)) -Force -ErrorAction Stop } catch { }
  Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}
Start-Process -FilePath $env:ComSpec -ArgumentList '/c', ('"' + $Launcher + '"') -WorkingDirectory $Repo -WindowStyle Hidden
Write-Host "Windows runner synchronized and restarted."
