"""Finds the recorded camera images of a dart (see DetectionService._record): an index from
(game id, event seq) to the recording folder, built lazily from the meta files."""

import json
import threading
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)


class RecordingIndex:
    def __init__(self, recordings_dir: Path) -> None:
        self.dir = recordings_dir
        self._lock = threading.Lock()
        self._index: dict[tuple[int, int], tuple[str, dict[str, Any]]] | None = None

    def _build(self) -> dict[tuple[int, int], tuple[str, dict[str, Any]]]:
        index: dict[tuple[int, int], tuple[str, dict[str, Any]]] = {}
        if self.dir.is_dir():
            for meta_file in sorted(self.dir.glob("*/*/meta.json")):
                try:
                    meta = json.loads(meta_file.read_text())
                except (OSError, ValueError):
                    continue
                self._put(index, meta_file.parent, meta)
        log.info("recording_index_built", recordings=len(index))
        return index

    def _put(
        self,
        index: dict[tuple[int, int], tuple[str, dict[str, Any]]],
        folder: Path,
        meta: dict[str, Any],
    ) -> None:
        game_id, seq = meta.get("game_id"), meta.get("event_seq")
        if isinstance(game_id, int) and isinstance(seq, int):
            index[(game_id, seq)] = (folder.relative_to(self.dir).as_posix(), meta)

    def add(self, folder: Path, meta: dict[str, Any]) -> None:
        with self._lock:
            if self._index is not None:
                self._put(self._index, folder, meta)

    def get(self, game_id: int, seq: int) -> tuple[str, dict[str, Any]] | None:
        with self._lock:
            if self._index is None:
                self._index = self._build()
            return self._index.get((game_id, seq))

    def image_path(self, game_id: int, seq: int, camera_id: str, kind: str) -> Path | None:
        found = self.get(game_id, seq)
        if found is None or kind not in ("before", "after"):
            return None
        path = (self.dir / found[0] / f"{camera_id}_{kind}.jpg").resolve()
        # never leave the recordings folder
        if self.dir.resolve() not in path.parents or not path.is_file():
            return None
        return path
