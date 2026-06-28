# Telegram Operator Agent

A Telegram-controlled remote operator for macOS and Windows. It accepts direct messages only from one configured Telegram numeric user ID, dispatches to registered devices, preserves task state and evidence, and requires explicit approval for destructive or irreversible actions.

## Stable macOS installation

Do not run the application from disposable Downloads extractions. Clone this repository once into a durable location, for example:

```bash
git clone https://github.com/temitayocharles/remote-desktop-agent.git \
  "$HOME/Documents/PERSONAL/remote-desktop-agent"
cd "$HOME/Documents/PERSONAL/remote-desktop-agent"
cp .env.example .env
```

Configure `.env` with the Telegram token, owner numeric user ID, control-plane token, runner token, and optional LLM settings. For a Mac runner on the same host as Docker, keep:

```dotenv
CONTROL_PLANE_URL=http://127.0.0.1:8080
```

Install the control plane and stable runner once:

```bash
docker compose up -d --build
./scripts/bootstrap_mac.sh
```

The installer stores runtime configuration and logs outside the Git checkout:

```text
~/Library/Application Support/TelegramOperatorAgent/
├── config/runner.env
├── config/repository.env
├── bin/run-runner.sh
└── logs/
```

The LaunchAgent always starts the stable launcher, not a temporary extraction path. Future updates are Git-based:

```bash
cd "$HOME/Documents/PERSONAL/remote-desktop-agent"
./scripts/sync_mac.sh
```

`sync_mac.sh` refuses to run with uncommitted changes, fast-forwards from Git, refreshes Python dependencies, rebuilds the Docker services, restarts the runner, and verifies the local health endpoint. It never overwrites `runner.env` or Telegram credentials.

## Telegram behavior

Ordinary messages such as `Hello` are conversation. Operational requests dispatch to an online runner. Internal transport states are not intended as the normal chat experience; use `/tasks` or `/status <task-id>` only when you need operational detail.

Without an LLM, use explicit commands:

```text
shell: pwd && git status --short --branch
browser: https://example.com
app: Safari
read: ~/Documents/example.txt
write: ~/Documents/example.txt
replacement file content
```

Control commands:

```text
/start
/tasks
/devices
/status <full-task-id>
/cancel <full-task-id>
```

## Validation

```bash
make lint
make test
curl -fsS http://127.0.0.1:8080/healthz
```

Expected health response: `{"status":"ok"}`.

## Rollback

To return the repository code to its previous Git revision:

```bash
git log --oneline -5
git reset --hard <known-good-commit>
./scripts/sync_mac.sh
```

To stop the runner entirely:

```bash
launchctl bootout "gui/$(id -u)" \
  "$HOME/Library/LaunchAgents/com.telegram.operator.runner.plist"
```
