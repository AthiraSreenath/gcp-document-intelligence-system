"""Simple logging helpers (small + scan-friendly)."""

import logging
import os
from typing import Any


def setup_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def get_logger(name: str = "app") -> logging.Logger:
    return logging.getLogger(name)


def log_event(logger: logging.Logger, msg: str, **kv: Any) -> None:
    tail = " ".join(f"{k}={str(v).replace(chr(10),' ')}" for k, v in kv.items()) if kv else ""
    logger.info(f"{msg} {tail}".rstrip())