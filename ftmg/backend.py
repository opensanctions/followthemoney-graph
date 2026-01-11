import logging

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
