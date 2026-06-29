#!/usr/bin/env python

import datetime
import os
import time
import traceback
from collections import defaultdict
from copy import deepcopy
from typing import Any

import bittensor as bt
import numpy as np
from cryptography.fernet import Fernet

from redteam_core.challenge_pool import ACTIVE_CHALLENGES
from redteam_core.config import constants
from redteam_core.protocol import Commit
from redteam_core.validator.utils import create_validator_request_header_fn

from ._base import BaseValidator
from .core_client import RestCoreClient


class Validator(BaseValidator):
    def __init__(self):
        super().__init__()
        self.validator_request_header_fn = create_validator_request_header_fn(
            validator_uid=self.uid,
            validator_hotkey=self.wallet.hotkey.ss58_address,
            keypair=self.wallet.hotkey,
        )
        self.core_client = RestCoreClient(
            base_url=os.getenv("RT_CORE_API_URL", str(self.config.STORAGE_API_URL)),
            header_fn=self.validator_request_header_fn,
            timeout=max(self.config.QUERY_TIMEOUT, 60),
        )
        self.commit_repo_id_to_chain(hf_repo_id="", max_retries=5)

    def forward(self):
        date_time = datetime.datetime.now(datetime.timezone.utc)
        bt.logging.info(f"[FORWARD] Starting stateless forward for {date_time}")

        active_challenges = deepcopy(ACTIVE_CHALLENGES)
        self._ensure_active_challenges_in_core(active_challenges)
        if not active_challenges:
            bt.logging.warning("[FORWARD] No local active challenges configured")
            return

        observations = self._collect_commit_observations(active_challenges)
        bt.logging.info(f"[FORWARD] Collected {len(observations)} commit observations")

        try:
            result = self.core_client.observe_commits(observations)
            bt.logging.success(
                "[FORWARD] Stored commit observations: "
                f"{len(result.get('accepted', []))} accepted, "
                f"{len(result.get('errors', []))} errors"
            )
            for error in result.get("errors", [])[:20]:
                bt.logging.warning(f"[FORWARD] Observation error: {error}")
        except Exception:
            bt.logging.error(
                f"[FORWARD] Failed to store commit observations: {traceback.format_exc()}"
            )

    def _ensure_active_challenges_in_core(
        self, active_challenges: dict[str, dict[str, Any]]
    ) -> None:
        payload = [
            self._challenge_storage_payload(challenge_name, challenge_info)
            for challenge_name, challenge_info in active_challenges.items()
        ]
        try:
            result = self.core_client.ensure_active_challenges(payload)
            bt.logging.success(
                "[FORWARD] Ensured active challenges in core: "
                f"{len(result.get('ensured', []))} ensured, "
                f"{len(result.get('errors', []))} errors"
            )
            for error in result.get("errors", [])[:20]:
                bt.logging.warning(f"[FORWARD] Challenge ensure error: {error}")
        except Exception:
            bt.logging.error(
                f"[FORWARD] Failed to ensure active challenges: {traceback.format_exc()}"
            )

    def _challenge_storage_payload(
        self, challenge_name: str, challenge_info: dict[str, Any]
    ) -> dict[str, Any]:
        spec = self._json_safe_challenge_spec(challenge_info)
        name = str(challenge_info.get("name") or challenge_name)
        return {
            "name": name,
            "description": str(challenge_info.get("description") or ""),
            "version": self._derive_challenge_version(name),
            "kind": self._derive_challenge_kind(challenge_info),
            "spec": spec,
            "active_from": self._challenge_datetime(
                challenge_info, ("release_date", "start_at", "active_from")
            ),
            "active_until": self._challenge_datetime(
                challenge_info, ("end_at", "active_until"), default=None
            ),
            "is_enabled": True,
        }

    def _json_safe_challenge_spec(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): self._json_safe_challenge_spec(item)
                for key, item in value.items()
                if key not in {"controller", "challenge_manager"}
            }
        if isinstance(value, list):
            return [self._json_safe_challenge_spec(item) for item in value]
        if isinstance(value, tuple):
            return [self._json_safe_challenge_spec(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, type):
            return f"{value.__module__}.{value.__qualname__}"
        if callable(value):
            return f"{value.__module__}.{value.__qualname__}"
        return str(value)

    @staticmethod
    def _derive_challenge_kind(challenge_info: dict[str, Any]) -> str:
        kind = challenge_info.get("kind") or challenge_info.get("challenge_type")
        return str(kind or "GENERIC").upper()

    @staticmethod
    def _derive_challenge_version(name: str) -> str:
        if "_v" in name:
            suffix = name.rsplit("_v", 1)[-1]
            if suffix and suffix[0].isdigit():
                return f"v{suffix}"
        return "v1"

    @staticmethod
    def _challenge_datetime(
        challenge_info: dict[str, Any],
        keys: tuple[str, ...],
        default: str | None = "1970-01-01T00:00:00+00:00",
    ) -> str | None:
        for key in keys:
            value = challenge_info.get(key)
            if value:
                return str(value)
        return default

    def set_weights(self) -> None:
        n_uids = int(self.metagraph.n)
        try:
            weight_inputs = self.core_client.fetch_weight_inputs()
        except Exception:
            bt.logging.error(
                f"[SET WEIGHTS] Failed to fetch weight inputs: {traceback.format_exc()}"
            )
            weight_inputs = []

        challenge_scores = self._get_challenge_scores_from_weight_inputs(
            n_uids=n_uids,
            weight_inputs=weight_inputs,
        )
        alpha_burn_scores = self._get_alpha_burn_scores(n_uids)
        weights = (
            challenge_scores * constants.CHALLENGE_SCORES_WEIGHT
            + alpha_burn_scores * constants.ALPHA_BURN_WEIGHT
        )

        bt.logging.debug(f"[SET WEIGHTS] scores: {weights}")
        (
            processed_weight_uids,
            processed_weights,
        ) = bt.utils.weight_utils.process_weights_for_netuid(
            uids=self.metagraph.uids,
            weights=weights,
            netuid=self.config.BITTENSOR.SUBNET_NETUID,
            subtensor=self.subtensor,
            metagraph=self.metagraph,
        )
        (
            uint_uids,
            uint_weights,
        ) = bt.utils.weight_utils.convert_weights_and_uids_for_emit(
            uids=processed_weight_uids, weights=processed_weights
        )

        bt.logging.info(
            f"[SET WEIGHTS] uint_weights: {uint_weights}, processed_weights: {processed_weights}"
        )
        result, log = self.subtensor.set_weights(
            wallet=self.wallet,
            netuid=self.config.BITTENSOR.SUBNET_NETUID,
            uids=uint_uids,
            weights=uint_weights,
            version_key=self.config.SPEC_VERSION,
        )

        if result:
            bt.logging.success(f"[SET WEIGHTS]: {log}")
        else:
            bt.logging.error(f"[SET WEIGHTS]: {log}")

    def _collect_commit_observations(
        self, active_challenges: dict[str, dict[str, Any]]
    ) -> list[dict[str, Any]]:
        uids = [int(uid) for uid in self.metagraph.uids]
        axons = [self.metagraph.axons[i] for i in uids]
        hotkeys = [self.metagraph.hotkeys[i] for i in uids]
        synapse = Commit()

        if bt.logging.get_level() < 20:
            bt.logging.set_info()
        responses: list[Commit] = self.dendrite.query(
            axons, synapse, timeout=self.config.QUERY_TIMEOUT
        )
        if bt.logging.get_level() < 20:
            bt.logging.set_debug()

        observed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        observations: list[dict[str, Any]] = []
        for uid, hotkey, response in zip(uids, hotkeys, responses):
            encrypted_commits = getattr(response, "encrypted_commit_dockers", {}) or {}
            keys = getattr(response, "public_keys", {}) or {}
            for challenge_name, encrypted_commit in encrypted_commits.items():
                if challenge_name not in active_challenges:
                    continue

                cipher_commit = self._stringify_secret(encrypted_commit)
                reveal_key = self._stringify_secret(keys.get(challenge_name))
                plain_commit = None
                if reveal_key:
                    plain_commit = self._decrypt_commit(
                        uid=uid,
                        hotkey=hotkey,
                        challenge_name=challenge_name,
                        cipher_commit=encrypted_commit,
                        reveal_key=keys.get(challenge_name),
                    )

                observations.append(
                    {
                        "miner_uid": uid,
                        "miner_hotkey": hotkey,
                        "challenge_name": challenge_name,
                        "cipher_commit": cipher_commit,
                        "committed_at": observed_at,
                        "reveal_key": reveal_key,
                        "plain_commit": plain_commit,
                    }
                )
        return observations

    def _decrypt_commit(
        self,
        uid: int,
        hotkey: str,
        challenge_name: str,
        cipher_commit: Any,
        reveal_key: Any,
    ) -> str | None:
        try:
            token = (
                cipher_commit
                if isinstance(cipher_commit, bytes)
                else str(cipher_commit).encode()
            )
            key = (
                reveal_key if isinstance(reveal_key, bytes) else str(reveal_key).encode()
            )
            commit = Fernet(key).decrypt(token).decode()
            bt.logging.success(
                f"[FORWARD] Decrypted commit: {uid} - {hotkey} - {challenge_name}"
            )
            return commit
        except Exception as err:
            bt.logging.error(
                f"[FORWARD] Failed to decrypt commit for {uid}/{challenge_name}: {err}"
            )
            return None

    @staticmethod
    def _stringify_secret(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode()
        return str(value)

    def _get_challenge_scores_from_weight_inputs(
        self, n_uids: int, weight_inputs: list[dict[str, Any]]
    ) -> np.ndarray:
        if not weight_inputs:
            bt.logging.info("[SET WEIGHTS] No challenge scores, using alpha burn only")
            return np.zeros(n_uids)

        by_challenge: dict[str, list[dict[str, Any]]] = defaultdict(list)
        challenge_weights: dict[str, float] = {}
        docker_usernames: dict[str, str | None] = {}
        for item in weight_inputs:
            challenge = item.get("challenge") or {}
            challenge_id = challenge.get("id") or challenge.get("name") or "unknown"
            by_challenge[challenge_id].append(item)
            challenge_weights[challenge_id] = self._challenge_weight(challenge)
            miner = item.get("miner") or {}
            uid = miner.get("uid")
            if uid is not None:
                docker_usernames[str(uid)] = miner.get("docker_username")

        aggregated_scores = np.zeros(n_uids)
        for challenge_id, items in by_challenge.items():
            scores = np.zeros(n_uids)
            for item in items:
                miner = item.get("miner") or {}
                uid = miner.get("uid")
                if uid is None or int(uid) >= n_uids:
                    continue
                scores[int(uid)] = max(
                    scores[int(uid)], float(item.get("final_score") or 0.0)
                )

            normalized = self._exclude_same_miner(scores, docker_usernames)
            bt.logging.info(
                f"[SET WEIGHTS] Challenge {challenge_id} scores: {normalized.tolist()}"
            )
            aggregated_scores += normalized * challenge_weights[challenge_id]

        total = np.sum(aggregated_scores)
        if total > 0:
            aggregated_scores = aggregated_scores / total
        return aggregated_scores

    @staticmethod
    def _challenge_weight(challenge: dict[str, Any]) -> float:
        config = challenge.get("config") or {}
        for key in ("challenge_incentive_weight", "incentive_weight", "weight"):
            if key in config:
                try:
                    return float(config[key])
                except (TypeError, ValueError):
                    return 1.0
        return 1.0

    def _exclude_same_miner(
        self,
        scores: np.ndarray,
        docker_usernames: dict[str, str | None],
        ignore_ip: str = "0.0.0.0",
    ) -> np.ndarray:
        if np.sum(scores) == 0:
            return scores

        ips = [getattr(axon, "ip", ignore_ip) for axon in self.metagraph.axons]
        coldkeys = list(getattr(self.metagraph, "coldkeys", []))
        if not coldkeys:
            coldkeys = [getattr(axon, "coldkey", "") for axon in self.metagraph.axons]

        final_scores = np.zeros(int(self.metagraph.n), dtype=float)
        ip_groups: dict[str, dict[str, list[Any]]] = defaultdict(
            lambda: {"index": [], "coldkey": [], "score": [], "docker_username": []}
        )
        for idx, score in enumerate(scores):
            if score == 0:
                continue
            ip = ips[idx] if idx < len(ips) else ignore_ip
            coldkey = coldkeys[idx] if idx < len(coldkeys) else ""
            ip_groups[ip]["index"].append(idx)
            ip_groups[ip]["coldkey"].append(coldkey)
            ip_groups[ip]["score"].append(score)
            ip_groups[ip]["docker_username"].append(docker_usernames.get(str(idx)))

        ip_groups.pop(ignore_ip, None)
        if not ip_groups:
            return np.zeros(int(self.metagraph.n))

        miner_groups: list[dict[str, list[Any]]] = []
        for ip, info in ip_groups.items():
            info["ip"] = [ip]
            for miner_info in miner_groups:
                overlaps_coldkey = not set(info["coldkey"]).isdisjoint(
                    set(miner_info["coldkey"])
                )
                incoming_usernames = {
                    username for username in info["docker_username"] if username
                }
                existing_usernames = {
                    username for username in miner_info["docker_username"] if username
                }
                overlaps_docker = (
                    bool(incoming_usernames)
                    and not incoming_usernames.isdisjoint(existing_usernames)
                )
                if overlaps_coldkey or overlaps_docker:
                    for key, values in info.items():
                        miner_info.setdefault(key, []).extend(values)
                    break
            else:
                miner_groups.append(info)

        for miner_info in miner_groups:
            max_score = max(miner_info["score"])
            max_index = miner_info["score"].index(max_score)
            max_uid = miner_info["index"][max_index]
            final_scores[max_uid] = max_score

        total = np.sum(final_scores)
        return final_scores / total if total > 0 else final_scores

    def _get_alpha_burn_scores(self, n_uids: int) -> np.ndarray:
        scores = np.zeros(n_uids)
        try:
            owner_hotkey = self.metagraph.owner_hotkey
            owner_hotkey_index = self.metagraph.hotkeys.index(owner_hotkey)
            scores[owner_hotkey_index] = 1.0
        except Exception as err:
            bt.logging.error(f"[SET WEIGHTS] Error calculating alpha burn score: {err}")
        return scores

    def commit_repo_id_to_chain(self, hf_repo_id: str, max_retries: int = 5) -> None:
        message = f"{self.wallet.hotkey.ss58_address}---{hf_repo_id}"
        for attempt in range(1, max_retries + 1):
            try:
                bt.logging.info(
                    f"Attempting to commit repo ID '{hf_repo_id}' to chain "
                    f"(Attempt {attempt})..."
                )
                self.subtensor.commit(
                    wallet=self.wallet,
                    netuid=self.config.BITTENSOR.SUBNET_NETUID,
                    data=message,
                )
                bt.logging.success(f"Successfully committed repo ID '{hf_repo_id}'.")
                return
            except Exception as err:
                bt.logging.error(
                    f"Error committing repo ID '{hf_repo_id}' on attempt {attempt}: {err}"
                )
                if attempt < max_retries:
                    time.sleep(min(2**attempt, 16))


__all__ = ["Validator"]
