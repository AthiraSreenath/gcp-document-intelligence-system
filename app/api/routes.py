"""FastAPI routes for the NLP Cloud Intelligence API (small + UI-aligned)."""

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from app.core.config import settings
from app.models.api import RunHNRequest, RunResponse
from app.processing.pipeline import run_hacker_news, run_pdf_upload
from app.services.bigquery_service import BigQueryService
from app.services.gcs_service import GCSService

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/run/hn", response_model=RunResponse)
def run_hn(req: RunHNRequest) -> RunResponse:
    model = (req.model or "flash").lower().strip()
    if model not in ("flash", "pro"):
        raise HTTPException(status_code=400, detail={"message": "model must be 'flash' or 'pro'"})
    run_id = run_hacker_news(model_tier=model)
    return RunResponse(run_id=run_id, status="RUNNING")


@router.post("/upload/pdf", response_model=RunResponse)
async def upload_pdf(
    model: str = Query("flash"),
    file: UploadFile = File(...),
) -> RunResponse:
    model = (model or "flash").lower().strip()
    if model not in ("flash", "pro"):
        raise HTTPException(status_code=400, detail={"message": "model must be 'flash' or 'pro'"})

    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=415, detail={"message": "Only PDF uploads are supported."})

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.MAX_PDF_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail={"message": f"PDF too large ({size_mb:.1f}MB). Limit is {settings.MAX_PDF_SIZE_MB}MB."},
        )

    if not settings.GCS_BUCKET:
        raise HTTPException(status_code=500, detail={"message": "GCS_BUCKET is not configured."})

    gcs_uri = GCSService().upload_bytes(
        content,
        object_name=f"uploads/{file.filename}",
        content_type="application/pdf",
    )
    run_id = run_pdf_upload(model_tier=model, gcs_uri=gcs_uri, filename=file.filename)
    return RunResponse(run_id=run_id, status="RUNNING")


@router.get("/run/{run_id}/status")
def run_status(run_id: str) -> dict:
    row = BigQueryService().get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail={"message": "run_id not found"})
    return {
        "run_id": run_id,
        "status": row.get("status"),
        "error_message": row.get("error_message"),
        "docs_processed": row.get("docs_processed"),
    }


@router.get("/run/{run_id}/results")
def run_results(run_id: str, limit: int = 50) -> dict:
    # BigQueryService.fetch_run_results already returns JSON-ready objects
    items = BigQueryService().fetch_run_results(run_id, limit=limit)
    return {"run_id": run_id, "items": items}


@router.get("/run/{run_id}/aggregate")
def run_aggregate(run_id: str) -> dict:
    return BigQueryService().aggregate_for_run(run_id)