import os
import sys

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self

from pydantic import Field, model_validator, field_validator
from pydantic_settings import SettingsConfigDict

from redteam_core.config import BaseConfig, ENV_PREFIX_VALIDATOR


class ValidatorMainConfig(BaseConfig):
    WALLET_DIR: str = Field(
        default="~/.bittensor/wallets", description="Directory where wallets are stored"
    )
    WALLET_NAME: str = Field(
        default="validator", description="Name of the wallet to use for validation"
    )
    HOTKEY_NAME: str = Field(
        default="default", description="Name of the hotkey to use for validation"
    )
    # HOTKEY_ADDRESS: Optional[str] = Field(
    #     default=None,
    #     description="SS58 address of the hotkey to use for validation (overrides HOTKEY_NAME if set)",
    # )
    USE_CENTRALIZED_SCORING: bool = Field(
        default=True,
        description="Use centralized scoring service instead of local scoring",
    )
    DATA_DIR: str = Field(
        default="/var/lib/agent-validator",
        min_length=1,
        description="Path to store validator data.",
    )
    CACHE_DIR: str = Field(
        default="{data_dir}/cache", min_length=3, description="Cache directory path."
    )

    @field_validator("WALLET_DIR", mode="after")
    @classmethod
    def _validate_wallet_dir(cls, val: str) -> str:
        if "~" in val:
            val = os.path.expanduser(val)

        return val

    @model_validator(mode="after")
    def _check_all(self) -> Self:

        if not os.path.isdir(self.DATA_DIR):
            os.makedirs(self.DATA_DIR, exist_ok=True)

        if "{data_dir}" in self.CACHE_DIR:
            self.CACHE_DIR = self.CACHE_DIR.format(data_dir=self.DATA_DIR)

        if not os.path.isdir(self.CACHE_DIR):
            os.makedirs(self.CACHE_DIR, exist_ok=True)

        if not os.access(self.CACHE_DIR, os.W_OK):
            raise ValueError(f"Cache directory not writable: {self.CACHE_DIR}")

        return self

    model_config = SettingsConfigDict(env_prefix=ENV_PREFIX_VALIDATOR)


__all__ = [
    "ValidatorMainConfig",
]
