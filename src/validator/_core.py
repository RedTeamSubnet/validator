"""Validator runtime limited to challenge sync, commit processing and weights."""

from __future__ import annotations

import datetime as dt
from typing import Any

import bittensor as bt
import numpy as np
from cryptography.fernet import Fernet
from redteam_core.challenge_pool import ACTIVE_CHALLENGES
from redteam_core.protocol import Commit

# from redteam_core.validator import start_bittensor_log_listener

from ._base import BaseValidator
from .cache import ValidatorCache
from .core_api import CoreApiClient, CoreCommitOutcome


class Validator(BaseValidator):
    """Relay validator: challenge metadata, miner commits, and weight setting."""

    def __init__(self) -> None:
        super().__init__()
        self.cache = ValidatorCache(self.validator_config.CACHE_DIR)
        self.core_api_client = CoreApiClient(
            base_url=str(self.config.CORE_API_URL), hotkey=self.wallet.hotkey
        )
        self.active_challenges: dict[str, dict[str, Any]] = {}
        #! TODO: Implement validator log sending to core API. This is currently disabled because the core API does not yet support log ingestion.
        # start_bittensor_log_listener()

    def get_active_challenges(self) -> dict[str, dict[str, Any]]:
        """Resolve redteam_core active challenges against REST core API metadata."""
        self.active_challenges = self.core_api_client.load_active_challenges(
            ACTIVE_CHALLENGES
        )
        return self.active_challenges

    def query_miners_and_relay_commits(self) -> None:
        """Query miner axons and persist every commit outcome independently."""
        if not self.active_challenges:
            self.get_active_challenges()
        axons = [
            axon
            for uid, axon in enumerate(self.metagraph.axons)
            if uid != self.uid and axon is not None
        ]
        if not axons:
            return
        try:
            responses = self.dendrite.query(
                axons, Commit(), timeout=self.config.QUERY_TIMEOUT
            )
        except Exception:
            bt.logging.exception("[COMMITS] Miner axon query failed")
            return
        for axon, response in zip(axons, responses):
            uid = self._uid_for_hotkey(getattr(axon, "hotkey", ""))
            for outcome in self._outcomes_from_response(uid, axon, response):
                self._relay_outcome(outcome)

    def set_weights(self) -> None:
        """Fetch REST core API matrix and submit it using this validator wallet."""
        _, matrix = self.core_api_client.fetch_weight_matrix()

        weights = np.zeros(int(self.metagraph.n), dtype=np.float32)
        for uid, score in matrix.items():
            if 0 <= uid < len(weights) and np.isfinite(score) and score >= 0:
                weights[uid] = score
            elif uid < 0 or uid >= len(weights):
                bt.logging.warning("[WEIGHTS] Ignoring stale UID %s", uid)
        if not np.any(weights):
            bt.logging.warning("[WEIGHTS] Core matrix contains no usable scores")
            return
        processed_uids, processed_weights = (
            bt.utils.weight_utils.process_weights_for_netuid(
                uids=self.metagraph.uids,
                weights=weights,
                netuid=self.config.BITTENSOR.SUBNET_NETUID,
                subtensor=self.subtensor,
                metagraph=self.metagraph,
            )
        )
        uint_uids, uint_weights = (
            bt.utils.weight_utils.convert_weights_and_uids_for_emit(
                uids=processed_uids, weights=processed_weights
            )
        )
        response = self.subtensor.set_weights(
            wallet=self.wallet,
            uids=uint_uids,
            weights=uint_weights,
            netuid=self.config.BITTENSOR.SUBNET_NETUID,
            version_key=self.config.SPEC_VERSION,
            mechid=0,
        )
        if not response.success:
            bt.logging.error(f"[WEIGHTS] Failed to set weights: {response.message}")
        self.cache.latest_weight_matrix = [
            float(matrix.get(uid, 0.0)) for uid in range(int(self.metagraph.n))
        ]

    def forward(self) -> None:
        self.get_active_challenges()
        self.query_miners_and_relay_commits()

    def _relay_outcome(self, outcome: CoreCommitOutcome) -> None:
        # A discovered-but-unrevealed commit must be queried again next epoch.
        if outcome.status == "decrypted" and self.cache.has_seen(outcome.identity):
            return
        try:
            self.core_api_client.sync_commit(
                outcome, subnet_id=self.config.BITTENSOR.SUBNET_NETUID
            )
        except Exception:
            bt.logging.exception("[COMMITS] Failed to relay %s", outcome.identity)
            return
        if outcome.status == "decrypted":
            self.cache.mark_seen(outcome.identity)

    def _outcomes_from_response(
        self, uid: int, axon: Any, response: Any
    ) -> list[CoreCommitOutcome]:
        encrypted = getattr(response, "encrypted_commit_dockers", None) or {}
        keys = getattr(response, "public_keys", None) or {}
        hotkey = getattr(axon, "hotkey", "")
        outcomes: list[CoreCommitOutcome] = []
        for challenge_name, cipher_commit in encrypted.items():
            if challenge_name not in self.active_challenges or not cipher_commit:
                continue
            revealed_key = keys.get(challenge_name)
            commit = None
            error = None
            if revealed_key:
                try:
                    commit = Fernet(revealed_key).decrypt(cipher_commit).decode()
                except Exception as exc:
                    error = f"decrypt_failed: {exc}"
            outcomes.append(
                CoreCommitOutcome(
                    miner_uid=uid,
                    miner_hotkey=hotkey,
                    challenge_name=challenge_name,
                    challenge_id=self.active_challenges[challenge_name]["_id"],
                    cipher_commit=str(cipher_commit),
                    revealed_key=revealed_key,
                    decrypted_commit=commit,
                    status="decrypted" if commit is not None else "discovered",
                    error=error,
                    committed_at=dt.datetime.now(dt.timezone.utc),
                )
            )
        return outcomes

    def _uid_for_hotkey(self, hotkey: str) -> int:
        try:
            return self.metagraph.hotkeys.index(hotkey)
        except ValueError:
            return -1
