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
    labels.add(ENTITY_LABEL)
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
    labels = get_schema_labels(config, proxy.schema)
    label = ":".join(labels)
    create_query = f"""
    UNWIND $batch AS props
    CREATE (n:{label})
    SET n = props
    """
    yield QueryBatch(query=create_query, params=properties)


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
    sconfig = config.nodes.schemata.get(proxy.schema.name)
    if sconfig is None or sconfig.ignore:
        return
    for type_name, tconfig in config.nodes.types.items():
        if not tconfig.reify:
            continue
        type_ = registry.get(type_name)
        values = proxy.get_type_values(type_, matchable=True)
        for value in values:
            if not should_reify_value(type_, value):
                continue

            node_id = type_.node_id(value)
            if node_id is None:
                continue

            caption = type_.caption(value)

            # Yield the value node query
            # Use ON CREATE to only set caption when node is first created
            node_query = f"""
            UNWIND $batch AS props
            MERGE (n:{tconfig.label} {{id: props.id}})
            ON CREATE SET n.caption = props.caption
            """
            yield QueryBatch(
                query=node_query, params={"id": node_id, "caption": caption}
            )

            # Yield the edge query
            # Use MERGE to avoid duplicate edges between same entity and value
            edge_query = f"""
            UNWIND $batch AS item
            MATCH (e:{sconfig.label} {{id: item.source_id}})
            MATCH (v:{tconfig.label} {{id: item.target_id}})
            MERGE (e)-[r:{tconfig.edge_label}]->(v)
            ON CREATE SET r = item.props
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

    sconfig = config.edges.schemata.get(proxy.schema.name)
    if sconfig is None or sconfig.ignore:
        return

    for prop in proxy.schema.sorted_properties:
        if prop.type != registry.entity or prop.range is None:
            continue

        pconfig = config.edges.properties.get(prop.qname)
        if pconfig is None or pconfig.ignore:
            continue

        srconfig = config.nodes.schemata.get(prop.range.name)
        if srconfig is None or srconfig.ignore:
            continue

        for value in proxy.get(prop):
            target_id = prop.type.node_id(value)
            if target_id is None:
                continue

            query = f"""
            UNWIND $batch AS item
            MATCH (s:{sconfig.label} {{id: item.source_id}})
            MATCH (t:{srconfig.label} {{id: item.target_id}})
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

    sconfig = config.edges.schemata.get(proxy.schema.name)
    if sconfig is None or sconfig.ignore:
        return

    for topic in proxy.get_type_values(registry.topic):
        tconfig = config.nodes.topics.get(topic)
        if tconfig is None or tconfig.ignore:
            continue

        query = f"""
        UNWIND $batch AS id
        MATCH (n:{sconfig.label} {{id: id}})
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

    if source_prop is None or source_prop.range is None:
        return
    if target_prop is None or target_prop.range is None:
        return

    ssconfig = config.nodes.schemata.get(source_prop.range.name)
    tsconfig = config.nodes.schemata.get(target_prop.range.name)
    if ssconfig is None or ssconfig.ignore:
        return
    if tsconfig is None or tsconfig.ignore:
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
    MATCH (s:{ssconfig.label} {{id: item.source_id}})
    MATCH (t:{tsconfig.label} {{id: item.target_id}})
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
        self.tx = session.begin_transaction()
        self.ops_since_commit = 0

    def add(self, batch: QueryBatch) -> None:
        self.queries[batch.query].append(batch.params)
        self.queries_count[batch.query] += 1
        if len(self.queries[batch.query]) >= self.batch_size:
            self.flush_query(batch.query)
        buffer_total = sum(len(v) for v in self.queries.values())
        if buffer_total % 10_000 == 0:
            log.info("Buffered %d queries...", buffer_total)

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
        self.tx.run(cast(LiteralString, query), batch=batch)
        self.ops_since_commit += len(batch)
        if self.ops_since_commit >= (self.batch_size * 10):
            self.tx.commit()
            self.tx = self.session.begin_transaction()
            self.ops_since_commit = 0

    def flush(self) -> None:
        for query in list(self.queries.keys()):
            self.flush_query(query)
        self.tx.commit()
        self.ops_since_commit = 0


def load_entities(
    config: Configuration,
    driver: Driver,
    source_path: Path,
) -> None:
    """Load FTM entities into Neo4j with batched transformation.

    This uses a three-pass approach by reading the file three times:
    1. First pass: Create all entity nodes (both regular and edge entities)
    2. Second pass: Create reified value nodes and edges to them
    3. Third pass: Create edges between entities

    This ensures nodes exist before edges reference them.

    Args:
        config: Configuration for transformation
        driver: Neo4j driver instance
        source_path: Path to the entities data file
    """
    # PASS 1: Create all entity nodes and add labels
    log.info("Pass 1: Creating entity nodes...")
    with driver.session() as session:
        batcher = QueryBatcher(config, session)

        for entity in read_entities(source_path):
            # Skip edge entities - they don't become nodes
            if entity.schema.edge:
                continue

            # Collect entity node queries
            batcher.consume(generate_node_entity(config, entity))

        # Execute batched queries
        total_nodes = sum(batcher.queries_count.values())
        batcher.flush()
        log.info("Created %d entity nodes", total_nodes)

    # PASS 2: Create edges between entities
    log.info("Pass 2: Creating relationship edges...")
    with driver.session() as session:
        batcher = QueryBatcher(config, session)

        for entity in read_entities(source_path):
            if entity.schema.edge:
                # Edge entities
                batcher.consume(generate_edge_entity(config, entity))
            else:
                # Collect topic label queries
                batcher.consume(generate_topic_labels(config, entity))
                # Collect reified value queries (both nodes and edges)
                batcher.consume(generate_reified_values(config, entity))
                # Entity links
                batcher.consume(generate_entity_links(config, entity))

        # Execute batched edge queries
        total_edges = sum(batcher.queries_count.values())
        batcher.flush()
        log.info("Created %d relationship edges", total_edges)

    log.info("Finished loading entities")
