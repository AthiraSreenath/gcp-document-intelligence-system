"""Pipeline orchestration for Hacker News and PDF uploads.

Design goal: keep this file readable in ~2 minutes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.utils import hash_text, new_run_id, timed, estimate_tokens, estimate_cost_usd
from app.models.document import Document
from app.processing.cleaning import clean_text
from app.processing.chunking import chunk_if_needed, map_reduce_summaries

from app.services.bigquery_service import BigQueryService
from app.services.docai_service import DocAIService
from app.services.dlp_service import DLPService
from app.services.gcs_service import GCSService
from app.services.gemini_service import GeminiService
from app.services.nl_service import NaturalLanguageService


# ----------------------------- public entrypoints -----------------------------


def run_hacker_news(model_tier: str) -> str:
    bq = BigQueryService()
    run_id = new_run_id()
    bq.create_run(run_id, source="hn", model_used=model_tier, docs_requested=settings.HN_DEFAULT_LIMIT)

    processed = 0
    try:
        with timed() as t:
            rows = bq.fetch_hn_documents(settings.HN_DEFAULT_LIMIT)
        log_stage(bq, run_id, None, "bq_fetch", t["ms"], status="ok", docs=len(rows))

        for r in rows:
            try:
                doc = Document(
                    doc_id=str(r["id"]),
                    source="hn",
                    title=r.get("title") or "",
                    text=clean_text(f"{r.get('title') or ''}. {r.get('text') or ''}".strip()),
                    metadata={"score": r.get("score"), "time": r.get("time")},
                )
                process_document(bq, run_id, doc, model_tier, pii=None)
                processed += 1
            except Exception as e:
                log_stage(bq, run_id, str(r.get("id")), "doc_failed", 0, status="error", error=str(e))

        bq.finalize_run(run_id, status="SUCCEEDED", docs_processed=processed)
    except Exception as e:
        bq.finalize_run(run_id, status="FAILED", docs_processed=processed, error_message=str(e))

    return run_id


def run_pdf_upload(model_tier: str, gcs_uri: str, filename: str) -> str:
    bq = BigQueryService()
    run_id = new_run_id()
    bq.create_run(run_id, source="pdf", model_used=model_tier, docs_requested=1)

    try:
        doc, pii = _pdf_to_document(bq, run_id, gcs_uri, filename)
        process_document(bq, run_id, doc, model_tier, pii=pii)
        bq.finalize_run(run_id, status="SUCCEEDED", docs_processed=1)
    except Exception as e:
        bq.finalize_run(run_id, status="FAILED", docs_processed=0, error_message=str(e))
        log_stage(bq, run_id, filename, "pdf_failed", 0, status="error", error=str(e))

    return run_id


# ------------------------------ core processing ------------------------------


def process_document(
    bq: BigQueryService,
    run_id: str,
    doc: Document,
    model_tier: str,
    pii: Optional[Dict[str, Any]],
    include_baselines: bool = False,
) -> None:
    doc_key = make_doc_key(doc.source, doc.doc_id, model_tier, doc.text)

    with timed() as t:
        cached = bq.lookup_cached_doc(doc_key)
    log_stage(bq, run_id, doc.doc_id, "cache_lookup", t["ms"], hit=bool(cached))

    if cached:
        cached = dict(cached)

        cached.update({
            "run_id": run_id,
            "doc_key": doc_key,
            "doc_id": doc.doc_id,
            "source": doc.source,
            "title": doc.title,
            "model_used": cached.get("model_used") or model_tier,
            "pipeline_version": cached.get("pipeline_version") or settings.PIPELINE_VERSION,
            "created_at": _now(),
        })

        return

    # NL API operates on a clipped input.
    nl_text = (doc.text or "")[: settings.MAX_CHARS_PER_DOC]
    nl = NaturalLanguageService()
    with timed() as t:
        nl_out = nl.analyze_entities_and_sentiment(nl_text)
    log_stage(bq, run_id, doc.doc_id, "nl_api", t["ms"], input_chars=len(nl_text))

    # Chunking for summarization.
    chunks = chunk_if_needed(doc.text or "", settings.MAX_CHARS_PER_DOC, settings.CHUNK_SIZE_CHARS, settings.CHUNK_OVERLAP_CHARS)

    gem = GeminiService(model_tier)

    with timed() as t:
        extraction, use_ex = gem.extract_structured(nl_text)
    log_llm_stage(bq, run_id, doc.doc_id, "gemini_extract", t["ms"], model_tier, nl_text, str(extraction), use_ex)

    with timed() as t:
        summary, use_sum = _summarize(gem, chunks)
    log_llm_stage(bq, run_id, doc.doc_id, "gemini_summary", t["ms"], model_tier, doc.text or "", summary, use_sum)

    bq.insert_processed_doc(
        {
            "run_id": run_id,
            "doc_key": doc_key,
            "doc_id": doc.doc_id,
            "source": doc.source,
            "title": doc.title,
            "summary": summary,
            "sentiment_score": nl_out["sentiment"]["score"],
            "sentiment_magnitude": nl_out["sentiment"]["magnitude"],
            "entities": nl_out["entities"],
            "extraction": extraction,
            "pii_findings": pii,
            "model_used": model_tier,
            "pipeline_version": settings.PIPELINE_VERSION,
            "created_at": _now(),
        }
    )


def _summarize(gem: GeminiService, chunks: List[str]) -> tuple[str, Dict[str, Any]]:
    if len(chunks) == 1:
        return gem.summarize(chunks[0])

    chunk_summaries: List[str] = []
    usage = {"prompt_tokens": None, "output_tokens": None}
    for c in chunks:
        s, u = gem.summarize(c)
        chunk_summaries.append(s)
        usage = merge_usage(usage, u)

    reducer_in = map_reduce_summaries(chunk_summaries, settings.MAX_CHARS_PER_DOC)
    final, u2 = gem.summarize(reducer_in)
    return final, merge_usage(usage, u2)


# ----------------------------- pdf ingest helpers ----------------------------


def _pdf_to_document(bq: BigQueryService, run_id: str, gcs_uri: str, filename: str) -> tuple[Document, Dict[str, Any]]:
    gcs = GCSService()
    with timed() as t:
        pdf_bytes = gcs.download_bytes(gcs_uri)
    log_stage(bq, run_id, filename, "gcs_download", t["ms"], bytes=len(pdf_bytes))

    docai = DocAIService()
    with timed() as t:
        extracted, pages = docai.extract_text_from_pdf_bytes(pdf_bytes)
    log_stage(bq, run_id, filename, "docai_ocr", t["ms"], pages=pages, chars=len(extracted))

    cleaned = clean_text(extracted)

    dlp = DLPService()
    with timed() as t:
        pii = dlp.inspect_text(cleaned[: settings.MAX_CHARS_PER_DOC])
    log_stage(bq, run_id, filename, "dlp_inspect", t["ms"], input_chars=min(len(cleaned), settings.MAX_CHARS_PER_DOC))

    doc = Document(doc_id=gcs_uri, source="pdf", title=filename, text=cleaned, metadata={"gcs_uri": gcs_uri, "pages": pages})
    return doc, pii


# --------------------------------- logging ----------------------------------


def make_doc_key(source: str, doc_id: str, model_tier: str, text: str) -> str:
    # Content-based key -> stable across runs/uploads
    content_hash = hash_text(clean_text(text))
    return f"{source}:{model_tier}:{content_hash}:{settings.PIPELINE_VERSION}"


def log_stage(bq: BigQueryService, run_id: str, doc_id: Optional[str], stage: str, latency_ms: int, **kv: Any) -> None:
    row = {
        "run_id": run_id,
        "doc_id": doc_id or "_run",
        "stage": stage,
        "latency_ms": latency_ms,
        "status": kv.pop("status", "ok"),
        "error_message": kv.pop("error", None),
        "created_at": _now(),
        **kv,
    }
    bq.insert_log(row)


def log_llm_stage(
    bq: BigQueryService,
    run_id: str,
    doc_id: str,
    stage: str,
    latency_ms: int,
    model_tier: str,
    prompt_text: str,
    output_text: str,
    usage: Dict[str, Any],
) -> None:
    p = usage.get("prompt_tokens")
    o = usage.get("output_tokens")
    p_est = estimate_tokens(len(prompt_text)) if p is None else None
    o_est = estimate_tokens(len(output_text)) if o is None else None
    cost = estimate_cost_usd(model_tier, p or p_est or 0, o or o_est or 0)
    log_stage(
        bq,
        run_id,
        doc_id,
        stage,
        latency_ms,
        model_used=model_tier,
        prompt_tokens=p,
        output_tokens=o,
        prompt_tokens_est=p_est,
        output_tokens_est=o_est,
        cost_est_usd=cost,
    )


def merge_usage(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(a)
    for k in ("prompt_tokens", "output_tokens"):
        av, bv = out.get(k), b.get(k)
        if isinstance(av, int) and isinstance(bv, int):
            out[k] = av + bv
        elif av is None and isinstance(bv, int):
            out[k] = bv
    return out


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()