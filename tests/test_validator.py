import datetime
from unittest.mock import MagicMock, call, patch

from src.validator import Validator
from src.validator.core_api import CoreApiClient, CoreCommitSubmission


class _Response:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


def _core_validator(active_challenges):
    hotkey = MagicMock()
    hotkey.ss58_address = "5" * 48
    hotkey.sign.return_value = bytes.fromhex("ab" * 64)
    return CoreApiClient("https://core.example/api/v1", hotkey), active_challenges


def _active_challenge(name="bot_virus_v1"):
    return {
        "name": name,
        "description": "Bot virus",
        "core_kind": "BV",
        "core_kind_description": "Bot virus challenge",
        "core_config_spec": {"challenge_type": "bv"},
        "core_config_active_from": "2026-01-01T00:00:00+00:00",
        "core_config_active_until": None,
        "core_version": "v1.0.0",
        "core_start_at": "2026-01-01T00:00:00+00:00",
        "core_end_at": None,
        "core_is_enabled": True,
    }


def test_sync_active_challenges_uses_existing_core_challenge():
    client, active_challenges = _core_validator({"bot_virus_v1": _active_challenge()})

    with (
        patch(
            "src.validator.core_api.requests.post",
            side_effect=[
                _Response({"nonce": "n" * 32}),
                _Response({"access_token": "wallet-token"}),
            ],
        ) as post,
        patch(
            "src.validator.core_api.requests.request",
            return_value=_Response({"data": [{"id": "ch_1", "name": "bot_virus_v1"}]}),
        ) as request,
    ):
        client.sync_active_challenges(active_challenges)

    assert active_challenges["bot_virus_v1"]["challenge_id"] == "ch_1"
    assert request.call_count == 1
    assert post.call_args_list[0] == call(
        "https://core.example/api/v1/auth/wallet/challenge",
        json={"ss58_address": "5" * 48},
        timeout=30,
    )


def test_sync_active_challenges_creates_missing_core_challenge():
    client, active_challenges = _core_validator({"bot_virus_v1": _active_challenge()})

    with (
        patch(
            "src.validator.core_api.requests.post",
            side_effect=[
                _Response({"nonce": "n" * 32}),
                _Response({"access_token": "wallet-token"}),
            ],
        ),
        patch(
            "src.validator.core_api.requests.request",
            side_effect=[
                _Response({"data": []}),
                _Response({"data": {"id": "chk_1"}}, 201),
                _Response({"data": {"id": "chc_1"}}, 201),
                _Response({"data": {"id": "ch_1"}}, 201),
            ],
        ) as request,
    ):
        client.sync_active_challenges(active_challenges)

    assert active_challenges["bot_virus_v1"]["challenge_id"] == "ch_1"
    assert [call.args[:2] for call in request.call_args_list] == [
        ("GET", "https://core.example/api/v1/challenges/"),
        ("POST", "https://core.example/api/v1/challenge-kinds/"),
        ("POST", "https://core.example/api/v1/challenge-configs/"),
        ("POST", "https://core.example/api/v1/challenges/"),
    ]


def test_get_core_api_challenges_follows_pagination():
    client, _ = _core_validator({})
    first_page = [{"id": f"ch_{index}", "name": f"challenge_{index}"} for index in range(100)]

    with patch.object(
        client,
        "_request",
        side_effect=[first_page, [{"id": "ch_100", "name": "challenge_100"}]],
    ) as request:
        challenges = client._challenges_by_name("wallet-token")

    assert challenges["challenge_100"]["id"] == "ch_100"
    assert request.call_args_list[1].kwargs["params"] == {"skip": 100, "limit": 100}


def test_fetch_seen_commits_groups_commits_by_challenge_and_cipher():
    client, active_challenges = _core_validator({"bot_virus_v1": _active_challenge()})
    active_challenges["bot_virus_v1"]["challenge_id"] = "ch_1"

    with (
        patch.object(client, "_access_token", return_value="wallet-token"),
        patch.object(
            client,
            "_request",
            return_value=[
                {
                    "cipher_commit": "cipher-text",
                    "committed_at": "2026-01-01T00:00:00Z",
                }
            ],
        ) as request,
    ):
        seen_commits = client.fetch_seen_commits(active_challenges)

    assert seen_commits == {
        "bot_virus_v1": {
            "cipher-text": datetime.datetime(
                2026, 1, 1, tzinfo=datetime.timezone.utc
            )
        }
    }
    assert request.call_args.kwargs["params"] == {
        "challenge_id": "ch_1",
        "skip": 0,
        "limit": 100,
    }


def test_sync_submissions_posts_only_unseen_commit_and_updates_cache():
    client, _ = _core_validator({})
    submitted_at = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)

    with (
        patch.object(client, "_access_token", return_value="wallet-token"),
        patch.object(
            client,
            "_request",
            side_effect=[
                [{"id": "miner_1"}],
                {"committed_at": "2026-01-01T00:00:00Z"},
            ],
        ) as request,
    ):
        seen_commits = {"bot_virus_v1": {}}
        client.sync_submissions(
            [
                CoreCommitSubmission(
                    miner_uid=7,
                    miner_hotkey="hotkey_7",
                    challenge_name="bot_virus_v1",
                    challenge_id="ch_1",
                    cipher_commit="cipher-text",
                    committed_at=submitted_at,
                )
            ],
            subnet_id=61,
            seen_commits=seen_commits,
        )

    assert request.call_args_list[1].kwargs["json"] == {
        "cipher_commit": "cipher-text",
        "committed_at": "2026-01-01T00:00:00+00:00",
        "challenge_id": "ch_1",
        "miner_id": "miner_1",
    }
    assert seen_commits["bot_virus_v1"]["cipher-text"] == submitted_at


def test_core_sync_queries_axons_without_reading_local_miner_commits():
    validator = Validator.__new__(Validator)
    validator.metagraph = MagicMock()
    validator.metagraph.uids = [0]
    validator.metagraph.axons = [MagicMock()]
    validator.metagraph.hotkeys = ["hotkey_0"]
    validator.wallet = MagicMock()
    validator.config = MagicMock()
    validator.config.QUERY_TIMEOUT = 12
    validator.config.BITTENSOR.SUBNET_NETUID = 61
    validator.seen_commits = {"bot_virus_v1": {}}
    validator.core_api_client = MagicMock()
    response = MagicMock()
    response.encrypted_commit_dockers = {"bot_virus_v1": "cipher-text"}

    with patch("src.validator._core.bt.Dendrite") as dendrite:
        dendrite.return_value.query.return_value = [response]
        validator.sync_miner_commits_to_core(
            {"bot_virus_v1": {"challenge_id": "ch_1"}}
        )

    submissions = validator.core_api_client.sync_submissions.call_args.args[0]
    assert len(submissions) == 1
    assert submissions[0].miner_hotkey == "hotkey_0"
    assert submissions[0].cipher_commit == "cipher-text"
    assert validator.core_api_client.sync_submissions.call_args.kwargs["subnet_id"] == 61


def test_validator_instantiation():
    def _setup_bt_objects(self):
        self.metagraph = MagicMock()
        self.metagraph.hotkeys = ["mock_hotkey"]
        self.wallet = MagicMock()
        self.wallet.hotkey.ss58_address = "mock_hotkey"
        self.uid = 0
        self.subtensor = MagicMock()
        self.dendrite = MagicMock()

    with (
        patch("src.validator._base.BaseValidator.setup_logging"),
        patch("src.validator._base.BaseValidator.setup_bittensor_objects", new=_setup_bt_objects),
        patch("src.validator._core.StorageManager"),
        patch("src.validator._core.start_bittensor_log_listener"),
        patch("src.validator._core.create_validator_request_header_fn"),
        patch("src.validator._core.Validator._get_storage_api_key", return_value="mock_api_key"),
        patch("src.validator._core.Validator.commit_repo_id_to_chain"),
        patch("src.validator._core.Validator._init_active_challenges"),
        patch("src.validator._core.Validator._init_seen_commits"),
        patch("src.validator._core.Validator._init_validator_state"),
    ):
        validator = Validator()
        assert isinstance(validator, Validator), "Validator should be instantiated"
