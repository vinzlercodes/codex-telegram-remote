from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                return {
                    "active_sessions": {},
                    "pending_approvals": {},
                    "socket_path": "",
                    "last_task_summary": "",
                }
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
            data.setdefault("active_sessions", {})
            data.setdefault("pending_approvals", {})
            data.setdefault("socket_path", "")
            data.setdefault("last_task_summary", "")
            return data

    def save(self, data: dict[str, Any]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(data, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            tmp.replace(self.path)

    def update(self, fn):
        with self._lock:
            data = self.load()
            result = fn(data)
            self.save(data)
            return result
