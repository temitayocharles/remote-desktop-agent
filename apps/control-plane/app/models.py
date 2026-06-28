from datetime import datetime
from sqlalchemy import String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

class Device(Base):
    __tablename__ = "devices"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    os_name: Mapped[str] = mapped_column(String(32), nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="offline")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    requester_id: Mapped[str] = mapped_column(String(64), nullable=False)
    device_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("devices.id"), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    risk: Mapped[str] = mapped_column(String(16), nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    plan_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
