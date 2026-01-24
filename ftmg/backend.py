import logging
from typing import LiteralString, cast

from neo4j import Driver, GraphDatabase

from ftmg.config import Configuration

log = logging.getLogger(__name__)


def get_driver(config: Configuration) -> Driver:
    """Create a Neo4j GraphDatabase client from the given configuration.

    Args:
        config: Configuration object containing database connection settings.
    Returns:
        A Neo4j GraphDatabase client instance.
    """
    driver = GraphDatabase.driver(
        config.db.url,
        auth=(config.db.username, config.db.password),
    )
    log.info("Connected to database: %s", config.db.url)
    return driver


def create_indexes(config: Configuration, driver: Driver) -> None:
    """Create indexes for all entity and reified value node types.

    Creates indexes on the `id` property for:
    - Entity nodes (base label)
    - All schema node labels (Person, Company, etc.)
    - All reified value node labels (Address, Email, etc.)

    Args:
        config: Configuration containing node type definitions
        driver: Neo4j driver instance
    """
    with driver.session() as session:
        indexes_created = 0

        # Index for base Entity label
        index_name = "entity_id_index"
        query = """
        CREATE INDEX entity_id_index IF NOT EXISTS FOR (n:Entity) ON (n.id)
        """
        session.run(cast(LiteralString, query))
        # log.info("Created index: %s", index_name)
        indexes_created += 1

        # Indexes for schema node labels
        for sconfig in config.nodes.schemata.values():
            if sconfig.ignore:
                continue

            label = sconfig.label
            index_name = f"{label.lower()}_id_index"
            query = f"""
            CREATE INDEX {index_name} IF NOT EXISTS FOR (n:{label}) ON (n.id)
            """
            session.run(cast(LiteralString, query))
            # log.info("Created index: %s", index_name)
            indexes_created += 1

        # Indexes for reified value node labels
        for type_config in config.nodes.types.values():
            if not type_config.reify:
                continue

            label = type_config.label
            index_name = f"{label.lower()}_id_index"
            query = f"""
            CREATE INDEX {index_name} IF NOT EXISTS FOR (n:{label}) ON (n.id)
            """
            session.run(cast(LiteralString, query))
            # log.info("Created index: %s", index_name)
            indexes_created += 1

        log.info("Created %d indexes total", indexes_created)


def delete_all(driver: Driver) -> None:
    """Delete all nodes and relationships from the database.

    Args:
        driver: Neo4j driver instance
    """
    with driver.session() as session:
        # First, get counts before deletion
        result = session.run("MATCH (n) RETURN count(n) as node_count")
        record = result.single()
        node_count = record["node_count"] if record else 0

        result = session.run("MATCH ()-[r]->() RETURN count(r) as rel_count")
        record = result.single()
        rel_count = record["rel_count"] if record else 0

        log.info(
            "Deleting %d nodes and %d relationships...",
            node_count,
            rel_count,
        )

        # Delete all nodes and relationships
        # DETACH DELETE removes all relationships connected to nodes before deleting nodes
        session.run("MATCH (n) DETACH DELETE n")

        log.info(
            "Deleted %d nodes and %d relationships",
            node_count,
            rel_count,
        )
