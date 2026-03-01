"""Internal document model (used by pipeline)."""

from typing import Any, Dict, Optional
from pydantic import BaseModel


class Document(BaseModel):
    doc_id: str
    source: str  # "hn" | "pdf"
    title: Optional[str] = None
    text: str
    metadata: Dict[str, Any] = {}