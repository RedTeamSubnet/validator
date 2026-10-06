import threading
import traceback

import bittensor as bt
from redteam_core.config import MainConfig

from .config.validator import ValidatorMainConfig


class BaseValidator:
    """Minimal synchronous runtime for a weight-setting validator."""

    def __init__(self) -> None:
        self.config: MainConfig = MainConfig()
        self.validator_config = ValidatorMainConfig()
        self.should_exit = False
        self._stop_event = threading.Event()

        self.setup_logging()
        self.setup_bittensor_objects()

    def setup_logging(self) -> None:
        bt.logging.enable_default()
        bt.logging.enable_info()
        if self.config.BITTENSOR.LOGGING_LEVEL == "DEBUG":
            bt.logging.enable_debug()
        elif self.config.BITTENSOR.LOGGING_LEVEL == "TRACE":
            bt.logging.enable_trace()
        bt.logging.info(
            f"Running validator for subnet {self.config.BITTENSOR.SUBNET_NETUID} "
            f"on network {self.config.BITTENSOR.SUBTENSOR_NETWORK}"
        )

    def setup_bittensor_objects(self) -> None:
        bt_config = self._create_bittensor_config()
        self.wallet = bt.Wallet(config=bt_config)
        self.subtensor = bt.Subtensor(config=bt_config)
        self.metagraph = self.subtensor.metagraph(
            netuid=self.config.BITTENSOR.SUBNET_NETUID
        )
        self._refresh_uid()

    def run(self) -> None:
        """Run one weight-setting cycle immediately, then once per epoch."""
        bt.logging.info("Starting validator weight loop")
        try:
            while not self.should_exit:
                try:
                    self.run_cycle()
                except Exception:
                    bt.logging.error(
                        f"Validator cycle failed: {traceback.format_exc()}"
                    )
                if self._stop_event.wait(self.config.EPOCH_LENGTH):
                    break
        except KeyboardInterrupt:
            bt.logging.info("Keyboard interrupt detected")
        finally:
            self.stop()
            bt.logging.info("Validator stopped")

    def run_cycle(self) -> None:
        self.resync_metagraph()
        self.set_weights()

    def stop(self) -> None:
        self.should_exit = True
        self._stop_event.set()

    def resync_metagraph(self) -> None:
        self.metagraph.sync(subtensor=self.subtensor)
        self._refresh_uid()
        bt.logging.info(
            f"Synced metagraph at block {self.metagraph.block}; "
            f"validator uid: {self.uid}"
        )

    def _refresh_uid(self) -> None:
        hotkey = self.wallet.hotkey.ss58_address
        if hotkey not in self.metagraph.hotkeys:
            raise RuntimeError(
                f"Validator hotkey {hotkey} is not registered on subnet "
                f"{self.config.BITTENSOR.SUBNET_NETUID}"
            )
        self.uid = self.metagraph.hotkeys.index(hotkey)

    def _create_bittensor_config(self) -> bt.Config:
        bt_config = bt.Config()
        if bt_config.wallet is None:
            bt_config.wallet = bt.Config()
        bt_config.wallet.path = self.validator_config.WALLET_DIR
        bt_config.wallet.name = self.validator_config.WALLET_NAME
        bt_config.wallet.hotkey = self.validator_config.HOTKEY_NAME

        if bt_config.subtensor is None:
            bt_config.subtensor = bt.Config()
        bt_config.subtensor.network = self.config.BITTENSOR.SUBTENSOR_NETWORK
        bt_config.netuid = self.config.BITTENSOR.SUBNET_NETUID
        return bt_config

    def set_weights(self) -> None:
        raise NotImplementedError
