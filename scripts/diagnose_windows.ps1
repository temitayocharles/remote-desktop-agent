$ErrorActionPreference = 'Stop'
$RuntimeRoot = Join-Path $env:LOCALAPPDATA 'TelegramOperatorAgent'
$RunnerEnv = Join-Path $RuntimeRoot 'config\runner.env'
$PidFile = Join-Path $RuntimeRoot 'runner.pid'
$ShortcutPath = Join-Path ([Environment]::GetFolderPath('Startup')) 'Telegram Operator Runner.lnk'
Write-Host "Runtime root: $RuntimeRoot"
Write-Host "Runner config present: $(Test-Path $RunnerEnv)"
Write-Host "Startup shortcut present: $(Test-Path $ShortcutPath)"
if (Test-Path $PidFile) {
  $id = Get-Content $PidFile -Raw
  try { Get-Process -Id ([int]$id) -ErrorAction Stop | Out-Null; Write-Host "Runner process: running (PID $id)" } catch { Write-Host "Runner process: not running (stale PID $id)" }
} else { Write-Host 'Runner process: PID file absent' }
Get-ChildItem (Join-Path $RuntimeRoot 'logs') -ErrorAction SilentlyContinue | Select-Object Name,Length,LastWriteTime
