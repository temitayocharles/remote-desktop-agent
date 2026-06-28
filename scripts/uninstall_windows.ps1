[CmdletBinding()]
param([switch]$RemoveRuntime)

$ErrorActionPreference = 'Stop'
$RuntimeRoot = Join-Path $env:LOCALAPPDATA 'TelegramOperatorAgent'
$PidFile = Join-Path $RuntimeRoot 'runner.pid'
$ShortcutPath = Join-Path ([Environment]::GetFolderPath('Startup')) 'Telegram Operator Runner.lnk'
if (Test-Path $PidFile) {
  try { Stop-Process -Id ([int](Get-Content $PidFile -Raw)) -Force -ErrorAction Stop } catch { }
}
Remove-Item $ShortcutPath -Force -ErrorAction SilentlyContinue
if ($RemoveRuntime) { Remove-Item $RuntimeRoot -Recurse -Force -ErrorAction SilentlyContinue }
Write-Host 'Windows runner removed. Runtime configuration was retained unless -RemoveRuntime was supplied.'
