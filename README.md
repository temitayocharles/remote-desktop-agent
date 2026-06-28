# Telegram Operator Agent

A Telegram-controlled remote operator for macOS and Windows. The agent executes explicit requests on a registered computer, records evidence, verifies task outcomes, and requires approval only for meaningful-impact actions.

## macOS

Canonical checkout:

```bash
/Volumes/512-B/Documents/PERSONAL/remote-desktop-agent
```

Install or upgrade runner dependencies:

```bash
cd "/Volumes/512-B/Documents/PERSONAL/remote-desktop-agent"
git pull --ff-only
bash ./scripts/bootstrap_mac.sh
```

Routine update:

```bash
bash ./scripts/sync_mac.sh
```

## Windows distribution

The Windows runner is designed for a recipient-owned computer and does not copy Telegram bot credentials. Each person must use a unique `RUNNER_ID` and `RUNNER_TOKEN` and a control-plane address they are authorized to use.

Prerequisites: Windows 10/11, PowerShell 5.1+, Git, and Python 3.11+. Docker Desktop is needed only when that Windows computer also hosts the control plane locally.

```powershell
git clone https://github.com/temitayocharles/remote-desktop-agent.git $HOME\source\remote-desktop-agent
cd $HOME\source\remote-desktop-agent
.\scripts\bootstrap_windows.ps1 -NoStart
notepad "$env:LOCALAPPDATA\TelegramOperatorAgent\config\runner.env"
.\scripts\bootstrap_windows.ps1 -ControlPlaneUrl "https://your-authorized-control-plane.example"
```

The first installer call creates a runner-only configuration file and exits until the recipient supplies unique runner credentials. It never copies Telegram bot credentials from the repository. The second call validates the configuration, installs dependencies and Chromium, creates the interactive startup entry, and starts the runner.

The Windows installer keeps runtime state outside the repository:

```text
%LOCALAPPDATA%\TelegramOperatorAgent\
├── config\runner.env
├── config\repository.env
├── bin\run-runner.cmd
├── logs\
├── artifacts\
└── browser-profile\
```

It creates a current-user Startup shortcut, so the runner begins in the interactive user session at sign-in. This is required for headed browser automation and is safer than installing a privileged Windows service.

Update a Windows runner:

```powershell
.\scripts\sync_windows.ps1
```

Diagnose it:

```powershell
.\scripts\diagnose_windows.ps1
```

Remove it while retaining configuration:

```powershell
.\scripts\uninstall_windows.ps1
```

Remove configuration and browser profile too:

```powershell
.\scripts\uninstall_windows.ps1 -RemoveRuntime
```

## Execution guarantees

- A non-zero shell exit code is a failed task, not a success.
- Every task creates durable evidence under `RUNNER_ARTIFACT_DIR/<task-id>/`.
- The runner checks for cancellation between actions and while shell commands are running.
- A user cancellation prevents a late `SUCCEEDED` update from overwriting `CANCELLED`.
- Browser and native workflows must return verified evidence before a task is marked successful.

## Current workflows

- Browser automation through a persisted Chromium profile.
- ChatGPT image generation followed by local file verification.
- Read-only macOS Mail Junk/Spam search with sender, subject, and date metadata.
- Application launch.

## Validation

```bash
make lint
make test
curl -fsS http://127.0.0.1:8080/healthz
```
