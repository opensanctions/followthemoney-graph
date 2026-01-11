import logging
from typing import Iterable

from followthemoney.proxy import EntityProxy
from neo4j import Driver

from ftmg.read import DEFAULT_BATCH_SIZE, batch_iterable

log = logging.getLogger(__name__)


def create_entities(
    driver: Driver,
    entities: Iterable[EntityProxy],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    """Create nodes from FollowTheMoney entities using batched UNWIND operations.

    Args:
        driver: Neo4j driver instance
        entities: Iterable of EntityProxy objects to load
        batch_size: Number of entities to load per transaction
    """
    total_count = 0

    with driver.session() as session:
        for batch in batch_iterable(entities, batch_size):
            # Convert entities to dictionaries for UNWIND
            nodes_data = []
            for entity in batch:
                node_data = {
                    "id": entity.id,
                    "schema": entity.schema.name,
                    "properties": {},
                }
                # Collect all properties
                for prop, values in entity.properties.items():
                    if values:
                        node_data["properties"][prop] = list(values)

                nodes_data.append(node_data)

            # Batch insert nodes using UNWIND
            session.run(
                """
                UNWIND $nodes AS node
                CREATE (n)
                SET n.id = node.id
                SET n.schema = node.schema
                SET n += node.properties
                """,
                nodes=nodes_data,
            )

            total_count += len(batch)
            log.info("Created %d entities (%d total)", len(batch), total_count)

    log.info("Finished creating %d entities", total_count)
