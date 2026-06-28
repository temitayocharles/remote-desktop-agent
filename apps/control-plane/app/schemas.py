from typing import Any
from pydantic import BaseModel, Field
class TaskCreate(BaseModel):
    requester_id: str
    text: str = Field(min_length=1, max_length=20000)
    device_id: str | None = None
class TaskUpdate(BaseModel):
    status: str
    plan: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
class DeviceRegister(BaseModel):
    id: str
    token: str
    os_name: str
    hostname: str
class DeviceHeartbeat(BaseModel):
    token: str
    status: str = "online"
