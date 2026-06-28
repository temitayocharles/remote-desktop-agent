# Telegram Operator Agent

A Telegram-controlled remote operator for macOS and Windows. The agent executes explicit requests on a registered computer, records evidence, verifies task outcomes, and requires approval only for meaningful-impact actions.

## Canonical installation

Keep one Git checkout at:

```bash
/Volumes/512-B/Documents/PERSONAL/remote-desktop-agent
```

First-time setup or an upgrade that changes runner dependencies:

```bash
cd "/Volumes/512-B/Documents/PERSONAL/remote-desktop-agent"
git pull --ff-only
bash ./scripts/bootstrap_mac.sh
```

Routine source updates:

```bash
cd "/Volumes/512-B/Documents/PERSONAL/remote-desktop-agent"
bash ./scripts/sync_mac.sh
```

## Execution guarantees

- A non-zero shell exit code is a failed task, not a success.
- Every task creates durable evidence under `RUNNER_ARTIFACT_DIR/<task-id>/`.
- The runner checks for cancellation between actions and while shell commands are running.
- A user cancellation prevents a late `SUCCEEDED` update from overwriting `CANCELLED`.
- Browser workflows and native workflows must return verified evidence before a task is marked successful.

## Current native workflows

- Browser automation through a persisted Chromium profile.
- ChatGPT image generation followed by local file verification.
- Read-only macOS Mail Junk/Spam search that returns sender, subject, and date metadata.
- Application launch on macOS.

For macOS Mail access, macOS may prompt for Automation permission. Grant it only to the local runner process when you intend to use Mail automation.

## Commands

```text
Open ChatGPT and create a hyper-realistic image of a beer and save the photo in desktop.
Open Mail and search for spam emails.
shell: pwd
browser: https://example.com
app: Safari
read: ~/Documents/example.txt
write: ~/Documents/example.txt
replacement file content
```

Use `/devices`, `/tasks`, `/status <task-id>`, and `/cancel <task-id>` for operator controls.

## Validation

```bash
make lint
make test
curl -fsS http://127.0.0.1:8080/healthz
```
