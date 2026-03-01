"""
Basic tests for chunking logic.
"""

import pytest

from app.processing.chunking import chunk_if_needed, chunk_text


def test_chunk_text_short_input():
    text = "short text"
    chunks = chunk_text(text, chunk_size=100, overlap=10)

    assert chunks == ["short text"]


def test_chunk_text_splits_long_input():
    text = "A" * 1000
    chunks = chunk_text(text, chunk_size=300, overlap=50)

    assert len(chunks) > 1
    assert all(len(c) <= 300 for c in chunks)


def test_chunk_text_validates_overlap():
    with pytest.raises(ValueError):
        chunk_text("x" * 10, chunk_size=5, overlap=5)


def test_chunk_if_needed_returns_single_when_small():
    assert chunk_if_needed("hello", max_chars=10, chunk_size=5, overlap=1) == ["hello"]