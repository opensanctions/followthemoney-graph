"""Pytest configuration and shared fixtures."""

from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def donations_file(fixtures_dir: Path) -> Path:
    """Return the path to the donations.ijson test file."""
    return fixtures_dir / "donations.ijson"
