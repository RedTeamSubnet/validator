import time
from datetime import datetime, timezone
from typing import Any, Callable

import requests


class RestCoreClient:
    def __init__(
        self,
        base_url: str,
        header_fn: Callable[[dict[str, Any]], dict[str, str]] | None = None,
        timeout: int = 60,
        max_retries: int = 3,
    ):
        self.base_url = self._normalize_base_url(base_url)
        self.header_fn = header_fn
        self.timeout = timeout
        self.max_retries = max_retries

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        url = str(base_url).rstrip("/")
        if not url.endswith("/api/v1"):
            url = f"{url}/api/v1"
        return url

    def _headers(self, payload: dict[str, Any] | None = None) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.header_fn:
            headers.update(self.header_fn(payload or {}))
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json,
                    headers=self._headers(json),
                    timeout=self.timeout,
                )
                response.raise_for_status()
                return response.json()
            except Exception as err:
                last_error = err
                if attempt == self.max_retries - 1:
                    break
                time.sleep(min(2**attempt, 8))
        raise RuntimeError(f"Core API request failed: {method} {url}: {last_error}")

    def fetch_active_challenges(self) -> dict[str, dict[str, Any]]:
        body = self._request(
            "GET",
            "/challenges/",
            params={"limit": 1000, "expands": "config"},
        )
        now = datetime.now(timezone.utc)
        active: dict[str, dict[str, Any]] = {}
        for challenge in body.get("data", []):
            if not challenge.get("is_enabled", True) or challenge.get("deleted_at"):
                continue
            start_at = self._parse_dt(challenge.get("start_at"))
            end_at = self._parse_dt(challenge.get("end_at"))
            if start_at and start_at > now:
                continue
            if end_at and now >= end_at:
                continue
            active[challenge["name"]] = challenge
        return active

    def ensure_active_challenges(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        ensured: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for item in items:
            try:
                ensured.append(self._ensure_one_active_challenge(item))
            except Exception as err:
                errors.append(
                    {
                        "id": f"challenge-{item.get('name', 'unknown')}"[:64],
                        "error_code": "ENSURE_FAILED",
                        "message": str(err),
                    }
                )
        return {"ensured": ensured, "errors": errors}

    def _ensure_one_active_challenge(self, item: dict[str, Any]) -> dict[str, Any]:
        config = self._ensure_challenge_config(item)
        challenge = self._find_challenge_by_name(item["name"])

        if challenge is None:
            created = self._create_challenge(item, config["id"])
            return {
                "challenge_id": created["id"],
                "challenge_config_id": config["id"],
                "name": item["name"],
                "status": "CREATED",
                "message": "Created challenge using CRUD endpoints.",
            }

        update_payload = self._challenge_update_payload(item, config["id"])
        needs_update = (
            challenge.get("challenge_config_id") != config["id"]
            or challenge.get("description") != update_payload["description"]
            or challenge.get("version") != update_payload["version"]
            or self._dt_key(challenge.get("start_at"))
            != self._dt_key(update_payload["start_at"])
            or self._dt_key(challenge.get("end_at"))
            != self._dt_key(update_payload["end_at"])
            or challenge.get("is_enabled") != update_payload["is_enabled"]
        )
        if needs_update:
            updated = self._update_challenge(challenge["id"], update_payload)
            return {
                "challenge_id": updated["id"],
                "challenge_config_id": config["id"],
                "name": item["name"],
                "status": "UPDATED",
                "message": "Updated challenge using CRUD endpoints.",
            }

        return {
            "challenge_id": challenge["id"],
            "challenge_config_id": config["id"],
            "name": item["name"],
            "status": "UNCHANGED",
            "message": "Challenge already current.",
        }

    def _ensure_challenge_config(self, item: dict[str, Any]) -> dict[str, Any]:
        existing = self._find_matching_challenge_config(item)
        if existing is not None:
            return existing
        body = self._request(
            "POST",
            "/challenge-configs/",
            json={
                "spec": item["spec"],
                "active_from": item["active_from"],
                "active_until": item.get("active_until"),
                "kind": item["kind"],
            },
        )
        return body["data"]

    def _find_matching_challenge_config(
        self, item: dict[str, Any]
    ) -> dict[str, Any] | None:
        body = self._request(
            "GET",
            "/challenge-configs/",
            params={"limit": 1000},
        )
        for config in body.get("data", []):
            if config.get("kind") != item["kind"]:
                continue
            if config.get("spec") != item["spec"]:
                continue
            if self._dt_key(config.get("active_from")) != self._dt_key(
                item.get("active_from")
            ):
                continue
            if self._dt_key(config.get("active_until")) != self._dt_key(
                item.get("active_until")
            ):
                continue
            return config
        return None

    def _find_challenge_by_name(self, name: str) -> dict[str, Any] | None:
        body = self._request(
            "GET",
            "/challenges/",
            params={"limit": 1000, "expands": "config"},
        )
        for challenge in body.get("data", []):
            if challenge.get("name") == name and not challenge.get("deleted_at"):
                return challenge
        return None

    def _create_challenge(self, item: dict[str, Any], config_id: str) -> dict[str, Any]:
        body = self._request(
            "POST",
            "/challenges/",
            json={
                **self._challenge_update_payload(item, config_id),
                "deleted_at": None,
                "note": None,
                "meta": None,
            },
        )
        return body["data"]

    def _update_challenge(
        self, challenge_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        body = self._request(
            "PUT",
            f"/challenges/{challenge_id}",
            json=payload,
        )
        return body["data"]

    @staticmethod
    def _challenge_update_payload(
        item: dict[str, Any], config_id: str
    ) -> dict[str, Any]:
        return {
            "name": item["name"],
            "description": item.get("description") or "",
            "version": item.get("version") or "v1",
            "start_at": item["active_from"],
            "end_at": item.get("active_until"),
            "is_enabled": item.get("is_enabled", True),
            "challenge_config_id": config_id,
        }

    def observe_commits(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        if not items:
            return {"accepted": [], "errors": []}
        body = self._request(
            "POST",
            "/validators/commits/observations/batch",
            json={"items": items},
        )
        return body.get("data", {"accepted": [], "errors": []})

    def fetch_weight_inputs(self, limit: int = 500) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        skip = 0
        while True:
            body = self._request(
                "GET",
                "/validators/weight-inputs",
                params={"skip": skip, "limit": limit},
            )
            page = body.get("data", [])
            items.extend(page)
            meta = body.get("meta", {})
            total = int(meta.get("total_count") or len(items))
            if len(items) >= total or not page:
                break
            skip += len(page)
        return items

    @staticmethod
    def _parse_dt(value: str | None) -> datetime | None:
        if not value:
            return None
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)

    @classmethod
    def _dt_key(cls, value: str | None) -> str | None:
        parsed = cls._parse_dt(value)
        if parsed is None:
            return None
        return parsed.astimezone(timezone.utc).isoformat()
