import hashlib, json, re, secrets, uuid
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from .models import Task, Device, AuditEvent
from .policy import assess
from .settings import settings


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def audit(db: Session, task_id: str | None, event_type: str, detail: str) -> None:
    db.add(AuditEvent(task_id=task_id, event_type=event_type, detail=detail))


def activity(db: Session, task_id: str, limit: int = 50) -> list[dict]:
    rows = db.query(AuditEvent).filter(AuditEvent.task_id == task_id).order_by(AuditEvent.id.asc()).limit(min(max(limit, 1), 100)).all()
    return [
        {"id": row.id, "type": row.event_type, "detail": row.detail, "created_at": row.created_at.isoformat()}
        for row in rows
    ]


def _result(task: Task) -> dict:
    try:
        return json.loads(task.result_json) if task.result_json else {}
    except json.JSONDecodeError:
        return {}


def conversation_context(db: Session, requester_id: str) -> dict:
    rows = db.query(Task).filter(Task.requester_id == requester_id).order_by(Task.created_at.desc()).limit(12).all()
    active_device = None
    active_application = None
    recent_tasks = []
    for task in reversed(rows):
        result = _result(task)
        actions = result.get("actions") if isinstance(result, dict) else []
        actions = actions if isinstance(actions, list) else []
        for action in actions:
            if action.get("type") == "macos_terminal_command" and task.status == "SUCCEEDED":
                active_application = "Terminal"
                active_device = task.device_id
            elif action.get("type") == "app" and action.get("verified") and task.status == "SUCCEEDED":
                active_application = action.get("app") or active_application
                active_device = task.device_id or active_device
        recent_tasks.append({
            "id": task.id,
            "text": task.text,
            "status": task.status,
            "device_id": task.device_id,
            "created_at": task.created_at.isoformat(),
        })
    return {
        "requester_id": requester_id,
        "active_device": active_device,
        "active_application": active_application,
        "recent_tasks": recent_tasks[-10:],
    }


def _continue_terminal(text: str, context: dict) -> str:
    if context.get("active_application") != "Terminal":
        return text
    match = re.match(r"^(?:run\s+)?((?:docker|kubectl|git|terraform|helm|npm|pnpm|yarn|python|pytest|make)\b.+)$", text.strip(), re.I)
    if not match:
        return text
    return "Open Terminal and run the command " + match.group(1).strip()


def serialize(task: Task):
    return {
        "id": task.id,
        "requester_id": task.requester_id,
        "device_id": task.device_id,
        "text": task.text,
        "status": task.status,
        "risk": task.risk,
        "requires_approval": task.requires_approval,
        "approved": task.approved,
        "plan": json.loads(task.plan_json) if task.plan_json else None,
        "result": _result(task) if task.result_json else None,
        "error": task.error,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


def bot_auth(value: str):
    if not secrets.compare_digest(value or "", settings.control_plane_bot_token):
        raise PermissionError("invalid bot token")


def online_devices(db: Session):
    cutoff = datetime.utcnow() - timedelta(seconds=settings.runner_offline_after_seconds)
    return db.query(Device).filter(Device.status == "online", Device.last_seen_at >= cutoff).order_by(Device.last_seen_at.desc()).all()


def resolve_device(db: Session, requested_device_id: str | None) -> Device:
    if requested_device_id:
        device = db.get(Device, requested_device_id)
        if not device:
            raise LookupError(f"device '{requested_device_id}' is not registered")
        cutoff = datetime.utcnow() - timedelta(seconds=settings.runner_offline_after_seconds)
        if device.status != "online" or not device.last_seen_at or device.last_seen_at < cutoff:
            raise LookupError(f"device '{requested_device_id}' is offline")
        return device
    devices = online_devices(db)
    if not devices:
        raise LookupError("no registered runner is online")
    return devices[0]


def create_task(db: Session, requester_id: str, text: str, device_id: str | None):
    context = conversation_context(db, requester_id)
    original_text = text
    text = _continue_terminal(text, context)
    chosen_device_id = device_id or context.get("active_device")
    device = resolve_device(db, chosen_device_id)
    decision = assess(text)
    task = Task(
        id=uuid.uuid4().hex,
        requester_id=requester_id,
        device_id=device.id,
        text=text,
        status="WAITING_FOR_APPROVAL" if decision.requires_approval else "QUEUED",
        risk=decision.risk,
        requires_approval=decision.requires_approval,
        approval_expires_at=datetime.utcnow()+timedelta(seconds=settings.approval_ttl_seconds) if decision.requires_approval else None,
    )
    db.add(task)
    audit(db, task.id, "TASK_RECEIVED", original_text)
    if text != original_text:
        audit(db, task.id, "CONTEXT_APPLIED", "Continued the active Terminal conversation: " + text)
    audit(db, task.id, "TASK_CREATED", decision.reason)
    audit(db, task.id, "TASK_QUEUED" if task.status == "QUEUED" else "TASK_WAITING_FOR_APPROVAL", "Queued for " + device.id if task.status == "QUEUED" else "Awaiting approval")
    db.commit()
    db.refresh(task)
    return task


def authorize_runner(db: Session, device_id: str, token: str):
    device = db.get(Device, device_id)
    if not device or not secrets.compare_digest(device.token_hash, digest(token)):
        raise PermissionError("invalid runner credentials")
    device.status = "online"
    device.last_seen_at = datetime.utcnow()
    db.commit()
    return device


def register_runner(db: Session, payload):
    device = db.get(Device, payload.id)
    if device and not secrets.compare_digest(device.token_hash, digest(payload.token)):
        raise PermissionError("runner token mismatch")
    if not device:
        device = Device(id=payload.id, token_hash=digest(payload.token), os_name=payload.os_name, hostname=payload.hostname)
        db.add(device)
    device.status="online"
    device.last_seen_at=datetime.utcnow()
    audit(db,None,"DEVICE_REGISTERED",payload.id)
    db.commit()
    db.refresh(device)
    return device


def next_task(db: Session, device_id: str):
    task = db.query(Task).filter(Task.device_id == device_id, Task.status == "QUEUED").order_by(Task.created_at).first()
    if task:
        task.status="DISPATCHED"
        audit(db,task.id,"TASK_DISPATCHED","Assigned to " + device_id)
        db.commit()
        db.refresh(task)
    return task
