"""Repository for the ``users`` table.

``users`` is a plain, mutable *reference* table — the one place in the schema
where a plain ``UPDATE`` is permitted (AGENTS.md §1).
"""

from __future__ import annotations

import sqlite3

from app.db.connection import rowid, transaction
from app.domain.types import User


def create_user(conn: sqlite3.Connection, name: str) -> int:
    """Insert a new active user and return its id."""
    with transaction(conn) as cur:
        cur.execute(
            "INSERT INTO users (name, active) VALUES (?, 1)", (name,)
        )
        lastrowid = rowid(cur)
    return lastrowid


def list_active_users(conn: sqlite3.Connection) -> list[User]:
    rows = conn.execute(
        "SELECT id, name, active FROM users WHERE active = 1 ORDER BY name"
    ).fetchall()
    return [User(id=r["id"], name=r["name"], active=bool(r["active"])) for r in rows]


def list_all_users(conn: sqlite3.Connection) -> list[User]:
    rows = conn.execute(
        "SELECT id, name, active FROM users ORDER BY name"
    ).fetchall()
    return [User(id=r["id"], name=r["name"], active=bool(r["active"])) for r in rows]


def set_user_active(conn: sqlite3.Connection, user_id: int, active: bool) -> None:
    """Toggle a user's ``active`` flag (plain UPDATE on a reference table)."""
    with transaction(conn):
        conn.execute(
            "UPDATE users SET active = ? WHERE id = ?", (int(active), user_id)
        )


def get_user(conn: sqlite3.Connection, user_id: int) -> User | None:
    row = conn.execute(
        "SELECT id, name, active FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if row is None:
        return None
    return User(id=row["id"], name=row["name"], active=bool(row["active"]))
