#!/usr/bin/env bash
set -euo pipefail

LABEL="com.telegram.operator.runner"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
RUNTIME_ROOT="$HOME/Library/Application Support/TelegramOperatorAgent"
CONFIG_DIR="$RUNTIME_ROOT/config"
BIN_DIR="$RUNTIME_ROOT/bin"
LOG_DIR="$RUNTIME_ROOT/logs"
LAUNCH_AGENT="$HOME/Library/LaunchAgents/${LABEL}.plist"
RUNNER_ENV="$CONFIG_DIR/runner.env"
LAUNCHER="$BIN_DIR/run-runner.sh"

if [[ -z "$ROOT" || ! -f "$ROOT/pyproject.toml" ]]; then
  echo "Run this script from a Git checkout of remote-desktop-agent." >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.11 or newer is required." >&2
  exit 1
fi
if [[ ! -f "$ROOT/.env" ]]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "Created $ROOT/.env. Configure the required values, then rerun this script." >&2
  exit 2
fi

mkdir -p "$CONFIG_DIR" "$BIN_DIR" "$LOG_DIR" "$HOME/Library/LaunchAgents"

# Preserve runtime secrets and runner settings outside the Git checkout.
if [[ ! -f "$RUNNER_ENV" ]]; then
  cp "$ROOT/.env" "$RUNNER_ENV"
fi
# A local runner is outside Docker and must never resolve the Docker-only service name.
if grep -q '^CONTROL_PLANE_URL=' "$RUNNER_ENV"; then
  sed -i '' 's|^CONTROL_PLANE_URL=.*|CONTROL_PLANE_URL=http://127.0.0.1:8080|' "$RUNNER_ENV"
else
  printf '\nCONTROL_PLANE_URL=http://127.0.0.1:8080\n' >> "$RUNNER_ENV"
fi
printf 'REPO_DIR=%s\n' "$ROOT" > "$CONFIG_DIR/repository.env"

python3 -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/python" -m pip install --upgrade pip
"$ROOT/.venv/bin/pip" install -e "$ROOT"

cat > "$LAUNCHER" <<'RUNNER'
#!/usr/bin/env bash
set -euo pipefail
RUNTIME_ROOT="$HOME/Library/Application Support/TelegramOperatorAgent"
# shellcheck disable=SC1090
source "$RUNTIME_ROOT/config/repository.env"
# shellcheck disable=SC1090
source "$RUNTIME_ROOT/config/runner.env"
export PYTHONPATH="$REPO_DIR/apps/runner"
cd "$REPO_DIR"
exec "$REPO_DIR/.venv/bin/python" -m agent_runner.main
RUNNER
chmod 700 "$LAUNCHER"

cat > "$LAUNCH_AGENT" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>${LABEL}</string>
  <key>ProgramArguments</key><array><string>${LAUNCHER}</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>${LOG_DIR}/runner.out.log</string>
  <key>StandardErrorPath</key><string>${LOG_DIR}/runner.err.log</string>
</dict></plist>
PLIST

launchctl bootout "gui/$(id -u)" "$LAUNCH_AGENT" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$LAUNCH_AGENT"
launchctl kickstart -k "gui/$(id -u)/${LABEL}"

echo "Mac runner installed."
echo "Repository: $ROOT"
echo "Runtime configuration: $RUNNER_ENV"
echo "Logs: $LOG_DIR"
echo "Use ./scripts/sync_mac.sh for future Git-based upgrades."
