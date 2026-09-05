import datetime as dt
from unittest.mock import Mock

from src.validator.core_api import CoreApiClient, CoreCommitOutcome


def test_commit_outcome_identity_is_stable():
    outcome = CoreCommitOutcome(
        miner_uid=7,
        miner_hotkey="hotkey",
        challenge_name="challenge",
        challenge_id="challenge-id",
        cipher_commit="ciphertext",
        revealed_key=None,
        decrypted_commit=None,
        status="discovered",
        error=None,
        committed_at=dt.datetime.now(dt.timezone.utc),
    )
    assert outcome.identity == "challenge-id:hotkey:ciphertext"


def test_outcome_updates_one_commit_record():
    client = CoreApiClient("https://core.example/api/v1", Mock())
    client._request = request = Mock()
    outcome = CoreCommitOutcome(
        miner_uid=7, miner_hotkey="hotkey", challenge_name="challenge",
        challenge_id="challenge-id", cipher_commit="ciphertext", revealed_key="key",
        decrypted_commit="repo", status="decrypted", error=None,
        committed_at=dt.datetime.now(dt.timezone.utc),
    )

    client._miner_id = Mock(return_value="miner-id")
    client._list = Mock(return_value=[{"id": "commit-id", "miner_id": "miner-id", "cipher_commit": "ciphertext"}])

    client.sync_commit(outcome, subnet_id=61)

    request.assert_called_once()
    assert request.call_args.args == ("PUT", "commits/commit-id")
    assert request.call_args.kwargs["json"]["plain_commit"] == "repo"
