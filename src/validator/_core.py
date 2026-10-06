"""Single-purpose validator: fetch a global matrix and publish chain weights."""

from __future__ import annotations

import datetime as dt
from typing import Iterable

import bittensor as bt
import numpy as np

from ._base import BaseValidator
from .cache import ValidatorCache
from .core_api import CoreApiClient, WeightMatrix


class Validator(BaseValidator):
    CACHE_EPOCHS = 3

    def __init__(self) -> None:
        super().__init__()
        self.cache = ValidatorCache(self.validator_config.CACHE_DIR)
        self.core_api_client = CoreApiClient(
            base_url=str(self.config.CORE_API_URL),
            hotkey=self.wallet.hotkey,
            timeout=int(getattr(self.config, "QUERY_TIMEOUT", 30)),
        )

    def set_weights(self) -> None:
        now = dt.datetime.now(dt.timezone.utc)
        max_age = float(1200 * self.CACHE_EPOCHS)
        cached = self.cache.load_weight_matrix(max_age, now)
        remote = self._fetch_remote_matrix()

        candidates = self._ordered_candidates(remote, cached, now, max_age)
        if not candidates:
            bt.logging.error("[WEIGHTS] No fresh API or cached matrix; skipping")
            return

        source, matrix = candidates[0]
        weights = self._build_weight_vector(matrix)
        if source == "api" and (
            cached is None or matrix.refreshed_at > cached.refreshed_at
        ):
            self.cache.save_weight_matrix(matrix, now)

        bt.logging.info(
            f"[WEIGHTS] Using {source} matrix "
            f"refreshed_at={matrix.refreshed_at.isoformat()} "
            f"age={matrix.age_seconds(now):.1f}s "
            f"entries={len(matrix.entries)} total={float(np.sum(weights)):.6f}"
        )
        processed_uids, processed_weights = (
            bt.utils.weight_utils.process_weights_for_netuid(
                uids=self.metagraph.uids,
                weights=weights,
                netuid=self.config.BITTENSOR.SUBNET_NETUID,
                subtensor=self.subtensor,
                metagraph=self.metagraph,
            )
        )
        if not np.any(np.asarray(processed_weights) > 0):
            bt.logging.error(
                "[WEIGHTS] Processing produced no positive weights; skipping"
            )
            return

        uint_uids, uint_weights = (
            bt.utils.weight_utils.convert_weights_and_uids_for_emit(
                uids=processed_uids,
                weights=processed_weights,
            )
        )
        response = self.subtensor.set_weights(
            wallet=self.wallet,
            uids=uint_uids,
            weights=uint_weights,
            netuid=self.config.BITTENSOR.SUBNET_NETUID,
            version_key=self.config.SPEC_VERSION,
            mechid=0,
            wait_for_inclusion=True,
            wait_for_finalization=False,
        )
        if not response.success:
            bt.logging.error(f"[WEIGHTS] Failed to set weights: {response.message}")
            return
        bt.logging.success("[WEIGHTS] Weights included on chain")

    def _fetch_remote_matrix(self) -> WeightMatrix | None:
        try:
            return self.core_api_client.fetch_weight_matrix()
        except Exception:
            bt.logging.exception("[WEIGHTS] Failed to fetch Core API matrix")
            return None

    @staticmethod
    def _ordered_candidates(
        remote: WeightMatrix | None,
        cached: WeightMatrix | None,
        now: dt.datetime,
        max_age: float,
    ) -> list[tuple[str, WeightMatrix]]:
        candidates: list[tuple[str, WeightMatrix]] = []
        if remote is not None and remote.age_seconds(now) <= max_age:
            candidates.append(("api", remote))
        elif remote is not None:
            bt.logging.warning(
                f"[WEIGHTS] API matrix is stale: "
                f"age={remote.age_seconds(now):.1f}s max_age={max_age:.1f}s"
            )
        if cached is not None:
            candidates.append(("cache", cached))
        return sorted(
            candidates,
            key=lambda item: (
                item[1].refreshed_at,
                item[0] == "api",
            ),
            reverse=True,
        )

    def _build_weight_vector(self, matrix: WeightMatrix) -> np.ndarray:
        weights = np.zeros(int(self.metagraph.n), dtype=np.float32)
        stale_uids: list[int] = []
        for uid, score in matrix.entries.items():
            if uid >= len(weights):
                stale_uids.append(uid)
                continue
            weights[uid] = score
        if stale_uids:
            bt.logging.warning(
                "[WEIGHTS] Ignoring UIDs outside current metagraph: "
                f"{self._compact_uids(stale_uids)}"
            )
        return weights

    @staticmethod
    def _compact_uids(uids: Iterable[int]) -> str:
        return ",".join(str(uid) for uid in sorted(uids))


__all__ = ["Validator"]
