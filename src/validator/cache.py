"""Atomic local fallback cache for the last valid Core API weight matrix."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from threading import Lock

from .core_api import WeightMatrix


class ValidatorCache:
    VERSION = 3

    def __init__(self, directory: str) -> None:
        self._path = Path(directory).expanduser() / "validator-weight-cache.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def load_weight_matrix(self) -> WeightMatrix | None:
        try:
            payload = json.loads(self._path.read_text())
            if payload.get("version") != self.VERSION:
                return None
            matrix_payload = payload["weight_matrix"]
            dt.datetime.fromisoformat(
                matrix_payload["saved_at"].replace("Z", "+00:00")
            )
            refreshed_at = dt.datetime.fromisoformat(
                matrix_payload["refreshed_at"].replace("Z", "+00:00")
            )
            if refreshed_at.tzinfo is None:
                return None
            matrix = WeightMatrix(
                refreshed_at=refreshed_at.astimezone(dt.timezone.utc),
                entries={
                    int(row["uid"]): float(row["score"])
                    for row in matrix_payload["entries"]
                },
            )
            return matrix
        except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
            return None

    def save_weight_matrix(
        self,
        matrix: WeightMatrix,
        saved_at: dt.datetime | None = None,
    ) -> None:
        saved_at = saved_at or dt.datetime.now(dt.timezone.utc)
        payload = {
            "version": self.VERSION,
            "weight_matrix": {
                "refreshed_at": matrix.refreshed_at.isoformat(),
                "saved_at": saved_at.isoformat(),
                "entries": [
                    {"uid": uid, "score": score}
                    for uid, score in sorted(matrix.entries.items())
                ],
            },
        }
        temporary = self._path.with_suffix(".tmp")
        with self._lock:
            temporary.write_text(json.dumps(payload, sort_keys=True))
            temporary.replace(self._path)


__all__ = ["ValidatorCache"]
