"""Persistent plot-job history for the web interface."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from copy import deepcopy
from pathlib import Path


class JobHistory:
    def __init__(self, path: str | Path | None = None, limit: int = 100) -> None:
        configured = os.environ.get("MUTOHPLOT_JOB_HISTORY")
        self.path = Path(path or configured or Path.home() / ".local/share/mutohplot/jobs.json")
        self.limit = limit
        self.lock = threading.Lock()
        self._jobs = self._load()

    def _load(self) -> list[dict]:
        if not self.path.is_file():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Auftragsverlauf konnte nicht geladen werden: {error}") from error
        if not isinstance(raw, list) or any(not isinstance(job, dict) for job in raw):
            raise ValueError("Auftragsverlauf hat ein ungültiges Format")
        return raw[-self.limit :]

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(prefix="jobs-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(self._jobs, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def add(self, job: dict) -> dict:
        with self.lock:
            self._jobs.append(deepcopy(job))
            self._jobs = self._jobs[-self.limit :]
            self._save()
            return deepcopy(job)

    def update(self, job_id: str, *, persist: bool = True, **changes) -> dict:
        with self.lock:
            for job in reversed(self._jobs):
                if job.get("id") == job_id:
                    job.update(changes)
                    if persist:
                        self._save()
                    return deepcopy(job)
        raise KeyError(job_id)

    def snapshot(self, limit: int = 20) -> list[dict]:
        with self.lock:
            return deepcopy(list(reversed(self._jobs[-limit:])))
