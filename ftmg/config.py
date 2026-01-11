from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseSettings):
    """Database connection settings."""

    model_config = SettingsConfigDict(env_prefix="FTMG_DB_")

    url: str
    username: str
    password: str


class Configuration(BaseModel):
    """Transformer configuration settings."""

    db: DatabaseConfig

    @classmethod
    def from_yaml(cls, path: Path) -> "Configuration":
        """Load configuration from a YAML file.

        Args:
            path: Path to the YAML configuration file

        Returns:
            Configuration object loaded from the YAML file

        Raises:
            FileNotFoundError: If the YAML file does not exist
            yaml.YAMLError: If the YAML file is malformed
            pydantic.ValidationError: If the configuration data is invalid
        """
        with path.open("r", encoding="utf-8") as f:
            data: dict[str, Any] = yaml.safe_load(f)

        return cls.model_validate(data)
