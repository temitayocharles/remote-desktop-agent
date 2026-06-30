from __future__ import annotations

import platform
import subprocess
from typing import Any


class MacOSWorkflowError(RuntimeError):
    pass


def _require_macos() -> None:
    if platform.system() != "Darwin":
        raise MacOSWorkflowError("this workflow is available only on macOS")


def _osascript(script: str, *args: str) -> str:
    _require_macos()
    completed = subprocess.run(["osascript", "-e", script, "--", *args], capture_output=True, text=True, timeout=90)
    if completed.returncode != 0:
        raise MacOSWorkflowError(completed.stderr.strip() or "AppleScript execution failed")
    return completed.stdout.strip()


def open_application(name: str) -> dict[str, Any]:
    _require_macos()
    app_name = str(name).strip()
    if not app_name:
        raise MacOSWorkflowError("application name is required")
    script = '''
on run argv
    set appName to item 1 of argv
    tell application appName to activate
end run
'''
    try:
        _osascript(script, app_name)
    except MacOSWorkflowError:
        completed = subprocess.run(["open", "-a", app_name], capture_output=True, text=True, timeout=30)
        if completed.returncode != 0:
            raise MacOSWorkflowError(completed.stderr.strip() or f"could not launch {app_name}")
    return {"type": "app", "app": app_name, "verified": True, "completion": "launched"}

def run_terminal_command(command: str, timeout_seconds: int = 900) -> dict[str, Any]:
    """Run a command visibly in Terminal and collect its result from task-local files."""
    _require_macos()
    command = str(command).strip()
    if not command or "\x00" in command:
        raise MacOSWorkflowError("a non-empty terminal command is required")

    import tempfile
    import time
    from pathlib import Path

    timeout_seconds = max(1, int(timeout_seconds))
    with tempfile.TemporaryDirectory(prefix="telegram-operator-terminal-") as directory:
        root = Path(directory)
        output_path = root / "stdout.txt"
        status_path = root / "exit-status.txt"
        # The user command remains visible in Terminal. It runs in a subshell so an `exit`
        # in the requested command cannot prevent status capture by the wrapper shell.
        wrapped = "\n".join([
            "(",
            command,
            f") > >(tee {output_path}) 2>&1",
            "__telegram_operator_status=$?",
            f"print -r -- \"$__telegram_operator_status\" > {status_path}",
        ])
        script = "\n".join([
            "on run argv",
            "    set commandText to item 1 of argv",
            "    tell application \"Terminal\"",
            "        activate",
            "        if (count of windows) is 0 then do script \"\"",
            "        do script commandText in front window",
            "    end tell",
            "end run",
        ])
        _osascript(script, wrapped)

        deadline = time.monotonic() + timeout_seconds
        while not status_path.is_file():
            if time.monotonic() >= deadline:
                raise MacOSWorkflowError(
                    f"Terminal command exceeded {timeout_seconds} seconds; it may still be running in the visible Terminal window"
                )
            time.sleep(0.1)

        # Give tee a brief opportunity to flush its final bytes after the status file appears.
        time.sleep(0.1)
        try:
            exit_code = int(status_path.read_text().strip())
        except ValueError as exc:
            raise MacOSWorkflowError("Terminal wrote an invalid exit status") from exc
        stdout = output_path.read_text(errors="replace")[-12000:] if output_path.exists() else ""
        return {
            "type": "macos_terminal_command",
            "terminal": "Terminal",
            "command": command,
            "exit_code": exit_code,
            "stdout": stdout,
            "verified": exit_code == 0,
            "completion": "executed_in_visible_terminal",
        }

def search_junk_mail(query: str = "", limit: int = 20) -> dict[str, Any]:
    _require_macos()
    limit = max(1, min(int(limit), 100))
    script = r'''
on run argv
    set searchText to item 1 of argv
    set maxCount to (item 2 of argv) as integer
    set outputLines to {}
    tell application "Mail"
        activate
        repeat with a in every account
            repeat with b in every mailbox of a
                set mailboxName to name of b
                if mailboxName contains "Junk" or mailboxName contains "Spam" then
                    set messageCount to count of messages of b
                    repeat with i from 1 to messageCount
                        if (count of outputLines) is greater than or equal to maxCount then exit repeat
                        set m to message i of b
                        set senderText to sender of m
                        set subjectText to subject of m
                        if searchText is "" or senderText contains searchText or subjectText contains searchText then
                            set end of outputLines to (senderText & tab & subjectText & tab & (date sent of m as text))
                        end if
                    end repeat
                end if
                if (count of outputLines) is greater than or equal to maxCount then exit repeat
            end repeat
            if (count of outputLines) is greater than or equal to maxCount then exit repeat
        end repeat
    end tell
    set AppleScript's text item delimiters to linefeed
    return outputLines as text
end run
'''
    output = _osascript(script, query, str(limit))
    messages = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            messages.append({"sender": parts[0], "subject": parts[1], "date": "\t".join(parts[2:])})
    return {"type": "macos_mail_search", "mailbox": "Junk/Spam", "query": query, "count": len(messages), "messages": messages, "verified": True, "completion": "searched"}
