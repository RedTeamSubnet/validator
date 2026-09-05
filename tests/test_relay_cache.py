from src.validator.cache import ValidatorCache


def test_cache_persists_seen_commits_and_last_matrix(tmp_path):
    cache = ValidatorCache(str(tmp_path))
    assert not cache.has_seen("commit-1")
    assert cache.latest_weight_matrix is None

    cache.mark_seen("commit-1")
    cache.latest_weight_matrix = [0.25, 0.75]

    reloaded = ValidatorCache(str(tmp_path))
    assert reloaded.has_seen("commit-1")
    assert reloaded.latest_weight_matrix == [0.25, 0.75]
