from typing import Any

import bittensor as bt
import requests


class CoreApiClient:
    """Wallet-authenticated client for active-challenge resources in rest-core-api."""

    def __init__(self, base_url: str, hotkey: bt.Keypair, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.hotkey = hotkey
        self.timeout = timeout

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    @staticmethod
    def _data(response: requests.Response) -> Any:
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Core API returned a non-object JSON response")
        return payload.get("data", payload)

    def _access_token(self) -> str:
        hotkey_address = self.hotkey.ss58_address
        challenge = self._data(
            requests.post(
                self._url("auth/wallet/challenge"),
                json={"ss58_address": hotkey_address},
                timeout=self.timeout,
            )
        )
        nonce = challenge.get("nonce") if isinstance(challenge, dict) else None
        if not isinstance(nonce, str) or not nonce:
            raise ValueError("Core API wallet challenge did not include a nonce")

        token = self._data(
            requests.post(
                self._url("auth/wallet/verify"),
                json={
                    "nonce": nonce,
                    "signature": self.hotkey.sign(nonce).hex(),
                    "ss58_address": hotkey_address,
                },
                timeout=self.timeout,
            )
        )
        access_token = token.get("access_token") if isinstance(token, dict) else None
        if not isinstance(access_token, str) or not access_token:
            raise ValueError(
                "Core API wallet verification did not include an access token"
            )
        return access_token

    def _request(
        self,
        method: str,
        path: str,
        access_token: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
    ) -> Any:
        return self._data(
            requests.request(
                method,
                self._url(path),
                headers={"Authorization": f"Bearer {access_token}"},
                json=json,
                params=params,
                timeout=self.timeout,
            )
        )

    def _challenges_by_name(self, access_token: str) -> dict[str, dict]:
        challenges: dict[str, dict] = {}
        skip = 0
        limit = 100
        while True:
            page = self._request(
                "GET",
                "challenges/",
                access_token,
                params={"skip": skip, "limit": limit},
            )
            if not isinstance(page, list):
                raise ValueError("Core API challenge list did not include a data list")
            for challenge in page:
                if not isinstance(challenge, dict):
                    raise ValueError(
                        "Core API challenge list included an invalid challenge"
                    )
                name = challenge.get("name")
                if isinstance(name, str):
                    challenges[name] = challenge
            if len(page) < limit:
                return challenges
            skip += len(page)

    def _create_challenge(self, challenge: dict, access_token: str) -> str:
        required_fields = (
            "core_kind",
            "core_kind_description",
            "core_config_spec",
            "core_config_active_from",
            "core_config_active_until",
            "core_version",
            "core_start_at",
            "core_end_at",
            "core_is_enabled",
        )
        missing_fields = [field for field in required_fields if field not in challenge]
        if missing_fields:
            raise ValueError(
                f"Active challenge '{challenge.get('name')}' is missing core metadata: "
                f"{', '.join(missing_fields)}"
            )

        self._request(
            "POST",
            "challenge-kinds/",
            access_token,
            json={
                "kind": challenge["core_kind"],
                "description": challenge["core_kind_description"],
            },
        )
        config = self._request(
            "POST",
            "challenge-configs/",
            access_token,
            json={
                "kind": challenge["core_kind"],
                "spec": challenge["core_config_spec"],
                "active_from": challenge["core_config_active_from"],
                "active_until": challenge["core_config_active_until"],
            },
        )
        if not isinstance(config, dict) or not isinstance(config.get("id"), str):
            raise ValueError("Core API challenge config creation did not include an ID")

        created = self._request(
            "POST",
            "challenges/",
            access_token,
            json={
                "name": challenge["name"],
                "description": challenge["description"],
                "version": challenge["core_version"],
                "start_at": challenge["core_start_at"],
                "end_at": challenge["core_end_at"],
                "is_enabled": challenge["core_is_enabled"],
                "challenge_config_id": config["id"],
            },
        )
        if not isinstance(created, dict) or not isinstance(created.get("id"), str):
            raise ValueError("Core API challenge creation did not include an ID")
        return created["id"]

    def sync_active_challenges(self, active_challenges: dict[str, dict]) -> None:
        access_token = self._access_token()
        existing_challenges = self._challenges_by_name(access_token)
        for challenge_name, challenge in active_challenges.items():
            existing = existing_challenges.get(challenge_name)
            if existing:
                challenge_id = existing.get("id")
                if not isinstance(challenge_id, str):
                    raise ValueError(
                        f"Core API challenge '{challenge_name}' did not include an ID"
                    )
            else:
                challenge_id = self._create_challenge(challenge, access_token)
            challenge["challenge_id"] = challenge_id


__all__ = ["CoreApiClient"]
