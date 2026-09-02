import datetime
from dataclasses import dataclass
from typing import Any, Iterable

import bittensor as bt
import requests

from ._schemas import CHALLENGES, COMMITS, CoreWeightMatrixPM


class CoreApiConflictError(RuntimeError):
    """A commit already exists in rest-core-api."""


@dataclass(frozen=True)
class CoreCommitSubmission:
    miner_uid: int
    miner_hotkey: str
    challenge_name: str
    challenge_id: str
    cipher_commit: str
    committed_at: datetime.datetime


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
        return payload.get("data", payload)

    # TODO: Change the behaviour to store a token and refresh it when it expires instead of requesting a new one every time
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
        access_token = token.get("access_token")
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
        response = requests.request(
            method,
            self._url(path),
            headers={"Authorization": f"Bearer {access_token}"},
            json=json,
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        if response.status_code == 409:
            raise CoreApiConflictError(f"Core API conflict for {method} {path}")
        return self._data(response)

    @staticmethod
    def _scoring_spec(challenge: dict) -> dict:
        spec = dict(challenge.get("core_config_spec") or {})
        emission = challenge.get("emission_config") or {}
        spec["challenge_incentive_weight"] = challenge.get(
            "challenge_incentive_weight", spec.get("challenge_incentive_weight", 1.0)
        )
        for key in ("stable_period_days", "expiration_days", "alpha", "t_max"):
            if key in emission:
                spec[key] = emission[key]
        return spec

    def fetch_weight_matrix(self) -> tuple[datetime.datetime | None, dict[int, float]]:
        """Fetch the latest completed scoring matrix from rest-core-api."""
        matrix = CoreWeightMatrixPM.model_validate(
            self._request(
                "GET", "integration/validator/weight-matrix", self._access_token()
            )
        )
        return matrix.refreshed_at, {entry.uid: entry.score for entry in matrix.entries}

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
            page = CHALLENGES.validate_python(page)
            for challenge in page:
                challenges[challenge.name] = challenge.model_dump(exclude_none=True)
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
                "spec": self._scoring_spec(challenge),
                "active_from": challenge["core_config_active_from"],
                "active_until": challenge["core_config_active_until"],
            },
        )

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
        return created["id"]

    def sync_active_challenges(self, active_challenges: dict[str, dict]) -> None:
        access_token = self._access_token()
        existing_challenges = self._challenges_by_name(access_token)
        for challenge_name, challenge in active_challenges.items():
            existing = existing_challenges.get(challenge_name)
            if existing:
                challenge_id = existing.get("id")
            else:
                challenge_id = self._create_challenge(challenge, access_token)
            if existing:
                config_id = existing.get("challenge_config_id")
                current = self._request(
                    "GET", f"challenge-configs/{config_id}", access_token
                )
                current_spec = (
                    current.get("spec", {}) if isinstance(current, dict) else {}
                )
                self._request(
                    "PUT",
                    f"challenge-configs/{config_id}",
                    access_token,
                    json={"spec": {**current_spec, **self._scoring_spec(challenge)}},
                )

            challenge["challenge_id"] = challenge_id

    def _commits_by_challenge(
        self, challenge_id: str, access_token: str
    ) -> dict[str, datetime.datetime]:
        commits: dict[str, datetime.datetime] = {}
        skip = 0
        limit = 100
        while True:
            page = self._request(
                "GET",
                "commits/",
                access_token,
                params={"challenge_id": challenge_id, "skip": skip, "limit": limit},
            )
            page = COMMITS.validate_python(page)
            for commit in page:
                commits[commit.cipher_commit] = commit.committed_at
            if len(page) < limit:
                return commits
            skip += len(page)

    def fetch_seen_commits(
        self, active_challenges: dict[str, dict]
    ) -> dict[str, dict[str, datetime.datetime]]:
        access_token = self._access_token()
        seen_commits: dict[str, dict[str, datetime.datetime]] = {}
        for challenge_name, challenge in active_challenges.items():
            challenge_id = challenge.get("challenge_id")
            seen_commits[challenge_name] = self._commits_by_challenge(
                challenge_id, access_token
            )
        return seen_commits

    def _miner_id_by_hotkey(self, hotkey: str, access_token: str) -> str | None:
        neurons = self._request(
            "GET",
            "neurons/",
            access_token,
            params={"hotkey_address": hotkey, "skip": 0, "limit": 1},
        )
        if not neurons:
            return None
        neuron_id = neurons[0].get("id") if isinstance(neurons[0], dict) else None
        return neuron_id

    def sync_submissions(
        self,
        submissions: Iterable[CoreCommitSubmission],
        *,
        subnet_id: int,
        seen_commits: dict[str, dict[str, datetime.datetime]],
    ) -> None:
        access_token = self._access_token()
        miner_ids: dict[str, str | None] = {}
        synced_missing_hotkeys: set[str] = set()

        for submission in submissions:
            challenge_seen_commits = seen_commits.setdefault(
                submission.challenge_name, {}
            )
            if submission.cipher_commit in challenge_seen_commits:
                continue

            if submission.miner_hotkey not in miner_ids:
                miner_ids[submission.miner_hotkey] = self._miner_id_by_hotkey(
                    submission.miner_hotkey, access_token
                )
            miner_id = miner_ids[submission.miner_hotkey]
            if (
                miner_id is None
                and submission.miner_hotkey not in synced_missing_hotkeys
            ):
                self._request("POST", f"subnets/{subnet_id}/sync", access_token)
                synced_missing_hotkeys.add(submission.miner_hotkey)
                miner_ids.clear()
                miner_id = self._miner_id_by_hotkey(
                    submission.miner_hotkey, access_token
                )
                miner_ids[submission.miner_hotkey] = miner_id
            if miner_id is None:
                bt.logging.warning(
                    f"[CORE COMMIT SYNC] Skipping UID {submission.miner_uid}: "
                    f"core neuron missing for {submission.miner_hotkey}"
                )
                continue

            try:
                created = self._request(
                    "POST",
                    "commits/",
                    access_token,
                    json={
                        "cipher_commit": submission.cipher_commit,
                        "committed_at": submission.committed_at.isoformat(),
                        "challenge_id": submission.challenge_id,
                        "miner_id": miner_id,
                    },
                )
            except CoreApiConflictError:
                seen_commits[submission.challenge_name] = self._commits_by_challenge(
                    submission.challenge_id, access_token
                )
                continue
            except Exception:
                bt.logging.exception(
                    f"[CORE COMMIT SYNC] Failed to create commit for UID "
                    f"{submission.miner_uid}, challenge {submission.challenge_name}"
                )
                continue

            committed_at = (
                created.get("committed_at") if isinstance(created, dict) else None
            )
            challenge_seen_commits[submission.cipher_commit] = (
                datetime.datetime.fromisoformat(committed_at.replace("Z", "+00:00"))
            )


__all__ = ["CoreApiClient", "CoreCommitSubmission"]
