#!/usr/bin/env bash
set -euo pipefail

LABEL="com.telegram.operator.runner"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
RUNTIME_ROOT="$HOME/Library/Application Support/TelegramOperatorAgent"
RUNNER_ENV="$RUNTIME_ROOT/config/runner.env"

if [[ -z "$ROOT" || ! -f "$ROOT/pyproject.toml" ]]; then
  echo "Run this script from the canonical Git checkout." >&2
  exit 1
fi
if [[ ! -f "$RUNNER_ENV" ]]; then
  echo "Stable runner configuration is missing. Run bash ./scripts/bootstrap_mac.sh once first." >&2
  exit 2
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Refusing to update because the checkout has uncommitted changes:" >&2
  git status --short >&2
  exit 3
fi
git fetch --prune origin
git pull --ff-only
"$ROOT/.venv/bin/pip" install -e "$ROOT"
"$ROOT/.venv/bin/python" -m playwright install chromium
bash "$ROOT/scripts/compose.sh" up -d --build
launchctl kickstart -k "gui/$(id -u)/${LABEL}"
curl -fsS --max-time 10 http://127.0.0.1:8080/healthz
echo
echo "Sync complete. Runner logs: $RUNTIME_ROOT/logs/runner.out.log"
