from pathlib import Path
from typing import Any

import yaml
from followthemoney import model, registry
from pydantic import BaseModel, Field, model_validator
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

    @model_validator(mode="before")
    @classmethod
    def complete_model(cls, config: dict[str, Any]) -> dict[str, Any]:
        """Fill in any missing schemata from the model."""
        schemata = config.get("schemata", {})
        if not isinstance(schemata, dict):
            raise ValueError("Nodes 'schemata' must be a dictionary.")
        # Fill in any missing node schemata from the model:
        for schema in model.schemata.values():
            if not schema.edge and schema.name not in schemata:
                schemata[schema.name] = {}
        for name, sconfig in schemata.items():
            schema = model.get(name)
            if schema is None or schema.edge:
                raise ValueError(f"Node schemata refers to invalid schema: {name}")
            sconfig["label"] = sconfig.get("label") or schema.name
            sconfig["properties"] = sconfig.get("properties", schema.featured)

        return config


class SchemaEdgeConfig(BaseModel):
    """Configuration for a specific edge schema."""

    ignore: bool = False
    label: str
    properties: list[str]


class PropertyEdgeConfig(BaseModel):
    """Configuration for property-based edge creation."""

    ignore: bool = False
    label: str


class EdgesConfig(BaseModel):
    """Configuration for edge transformation rules."""

    schemata: dict[str, SchemaEdgeConfig] = Field(default_factory=dict)
    properties: dict[str, PropertyEdgeConfig] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def complete_model(cls, config: dict[str, Any]) -> dict[str, Any]:
        """Ensure that schemata and properties are dictionaries."""
        schemata = config.get("schemata", {})
        if not isinstance(schemata, dict):
            raise ValueError("Edges 'schemata' must be a dictionary.")
        # Fill in any missing edge schemata from the model
        for schema in model.schemata.values():
            if schema.edge and schema.name not in schemata:
                schemata[schema.name] = {}
        for name, sconfig in schemata.items():
            schema = model.get(name)
            if schema is None or not schema.edge:
                raise ValueError(f"Edge schemata refers to invalid edge schema: {name}")
            sconfig["label"] = sconfig.get("label") or schema.name
            sconfig["properties"] = sconfig.get("properties", schema.featured)

        properties = config.get("properties", {})
        if not isinstance(properties, dict):
            raise ValueError("Edges 'properties' must be a dictionary.")
        for name, pconfig in properties.items():
            prop = model.get_qname(name)
            if prop is None or prop.type != registry.entity:
                raise ValueError(f"Edge properties refers to invalid property: {name}")
            # pconfig["label"] = pconfig.get("label") or prop.name
        return config


class Configuration(BaseModel):
    """Transformer configuration settings."""

    path: Path
    db: DatabaseConfig
    nodes: NodesConfig = Field(default_factory=NodesConfig)
    edges: EdgesConfig = Field(default_factory=EdgesConfig)

    def __hash__(self) -> int:
        return hash(self.path)

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

        data["path"] = path  # Set the path attribute
        return cls.model_validate(data)
