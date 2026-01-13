from pathlib import Path
from typing import Generator, Iterable

from followthemoney import ValueEntity

# Batch size for bulk loading - balance between memory and performance
DEFAULT_BATCH_SIZE = 10_000


def read_entities(
    path: Path, max_line: int = 200 * 1024 * 1024
) -> Generator[ValueEntity, None, None]:
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
            yield ValueEntity.from_dict(data, cleaned=True)


def batch_iterable(
    iterable: Iterable[ValueEntity], batch_size: int = DEFAULT_BATCH_SIZE
) -> Generator[list[ValueEntity], None, None]:
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
