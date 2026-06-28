#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
command -v python3 >/dev/null || { echo "Python 3.11+ is required"; exit 1; }
if [[ ! -f .env ]]; then cp .env.example .env; echo "Created .env. Set all required Telegram, control-plane, and runner values, then rerun."; exit 2; fi
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
mkdir -p artifacts
cat > "$HOME/Library/LaunchAgents/com.telegram.operator.runner.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>Label</key><string>com.telegram.operator.runner</string><key>ProgramArguments</key><array><string>$ROOT/.venv/bin/python</string><string>-m</string><string>agent_runner.main</string></array><key>WorkingDirectory</key><string>$ROOT</string><key>EnvironmentVariables</key><dict><key>PYTHONPATH</key><string>$ROOT/apps/runner</string></dict><key>RunAtLoad</key><true/><key>KeepAlive</key><true/><key>StandardOutPath</key><string>$ROOT/artifacts/runner.out.log</string><key>StandardErrorPath</key><string>$ROOT/artifacts/runner.err.log</string></dict></plist>
PLIST
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.telegram.operator.runner.plist" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.telegram.operator.runner.plist"
echo "Mac runner installed. Grant Accessibility and Automation permissions to the runner Python executable if native app control is required."
