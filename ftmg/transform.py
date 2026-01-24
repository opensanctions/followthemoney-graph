from collections import defaultdict
from functools import cache
import logging
from pathlib import Path
from typing import Generator, LiteralString, NamedTuple, cast

from normality import squash_spaces
from followthemoney import Schema
from followthemoney.entity import ValueEntity
from followthemoney.types import registry
from neo4j import Driver, Session

from ftmg.config import Configuration
from ftmg.read import read_entities

log = logging.getLogger(__name__)

ENTITY_LABEL = "Entity"

QueryParams = dict[str, str | list[str] | dict[str, str | list[str]]]


class QueryBatch(NamedTuple):
    """A query with its parameters to be batched."""

    query: str
    params: QueryParams


def should_reify_value(prop_type, value: str) -> bool:
    """Check if a property value should be reified into a separate node.

    Args:
        prop_type: The property type
        value: The property value

    Returns:
        True if the value should be reified
    """
    # Filter out short identifiers
    if prop_type == registry.identifier and len(value) < 7:
        return False

    # Filter out names with no spaces
    if prop_type == registry.name and " " not in value:
        return False

    return True


@cache
def get_schema_labels(config: Configuration, schema: Schema) -> list[str]:
    """Get the labels for a given schema name.

    Args:
        config: Configuration for transformation
        schema: FollowTheMoney schema
    Returns:
        Set of labels
    """
    labels = set()
    schema_config = config.nodes.schemata.get(schema.name)
    if schema_config is not None and not schema_config.ignore:
        labels.add(schema_config.label)
    for parent in schema.extends:
        labels.update(get_schema_labels(config, parent))
    return sorted(labels)


def generate_node_entity(
    config: Configuration,
    proxy: ValueEntity,
) -> Generator[QueryBatch, None, None]:
    """Generate node creation and label queries from an FTM entity.

    Args:
        config: Configuration for transformation
        proxy: Entity proxy to convert

    Yields:
        QueryBatch with CREATE query and properties, plus label queries
    """
    sconfig = config.nodes.schemata.get(proxy.schema.name)
    if sconfig is None or sconfig.ignore:
        return

    # Build properties dict
    properties: dict[str, str | list[str]] = {
        "id": proxy.id,
        "caption": proxy.caption,
        "datasets": list(proxy.datasets),
    }

    # Process properties
    for prop_name in sconfig.properties:
        prop = proxy.schema.get(prop_name)
        assert prop is not None

        values = proxy.get(prop)
        if len(values):
            properties[prop.name] = values

    # Create node with just Entity label
    create_query = f"""
    UNWIND $batch AS props
    CREATE (n:{ENTITY_LABEL})
    SET n = props
    """
    yield QueryBatch(query=create_query, params=properties)

    # Add schema labels
    entity_id = proxy.id
    labels = get_schema_labels(config, proxy.schema)
    for label in labels:
        label_query = f"""
        UNWIND $batch AS id
        MATCH (n:{ENTITY_LABEL} {{id: id}})
        SET n:{label}
        """
        yield QueryBatch(query=label_query, params=entity_id)


def generate_reified_values(
    config: Configuration,
    proxy: ValueEntity,
) -> Generator[QueryBatch, None, None]:
    """Generate reified value node and edge queries for an entity's properties.

    Args:
        config: Configuration for transformation
        proxy: Entity proxy

    Yields:
        QueryBatch for value node creation (MERGE) and edge creation
    """
    for prop in proxy.schema.properties.values():
        pconfig = config.nodes.types.get(prop.type.name)
        if pconfig is None or not pconfig.reify:
            continue

        values = proxy.get(prop)
        for value in values:
            if not should_reify_value(prop.type, value):
                continue

            node_id = prop.type.node_id(value)
            if node_id is None:
                continue

            caption = prop.type.caption(value)

            # Yield the value node query
            node_query = f"""
            UNWIND $batch AS props
            MERGE (n:{pconfig.label} {{id: props.id}})
            SET n.caption = props.caption
            """
            yield QueryBatch(
                query=node_query, params={"id": node_id, "caption": caption}
            )

            # Yield the edge query
            edge_query = f"""
            UNWIND $batch AS item
            MATCH (e:Entity {{id: item.source_id}})
            MATCH (v {{id: item.target_id}})
            CREATE (e)-[r:{pconfig.edge_label}]->(v)
            SET r = item.props
            """
            datasets = list(proxy.datasets)
            yield QueryBatch(
                query=edge_query,
                params={
                    "source_id": proxy.id,
                    "target_id": node_id,
                    "props": {"datasets": datasets},
                },
            )


def generate_entity_links(
    config: Configuration,
    proxy: ValueEntity,
) -> Generator[QueryBatch, None, None]:
    """Generate edge queries for entity-reference properties.

    Args:
        config: Configuration for transformation
        proxy: Entity proxy

    Yields:
        QueryBatch for entity reference edge creation
    """
    entity_id = registry.entity.node_id_safe(proxy.id)
    if entity_id is None:
        return

    for prop in proxy.schema.sorted_properties:
        if prop.type != registry.entity:
            continue

        pconfig = config.edges.properties.get(prop.qname)
        if pconfig is None or pconfig.ignore:
            continue

        for value in proxy.get(prop):
            target_id = prop.type.node_id(value)
            if target_id is None:
                continue

            query = f"""
            UNWIND $batch AS item
            MATCH (s:Entity {{id: item.source_id}})
            MATCH (t:Entity {{id: item.target_id}})
            CREATE (s)-[r:{pconfig.label}]->(t)
            SET r = item.props
            """
            yield QueryBatch(
                query=query,
                params={
                    "source_id": entity_id,
                    "target_id": target_id,
                    "props": {},
                },
            )


def generate_topic_labels(
    config: Configuration,
    proxy: ValueEntity,
) -> Generator[QueryBatch, None, None]:
    """Generate topic label queries for an entity.

    Args:
        config: Configuration for transformation
        proxy: Entity proxy

    Yields:
        QueryBatch for adding topic labels to nodes
    """
    entity_id = registry.entity.node_id_safe(proxy.id)
    if entity_id is None:
        return

    for topic in proxy.get_type_values(registry.topic):
        tconfig = config.nodes.topics.get(topic)
        if tconfig is None or tconfig.ignore:
            continue

        query = f"""
        UNWIND $batch AS id
        MATCH (n:Entity {{id: id}})
        SET n:{tconfig.label}
        """
        yield QueryBatch(query=query, params=entity_id)


def generate_edge_entity(
    config: Configuration,
    proxy: ValueEntity,
) -> Generator[QueryBatch, None, None]:
    """Generate edge queries from an FTM relationship entity.

    Args:
        config: Configuration for transformation
        proxy: Edge entity proxy

    Yields:
        QueryBatch for relationship edge creation
    """
    # Check if schema should be ignored
    sconfig = config.edges.schemata.get(proxy.schema.name)
    if sconfig is None or sconfig.ignore:
        return

    source_prop = proxy.schema.source_prop
    target_prop = proxy.schema.target_prop

    if not source_prop or not target_prop:
        return

    sources = proxy.get(source_prop)
    targets = proxy.get(target_prop)

    # Build edge properties
    props: dict[str, str | list[str]] = {
        "id": proxy.id,
        # "caption": proxy.caption,
        "datasets": list(proxy.datasets),
        # "referents": list(proxy.referents),
    }

    # Add featured properties
    for prop_name in sconfig.properties:
        prop = proxy.schema.get(prop_name)
        if not prop or prop == source_prop or prop == target_prop:
            continue
        values = proxy.get(prop)
        if len(values):
            props[prop.name] = values

    # Generate edges for all source/target combinations
    query = f"""
    UNWIND $batch AS item
    MATCH (s:Entity {{id: item.source_id}})
    MATCH (t:Entity {{id: item.target_id}})
    CREATE (s)-[r:{sconfig.label}]->(t)
    SET r = item.props
    """

    for source_id in sources:
        for target_id in targets:
            if source_id == target_id:
                continue

            yield QueryBatch(
                query=query,
                params={
                    "source_id": source_id,
                    "target_id": target_id,
                    "props": props,
                },
            )


class QueryBatcher:
    def __init__(self, config: Configuration, session: Session) -> None:
        self.queries: dict[str, list[QueryParams]] = defaultdict(list)
        self.queries_count: dict[str, int] = defaultdict(int)
        self.batch_size = config.db.batch
        self.session = session

    def add(self, batch: QueryBatch) -> None:
        self.queries[batch.query].append(batch.params)
        self.queries_count[batch.query] += 1
        if self.queries_count[batch.query] >= self.batch_size:
            self.flush_query(batch.query)

    def consume(self, batches: Generator[QueryBatch, None, None]) -> None:
        for batch in batches:
            self.add(batch)

    def flush_query(self, query: str) -> None:
        batch = self.queries.pop(query, [])
        log.info(
            "Flushing query (%d items): %s",
            len(batch),
            squash_spaces(query),
        )
        self.session.run(cast(LiteralString, query), batch=batch)

    def flush(self) -> None:
        for query in list(self.queries.keys()):
            self.flush_query(query)


def load_entities(
    config: Configuration,
    driver: Driver,
    source_path: Path,
) -> None:
    """Load FTM entities into Neo4j with batched transformation.

    This uses a two-pass approach by reading the file twice:
    1. First pass: Collect all node-related queries
    2. Second pass: Collect all edge-related queries

    Queries are grouped by their query string and parameters are batched.

    Args:
        config: Configuration for transformation
        driver: Neo4j driver instance
        source_path: Path to the entities data file
    """
    # PASS 1: Collect all node queries
    log.info("Pass 1: Collecting node queries...")
    with driver.session() as session:
        batcher = QueryBatcher(config, session)

        for entity in read_entities(source_path):
            if entity.schema.edge:
                continue

            # Collect entity node queries
            batcher.consume(generate_node_entity(config, entity))

            # Collect reified value queries
            batcher.consume(generate_reified_values(config, entity))

            # Collect topic label queries
            batcher.consume(generate_topic_labels(config, entity))

        # Execute batched queries
        total_nq = sum(batcher.queries_count.values())
        batcher.flush()
        log.info("Executed %d distinct node queries...", total_nq)

        # PASS 2: Collect all edge queries
        log.info("Pass 2: Collecting edge queries...")

        for entity in read_entities(source_path):
            if entity.schema.edge:
                # Edge entities
                batcher.consume(generate_edge_entity(config, entity))
            else:
                # Entity links
                batcher.consume(generate_entity_links(config, entity))

        # Execute batched edge queries
        total_eq = sum(batcher.queries_count.values()) - total_nq
        batcher.flush()
        log.info("Executed %d distinct edge queries...", total_eq)

    log.info("Finished loading entities")
