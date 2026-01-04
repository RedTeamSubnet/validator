#!/usr/bin/env python

import time
import bittensor as bt
from ._core import Validator
from .utils import AutoUpdater


# The main function parses the configuration and runs the validator.
if __name__ == "__main__":
    # Initialize the auto-updater
    AutoUpdater()

    # Start the validator
    with Validator() as validator:
        while True:
            bt.logging.info("Validator running...")
            time.sleep(validator.config.EPOCH_LENGTH // 4)

            if validator.should_exit:
                bt.logging.warning("Ending validator...")
                break
