import os
from typing_extensions import Optional, Self
from pydantic import Field, model_validator
from pydantic_settings import SettingsConfigDict

from redteam_core.config import BaseConfig, ENV_PREFIX_VALIDATOR


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
    USE_CENTRALIZED_SCORING: bool = Field(
        default=True,
        description="Use centralized scoring service instead of local scoring",
    )
    CACHE_DIR: str = Field(
        default="/var/lib/agent-validator/cache", description="Cache directory path"
    )
    model_config = SettingsConfigDict(env_prefix=ENV_PREFIX_VALIDATOR)

    @model_validator(mode="after")
    def validate_cache_dir(self) -> Self:
        """Ensure cache directory exists and is writable."""
        expanded = os.path.expanduser(self.CACHE_DIR)
        os.makedirs(expanded, exist_ok=True)
        if not os.access(expanded, os.W_OK):
            raise ValueError(f"Cache directory not writable: {expanded}")
        return self


__all__ = ["AutoUpdaterConfig", "ValidatorMainConfig"]
