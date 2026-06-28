import logging, socket, time
from .client import Client
from .planner import plan
from .executor import execute
from .config import config
logging.basicConfig(level="INFO",format="%(asctime)s %(levelname)s %(message)s")
def main():
    if not config.runner_id or not config.runner_token:
        raise RuntimeError("RUNNER_ID and RUNNER_TOKEN must be configured")
    client=Client(); client.register(socket.gethostname()); logging.info("runner registered: %s",config.runner_id)
    while True:
        task=None
        try:
            client.heartbeat(); task=client.next_task()
            if not task: time.sleep(config.runner_poll_seconds); continue
            client.update(task["id"],"RUNNING")
            task_plan=plan(task["text"]); client.update(task["id"],"RUNNING",plan=task_plan)
            client.update(task["id"],"SUCCEEDED",result=execute(task,task_plan))
        except Exception as exc:
            logging.exception("runner cycle failed")
            if task:
                try: client.update(task["id"],"FAILED",error=f"{type(exc).__name__}: {exc}")
                except Exception: logging.exception("failure reporting failed")
            time.sleep(max(config.runner_poll_seconds,3))
if __name__=="__main__": main()
