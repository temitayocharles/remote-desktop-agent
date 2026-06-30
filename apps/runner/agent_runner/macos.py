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
def run_terminal_command(command: str) -> dict[str, Any]:
    """Run a command in a visible Terminal tab and return its actual result."""
    _require_macos()
    command = str(command).strip()
    if not command or "\x00" in command:
        raise MacOSWorkflowError("a non-empty terminal command is required")
    wrapped = command + "\n__telegram_operator_status=$?\n" + "printf '\\n__TELEGRAM_OPERATOR_EXIT__:%s\\n' \"$__telegram_operator_status\"\n"
    script = "\n".join([
        "on run argv",
        "    set commandText to item 1 of argv",
        "    tell application \"Terminal\"",
        "        activate",
        "        if (count of windows) is 0 then do script \"\"",
        "        set targetWindow to front window",
        "        do script commandText in targetWindow",
        "        set targetTab to selected tab of targetWindow",
        "        repeat while busy of targetTab",
        "            delay 0.2",
        "        end repeat",
        "        return contents of targetTab",
        "    end tell",
        "end run",
    ])
    transcript = _osascript(script, wrapped)
    marker = "__TELEGRAM_OPERATOR_EXIT__:"
    before, separator, after = transcript.rpartition(marker)
    if not separator:
        raise MacOSWorkflowError("Terminal did not return a completion marker; the command may still be running")
    try:
        exit_code = int(after.splitlines()[0].strip())
    except (IndexError, ValueError) as exc:
        raise MacOSWorkflowError("Terminal returned an unreadable completion marker") from exc
    command_start = before.rfind(command)
    stdout = before[command_start + len(command):].lstrip("\r\n") if command_start >= 0 else before
    return {"type": "macos_terminal_command", "terminal": "Terminal", "command": command, "exit_code": exit_code, "stdout": stdout[-12000:], "verified": exit_code == 0, "completion": "executed_in_visible_terminal"}


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
