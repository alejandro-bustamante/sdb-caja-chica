"""Tests for the shared UI controller helpers (plan Task 8 §1)."""

from __future__ import annotations

from app.ui.views import common_controller


def test_parse_money_input_valid_forms():
    assert common_controller.parse_money_input("10.5") == 1050
    assert common_controller.parse_money_input("10,50") == 1050
    assert common_controller.parse_money_input("$12.00") == 1200
    assert common_controller.parse_money_input("1200") == 120000
    assert common_controller.parse_money_input("0") == 0
    assert common_controller.parse_money_input("0.05") == 5
    assert common_controller.parse_money_input(" 5 ") == 500


def test_parse_money_input_invalid():
    assert common_controller.parse_money_input("") is None
    assert common_controller.parse_money_input(None) is None
    assert common_controller.parse_money_input("abc") is None
    assert common_controller.parse_money_input("-5") is None
    assert common_controller.parse_money_input("10.555") is None
    assert common_controller.parse_money_input("10.") is None


def test_parse_quantity_input():
    assert common_controller.parse_quantity_input("3") == 3
    assert common_controller.parse_quantity_input("0") is None
    assert common_controller.parse_quantity_input("-2") is None
    assert common_controller.parse_quantity_input("abc") is None
    assert common_controller.parse_quantity_input("") is None
    assert common_controller.parse_quantity_input(None) is None


def test_format_items_summary():
    items = [
        {"product_name": "Azúcar", "quantity": 2},
        {"product_name": "Cloro", "quantity": 1},
    ]
    assert common_controller.format_items_summary(items) == "Azúcar x2, Cloro x1"


def test_format_timestamp_smoke():
    import time

    value = common_controller.format_timestamp(int(time.time()))
    assert value.count("/") == 1


def test_start_of_today_ts_smoke():
    assert isinstance(common_controller.start_of_today_ts(), int)
