import logging
from typing import Tuple

from google.cloud import documentai

from app.core.config import settings

logger = logging.getLogger(__name__)


class DocAIService:
    """Extract text from PDF using Document AI.

    Requires settings.DOC_AI_PROCESSOR_NAME to be set to full processor name:
    projects/.../locations/.../processors/...
    """

    def __init__(self):
        if not settings.DOC_AI_PROCESSOR_NAME:
            raise ValueError("DOC_AI_PROCESSOR_NAME env var is required for PDF extraction via Document AI.")
        self.client = documentai.DocumentProcessorServiceClient()

    def extract_text_from_pdf_bytes(self, pdf_bytes: bytes) -> Tuple[str, int]:
        raw_document = documentai.RawDocument(content=pdf_bytes, mime_type="application/pdf")
        req = documentai.ProcessRequest(name=settings.DOC_AI_PROCESSOR_NAME, raw_document=raw_document)
        result = self.client.process_document(request=req)
        doc = result.document
        pages = len(getattr(doc, "pages", []) or [])
        return (doc.text or ""), pages