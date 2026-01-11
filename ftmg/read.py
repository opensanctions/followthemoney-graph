from pathlib import Path
from typing import Generator, Iterable

from followthemoney.proxy import EntityProxy

# Batch size for bulk loading - balance between memory and performance
DEFAULT_BATCH_SIZE = 10_000


def read_entities(
    path: Path, max_line: int = 200 * 1024 * 1024
) -> Generator[EntityProxy, None, None]:
    """Read a stream of FollowTheMoney entities from a file.

    Args:
        path: Path to the file
        max_line: Maximum line length in bytes

    Yields:
        EntityProxy objects parsed from the stream
    """
    import orjson

    with open(path, "rb") as fh:
        while line := fh.readline(max_line):
            data = orjson.loads(line)
            yield EntityProxy.from_dict(data, cleaned=True)


def batch_iterable(
    iterable: Iterable[EntityProxy], batch_size: int = DEFAULT_BATCH_SIZE
) -> Generator[list[EntityProxy], None, None]:
    """Batch an iterable into chunks of specified size.

    Args:
        iterable: Iterable to batch
        batch_size: Number of items per batch

    Yields:
        Lists of items up to batch_size length
    """
    batch = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch
