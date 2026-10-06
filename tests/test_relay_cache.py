import datetime as dt
import json

from src.validator.cache import ValidatorCache
from src.validator.core_api import WeightMatrix


UTC = dt.timezone.utc


def test_cache_persists_fresh_weight_matrix(tmp_path):
    now = dt.datetime(2026, 10, 5, 23, 0, tzinfo=UTC)
    matrix = WeightMatrix(
        refreshed_at=now - dt.timedelta(minutes=5),
        entries={0: 0.0, 7: 0.75},
    )
    cache = ValidatorCache(str(tmp_path))

    cache.save_weight_matrix(matrix, now)

    assert ValidatorCache(str(tmp_path)).load_weight_matrix(3600, now) == matrix


def test_cache_rejects_stale_matrix(tmp_path):
    now = dt.datetime(2026, 10, 5, 23, 0, tzinfo=UTC)
    cache = ValidatorCache(str(tmp_path))
    cache.save_weight_matrix(
        WeightMatrix(
            refreshed_at=now - dt.timedelta(seconds=3601),
            entries={7: 0.75},
        ),
        now,
    )

    assert cache.load_weight_matrix(3600, now) is None


def test_cache_ignores_legacy_payload(tmp_path):
    path = tmp_path / "validator-weight-cache.json"
    path.write_text(
        json.dumps({"seen_commits": ["old"], "latest_weight_matrix": [0.25, 0.75]})
    )

    assert ValidatorCache(str(tmp_path)).load_weight_matrix(3600) is None
