"""Basic tests for core utility helpers."""

from app.core.utils import new_run_id, estimate_tokens


def test_new_run_id_format():
    run_id = new_run_id()
    assert isinstance(run_id, str)
    assert len(run_id) == 36  # UUID length


def test_token_estimation():
    assert estimate_tokens(100) == 25  # 100 / 4 heuristic