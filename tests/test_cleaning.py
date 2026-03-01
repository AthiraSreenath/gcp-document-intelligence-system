"""
Basic tests for text cleaning.
"""

from app.processing.cleaning import clean_text


def test_clean_text_removes_html():
    raw = "Hello<p>World</p>"
    out = clean_text(raw)

    assert "<p>" not in out
    assert "Hello" in out
    assert "World" in out


def test_clean_text_handles_empty():
    assert clean_text("") == ""