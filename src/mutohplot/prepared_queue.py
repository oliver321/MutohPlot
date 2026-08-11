"""Persistent storage for prepared plot payloads and their order."""

from __future__ import annotations

import base64
import json
import os
import tempfile
import threading
from copy import deepcopy
from pathlib import Path


class PreparedQueueStore:
    def __init__(self, path: str | Path | None = None) -> None:
        configured = os.environ.get("MUTOHPLOT_PREPARED_QUEUE")
        self.path = Path(path or configured or Path.home() / ".local/share/mutohplot/queue.json")
        self.lock = threading.Lock()
        self._items = self._load()

    def _load(self) -> list[dict]:
        if not self.path.is_file():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                raise TypeError("root is not a list")
            items = []
            for item in raw:
                restored = dict(item)
                restored["data"] = base64.b64decode(restored.pop("data_base64"), validate=True)
                items.append(restored)
            return items
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise ValueError(f"Warteschlange konnte nicht geladen werden: {error}") from error

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serializable = []
        for item in self._items:
            encoded = deepcopy(item)
            encoded["data_base64"] = base64.b64encode(encoded.pop("data")).decode("ascii")
            serializable.append(encoded)
        handle, temporary = tempfile.mkstemp(prefix="queue-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(serializable, stream, ensure_ascii=False)
                stream.write("\n")
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def snapshot(self) -> list[dict]:
        with self.lock:
            return deepcopy(self._items)

    def append(self, item: dict) -> None:
        with self.lock:
            self._items.append(deepcopy(item))
            self._save()

    def remove(self, token: str) -> None:
        with self.lock:
            self._items = [item for item in self._items if item.get("token") != token]
            self._save()

    def reorder(self, tokens: list[str]) -> None:
        with self.lock:
            by_token = {item["token"]: item for item in self._items}
            if set(tokens) != set(by_token):
                raise ValueError("Warteschlangenreihenfolge ist unvollständig")
            self._items = [by_token[token] for token in tokens]
            self._save()
