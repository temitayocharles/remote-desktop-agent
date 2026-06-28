$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if (-not (Test-Path .env)) { Copy-Item .env.example .env; Write-Host 'Created .env. Configure required values and rerun.'; exit 2 }
py -3 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\pip.exe install -e .
$action = New-ScheduledTaskAction -Execute "$Root\.venv\Scripts\python.exe" -Argument '-m agent_runner.main' -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName 'TelegramOperatorRunner' -Action $action -Trigger $trigger -Description 'Telegram Operator Agent runner' -Force | Out-Null
Start-ScheduledTask -TaskName 'TelegramOperatorRunner'
Write-Host 'Windows runner installed and started.'
