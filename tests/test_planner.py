import pytest

from agent_runner.executor import TaskCancelled, UnsupportedTargetError, VerificationError, execute
from agent_runner.planner import explicit


def test_shell():
    assert explicit("shell: echo hello")["actions"][0]["type"] == "shell"


def test_browser():
    assert explicit("https://example.com")["actions"][0]["type"] == "browser"


def test_chatgpt_image_workflow():
    plan = explicit("Open ChatGPT and create a hyper-realistic image of a beer and save the photo in desktop")
    assert plan["actions"][0]["type"] == "browser_workflow"


def test_terminal_command_honors_both_requested_steps():
    plan = explicit("Open terminal or iterm and run the command pwd")
    assert [item["type"] for item in plan["actions"]] == ["app", "shell"]
    assert plan["actions"][0]["value"] == "Terminal"
    assert plan["actions"][1]["value"] == "pwd"


def test_browser_search_workflow():
    plan = explicit("open safari browser and search for best gym in shelburne, ON")
    assert plan["actions"][0]["type"] == "browser_search"


def test_junk_mail_workflow():
    assert explicit("Open Mail and search for spam emails")["actions"][0]["type"] == "macos_mail_search"


def test_resume_search_is_bounded():
    plan = explicit("I want you to search for any file named Resume on my mac and send me a list")
    assert "mdfind" in plan["actions"][0]["value"]


def test_phone_request_is_explicitly_unsupported():
    assert explicit("open message on my phone and send I love you to madam dearest")["actions"][0]["type"] == "unsupported_target"


def test_failed_shell_is_not_success(tmp_path, monkeypatch):
    monkeypatch.setattr("agent_runner.executor.config.runner_artifact_dir", str(tmp_path))
    with pytest.raises(VerificationError):
        execute({"id": "bad-shell", "approved": False}, {"actions": [{"type": "shell", "value": "exit 7"}]})


def test_cancelled_task_stops_before_action(tmp_path, monkeypatch):
    monkeypatch.setattr("agent_runner.executor.config.runner_artifact_dir", str(tmp_path))
    with pytest.raises(TaskCancelled):
        execute({"id": "cancelled", "approved": False}, {"actions": [{"type": "shell", "value": "echo no"}]}, cancelled=lambda: True)


def test_unsupported_target_is_not_silent(tmp_path, monkeypatch):
    monkeypatch.setattr("agent_runner.executor.config.runner_artifact_dir", str(tmp_path))
    with pytest.raises(UnsupportedTargetError):
        execute({"id": "phone", "approved": False}, {"actions": [{"type": "unsupported_target", "value": "No phone runner is registered."}]})
