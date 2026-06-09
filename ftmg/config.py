from pathlib import Path
from typing import Any

import stringcase
import yaml
from followthemoney import model, registry
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENTITY_IGNORE_PROP_TYPES = (
    registry.entity,
    registry.html,
    registry.text,
    registry.checksum,
    registry.json,
    registry.topic,
    registry.mimetype,
)


class DatabaseConfig(BaseSettings):
    """Database connection settings."""

    model_config = SettingsConfigDict(env_prefix="FTMG_DB_")

    url: str
    username: str
    password: str
    batch: int = 10_000


class TypeReificationConfig(BaseModel):
    """Configuration for property type reification."""

    reify: bool = False
    label: str
    edge_label: str


class SchemaNodeConfig(BaseModel):
    """Configuration for a specific entity schema's node representation."""

    ignore: bool = False
    label: str
    properties: list[str]


class TopicLabelsConfig(BaseModel):
    """Configuration for topic to label mapping."""

    label: str
    ignore: bool = False


class NodesConfig(BaseModel):
    """Configuration for node transformation rules."""

    schemata: dict[str, SchemaNodeConfig] = Field(default_factory=dict)
    types: dict[str, TypeReificationConfig] = Field(default_factory=dict)
    topics: dict[str, TopicLabelsConfig] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def complete_model(cls, config: dict[str, Any]) -> dict[str, Any]:
        # Fill in any missing node schemata from the model:
        schemata = config.get("schemata", {})
        for schema in model.schemata.values():
            if schema.name not in schemata:
                if not schema.edge and not schema.abstract:
                    schemata[schema.name] = {}
        for name, sconfig in schemata.items():
            node_schema = model.get(name)
            if node_schema is None or node_schema.edge or node_schema.abstract:
                raise ValueError(f"Node schemata refers to invalid schema: {name}")
            sconfig["label"] = sconfig.get("label", node_schema.name)
            inline_properties: list[str] = []
            for prop in node_schema.properties.values():
                if prop.hidden or prop.type in ENTITY_IGNORE_PROP_TYPES:
                    continue
                inline_properties.append(prop.name)
            sconfig["properties"] = sconfig.get("properties", inline_properties)
        config["schemata"] = schemata

        # Fill in any missing type reification configs from the model:
        types = config.get("types", {})
        for type_ in registry.types:
            if type_.matchable and type_.name not in types:
                types[type_.name] = {"reify": False}
        for name, tconfig in types.items():
            try:
                type_ = registry.get(name)
            except AttributeError as err:
                raise ValueError(f"Types config refers to invalid type: {name}") from err
            if not type_.matchable:
                raise ValueError(f"Type is not matchable: {name}")
            tconfig["label"] = tconfig.get("label", type_.name)
            edge_label = f"HAS_{stringcase.constcase(type_.name)}"
            tconfig["edge_label"] = tconfig.get("edge_label", edge_label)

        config["types"] = types

        # Fill in any missing topic labels from the model:
        topics = config.get("topics", {})
        for topic in registry.topic.codes:
            if topic not in topics:
                topics[topic] = {}
        for name, tconfig in topics.items():
            if name not in registry.topic.codes:
                raise ValueError(f"Config refers to invalid topic: {name}")
            label = name.replace(".", "_").capitalize()
            label = stringcase.pascalcase(label)
            tconfig["label"] = tconfig.get("label", label)
            tconfig["ignore"] = tconfig.get("ignore", False)
        config["topics"] = topics

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
        # Fill in any missing edge schemata from the model
        schemata = config.get("schemata", {})
        if not isinstance(schemata, dict):
            raise ValueError("Edges 'schemata' must be a dictionary.")
        for schema in model.schemata.values():
            if schema.edge and schema.name not in schemata:
                schemata[schema.name] = {}
        for name, sconfig in schemata.items():
            edge_schema = model.get(name)
            if edge_schema is None or not edge_schema.edge:
                raise ValueError(f"Edge schemata refers to invalid edge schema: {name}")
            label = stringcase.constcase(edge_schema.edge_label)
            sconfig["label"] = sconfig.get("label", label)
            inline_properties: list[str] = []
            for prop in edge_schema.properties.values():
                if prop.type == registry.entity or prop.hidden:
                    continue
                inline_properties.append(prop.name)
            sconfig["properties"] = sconfig.get("properties", inline_properties)
        config["schemata"] = schemata

        # Entity properties that are meant to be turned into edges:
        properties = config.get("properties", {})
        if not isinstance(properties, dict):
            raise ValueError("Edges 'properties' must be a dictionary.")
        for prop in model.properties:
            if prop.type == registry.entity and prop.qname not in properties:
                properties[prop.qname] = {}
        for name, pconfig in properties.items():
            edge_prop = model.get_qname(name)
            if edge_prop is None or edge_prop.type != registry.entity:
                raise ValueError(f"Edge properties refers to invalid property: {name}")
            pconfig["label"] = pconfig.get("label", stringcase.constcase(edge_prop.name))
            pconfig["ignore"] = pconfig.get("ignore", edge_prop.hidden)
        config["properties"] = properties
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
