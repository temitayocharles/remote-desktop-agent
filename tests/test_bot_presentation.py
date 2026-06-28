import importlib.util
from pathlib import Path

BOT_PATH = Path("apps/telegram-bot/bot.py")

# Source-level regression checks avoid importing Telegram in an isolated test environment.
def _source():
    return BOT_PATH.read_text()

def test_non_approval_tasks_do_not_send_queue_status_to_user():
    src = _source()
    assert 'reply_text("Working on it…")' in src
    assert 'Status: {task[\'status\']}' not in src

def test_completion_uses_human_readable_formatter():
    src = _source()
    assert 'format_result(task)' in src
    assert 'Task {task[\'id\'][:8]}: {status}' not in src
