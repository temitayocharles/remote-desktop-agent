from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class EvidenceWriter:
    def __init__(self, root: str | Path, task_id: str):
        self.directory = Path(root).expanduser().resolve() / task_id
        self.directory.mkdir(parents=True, exist_ok=True)
        self.events_path = self.directory / "events.jsonl"

    def event(self, event_type: str, **data: Any) -> dict[str, Any]:
        record = {
            "at": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            **data,
        }
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")
        return record

    def result(self, payload: dict[str, Any]) -> Path:
        path = self.directory / "result.json"
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return path
