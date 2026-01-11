"""Tests for the read module."""

from pathlib import Path

from followthemoney.proxy import EntityProxy

from ftmg.read import batch_iterable, read_entities


def test_read_entities(donations_file: Path) -> None:
    """Test reading entities from a JSON lines file."""
    entities = list(read_entities(donations_file))

    # Check we got some entities
    assert len(entities) > 0

    # Check all are EntityProxy instances
    assert all(isinstance(e, EntityProxy) for e in entities)

    # Check the first entity (MLPD organization)
    first = entities[0]
    assert first.id == "6d03aec76fdeec8f9697d8b19954ab6fc2568bc8"
    assert first.schema.name == "Organization"
    assert first.get("name") == ["MLPD"]


def test_read_entities_schemas(donations_file: Path) -> None:
    """Test that entities have correct schemas."""
    entities = list(read_entities(donations_file))

    # Group by schema
    schemas = {e.schema.name for e in entities}

    # Check we have expected schemas
    assert "Organization" in schemas
    assert "Person" in schemas
    assert "Address" in schemas
    assert "Payment" in schemas


def test_read_entities_properties(donations_file: Path) -> None:
    """Test that entity properties are correctly loaded."""
    entities = list(read_entities(donations_file))

    # Find a Payment entity (4th entity in the file)
    payment = next(e for e in entities if e.schema.name == "Payment")

    assert payment.id == "2216b422a31242fe204654ce194864661f515921"
    assert payment.get("amountEur") == ["100000"]
    assert payment.get("date") == ["2011-12-29"]
    assert payment.get("beneficiary") == ["6d03aec76fdeec8f9697d8b19954ab6fc2568bc8"]
    assert payment.get("payer") == ["f9c295f21b233ac878fbac4d271bb6fd13d7952a"]


def test_batch_iterable_full_batches() -> None:
    """Test batching with full batches."""
    items = list(range(25))  # 25 items
    batches = list(batch_iterable(items, batch_size=10))

    assert len(batches) == 3
    assert len(batches[0]) == 10
    assert len(batches[1]) == 10
    assert len(batches[2]) == 5  # Partial batch
    assert batches[0] == list(range(0, 10))
    assert batches[1] == list(range(10, 20))
    assert batches[2] == list(range(20, 25))


def test_batch_iterable_exact_batches() -> None:
    """Test batching when items divide evenly."""
    items = list(range(20))  # 20 items
    batches = list(batch_iterable(items, batch_size=10))

    assert len(batches) == 2
    assert len(batches[0]) == 10
    assert len(batches[1]) == 10


def test_batch_iterable_single_batch() -> None:
    """Test batching when all items fit in one batch."""
    items = list(range(5))
    batches = list(batch_iterable(items, batch_size=10))

    assert len(batches) == 1
    assert len(batches[0]) == 5
    assert batches[0] == items


def test_batch_iterable_empty() -> None:
    """Test batching with empty iterable."""
    items: list[int] = []
    batches = list(batch_iterable(items, batch_size=10))

    assert len(batches) == 0


def test_batch_iterable_with_entities(donations_file: Path) -> None:
    """Test batching with actual entities."""
    entities = read_entities(donations_file)
    batches = list(batch_iterable(entities, batch_size=3))

    # Check we got multiple batches
    assert len(batches) > 1

    # Check batch sizes
    for batch in batches[:-1]:  # All but last should be full
        assert len(batch) == 3

    # Last batch may be partial
    assert len(batches[-1]) <= 3

    # Check all items are EntityProxy
    for batch in batches:
        assert all(isinstance(e, EntityProxy) for e in batch)
