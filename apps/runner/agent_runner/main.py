import logging
import os
import socket
import time
from pathlib import Path

from .client import Client
from .config import config
from .executor import TaskCancelled, execute
from .planner import plan

logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(message)s")


def _write_pid() -> Path | None:
    if not config.runner_pid_file:
        return None
    path = Path(config.runner_pid_file).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(os.getpid()), encoding="utf-8")
    return path


def _clear_pid(path: Path | None) -> None:
    if not path:
        return
    try:
        if path.exists() and path.read_text(encoding="utf-8").strip() == str(os.getpid()):
            path.unlink()
    except OSError:
        logging.warning("could not remove runner PID file: %s", path)


def main():
    if not config.runner_id or not config.runner_token:
        raise RuntimeError("RUNNER_ID and RUNNER_TOKEN must be configured")
    pid_path = _write_pid()
    try:
        client = Client()
        client.register(socket.gethostname())
        logging.info("runner registered: %s", config.runner_id)
        while True:
            task = None
            try:
                client.heartbeat()
                task = client.next_task()
                if not task:
                    time.sleep(config.runner_poll_seconds)
                    continue
                client.update(task["id"], "RUNNING")
                task_plan = plan(task["text"])
                client.update(task["id"], "RUNNING", plan=task_plan)
                result = execute(task, task_plan, cancelled=lambda: client.task_state(task["id"]) == "CANCELLED")
                client.update(task["id"], "SUCCEEDED", result=result)
            except TaskCancelled as exc:
                logging.info("task cancelled: %s", exc)
                if task:
                    try:
                        client.update(task["id"], "CANCELLED", error=str(exc))
                    except Exception:
                        logging.exception("cancellation reporting failed")
            except Exception as exc:
                logging.exception("runner cycle failed")
                if task:
                    try:
                        if client.task_state(task["id"]) == "CANCELLED":
                            client.update(task["id"], "CANCELLED", error="cancelled during execution")
                        else:
                            client.update(task["id"], "FAILED", error=f"{type(exc).__name__}: {exc}")
                    except Exception:
                        logging.exception("failure reporting failed")
                time.sleep(max(config.runner_poll_seconds, 3))
    finally:
        _clear_pid(pid_path)


if __name__ == "__main__":
    main()
