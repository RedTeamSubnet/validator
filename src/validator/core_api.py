"""Wallet-authenticated Core API client for validator weight matrices."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import bittensor as bt
import requests


@dataclass(frozen=True)
class WeightMatrix:
    refreshed_at: dt.datetime
    entries: dict[int, float]

    def age_seconds(self, now: dt.datetime | None = None) -> float:
        now = now or dt.datetime.now(dt.timezone.utc)
        return max((now - self.refreshed_at).total_seconds(), 0.0)


class CoreApiClient:
    """Fetch the Core API's already-aggregated validator weight matrix."""

    def __init__(self, base_url: str, hotkey: bt.Keypair, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.hotkey = hotkey
        self.timeout = timeout

    def fetch_weight_matrix(self) -> WeightMatrix:
        payload = self._request("GET", "integration/validator/weight-matrix")
        return WeightMatrix(
            refreshed_at=self._parse_datetime(payload["refreshed_at"]),
            entries={
                int(row["uid"]): float(row["score"])
                for row in payload["entries"]
            },
        )

    @staticmethod
    def _parse_datetime(value: str) -> dt.datetime:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(dt.timezone.utc)

    def _request(self, method: str, path: str) -> Any:
        response = requests.request(
            method,
            f"{self.base_url}/{path.lstrip('/')}",
            headers={"Authorization": f"Bearer {self._access_token()}"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("data", payload)

    def _access_token(self) -> str:
        address = self.hotkey.ss58_address
        challenge = requests.post(
            f"{self.base_url}/auth/wallet/challenge",
            json={"ss58_address": address},
            timeout=self.timeout,
        )
        challenge.raise_for_status()
        challenge_payload = challenge.json()
        challenge_data = challenge_payload.get("data", challenge_payload)
        nonce = challenge_data["nonce"]

        verified = requests.post(
            f"{self.base_url}/auth/wallet/verify",
            json={
                "nonce": nonce,
                "signature": self.hotkey.sign(nonce).hex(),
                "ss58_address": address,
            },
            timeout=self.timeout,
        )
        verified.raise_for_status()
        verified_payload = verified.json()
        token_data = verified_payload.get("data", verified_payload)
        return token_data["access_token"]


__all__ = ["CoreApiClient", "WeightMatrix"]
