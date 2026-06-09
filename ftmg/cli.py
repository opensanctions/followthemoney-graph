import logging
from pathlib import Path
from typing import TextIO

import click
import yaml

from ftmg.backend import (
    create_indexes,
    delete_all,
    get_driver,
    prune_reified_nodes,
    prune_unused_unique_constraints,
)
from ftmg.config import Configuration
from ftmg.transform import load_entities


@click.group()
def cli() -> None:
    """FollowTheMoney graph database transformer."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Suppress verbose Neo4j logging
    logging.getLogger("neo4j").setLevel(logging.WARNING)


@cli.command("check-config")
@click.argument(
    "config",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option("-o", "--output", type=click.File("w"), default="-")
def check_config_command(config: Path, output: TextIO) -> None:
    """Validate and expand the YAML configuration file.

    Args:
        config: Path to the YAML configuration file
    """
    configuration = Configuration.from_yaml(config)
    output.write(yaml.dump(configuration.model_dump()))


@cli.command("trash")
@click.argument(
    "config",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
def trash_command(config: Path) -> None:
    """Delete all nodes and relationships from the database.

    This command will completely wipe the graph database, removing all nodes
    and their relationships. This operation is irreversible.

    Args:
        config: Path to the YAML configuration file
    """
    configuration = Configuration.from_yaml(config)
    driver = get_driver(configuration)
    try:
        delete_all(driver)
        prune_unused_unique_constraints(driver)
    finally:
        driver.close()


@cli.command("load")
@click.argument(
    "config",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "-d",
    "--source",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to the entities data file",
)
def load_command(config: Path, source: Path) -> None:
    """Load FollowTheMoney entities into the graph database.

    Args:
        config: Path to the YAML configuration file
        source: Path to the entities data file (JSON lines format)
    """
    configuration = Configuration.from_yaml(config)
    driver = get_driver(configuration)
    create_indexes(configuration, driver)
    try:
        load_entities(configuration, driver, source)
        prune_unused_unique_constraints(driver)
    finally:
        driver.close()


@cli.command("prune")
@click.argument(
    "config",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
def prune_command(config: Path) -> None:
    """Remove reified value nodes with fewer than 2 inbound edges.

    This command cleans up reified nodes (e.g., name, address, email) that are
    only referenced by a single entity. Reified nodes are most useful when they
    represent shared values between multiple entities, so single-reference nodes
    don't provide additional value in the graph structure.

    Args:
        config: Path to the YAML configuration file
    """
    configuration = Configuration.from_yaml(config)
    driver = get_driver(configuration)
    try:
        prune_reified_nodes(configuration, driver)
        prune_unused_unique_constraints(driver)
    finally:
        driver.close()


if __name__ == "__main__":
    cli()
