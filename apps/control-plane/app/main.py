import json
from fastapi import FastAPI, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from .database import Base, engine, get_db
from .models import Task, Device
from .schemas import TaskCreate, TaskUpdate, DeviceRegister, DeviceHeartbeat
from .service import bot_auth, create_task, serialize, register_runner, authorize_runner, next_task, audit
from .llm import classify, chat_reply, LLMUnavailable

app = FastAPI(title="Telegram Operator Agent", version="2.1.0")

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)

def authorize_bot(x_bot_token: str = Header(default="")):
    try:
        bot_auth(x_bot_token)
    except PermissionError as exc:
        raise HTTPException(401, str(exc))

def authorize_device(device_id: str, x_runner_token: str = Header(default=""), db: Session = Depends(get_db)):
    try:
        return authorize_runner(db, device_id, x_runner_token)
    except PermissionError as exc:
        raise HTTPException(401, str(exc))

@app.get("/healthz")
def health():
    return {"status": "ok"}

@app.post("/v1/intake", dependencies=[Depends(authorize_bot)])
def intake(payload: TaskCreate, db: Session = Depends(get_db)):
    try:
        decision = classify(payload.text)
        if decision["kind"] == "chat":
            return {"kind": "chat", "reply": chat_reply(payload.text), "reason": decision.get("reason", "conversation")}
        task = create_task(db, payload.requester_id, payload.text, payload.device_id)
        return {"kind": "task", "task": serialize(task), "reason": decision.get("reason", "operational intent")}
    except LookupError as exc:
        raise HTTPException(409, str(exc))
    except LLMUnavailable as exc:
        raise HTTPException(503, str(exc))
    except Exception as exc:
        raise HTTPException(422, f"Unable to interpret request: {type(exc).__name__}: {exc}")

@app.post("/v1/tasks", dependencies=[Depends(authorize_bot)])
def submit(payload: TaskCreate, db: Session = Depends(get_db)):
    try:
        return serialize(create_task(db, payload.requester_id, payload.text, payload.device_id))
    except LookupError as exc:
        raise HTTPException(409, str(exc))

@app.get("/v1/tasks", dependencies=[Depends(authorize_bot)])
def tasks(limit: int = 10, db: Session = Depends(get_db)):
    return [serialize(x) for x in db.query(Task).order_by(Task.created_at.desc()).limit(min(limit, 100)).all()]

@app.get("/v1/tasks/{task_id}", dependencies=[Depends(authorize_bot)])
def task(task_id: str, db: Session = Depends(get_db)):
    item = db.get(Task, task_id)
    if not item:
        raise HTTPException(404, "task not found")
    return serialize(item)

@app.post("/v1/tasks/{task_id}/approve", dependencies=[Depends(authorize_bot)])
def approve(task_id: str, requester_id: str, db: Session = Depends(get_db)):
    item = db.get(Task, task_id)
    if not item:
        raise HTTPException(404, "task not found")
    if item.requester_id != requester_id:
        raise HTTPException(403, "requester mismatch")
    if not item.requires_approval:
        raise HTTPException(409, "approval not required")
    if item.approval_expires_at and item.approval_expires_at.timestamp() < __import__('time').time():
        item.status = "FAILED_POLICY"
        db.commit()
        raise HTTPException(409, "approval expired")
    item.approved = True
    item.status = "QUEUED"
    audit(db, item.id, "TASK_APPROVED", "Approved through Telegram")
    db.commit()
    return serialize(item)

@app.post("/v1/tasks/{task_id}/cancel", dependencies=[Depends(authorize_bot)])
def cancel(task_id: str, requester_id: str, db: Session = Depends(get_db)):
    item = db.get(Task, task_id)
    if not item:
        raise HTTPException(404, "task not found")
    if item.requester_id != requester_id:
        raise HTTPException(403, "requester mismatch")
    if item.status in {"SUCCEEDED", "FAILED", "CANCELLED", "FAILED_POLICY"}:
        raise HTTPException(409, "task is terminal")
    item.status = "CANCELLED"
    audit(db, item.id, "TASK_CANCELLED", "Cancelled through Telegram")
    db.commit()
    return serialize(item)

@app.post("/v1/runners/register")
def register(payload: DeviceRegister, db: Session = Depends(get_db)):
    try:
        device = register_runner(db, payload)
        return {"id": device.id, "status": device.status}
    except PermissionError as exc:
        raise HTTPException(401, str(exc))

@app.post("/v1/runners/{device_id}/heartbeat")
def heartbeat(device_id: str, payload: DeviceHeartbeat, db: Session = Depends(get_db)):
    try:
        device = authorize_runner(db, device_id, payload.token)
        device.status = payload.status
        db.commit()
        return {"status": "ok"}
    except PermissionError as exc:
        raise HTTPException(401, str(exc))

@app.get("/v1/runners/{device_id}/next")
def lease(device_id: str, _: Device = Depends(authorize_device), db: Session = Depends(get_db)):
    item = next_task(db, device_id)
    return {"task": serialize(item) if item else None}

@app.get("/v1/runners/{device_id}/tasks/{task_id}")
def runner_task(task_id: str, device_id: str, _: Device = Depends(authorize_device), db: Session = Depends(get_db)):
    item = db.get(Task, task_id)
    if not item or item.device_id != device_id:
        raise HTTPException(404, "task not found")
    return {"id": item.id, "status": item.status}

@app.post("/v1/runners/{device_id}/tasks/{task_id}")
def update(device_id: str, task_id: str, payload: TaskUpdate, _: Device = Depends(authorize_device), db: Session = Depends(get_db)):
    item = db.get(Task, task_id)
    if not item or item.device_id != device_id:
        raise HTTPException(404, "task not found")
    if item.status == "CANCELLED" and payload.status != "CANCELLED":
        raise HTTPException(409, "task has been cancelled")
    if item.status in {"SUCCEEDED", "FAILED", "FAILED_POLICY"} and payload.status != item.status:
        raise HTTPException(409, "task is terminal")
    item.status = payload.status
    if payload.plan is not None:
        item.plan_json = json.dumps(payload.plan)
    if payload.result is not None:
        item.result_json = json.dumps(payload.result)
    if payload.error is not None:
        item.error = payload.error
    audit(db, item.id, "TASK_" + payload.status, payload.error or "runner update")
    db.commit()
    return serialize(item)

@app.get("/v1/devices", dependencies=[Depends(authorize_bot)])
def devices(db: Session = Depends(get_db)):
    return [{"id": d.id, "os": d.os_name, "hostname": d.hostname, "status": d.status, "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None} for d in db.query(Device).all()]
