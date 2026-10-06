import datetime as dt
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from src.validator._base import BaseValidator
from src.validator._core import Validator
from src.validator.core_api import WeightMatrix


UTC = dt.timezone.utc


def make_validator(matrix, cached=None, n=3):
    validator = object.__new__(Validator)
    validator.config = SimpleNamespace(
        EPOCH_LENGTH=1200,
        SPEC_VERSION=20323,
        BITTENSOR=SimpleNamespace(SUBNET_NETUID=61),
    )
    validator.metagraph = SimpleNamespace(n=n, uids=np.arange(n))
    validator.wallet = Mock()
    validator.subtensor = Mock()
    validator.subtensor.set_weights.return_value = SimpleNamespace(
        success=True, message="included"
    )
    validator.core_api_client = Mock()
    if isinstance(matrix, Exception):
        validator.core_api_client.fetch_weight_matrix.side_effect = matrix
    else:
        validator.core_api_client.fetch_weight_matrix.return_value = matrix
    validator.cache = Mock()
    validator.cache.load_weight_matrix.return_value = cached
    return validator


def test_set_weights_uses_global_api_matrix_and_waits_for_inclusion():
    now = dt.datetime.now(UTC)
    matrix = WeightMatrix(refreshed_at=now, entries={0: 0, 1: 0.25, 2: 0.75})
    validator = make_validator(matrix)

    with patch(
        "src.validator._core.bt.utils.weight_utils.process_weights_for_netuid",
        return_value=(np.array([1, 2]), np.array([0.25, 0.75])),
    ), patch(
        "src.validator._core.bt.utils.weight_utils.convert_weights_and_uids_for_emit",
        return_value=([1, 2], [16384, 49151]),
    ):
        validator.set_weights()

    kwargs = validator.subtensor.set_weights.call_args.kwargs
    assert kwargs["uids"] == [1, 2]
    assert kwargs["weights"] == [16384, 49151]
    assert kwargs["wait_for_inclusion"] is True
    assert kwargs["wait_for_finalization"] is False
    assert kwargs["mechid"] == 0
    validator.cache.save_weight_matrix.assert_called_once()


def test_set_weights_uses_fresh_cache_when_api_fails():
    cached = WeightMatrix(
        refreshed_at=dt.datetime.now(UTC) - dt.timedelta(minutes=10),
        entries={1: 1.0},
    )
    validator = make_validator(RuntimeError("offline"), cached=cached)

    with patch(
        "src.validator._core.bt.utils.weight_utils.process_weights_for_netuid",
        return_value=(np.array([1]), np.array([1.0])),
    ), patch(
        "src.validator._core.bt.utils.weight_utils.convert_weights_and_uids_for_emit",
        return_value=([1], [65535]),
    ):
        validator.set_weights()

    validator.subtensor.set_weights.assert_called_once()
    validator.cache.save_weight_matrix.assert_not_called()


def test_set_weights_processes_and_submits_all_zero_example():
    matrix = WeightMatrix(
        refreshed_at=dt.datetime.now(UTC),
        entries={0: 0.0},
    )
    validator = make_validator(matrix)

    with patch(
        "src.validator._core.bt.utils.weight_utils.process_weights_for_netuid",
        return_value=(np.array([0, 1, 2]), np.array([1 / 3, 1 / 3, 1 / 3])),
    ), patch(
        "src.validator._core.bt.utils.weight_utils.convert_weights_and_uids_for_emit",
        return_value=([0, 1, 2], [21845, 21845, 21845]),
    ):
        validator.set_weights()

    validator.subtensor.set_weights.assert_called_once()
    validator.cache.save_weight_matrix.assert_called_once()


def test_set_weights_ignores_uid_outside_metagraph():
    matrix = WeightMatrix(
        refreshed_at=dt.datetime.now(UTC),
        entries={1: 0.5, 99: 1.0},
    )
    validator = make_validator(matrix)

    weights = validator._build_weight_vector(matrix)

    np.testing.assert_array_equal(weights, np.array([0.0, 0.5, 0.0]))


def test_newer_cache_wins_over_older_api_snapshot():
    now = dt.datetime.now(UTC)
    remote = WeightMatrix(
        refreshed_at=now - dt.timedelta(minutes=20), entries={1: 1.0}
    )
    cached = WeightMatrix(
        refreshed_at=now - dt.timedelta(minutes=10), entries={2: 1.0}
    )

    candidates = Validator._ordered_candidates(remote, cached, now, 3600)

    assert candidates == [("cache", cached), ("api", remote)]


def test_runtime_runs_one_immediate_cycle_then_stops():
    validator = object.__new__(BaseValidator)
    validator.should_exit = False
    validator.config = SimpleNamespace(EPOCH_LENGTH=1200)
    validator.run_cycle = Mock()
    validator._stop_event = Mock()
    validator._stop_event.wait.return_value = True

    validator.run()

    validator.run_cycle.assert_called_once_with()
    validator._stop_event.wait.assert_called_once_with(1200)
    assert validator.should_exit is True
