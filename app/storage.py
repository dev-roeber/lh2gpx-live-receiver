from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from .models import LiveLocationRequest


class NDJSONStorage:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, payload: LiveLocationRequest) -> Path:
        record = payload.model_dump(mode="json")
        record["receivedAt"] = datetime.now(timezone.utc).isoformat()
        line = json.dumps(record, ensure_ascii=True, sort_keys=True)

        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())

        return self.path

