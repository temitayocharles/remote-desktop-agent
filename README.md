# Telegram Operator Agent

A Telegram-controlled remote operator for macOS and Windows. It accepts direct messages only from one configured Telegram numeric user ID, dispatches to registered devices, preserves task state and evidence, and uses explicit approval for destructive or irreversible actions.

## Deploy

1. Create a Telegram bot through BotFather and copy the bot token.
2. Obtain your immutable numeric Telegram user ID.
3. Copy `.env.example` to `.env`. Set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_OWNER_USER_ID`, `CONTROL_PLANE_BOT_TOKEN`, `RUNNER_ID`, and `RUNNER_TOKEN`. For natural-language task planning, also configure `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL`.
4. Run `docker compose up -d --build` on the host that runs the control plane.
5. On the Mac where tasks execute, run `./scripts/bootstrap_mac.sh`. On Windows, run `scripts/bootstrap_windows.ps1`.

Generate control-plane and runner tokens locally:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48)); print(secrets.token_urlsafe(48))'
```

## Telegram commands

Send normal language if an OpenAI-compatible LLM is configured. Without an LLM, use explicit commands:

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

High-impact requests create an inline Telegram approval request. The local runner independently refuses destructive commands without the recorded approval.

## Validate

```bash
make install
make lint
make test
curl -fsS http://127.0.0.1:8080/healthz
```

Expected health response: `{"status":"ok"}`.

## Rollback

```bash
docker compose down
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.telegram.operator.runner.plist"
rm -f "$HOME/Library/LaunchAgents/com.telegram.operator.runner.plist"
```

Windows:

```powershell
Unregister-ScheduledTask -TaskName TelegramOperatorRunner -Confirm:$false
```

## Version 2 correction: natural language and device-aware dispatch

The original package incorrectly queued all ordinary Telegram messages. Version 2 separates chat from operations:

- `Hello` and `How are you?` are answered as conversation.
- `pwd`, `list files`, URLs, and explicit operational requests are dispatched only when an online runner exists.
- When no device is online, the bot returns a direct error instead of leaving a task in `QUEUED` state.
- Free-form requests such as `open Safari and search for ...` require `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL` in both the control-plane and runner environments.
- Task state changes are pushed back into the Telegram conversation through a task watcher.

After replacing the deployment, restart the control plane and bot, then restart the local runner. Confirm `/devices` shows the Mac as `online` before testing a device task.
