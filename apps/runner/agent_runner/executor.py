from __future__ import annotations

import json
import platform
import subprocess
import time
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Any, Callable

from .browser import run_browser_workflow
from .config import config
from .evidence import EvidenceWriter
from .macos import open_application, run_terminal_command, search_junk_mail

HIGH_TERMS = (
    "rm -rf", "delete", "destroy", "drop database", "terraform apply", "kubectl delete",
    "git push --force", "shutdown", "reboot", "format ", "wipe", "payment", "purchase", "transfer",
)


class TaskCancelled(RuntimeError):
    pass


class VerificationError(RuntimeError):
    pass


class UnsupportedTargetError(RuntimeError):
    pass


def requires_approval(value: Any) -> bool:
    return any(term in str(value).lower() for term in HIGH_TERMS)


def _cancelled(check: Callable[[], bool] | None) -> None:
    if check and check():
        raise TaskCancelled("task was cancelled before the next action could run")


def _run_shell(command: str, cancelled: Callable[[], bool] | None) -> dict[str, Any]:
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + config.task_timeout_seconds
    try:
        while process.poll() is None:
            _cancelled(cancelled)
            if time.monotonic() >= deadline:
                process.kill()
                stdout, stderr = process.communicate()
                raise TimeoutError(f"shell command exceeded {config.task_timeout_seconds} seconds: {stderr[-1000:]}")
            time.sleep(0.25)
    except TaskCancelled:
        process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
        raise
    stdout, stderr = process.communicate()
    result = {"type": "shell", "exit_code": process.returncode, "stdout": stdout[-12000:], "stderr": stderr[-12000:]}
    if process.returncode != 0:
        raise VerificationError(f"shell command exited {process.returncode}: {stderr[-2000:] or stdout[-2000:]}")
    result["verified"] = True
    result["completion"] = "executed"
    return result


def _open_url(url: str, browser: str | None = None) -> dict[str, Any]:
    if not url.startswith(("http://", "https://")):
        raise ValueError("browser requires an http(s) URL")
    if browser and platform.system() == "Darwin":
        completed = subprocess.run(["open", "-a", browser, url], capture_output=True, text=True, timeout=30)
        if completed.returncode != 0:
            raise VerificationError(completed.stderr.strip() or f"could not open {browser}")
        return {"type": "browser", "opened": url, "browser": browser, "verified": True, "completion": "launched"}
    opened = webbrowser.open(url, new=2)
    if not opened:
        raise VerificationError("the operating system did not accept the browser launch request")
    return {"type": "browser", "opened": url, "browser": browser, "verified": True, "completion": "launched"}


def _browser_search(payload: dict[str, Any]) -> dict[str, Any]:
    query = str(payload.get("query") or "").strip()
    if not query:
        raise ValueError("browser_search requires a query")
    browser = str(payload.get("browser") or "").strip() or None
    url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
    result = _open_url(url, browser)
    result.update({"type": "browser_search", "query": query, "completion": "search_launched"})
    return result


def _verify(item: dict[str, Any], result: dict[str, Any]) -> None:
    rule = item.get("verify")
    if rule is None:
        if result.get("type") in {"browser_workflow", "macos_terminal_command", "macos_mail_search", "shell", "app", "browser", "browser_search"} and not result.get("verified"):
            raise VerificationError(f"{result.get('type')} returned without verification")
        return
    if not isinstance(rule, dict):
        raise VerificationError("verify must be an object")
    if rule.get("file_exists"):
        path = Path(str(rule["file_exists"])).expanduser()
        if not path.is_file() or path.stat().st_size <= 0:
            raise VerificationError(f"expected output file is missing: {path}")
    if rule.get("result_verified") and not result.get("verified"):
        raise VerificationError("action did not report verified completion")


def action(item: dict[str, Any], approved: bool, cancelled: Callable[[], bool] | None = None, evidence: EvidenceWriter | None = None) -> dict[str, Any]:
    _cancelled(cancelled)
    kind = item.get("type")
    value = item.get("value", "")
    if not kind or value in (None, ""):
        raise ValueError("malformed action")
    if requires_approval(value) and not approved:
        raise PermissionError("runner rejected high-impact action without recorded approval")
    if evidence:
        evidence.event("ACTION_STARTED", action_type=kind)
    if kind == "shell":
        result = _run_shell(str(value), cancelled)
    elif kind == "browser":
        result = _open_url(str(value))
    elif kind == "browser_open":
        payload = json.loads(value) if isinstance(value, str) else value
        if not isinstance(payload, dict):
            raise ValueError("browser_open requires an object value")
        result = _open_url(str(payload.get("url") or ""), str(payload.get("browser") or "").strip() or None)
    elif kind == "browser_search":
        payload = json.loads(value) if isinstance(value, str) else value
        if not isinstance(payload, dict):
            raise ValueError("browser_search requires an object value")
        result = _browser_search(payload)
    elif kind == "browser_workflow":
        payload = json.loads(value) if isinstance(value, str) else value
        if not isinstance(payload, dict):
            raise ValueError("browser_workflow requires an object value")
        result = run_browser_workflow(payload)
    elif kind == "app":
        result = open_application(str(value)) if platform.system() == "Darwin" else {"type": "app", "app": str(value), "verified": False}
        if platform.system() != "Darwin":
            run = subprocess.run([str(value)], capture_output=True, text=True)
            result.update({"exit_code": run.returncode, "stdout": run.stdout[-4000:], "stderr": run.stderr[-4000:], "verified": run.returncode == 0})
        result.setdefault("completion", "launched")
    elif kind == "macos_terminal_command":
        payload = json.loads(value) if isinstance(value, str) else value
        if not isinstance(payload, dict):
            raise ValueError("macos_terminal_command requires an object value")
        result = run_terminal_command(str(payload.get("command") or ""))
        if result.get("exit_code") != 0:
            raise VerificationError(f"Terminal command exited {result.get('exit_code')}: {result.get('stdout', '')[-2000:]}")
    elif kind == "macos_mail_search":
        payload = json.loads(value) if isinstance(value, str) else value
        if not isinstance(payload, dict):
            raise ValueError("macos_mail_search requires an object value")
        result = search_junk_mail(str(payload.get("query") or ""), int(payload.get("limit", 20)))
        result.setdefault("completion", "searched")
    elif kind == "file_read":
        path = Path(str(value)).expanduser().resolve()
        result = {"type": kind, "path": str(path), "content": path.read_text(errors="replace")[:12000], "verified": path.is_file(), "completion": "read"}
    elif kind == "file_write":
        if "\n" not in str(value):
            raise ValueError("write format requires first line as path and remaining content")
        target, content = str(value).split("\n", 1)
        path = Path(target.strip()).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        result = {"type": kind, "path": str(path), "bytes": len(content.encode()), "verified": path.is_file() and path.read_text() == content, "completion": "written"}
    elif kind == "unsupported_target":
        raise UnsupportedTargetError(str(value))
    else:
        raise ValueError("unsupported action type: " + str(kind))
    _verify(item, result)
    if evidence:
        evidence.event("ACTION_SUCCEEDED", action_type=kind, verified=result.get("verified", False), result=result)
    return result


def execute(task: dict[str, Any], plan: dict[str, Any], cancelled: Callable[[], bool] | None = None) -> dict[str, Any]:
    actions = plan.get("actions", [])
    if not actions:
        raise VerificationError("plan contains no executable actions")
    evidence = EvidenceWriter(config.runner_artifact_dir, task["id"])
    evidence.event("TASK_STARTED", summary=plan.get("summary", ""), action_count=len(actions))
    results = []
    for index, item in enumerate(actions, start=1):
        _cancelled(cancelled)
        evidence.event("CHECKPOINT", step=index, status="starting")
        results.append(action(item, task.get("approved", False), cancelled, evidence))
        evidence.event("CHECKPOINT", step=index, status="complete")
    result = {"summary": plan.get("summary", ""), "actions": results, "verified": all(x.get("verified", False) for x in results), "evidence_path": str(evidence.directory)}
    evidence.event("TASK_SUCCEEDED", verified=result["verified"])
    evidence.result(result)
    return result
