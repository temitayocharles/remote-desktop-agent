import pytest

from agent_runner.executor import TaskCancelled, VerificationError, execute
from agent_runner.planner import explicit


def test_shell():
    assert explicit("shell: echo hello")["actions"][0]["type"] == "shell"


def test_browser():
    assert explicit("https://example.com")["actions"][0]["type"] == "browser"


def test_chatgpt_image_workflow():
    plan = explicit("Open ChatGPT and create a hyper-realistic image of a beer and save the photo in desktop")
    action = plan["actions"][0]
    assert action["type"] == "browser_workflow"
    assert action["value"]["workflow"] == "chatgpt_image"


def test_junk_mail_workflow():
    plan = explicit("Open Mail and search for spam emails")
    assert plan["actions"][0]["type"] == "macos_mail_search"


def test_failed_shell_is_not_success(tmp_path, monkeypatch):
    monkeypatch.setattr("agent_runner.executor.config.runner_artifact_dir", str(tmp_path))
    with pytest.raises(VerificationError):
        execute({"id": "bad-shell", "approved": False}, {"actions": [{"type": "shell", "value": "exit 7"}]})


def test_cancelled_task_stops_before_action(tmp_path, monkeypatch):
    monkeypatch.setattr("agent_runner.executor.config.runner_artifact_dir", str(tmp_path))
    with pytest.raises(TaskCancelled):
        execute({"id": "cancelled", "approved": False}, {"actions": [{"type": "shell", "value": "echo no"}]}, cancelled=lambda: True)
