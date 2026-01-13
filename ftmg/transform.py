import logging
from pathlib import Path

import stringcase
from followthemoney.entity import ValueEntity
from followthemoney.types import registry
from neo4j import Driver, Session

from ftmg.config import Configuration
from ftmg.read import read_entities

log = logging.getLogger(__name__)

ENTITY_LABEL = "Entity"


# Property types to inline on nodes
TYPES_INLINE = (
    registry.name,
    registry.date,
    registry.identifier,
    registry.country,
)

# Property types to reify into separate nodes
TYPES_REIFY = (
    registry.name,
    registry.url,
    registry.identifier,
    registry.email,
    registry.phone,
)


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


def get_topic_label(config: Configuration, topic: str) -> str:
    """Convert a topic code to a graph label.

    Args:
        topic: Topic code (e.g., "role.pep")

    Returns:
        Label name or None if topic should be skipped
    """
    label = config.nodes.topics.labels.get(topic)
    if label is not None:
        return label

    label = topic.replace(".", " ")
    label = stringcase.pascalcase(label)
    return label


def create_node_entity(
    config: Configuration,
    session: Session,
    proxy: ValueEntity,
) -> None:
    """Create a node from an FTM entity.

    Args:
        config: Configuration for transformation
        session: Neo4j session
        proxy: Entity proxy to convert
    """
    # Check if schema should be ignored
    schema_config = config.nodes.schemata.get(proxy.schema.name)
    if schema_config and schema_config.ignore:
        # log.debug("Ignoring entity %s (schema: %s)", proxy.id, proxy.schema.name)
        return

    # Skip specific schemata (from contrib/export.py)
    if proxy.schema.name in config.nodes.ignored_schemata:
        return

    # Build properties dict
    properties: dict[str, str | list[str]] = {
        "id": proxy.id,
        "caption": proxy.caption,
    }

    # Add metadata
    if proxy.datasets:
        properties["datasets"] = list(proxy.datasets)
    if proxy.referents:
        properties["referents"] = list(proxy.referents)
    # Process properties
    featured = proxy.schema.featured
    for prop in proxy.schema.sorted_properties:
        if prop.hidden:
            continue
        if prop.type.matchable and not prop.matchable:
            continue

        values = proxy.get(prop)
        if not values:
            continue

        # Inline featured properties or specific types
        if prop.name in featured or prop.type in TYPES_INLINE:
            # Store as array for multi-valued properties
            properties[prop.name] = list(values)

    # Determine labels
    labels = []
    schemata = [s for s in proxy.schema.schemata if not s.abstract]
    labels.extend([s.name for s in schemata])
    labels.append(ENTITY_LABEL)

    # Create the node with all labels and properties
    labels_str = ":".join(labels)
    session.run(
        f"CREATE (n:{labels_str}) SET n = $props",
        props=properties,
    )


def create_reified_values(
    config: Configuration,
    session: Session,
    proxy: ValueEntity,
) -> None:
    """Create reified value nodes and edges for an entity's properties.

    Args:
        _config: Configuration for transformation (unused, reserved for future use)
        session: Neo4j session
        proxy: Entity proxy
    """
    for prop in proxy.schema.sorted_properties:
        if prop.hidden:
            continue
        if prop.type not in TYPES_REIFY:
            continue

        values = proxy.get(prop)
        for value in values:
            if not should_reify_value(prop.type, value):
                continue

            node_id = prop.type.node_id(value)
            if node_id is None:
                continue

            # Create value node
            caption = prop.type.caption(value)
            session.run(
                f"""
                MERGE (v:{prop.type.name} {{id: $id}})
                SET v.caption = $caption
                """,
                id=node_id,
                caption=caption,
            )

            # Create edge from entity to value node
            edge_label = f"HAS_{stringcase.constcase(prop.type.name)}"
            datasets = list(proxy.datasets)
            session.run(
                f"""
                MATCH (e:Entity {{id: $entity_id}})
                MATCH (v:{prop.type.name} {{id: $value_id}})
                CREATE (e)-[r:{edge_label}]->(v)
                SET r.datasets = $datasets
                """,
                entity_id=proxy.id,
                value_id=node_id,
                datasets=datasets,
            )


def create_entity_links(
    config: Configuration,
    session: Session,
    proxy: ValueEntity,
) -> None:
    """Create edges for entity-reference properties.

    Args:
        _config: Configuration for transformation (unused, reserved for future use)
        session: Neo4j session
        proxy: Entity proxy
    """
    entity_id = registry.entity.node_id_safe(proxy.id)
    if entity_id is None:
        return
    for prop in proxy.schema.sorted_properties:
        if prop.type != registry.entity:
            continue

        values = proxy.get(prop)
        for value in values:
            target_id = prop.type.node_id(value)
            if target_id is None:
                continue
            edge_label = stringcase.constcase(prop.name)
            session.run(
                f"""
                MATCH (s:Entity {{id: $source_id}})
                MATCH (t:Entity {{id: $target_id}})
                CREATE (s)-[r:{edge_label}]->(t)
                SET r.datasets = $datasets
                """,
                source_id=entity_id,
                target_id=target_id,
                datasets=list(proxy.datasets),
            )


def create_topic_labels(
    config: Configuration,
    session: Session,
    proxy: ValueEntity,
) -> None:
    """Add topic labels to entity nodes.

    Args:
        config: Configuration for transformation
        session: Neo4j session
        proxy: Entity proxy
    """
    entity_id = registry.entity.node_id_safe(proxy.id)
    if entity_id is None:
        return
    topics = proxy.get_type_values(registry.topic)
    for topic in topics:
        # Check if topic should be ignored
        if topic in config.nodes.topics.ignore:
            continue

        # Get label from config or default mapping
        topic_label = get_topic_label(config, topic)

        # Add the topic label to the node
        session.run(
            f"""
            MATCH (n:Entity {{id: $id}})
            SET n:{topic_label}
            """,
            id=entity_id,
        )


def create_edge_entity(
    config: Configuration,
    session: Session,
    proxy: ValueEntity,
) -> None:
    """Create an edge from an FTM relationship entity.

    Args:
        config: Configuration for transformation
        session: Neo4j session
        proxy: Edge entity proxy
    """
    # Check if schema should be ignored
    schema_config = config.edges.schemata.get(proxy.schema.name)
    if schema_config and schema_config.ignore:
        log.debug("Ignoring edge %s (schema: %s)", proxy.id, proxy.schema.name)
        return

    source_prop = proxy.schema.source_prop
    target_prop = proxy.schema.target_prop

    if not source_prop or not target_prop:
        return

    sources = proxy.get(source_prop)
    targets = proxy.get(target_prop)

    # Determine edge label
    edge_label = schema_config.label if schema_config and schema_config.label else None
    if not edge_label:
        edge_label = stringcase.constcase(proxy.schema.name)

    # Build edge properties
    edge_props: dict[str, str | list[str]] = {"caption": proxy.caption}

    if proxy.datasets:
        edge_props["datasets"] = list(proxy.datasets)
    if proxy.referents:
        edge_props["referents"] = list(proxy.referents)

    # Add featured properties
    for prop_name in proxy.schema.featured:
        prop = proxy.schema.get(prop_name)
        if not prop or prop == source_prop or prop == target_prop:
            continue
        values = proxy.get(prop)
        if values:
            edge_props[prop.name] = values

    # Create edges for all source/target combinations
    for source_id in sources:
        for target_id in targets:
            if source_id == target_id:
                continue

            session.run(
                f"""
                MATCH (s:Entity {{id: $source_id}})
                MATCH (t:Entity {{id: $target_id}})
                CREATE (s)-[r:{edge_label}]->(t)
                SET r = $props
                """,
                source_id=source_id,
                target_id=target_id,
                edge_label=edge_label,
                props=edge_props,
            )


def load_entities(
    config: Configuration,
    driver: Driver,
    source_path: Path,
) -> None:
    """Load FTM entities into Neo4j with full transformation.

    This uses a two-pass approach by reading the file twice:
    1. First pass: Create all nodes and their reified values
    2. Second pass: Create all edges (entity links and edge entities)

    This ensures that edge entities can reference nodes regardless of
    ordering in the input file, without loading all entities into memory.

    Args:
        config: Configuration for transformation
        driver: Neo4j driver instance
        data_path: Path to the entities data file
        batch_size: Number of entities to load per transaction
    """
    node_count = 0
    edge_count = 0

    # PASS 1: Create all nodes and reified values
    log.info("Pass 1: Creating nodes and reified values...")
    with driver.session() as session:
        for entity in read_entities(source_path):
            # Process only node entities
            if entity.schema.edge:
                continue

            create_node_entity(config, session, entity)
            create_reified_values(config, session, entity)
            create_topic_labels(config, session, entity)
            node_count += 1
            if node_count > 0 and node_count % 1000 == 0:
                log.info("Created %d nodes", node_count)

    # PASS 2: Create all edges
    log.info("Pass 2: Creating edges...")
    with driver.session() as session:
        for entity in read_entities(source_path):
            # Process entity links from node entities
            if not entity.schema.edge:
                create_entity_links(config, session, entity)
                edge_count += 1
            else:
                create_edge_entity(config, session, entity)
                edge_count += 1

            if edge_count > 0 and edge_count % 1000 == 0:
                log.info("Created %d edges from batch", edge_count)

    log.info(
        "Finished loading %d entities (%d nodes, %d edges)",
        node_count + edge_count,
        node_count,
        edge_count,
    )
