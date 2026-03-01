"""Small utilities: run_id, hashing, timing, token/cost estimate."""

import hashlib
import time
import uuid
from contextlib import contextmanager
from typing import Dict, Iterator

from app.core.config import settings


def new_run_id() -> str:
    return str(uuid.uuid4())


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


@contextmanager
def timed() -> Iterator[Dict[str, int]]:
    t0 = time.time()
    out = {"ms": 0}
    try:
        yield out
    finally:
        out["ms"] = int((time.time() - t0) * 1000)


def estimate_tokens(chars: int) -> int:
    return max(0, chars // 4)  # rough: ~4 chars/token


def estimate_cost_usd(model_tier: str, prompt_tokens: int, output_tokens: int) -> float:
    rate = settings.COST_FLASH_PER_1K if model_tier == "flash" else settings.COST_PRO_PER_1K
    return ((max(0, prompt_tokens) + max(0, output_tokens)) / 1000.0) * float(rate)

