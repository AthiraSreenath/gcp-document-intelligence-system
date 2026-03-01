import json
import logging
from typing import Any, Dict, Tuple

from vertexai import init as vertex_init
from vertexai.generative_models import GenerationConfig, GenerativeModel

from app.core.config import settings
from app.processing.prompts import (
    extraction_prompt,
    extraction_repair_prompt,
    summary_prompt,
)

logger = logging.getLogger(__name__)


class GeminiService:
    """Tiny wrapper around Vertex AI Gemini (Flash by default)."""

    def __init__(self, model_tier: str = "flash"):
        vertex_init(project=settings.PROJECT_ID, location=settings.REGION)
        self.model_tier = model_tier
        self.model_name = settings.GEMINI_MODEL_FLASH if model_tier == "flash" else settings.GEMINI_MODEL_PRO
        self.model = GenerativeModel(self.model_name)

    def extract_structured(self, text: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        prompt = extraction_prompt(text)
        resp = self.model.generate_content(
            prompt,
            generation_config=GenerationConfig(
                temperature=0.1,
                max_output_tokens=5000,
                response_mime_type="application/json",
            ),
        )
        raw = resp.text or ""
        usage = _usage(resp)

        try:
            return json.loads(raw), usage
        except Exception:
    
            repaired = self.model.generate_content(
                extraction_repair_prompt(raw),
                generation_config=GenerationConfig(
                    temperature=0.0,
                    max_output_tokens=5000,
                    response_mime_type="application/json",
                ),
            )
            usage = _merge_usage(usage, _usage(repaired))
            try:
                return json.loads(repaired.text or ""), usage
            except Exception:
                logger.warning("Gemini JSON parse failed; returning empty schema-ish output.")
                return {"people": [], "organizations": [], "locations": [], "dates": [], "metrics": [], "core_issues": [], "sentiment": {"label": "", "rationale": ""}}, usage

    def summarize(self, text: str) -> Tuple[str, Dict[str, Any]]:
        resp = self.model.generate_content(
            summary_prompt(text),
            generation_config=GenerationConfig(temperature=0.2, max_output_tokens=5000),
        )
        return (resp.text or "").strip(), _usage(resp)


def _usage(resp: Any) -> Dict[str, Any]:
    u = getattr(resp, "usage_metadata", None)
    if not u:
        return {"prompt_tokens": None, "output_tokens": None}
    return {
        "prompt_tokens": getattr(u, "prompt_token_count", None),
        "output_tokens": getattr(u, "candidates_token_count", None),
    }


def _merge_usage(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(a)
    for k in ("prompt_tokens", "output_tokens"):
        av, bv = out.get(k), b.get(k)
        if isinstance(av, int) and isinstance(bv, int):
            out[k] = av + bv
        elif av is None and isinstance(bv, int):
            out[k] = bv
    return out