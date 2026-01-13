import logging
from pathlib import Path

import click

from ftmg.backend import delete_all, get_driver
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


@cli.command("trash")
@click.argument(
    "config",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.confirmation_option(
    prompt="Are you sure you want to delete ALL nodes and relationships?"
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
    try:
        load_entities(configuration, driver, source)
    finally:
        driver.close()


if __name__ == "__main__":
    cli()
