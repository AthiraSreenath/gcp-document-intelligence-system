"""Prompt templates for Gemini (keep short, no magic)."""

from app.core.config import settings


SCHEMA = """{
  "people": [],
  "organizations": [],
  "locations": [],
  "dates": [],
  "metrics": [],
  "core_issues": [],
  "sentiment": {"label": "", "rationale": ""}
}"""


def extraction_prompt(text: str) -> str:
    return (
        "You are an information extraction system.\n"
        "Return ONLY valid JSON matching this schema (no markdown).\n\n"
        f"Schema:\n{SCHEMA}\n\n"
        "Rules: sentiment.label in {positive, neutral, negative}.\n"
        "core_issues are short noun phrases.\n\n"
        f"Document:\n{text}"
    )


def extraction_repair_prompt(bad: str) -> str:
    return (
        "Fix this so it becomes ONLY valid JSON matching the schema.\n\n"
        f"Schema:\n{SCHEMA}\n\n"
        f"Invalid output:\n{bad}"
    )


def summary_prompt(text: str) -> str:
    return (
        f"Understand the nature and contents of the given text. Then write a concise summary in 3-{settings.SUMMARY_SENTENCES} sentences. "
        "Focus on key facts; avoid speculation.\n\n"
        f"Document:\n{text}"
    )