import logging
from typing import LiteralString, Set, cast

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
    """Create unique constraints and indexes for all entity and reified value node types.

    Creates unique constraints on the `id` property for:
    - Entity nodes (base label)
    - All schema node labels (Person, Company, etc.)
    - All reified value node labels (Address, Email, etc.)

    Note: Unique constraints automatically create an index, so this enforces both
    uniqueness and fast lookups on the `id` property.

    Args:
        config: Configuration containing node type definitions
        driver: Neo4j driver instance
    """
    with driver.session() as session:
        constraints_created = 0

        # Unique constraint for base Entity label
        constraint_name = "entity_id_unique"
        query = """
        CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE
        """
        session.run(cast(LiteralString, query))
        # log.info("Created constraint: %s", constraint_name)
        constraints_created += 1

        # Unique constraints for schema node labels
        for sconfig in config.nodes.schemata.values():
            if sconfig.ignore:
                continue

            label = sconfig.label
            constraint_name = f"{label.lower()}_id_unique"
            query = f"""
            CREATE CONSTRAINT {constraint_name} IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE
            """
            session.run(cast(LiteralString, query))
            # log.info("Created constraint: %s", constraint_name)
            constraints_created += 1

        # Unique constraints for reified value node labels
        for type_config in config.nodes.types.values():
            if not type_config.reify:
                continue

            label = type_config.label
            constraint_name = f"{label.lower()}_id_unique"
            query = f"""
            CREATE CONSTRAINT {constraint_name} IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE
            """
            session.run(cast(LiteralString, query))
            # log.info("Created constraint: %s", constraint_name)
            constraints_created += 1

        log.info("Created %d unique constraints total", constraints_created)


def prune_unused_unique_constraints(driver: Driver) -> None:
    """
    Find and delete unique constraints where no nodes use the constrained label.

    Args:
        driver: Neo4j driver instance

    Returns:
        List of deleted (or would-be-deleted) constraint names
    """
    removed: Set[str] = set()
    with driver.session() as session:
        # Get all unique constraints
        result = session.run("SHOW CONSTRAINTS")
        constraints = result.data()

        for constraint in constraints:
            if constraint["type"] != "UNIQUENESS":
                continue
            total_count = 0
            for label in constraint["labelsOrTypes"]:
                # Check if any nodes exist with this label
                q = f"MATCH (n:`{label}`) RETURN count(n) AS cnt"
                res = session.run(cast(LiteralString, q)).single()
                if res is not None:
                    total_count += res["cnt"]

            removed.add(constraint["name"])

            if total_count == 0:
                q = f"DROP CONSTRAINT `{constraint['name']}`"
                session.run(cast(LiteralString, q))

    if len(removed) > 0:
        log.info("Removed %d unused unique constraints: %r", len(removed), removed)


def prune_reified_nodes(config: Configuration, driver: Driver) -> None:
    """Delete reified value nodes that are referenced by fewer than 2 unique entities.

    Reified nodes are only useful when they represent shared values between multiple
    entities. This function removes reified nodes that are only referenced by a single
    entity (even if that entity has multiple edges to the node), as they don't provide
    additional value in the graph structure.

    This uses a batched approach to avoid memory issues with large graphs.

    Args:
        config: Configuration containing node type definitions
        driver: Neo4j driver instance
    """
    with driver.session() as session:
        total_deleted = 0

        # Iterate over all reified value node types
        for tconfig in config.nodes.types.values():
            if not tconfig.reify:
                continue

            label = tconfig.label
            label_deleted = 0
            batch = config.db.batch * 10

            # Process deletions in batches to avoid memory issues
            while True:
                # Find and delete a batch of nodes referenced by fewer than 2 unique source entities
                query = f"""
                MATCH (n:{label})
                OPTIONAL MATCH (n)<-[]-(source)
                WITH n, count(DISTINCT source) as unique_sources
                WHERE unique_sources < 2
                WITH n LIMIT $batch_size
                DETACH DELETE n
                RETURN count(n) as deleted_count
                """
                result = session.run(cast(LiteralString, query), batch_size=batch)
                record = result.single()
                deleted_count = record["deleted_count"] if record else 0

                label_deleted += deleted_count
                total_deleted += deleted_count

                if deleted_count > 0:
                    log.info(
                        "Deleted batch of %d %s nodes with <2 unique source entities",
                        deleted_count,
                        label,
                    )

                # If we deleted fewer than batch_size, we're done with this label
                if deleted_count < batch:
                    break

            if label_deleted > 0:
                log.info(
                    "Total deleted for %s: %d nodes",
                    label,
                    label_deleted,
                )

        log.info("Total reified nodes pruned: %d", total_deleted)


def delete_all(driver: Driver, batch_size: int = 50_000) -> None:
    """Delete all nodes and relationships from the database.

    Uses batched deletion to avoid transaction size limits and timeouts.

    Args:
        driver: Neo4j driver instance
        batch_size: Number of nodes to delete per batch
    """
    with driver.session() as session:
        # First, get counts before deletion
        result = session.run("MATCH (n) RETURN count(n) as node_count")
        record = result.single()
        initial_node_count = record["node_count"] if record else 0

        result = session.run("MATCH ()-[r]->() RETURN count(r) as rel_count")
        record = result.single()
        initial_rel_count = record["rel_count"] if record else 0

        log.info(
            "Deleting %d nodes and %d relationships...",
            initial_node_count,
            initial_rel_count,
        )

        # Delete nodes in batches
        # DETACH DELETE removes all relationships connected to nodes before deleting nodes
        total_deleted = 0
        while True:
            query = """
            MATCH (n)
            WITH n LIMIT $batch_size
            DETACH DELETE n
            RETURN count(n) as deleted_count
            """
            result = session.run(cast(LiteralString, query), batch_size=batch_size)
            record = result.single()
            deleted_count = record["deleted_count"] if record else 0

            total_deleted += deleted_count

            if deleted_count > 0:
                log.info("Deleted %d nodes, total: %d", deleted_count, total_deleted)

            # If we deleted fewer than batch_size, we're done
            if deleted_count < batch_size:
                break

        log.info(
            "Deleted %d nodes total (had %d nodes, %d relationships)",
            total_deleted,
            initial_node_count,
            initial_rel_count,
        )
