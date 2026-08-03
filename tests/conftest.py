"""Shared pytest fixtures: a fresh migrated in-memory-connected temp DB."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.db.connection import migrate, open_connection
from app.db.repositories.users import create_user


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """A temp DB file, freshly migrated."""
    path = tmp_path / "test.db"
    migrate(path)
    return path


@pytest.fixture
def conn(db_path: Path):
    """An open WAL connection to the migrated temp DB."""
    connection = open_connection(db_path)
    yield connection
    connection.close()


@pytest.fixture
def user_id(conn) -> int:
    """The id of an active test user."""
    return create_user(conn, "Alice")


@pytest.fixture
def other_user_id(conn) -> int:
    """A second active user, for reassignment tests."""
    return create_user(conn, "Blanca")


def make_product(conn, user_id: int, name: str, price: int) -> int:
    from app.db.repositories.products import create_product

    return create_product(conn, name, price, user_id)
