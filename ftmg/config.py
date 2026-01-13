from functools import cached_property
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseSettings):
    """Database connection settings."""

    model_config = SettingsConfigDict(env_prefix="FTMG_DB_")

    url: str
    username: str
    password: str
    batch: int = 50_000


class TypeReificationConfig(BaseModel):
    """Configuration for property type reification."""

    reify: bool = True
    label: str | None = None


class SchemaNodeConfig(BaseModel):
    """Configuration for a specific entity schema's node representation."""

    ignore: bool = False
    label: str | None = None
    properties: list[str] | None = None


class TopicsConfig(BaseModel):
    """Configuration for topic-to-label mapping."""

    labels: dict[str, str] = Field(default_factory=dict)
    ignore: list[str] = Field(default_factory=list)


class NodesConfig(BaseModel):
    """Configuration for node transformation rules."""

    schemata: dict[str, SchemaNodeConfig] = Field(default_factory=dict)
    types: dict[str, TypeReificationConfig] = Field(default_factory=dict)
    topics: TopicsConfig = Field(default_factory=TopicsConfig)

    @cached_property
    def ignored_schemata(self) -> set[str]:
        """Get the set of schemata names that are configured to be ignored.

        Returns:
            Set of schema names to ignore
        """
        return {name for name, cfg in self.schemata.items() if cfg.ignore}


class SchemaEdgeConfig(BaseModel):
    """Configuration for a specific edge schema."""

    ignore: bool = False
    label: str | None = None
    properties: list[str] | None = None


class PropertyEdgeConfig(BaseModel):
    """Configuration for property-based edge creation."""

    label: str


class EdgesConfig(BaseModel):
    """Configuration for edge transformation rules."""

    schemata: dict[str, SchemaEdgeConfig] = Field(default_factory=dict)
    properties: dict[str, PropertyEdgeConfig] = Field(default_factory=dict)


class Configuration(BaseModel):
    """Transformer configuration settings."""

    db: DatabaseConfig
    nodes: NodesConfig = Field(default_factory=NodesConfig)
    edges: EdgesConfig = Field(default_factory=EdgesConfig)

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
