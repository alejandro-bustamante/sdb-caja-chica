"""Tests for repositories.users."""

from __future__ import annotations

from app.db.repositories import users


def test_create_and_list_active_users(conn, user_id):
    assert user_id is not None
    names = [u.name for u in users.list_active_users(conn)]
    assert "Alice" in names


def test_set_user_active_toggles(conn, user_id):
    users.set_user_active(conn, user_id, False)
    u = users.get_user(conn, user_id)
    assert u is not None and u.active is False
    assert user_id not in [u.id for u in users.list_active_users(conn)]
    users.set_user_active(conn, user_id, True)
    assert users.list_active_users(conn) != []
