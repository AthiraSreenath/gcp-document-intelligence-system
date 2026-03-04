"""BigQuery service).

Tables (all in settings.DATASET):
- runs: one row per run_id (updated via UPDATE)
- run_logs: stage-level logs (append-only)
- processed_docs: per-run outputs shown in UI (append-only)
- doc_cache: per-doc_key cache to avoid re-calling LLM (upsert)

Design: keep schema flat and store complex objects as JSON strings.
This avoids painful RECORD schemas and keeps code short.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import time

from google.cloud import bigquery
from google.api_core.exceptions import NotFound
from google.api_core.exceptions import BadRequest

from app.core.config import settings

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _j(v: Any) -> Optional[str]:
    """Serialize lists/dicts to JSON for storage."""
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def _unj(s: Any) -> Any:
    """Deserialize JSON strings back to objects (best-effort)."""
    if s is None or not isinstance(s, str):
        return s
    s = s.strip()
    if not s or (s[0] not in "[{"):
        return s
    try:
        return json.loads(s)
    except Exception:
        return s


class BigQueryService:
    def __init__(self):
        self.client = bigquery.Client(project=settings.PROJECT_ID)
        # Optional auto-create for easier reviewer experience.
        if str(getattr(settings, "BQ_AUTOCREATE", "0")) == "1":
            self.ensure_tables()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    def ensure_tables(self) -> None:
        """Create dataset/tables if missing. Optional."""
        dataset_id = f"{settings.PROJECT_ID}.{settings.DATASET}"

        try:
            self.client.get_dataset(dataset_id)
        except NotFound:
            self.client.create_dataset(bigquery.Dataset(dataset_id))

        self._ensure_table("runs", [
            bigquery.SchemaField("run_id", "STRING"),
            bigquery.SchemaField("source", "STRING"),
            bigquery.SchemaField("model_used", "STRING"),
            bigquery.SchemaField("docs_requested", "INTEGER"),
            bigquery.SchemaField("docs_processed", "INTEGER"),
            bigquery.SchemaField("status", "STRING"),
            bigquery.SchemaField("error_message", "STRING"),
            bigquery.SchemaField("created_at", "TIMESTAMP"),
            bigquery.SchemaField("updated_at", "TIMESTAMP"),
        ])

        self._ensure_table("run_logs", [
            bigquery.SchemaField("run_id", "STRING"),
            bigquery.SchemaField("doc_id", "STRING"),
            bigquery.SchemaField("stage", "STRING"),
            bigquery.SchemaField("latency_ms", "INTEGER"),
            bigquery.SchemaField("status", "STRING"),
            bigquery.SchemaField("error_message", "STRING"),
            bigquery.SchemaField("model_used", "STRING"),
            bigquery.SchemaField("prompt_tokens", "INTEGER"),
            bigquery.SchemaField("output_tokens", "INTEGER"),
            bigquery.SchemaField("prompt_tokens_est", "INTEGER"),
            bigquery.SchemaField("output_tokens_est", "INTEGER"),
            bigquery.SchemaField("cost_est_usd", "FLOAT"),
            bigquery.SchemaField("meta_json", "STRING"),
            bigquery.SchemaField("created_at", "TIMESTAMP"),
        ])

        self._ensure_table("processed_docs", [
            bigquery.SchemaField("run_id", "STRING"),
            bigquery.SchemaField("doc_key", "STRING"),
            bigquery.SchemaField("doc_id", "STRING"),
            bigquery.SchemaField("source", "STRING"),
            bigquery.SchemaField("title", "STRING"),
            bigquery.SchemaField("summary", "STRING"),
            bigquery.SchemaField("sentiment_score", "FLOAT"),
            bigquery.SchemaField("sentiment_magnitude", "FLOAT"),
            bigquery.SchemaField("entities_json", "STRING"),
            bigquery.SchemaField("extraction_json", "STRING"),
            bigquery.SchemaField("pii_json", "STRING"),
            bigquery.SchemaField("baselines_json", "STRING"),
            bigquery.SchemaField("model_used", "STRING"),
            bigquery.SchemaField("pipeline_version", "STRING"),
            bigquery.SchemaField("created_at", "TIMESTAMP"),
        ])

        self._ensure_table("doc_cache", [
            bigquery.SchemaField("doc_key", "STRING"),
            bigquery.SchemaField("summary", "STRING"),
            bigquery.SchemaField("sentiment_score", "FLOAT"),
            bigquery.SchemaField("sentiment_magnitude", "FLOAT"),
            bigquery.SchemaField("entities_json", "STRING"),
            bigquery.SchemaField("extraction_json", "STRING"),
            bigquery.SchemaField("pii_json", "STRING"),
            bigquery.SchemaField("baselines_json", "STRING"),
            bigquery.SchemaField("model_used", "STRING"),
            bigquery.SchemaField("pipeline_version", "STRING"),
            bigquery.SchemaField("updated_at", "TIMESTAMP"),
        ])

    def _ensure_table(self, name: str, schema: List[bigquery.SchemaField]) -> None:
        table_id = f"{settings.PROJECT_ID}.{settings.DATASET}.{name}"
        try:
            self.client.get_table(table_id)
        except NotFound:
            t = bigquery.Table(table_id, schema=schema)
            self.client.create_table(t)

    # ------------------------------------------------------------------
    # Hacker News fetch
    # ------------------------------------------------------------------
    def fetch_hn_documents(self, limit: int = 50) -> List[Dict[str, Any]]:
        q = f"""
        SELECT id, title, text, time, score
        FROM `{settings.PROJECT_ID}.{settings.DATASET}.{settings.HN_CORPUS_TABLE}`
        WHERE text IS NOT NULL
        LIMIT {int(limit)}
        """
        return [dict(r) for r in self.client.query(q).result()]

    # ------------------------------------------------------------------
    # Run lifecycle
    # ------------------------------------------------------------------
    def create_run(self, run_id: str, source: str, model_used: str, docs_requested: int) -> None:
        q = f"""
        INSERT INTO `{settings.PROJECT_ID}.{settings.DATASET}.runs`
        (run_id, source, model_used, docs_requested, docs_processed, status, error_message, created_at, updated_at)
        VALUES (@run_id, @source, @model_used, @docs_requested, @docs_processed, @status, @error_message, @created_at, @updated_at)
        """
        params = [
            bigquery.ScalarQueryParameter("run_id", "STRING", run_id),
            bigquery.ScalarQueryParameter("source", "STRING", source),
            bigquery.ScalarQueryParameter("model_used", "STRING", model_used),
            bigquery.ScalarQueryParameter("docs_requested", "INT64", int(docs_requested)),
            bigquery.ScalarQueryParameter("docs_processed", "INT64", 0),
            bigquery.ScalarQueryParameter("status", "STRING", "RUNNING"),
            bigquery.ScalarQueryParameter("error_message", "STRING", None),
            bigquery.ScalarQueryParameter("created_at", "TIMESTAMP", _now()),
            bigquery.ScalarQueryParameter("updated_at", "TIMESTAMP", _now()),
        ]
        self.client.query(q, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()

    def finalize_run(self, run_id: str, status: str, docs_processed: int, error_message: str | None = None) -> None:
        q = f"""
        UPDATE `{settings.PROJECT_ID}.{settings.DATASET}.runs`
        SET status=@status,
            docs_processed=@docs_processed,
            error_message=@error_message,
            updated_at=@updated_at
        WHERE run_id=@run_id
        """
        params = [
            bigquery.ScalarQueryParameter("status", "STRING", status),
            bigquery.ScalarQueryParameter("docs_processed", "INT64", int(docs_processed)),
            bigquery.ScalarQueryParameter("error_message", "STRING", error_message),
            bigquery.ScalarQueryParameter("updated_at", "TIMESTAMP", _now()),
            bigquery.ScalarQueryParameter("run_id", "STRING", run_id),
        ]
        cfg = bigquery.QueryJobConfig(query_parameters=params)

        for i in range(5):
            try:
                self.client.query(q, job_config=cfg).result()
                return
            except BadRequest as e:
                # If someone used streaming insert again, this avoids a hard fail.
                if "streaming buffer" in str(e).lower():
                    time.sleep(2 ** i)
                    continue
                raise

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        q = f"""
        SELECT * FROM `{settings.PROJECT_ID}.{settings.DATASET}.runs`
        WHERE run_id = @run_id
        LIMIT 1
        """
        job_config = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("run_id", "STRING", run_id)
        ])
        rows = list(self.client.query(q, job_config=job_config).result())
        return dict(rows[0]) if rows else None

    # ------------------------------------------------------------------
    # Cache (doc_key-based)
    # ------------------------------------------------------------------
    def lookup_cached_doc(self, doc_key: str) -> Optional[Dict[str, Any]]:
        """Cache lookup used by pipeline."""
        q = f"""
        SELECT * FROM `{settings.PROJECT_ID}.{settings.DATASET}.doc_cache`
        WHERE doc_key = @doc_key
        LIMIT 1
        """
        job_config = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("doc_key", "STRING", doc_key)
        ])
        rows = list(self.client.query(q, job_config=job_config).result())
        if not rows:
            return None
        r = dict(rows[0])
        return {
            "doc_key": r["doc_key"],
            "summary": r.get("summary"),
            "sentiment_score": r.get("sentiment_score"),
            "sentiment_magnitude": r.get("sentiment_magnitude"),
            "entities": _unj(r.get("entities_json")) or [],
            "extraction": _unj(r.get("extraction_json")) or {},
            "pii_findings": _unj(r.get("pii_json")) or {},
            "baselines": _unj(r.get("baselines_json")) or {},
            "model_used": r.get("model_used"),
            "pipeline_version": r.get("pipeline_version"),
        }

    def upsert_cache(self, doc_key: str, row: Dict[str, Any]) -> None:
        """Upsert doc_cache via MERGE (short + clear)."""
        q = f"""
        MERGE `{settings.PROJECT_ID}.{settings.DATASET}.doc_cache` T
        USING (SELECT @doc_key AS doc_key) S
        ON T.doc_key = S.doc_key
        WHEN MATCHED THEN UPDATE SET
          summary=@summary,
          sentiment_score=@sentiment_score,
          sentiment_magnitude=@sentiment_magnitude,
          entities_json=@entities_json,
          extraction_json=@extraction_json,
          pii_json=@pii_json,
          baselines_json=@baselines_json,
          model_used=@model_used,
          pipeline_version=@pipeline_version,
          updated_at=@updated_at
        WHEN NOT MATCHED THEN INSERT (
          doc_key, summary, sentiment_score, sentiment_magnitude,
          entities_json, extraction_json, pii_json, baselines_json,
          model_used, pipeline_version, updated_at
        ) VALUES (
          @doc_key, @summary, @sentiment_score, @sentiment_magnitude,
          @entities_json, @extraction_json, @pii_json, @baselines_json,
          @model_used, @pipeline_version, @updated_at
        )
        """
        params = [
            bigquery.ScalarQueryParameter("doc_key", "STRING", doc_key),
            bigquery.ScalarQueryParameter("summary", "STRING", row.get("summary")),
            bigquery.ScalarQueryParameter("sentiment_score", "FLOAT64", row.get("sentiment_score")),
            bigquery.ScalarQueryParameter("sentiment_magnitude", "FLOAT64", row.get("sentiment_magnitude")),
            bigquery.ScalarQueryParameter("entities_json", "STRING", _j(row.get("entities"))),
            bigquery.ScalarQueryParameter("extraction_json", "STRING", _j(row.get("extraction"))),
            bigquery.ScalarQueryParameter("pii_json", "STRING", _j(row.get("pii_findings"))),
            bigquery.ScalarQueryParameter("baselines_json", "STRING", _j(row.get("baselines"))),
            bigquery.ScalarQueryParameter("model_used", "STRING", row.get("model_used")),
            bigquery.ScalarQueryParameter("pipeline_version", "STRING", row.get("pipeline_version")),
            bigquery.ScalarQueryParameter("updated_at", "TIMESTAMP", _now()),
        ]
        self.client.query(q, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()

    # ------------------------------------------------------------------
    # Processed docs (per run)
    # ------------------------------------------------------------------
    def insert_processed_doc(self, row: Dict[str, Any]) -> None:
        """Insert processed doc via query (avoids streaming visibility issues)."""
        q = f"""
        INSERT INTO `{settings.PROJECT_ID}.{settings.DATASET}.processed_docs`
        (run_id, doc_key, doc_id, source, title, summary,
        sentiment_score, sentiment_magnitude,
        entities_json, extraction_json, pii_json, baselines_json,
        model_used, pipeline_version, created_at)
        VALUES
        (@run_id, @doc_key, @doc_id, @source, @title, @summary,
        @sentiment_score, @sentiment_magnitude,
        @entities_json, @extraction_json, @pii_json, @baselines_json,
        @model_used, @pipeline_version, @created_at)
        """

        out = {
            "run_id": row.get("run_id"),
            "doc_key": row.get("doc_key"),
            "doc_id": row.get("doc_id"),
            "source": row.get("source"),
            "title": row.get("title"),
            "summary": row.get("summary"),
            "sentiment_score": row.get("sentiment_score"),
            "sentiment_magnitude": row.get("sentiment_magnitude"),
            "entities_json": _j(row.get("entities")),
            "extraction_json": _j(row.get("extraction")),
            "pii_json": _j(row.get("pii_findings")),
            "baselines_json": _j(row.get("baselines")),
            "model_used": row.get("model_used"),
            "pipeline_version": row.get("pipeline_version"),
            "created_at": row.get("created_at") or _now(),
        }

        params = [
            bigquery.ScalarQueryParameter("run_id", "STRING", out["run_id"]),
            bigquery.ScalarQueryParameter("doc_key", "STRING", out["doc_key"]),
            bigquery.ScalarQueryParameter("doc_id", "STRING", out["doc_id"]),
            bigquery.ScalarQueryParameter("source", "STRING", out["source"]),
            bigquery.ScalarQueryParameter("title", "STRING", out["title"]),
            bigquery.ScalarQueryParameter("summary", "STRING", out["summary"]),
            bigquery.ScalarQueryParameter("sentiment_score", "FLOAT64", out["sentiment_score"]),
            bigquery.ScalarQueryParameter("sentiment_magnitude", "FLOAT64", out["sentiment_magnitude"]),
            bigquery.ScalarQueryParameter("entities_json", "STRING", out["entities_json"]),
            bigquery.ScalarQueryParameter("extraction_json", "STRING", out["extraction_json"]),
            bigquery.ScalarQueryParameter("pii_json", "STRING", out["pii_json"]),
            bigquery.ScalarQueryParameter("baselines_json", "STRING", out["baselines_json"]),
            bigquery.ScalarQueryParameter("model_used", "STRING", out["model_used"]),
            bigquery.ScalarQueryParameter("pipeline_version", "STRING", out["pipeline_version"]),
            bigquery.ScalarQueryParameter("created_at", "TIMESTAMP", out["created_at"]),
        ]

        self.client.query(q, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()

        # Update cache (best-effort)
        try:
            if row.get("doc_key"):
                self.upsert_cache(row["doc_key"], row)
        except Exception as e:
            logger.warning("Cache upsert failed: %s", e)

    # Backwards compatibility
    def write_processed_document(self, row: Dict[str, Any]) -> None:
        self.insert_processed_doc(row)

    # ------------------------------------------------------------------
    # Logs
    # ------------------------------------------------------------------
    def insert_log(self, row: Dict[str, Any]) -> None:
        table_id = f"{settings.PROJECT_ID}.{settings.DATASET}.run_logs"
        out = {
            "run_id": row.get("run_id"),
            "doc_id": row.get("doc_id"),
            "stage": row.get("stage"),
            "latency_ms": row.get("latency_ms"),
            "status": row.get("status"),
            "error_message": row.get("error_message"),
            "model_used": row.get("model_used"),
            "prompt_tokens": row.get("prompt_tokens"),
            "output_tokens": row.get("output_tokens"),
            "prompt_tokens_est": row.get("prompt_tokens_est"),
            "output_tokens_est": row.get("output_tokens_est"),
            "cost_est_usd": row.get("cost_est_usd"),
            "meta_json": _j({k: v for k, v in row.items() if k not in {
                "run_id","doc_id","stage","latency_ms","status","error_message",
                "model_used","prompt_tokens","output_tokens","prompt_tokens_est","output_tokens_est","cost_est_usd","created_at"
            }}),
            "created_at": row.get("created_at") or _now(),
        }
        self.client.insert_rows_json(table_id, [out])

    def write_run_log(self, row: Dict[str, Any]) -> None:
        self.insert_log(row)

    # ------------------------------------------------------------------
    # Fetch results + attach timing
    # ------------------------------------------------------------------
    def fetch_run_results(self, run_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        q = f"""
        SELECT * FROM `{settings.PROJECT_ID}.{settings.DATASET}.processed_docs`
        WHERE run_id = @run_id
        ORDER BY created_at DESC
        LIMIT {int(limit)}
        """
        rows = list(self.client.query(
            q,
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("run_id", "STRING", run_id)
            ]),
        ).result())

        logs = self.fetch_run_logs(run_id)
        timing_by_doc: Dict[str, Dict[str, Any]] = {}
        for l in logs:
            did = l.get("doc_id") or "_run"
            t = timing_by_doc.setdefault(did, {"stages": {}, "total_ms": 0, "cost_est_usd": 0.0})
            stage = l.get("stage") or "unknown"
            ms = int(l.get("latency_ms") or 0)
            t["stages"][stage] = ms
            t["total_ms"] += ms
            t["cost_est_usd"] += float(l.get("cost_est_usd") or 0.0)

        out: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            out.append({
                "run_id": d.get("run_id"),
                "doc_key": d.get("doc_key"),
                "doc_id": d.get("doc_id"),
                "source": d.get("source"),
                "title": d.get("title"),
                "summary": d.get("summary"),
                "sentiment_score": d.get("sentiment_score"),
                "sentiment_magnitude": d.get("sentiment_magnitude"),
                "entities": _unj(d.get("entities_json")) or [],
                "extraction": _unj(d.get("extraction_json")) or {},
                "pii_findings": _unj(d.get("pii_json")) or {},
                "baselines": _unj(d.get("baselines_json")) or {},
                "model_used": d.get("model_used"),
                "pipeline_version": d.get("pipeline_version"),
                "created_at": d.get("created_at"),
                "timing": timing_by_doc.get(d.get("doc_id") or "", {}),
            })
        return out

    def fetch_run_logs(self, run_id: str, limit: int = 2000) -> List[Dict[str, Any]]:
        q = f"""
        SELECT * FROM `{settings.PROJECT_ID}.{settings.DATASET}.run_logs`
        WHERE run_id = @run_id
        ORDER BY created_at ASC
        LIMIT {int(limit)}
        """
        rows = self.client.query(
            q,
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("run_id", "STRING", run_id)
            ]),
        ).result()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Aggregate for UI
    # ------------------------------------------------------------------
    def aggregate_for_run(self, run_id: str) -> Dict[str, Any]:
        run = self.get_run(run_id) or {"status": "UNKNOWN"}
        items = self.fetch_run_results(run_id, limit=500)

        # Simple aggregates in Python (small + robust).
        docs = len(items)
        scores = [it["sentiment_score"] for it in items if isinstance(it.get("sentiment_score"), (int, float))]
        avg_sent = round(sum(scores) / len(scores), 4) if scores else None

        # Top entities by count (name)
        counts: Dict[str, int] = {}
        for it in items:
            for e in (it.get("entities") or []):
                name = (e.get("name") or "").strip()
                if name:
                    counts[name] = counts.get(name, 0) + 1
        top_entities = [{"name": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:10]]

        # Cost estimate from timing rollups if present
        costs = []
        for it in items:
            c = (it.get("timing") or {}).get("cost_est_usd")
            if isinstance(c, (int, float)):
                costs.append(float(c))
        total_cost = round(sum(costs), 4) if costs else 0.0

        return {
            "run_id": run_id,
            "status": run.get("status"),
            "docs_processed": run.get("docs_processed", docs),
            "docs": docs,
            "avg_sentiment": avg_sent,
            "top_entities": top_entities,
            "cost_est_usd": total_cost,
            "model_used": run.get("model_used"),
            "source": run.get("source"),
        }