from typing import Optional
from pydantic import Field
from pydantic_settings import SettingsConfigDict

from redteam_core.config import BaseConfig, ENV_PREFIX_VALIDATOR


class AutoUpdaterConfig(BaseConfig):
    """
    Validator configuration.

    Environment Variables:
        RT_VALIDATOR_UPDATE_RATE_MINUTES: Update rate in minutes (default: 60)
        RT_VALIDATOR_UPDATE_BRANCH_NAME: Git branch for updates (default: main)
    """

    UPDATE_RATE_MINUTES: int = Field(
        default=60, description="Update rate in minutes", ge=1
    )
    UPDATE_BRANCH_NAME: str = Field(
        default="main", description="Git branch name for updates"
    )

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX_VALIDATOR}AUTOUPDATER_")


class HuggingFaceConfig(BaseConfig):
    REPO_ID: str = Field(
        default="my_username/rt.agent-validator",
        description="Hugging Face repository for validator updates",
    )
    TOKEN: Optional[str] = Field(
        default=None,
        description="Hugging Face token for private repository access",
    )

    model_config = SettingsConfigDict(env_prefix=f"{ENV_PREFIX_VALIDATOR}HF_")


class ValidatorMainConfig(BaseConfig):
    WALLET_NAME: str = Field(
        default="validator", description="Name of the wallet to use for validation"
    )
    HOTKEY_NAME: str = Field(
        default="default", description="Name of the hotkey to use for validation"
    )
    HOTKEY_ADDRESS: Optional[str] = Field(
        default=None,
        description="SS58 address of the hotkey to use for validation (overrides HOTKEY_NAME if set)",
    )
    AXON_PORT: int = Field(
        default=8091,
        description="Port for the validator's Axon service",
        ge=1,
        le=65535,
    )
    HUGGINGFACE: HuggingFaceConfig = Field(default_factory=HuggingFaceConfig)
    AUTOUPDATER: AutoUpdaterConfig = Field(default_factory=AutoUpdaterConfig)
    model_config = SettingsConfigDict(env_prefix=ENV_PREFIX_VALIDATOR)


__all__ = ["AutoUpdaterConfig", "ValidatorMainConfig"]
