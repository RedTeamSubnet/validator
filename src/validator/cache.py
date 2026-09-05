"""Local validator coordination cache; never communicates with a REST service."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock


class ValidatorCache:
    """Persist only seen commits and the latest successful score matrix."""

    def __init__(self, directory: str) -> None:
        self._path = Path(directory).expanduser() / "relay-validator-cache.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._data = self._load()

    def has_seen(self, identity: str) -> bool:
        return identity in self._data["seen_commits"]

    def mark_seen(self, identity: str) -> None:
        with self._lock:
            self._data["seen_commits"].add(identity)
            self._save()

    @property
    def latest_weight_matrix(self) -> list[float] | None:
        return self._data.get("latest_weight_matrix")

    @latest_weight_matrix.setter
    def latest_weight_matrix(self, value: list[float]) -> None:
        with self._lock:
            self._data["latest_weight_matrix"] = value
            self._save()

    def _load(self) -> dict:
        try:
            payload = json.loads(self._path.read_text())
            return {
                "seen_commits": set(payload.get("seen_commits", [])),
                "latest_weight_matrix": payload.get("latest_weight_matrix"),
            }
        except (FileNotFoundError, OSError, ValueError):
            return {"seen_commits": set(), "latest_weight_matrix": None}

    def _save(self) -> None:
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(json.dumps({
            "seen_commits": sorted(self._data["seen_commits"]),
            "latest_weight_matrix": self._data["latest_weight_matrix"],
        }))
        temporary.replace(self._path)


__all__ = ["ValidatorCache"]
