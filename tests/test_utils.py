"""Extra utility tests (kept small)."""

from app.core.utils import estimate_cost_usd, hash_text


def test_hash_text_is_stable():
    assert hash_text("abc") == hash_text("abc")
    assert hash_text("abc") != hash_text("abcd")


def test_cost_estimate_non_negative():
    assert estimate_cost_usd("flash", 0, 0) >= 0
    assert estimate_cost_usd("pro", 10, 20) >= 0