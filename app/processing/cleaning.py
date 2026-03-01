"""Text cleaning utilities."""

from bs4 import BeautifulSoup
import html
import re


def strip_html(text: str) -> str:
    """Strip HTML tags from text."""
    soup = BeautifulSoup(text or "", "html.parser")
    return soup.get_text(separator=" ")


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace to single spaces."""
    return re.sub(r"\s+", " ", (text or "")).strip()


def clean_text(text: str) -> str:
    """Clean text for NLP by stripping HTML and normalizing whitespace."""
    final_text = html.unescape(text)
    return normalize_whitespace(strip_html(final_text))
