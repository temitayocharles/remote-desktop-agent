import json, platform, subprocess, webbrowser
from pathlib import Path
from .config import config
HIGH_TERMS=("rm -rf","delete","destroy","drop database","terraform apply","kubectl delete","git push --force","shutdown","reboot","format ","wipe","payment","purchase","transfer")
def requires_approval(value): return any(x in value.lower() for x in HIGH_TERMS)
def artifact(task_id):
    path=Path(config.runner_artifact_dir); path.mkdir(parents=True,exist_ok=True); return path/(task_id+".json")
def action(item,approved):
    kind=item.get("type"); value=item.get("value","")
    if not kind or not value: raise ValueError("malformed action")
    if requires_approval(value) and not approved: raise PermissionError("runner rejected high-impact action without recorded approval")
    if kind=="shell":
        run=subprocess.run(value,shell=True,capture_output=True,text=True,timeout=config.task_timeout_seconds)
        return {"type":kind,"exit_code":run.returncode,"stdout":run.stdout[-12000:],"stderr":run.stderr[-12000:]}
    if kind=="browser":
        if not value.startswith(("http://","https://")): raise ValueError("browser requires an http(s) URL")
        webbrowser.open(value,new=2); return {"type":kind,"opened":value}
    if kind=="app":
        if platform.system()=="Darwin": run=subprocess.run(["open","-a",value],capture_output=True,text=True)
        elif platform.system()=="Windows": run=subprocess.run(["cmd","/c","start","",value],capture_output=True,text=True)
        else: run=subprocess.run([value],capture_output=True,text=True)
        return {"type":kind,"exit_code":run.returncode,"stdout":run.stdout[-4000:],"stderr":run.stderr[-4000:]}
    if kind=="file_read":
        path=Path(value).expanduser().resolve(); return {"type":kind,"path":str(path),"content":path.read_text(errors="replace")[:12000]}
    if kind=="file_write":
        if "\n" not in value: raise ValueError("write format requires first line as path and remaining content")
        target,content=value.split("\n",1); path=Path(target.strip()).expanduser().resolve(); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(content); return {"type":kind,"path":str(path),"bytes":len(content.encode())}
    raise ValueError("unsupported action type: "+kind)
def execute(task,plan):
    actions=plan.get("actions",[])
    if not actions: return {"summary":plan.get("summary"),"actions":[],"note":"no executable action"}
    result={"summary":plan.get("summary",""),"actions":[action(x,task.get("approved",False)) for x in actions]}
    artifact(task["id"]).write_text(json.dumps(result,indent=2)); return result
