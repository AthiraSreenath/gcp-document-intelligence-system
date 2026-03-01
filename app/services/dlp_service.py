from typing import Any, Dict, List
import logging

from google.cloud import dlp_v2

from app.core.config import settings

logger = logging.getLogger(__name__)

_DEFAULT_INFO_TYPES = [
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD_NUMBER",
    "US_SOCIAL_SECURITY_NUMBER",
    "PERSON_NAME",
    "LOCATION",
]


class DLPService:
    """Minimal DLP wrapper for PII inspection (uploads only)."""

    def __init__(self):
        self.client = dlp_v2.DlpServiceClient()
        self.parent = f"projects/{settings.PROJECT_ID}/locations/global"

    def inspect_text(self, text: str) -> Dict[str, Any]:
        if not text:
            return {"findings": []}

        inspect_config = {
            "info_types": [{"name": n} for n in _DEFAULT_INFO_TYPES],
            "min_likelihood": dlp_v2.Likelihood.POSSIBLE,
            "include_quote": True,
        }
        item = {"value": text}

        resp = self.client.inspect_content(
            request={"parent": self.parent, "inspect_config": inspect_config, "item": item}
        )

        findings: List[Dict[str, Any]] = []
        for f in resp.result.findings:
            quote = (f.quote or "")[:60]
            findings.append(
                {
                    "info_type": f.info_type.name,
                    "likelihood": dlp_v2.Likelihood(f.likelihood).name,
                    "quote": quote,
                }
            )
        return {"findings": findings}