import pytest

from app.modules.inventory.repository import is_low_stock


@pytest.mark.parametrize(
    ("balance", "minimum", "expected"),
    [(6, 5, False), (5, 5, True), (0, 5, True), (0, 0, True)],
)
def test_low_stock_includes_minimum_and_empty_zero_threshold(balance, minimum, expected):
    assert is_low_stock(balance, minimum) is expected
