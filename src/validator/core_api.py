"""REST core API client used only by the relay validator workflows."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

import bittensor as bt
import requests


@dataclass(frozen=True)
class CoreCommitOutcome:
    miner_uid: int
    miner_hotkey: str
    challenge_name: str
    challenge_id: str
    cipher_commit: str
    revealed_key: str | None
    decrypted_commit: str | None
    status: str
    error: str | None
    committed_at: dt.datetime

    @property
    def identity(self) -> str:
        return f"{self.challenge_id}:{self.miner_hotkey}:{self.cipher_commit}"


class CoreApiClient:
    """Wallet-authenticated REST core API client."""

    def __init__(self, base_url: str, hotkey: bt.Keypair, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.hotkey = hotkey
        self.timeout = timeout

    def fetch_weight_matrix(self) -> tuple[dt.datetime | None, dict[int, float]]:
        payload = self._request("GET", "integration/validator/weight-matrix")
        refreshed_at = payload.get("refreshed_at")
        return (
            dt.datetime.fromisoformat(refreshed_at.replace("Z", "+00:00"))
            if refreshed_at else None,
            {int(row["uid"]): float(row["score"]) for row in payload.get("entries", [])},
        )

    def load_active_challenges(
        self, runtime_challenges: dict[str, dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        """Merge local active selection with canonical REST core challenge metadata."""
        by_name = {
            challenge["name"]: challenge
            for challenge in self._list("challenges/", params={"expands": "config"})
        }
        resolved: dict[str, dict[str, Any]] = {}
        for name, runtime in runtime_challenges.items():
            challenge = by_name.get(name)
            if not challenge or not challenge.get("is_active"):
                raise RuntimeError(f"Active challenge '{name}' is unavailable in REST core API")
            config = challenge.get("config")
            if not config:
                raise RuntimeError(f"Active challenge '{name}' has no core configuration")
            kind = self._request("GET", f"challenge-kinds/{challenge['kind']}")
            resolved[name] = {
                **runtime,
                "_id": challenge["id"],
                "challenge_config": config,
                "challenge_kind": kind,
                "core_db": challenge,
            }
        return resolved

    def sync_commit(self, outcome: CoreCommitOutcome, *, subnet_id: int) -> None:
        """Create one commit, then update that same core commit as it is revealed."""
        miner_id = self._miner_id(outcome.miner_hotkey, subnet_id)
        commit = next(
            (
                item for item in self._list("commits/", params={"challenge_id": outcome.challenge_id})
                if item.get("miner_id") == miner_id
                and item.get("cipher_commit") == outcome.cipher_commit
            ),
            None,
        )
        if commit is None:
            commit = self._request("POST", "commits/", json={
                "cipher_commit": outcome.cipher_commit,
                "committed_at": outcome.committed_at.isoformat(),
                "challenge_id": outcome.challenge_id,
                "miner_id": miner_id,
                "reveal_key": outcome.revealed_key,
            })
        update = {
            "reveal_key": outcome.revealed_key,
            "plain_commit": outcome.decrypted_commit,
            "state": "FAILED" if outcome.error else (
                "REVEALED" if outcome.decrypted_commit else "COMMITTED"
            ),
            "note": outcome.error,
        }
        self._request("PUT", f"commits/{commit['id']}", json=update)

    def _miner_id(self, hotkey: str, subnet_id: int) -> str:
        neurons = self._request(
            "GET", "neurons/", params={"hotkey_address": hotkey, "limit": 1}
        )
        if not neurons:
            self._request("POST", f"subnets/{subnet_id}/sync")
            neurons = self._request(
                "GET", "neurons/", params={"hotkey_address": hotkey, "limit": 1}
            )
        if not neurons:
            raise RuntimeError(f"Miner hotkey '{hotkey}' is absent from REST core API")
        return neurons[0]["id"]

    def _list(self, path: str, *, params: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        skip = 0
        while True:
            page = self._request("GET", path, params={**params, "skip": skip, "limit": 100})
            rows.extend(page)
            if len(page) < 100:
                return rows
            skip += len(page)

    def _request(self, method: str, path: str, *, json: dict | None = None,
                 params: dict | None = None) -> Any:
        response = requests.request(
            method, f"{self.base_url}/{path.lstrip('/')}",
            headers={"Authorization": f"Bearer {self._access_token()}"},
            json=json, params=params, timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("data", payload)

    def _access_token(self) -> str:
        address = self.hotkey.ss58_address
        challenge = requests.post(
            f"{self.base_url}/auth/wallet/challenge", json={"ss58_address": address},
            timeout=self.timeout,
        )
        challenge.raise_for_status()
        challenge_data = challenge.json().get("data", challenge.json())
        nonce = challenge_data["nonce"]
        verified = requests.post(
            f"{self.base_url}/auth/wallet/verify",
            json={"nonce": nonce, "signature": self.hotkey.sign(nonce).hex(), "ss58_address": address},
            timeout=self.timeout,
        )
        verified.raise_for_status()
        token_data = verified.json().get("data", verified.json())
        return token_data["access_token"]


__all__ = ["CoreApiClient", "CoreCommitOutcome"]
