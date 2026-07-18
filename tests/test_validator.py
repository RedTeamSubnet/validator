from unittest.mock import MagicMock, patch

from src.validator import Validator


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
        patch("src.validator._core.Validator._init_validator_state"),
    ):
        validator = Validator()
        assert isinstance(validator, Validator), "Validator should be instantiated"
