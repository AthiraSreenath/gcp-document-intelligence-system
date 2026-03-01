"""Application configuration (env-driven)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- GCP ---
    PROJECT_ID: str
    REGION: str = "us-west1"

    # --- Storage ---
    DATASET: str = "nlp_intelligence"
    HN_CORPUS_TABLE: str = "hn_corpus"
    GCS_BUCKET: str | None = None
    DOC_AI_PROCESSOR_NAME: str | None = None  # full resource name (optional)

    # --- Models ---
    GEMINI_MODEL_FLASH: str = "gemini-2.5-flash"
    GEMINI_MODEL_PRO: str = "gemini-2.5-pro"
    PIPELINE_VERSION: str = "v1"

    # --- Defaults / Limits ---
    HN_DEFAULT_LIMIT: int = 25
    MAX_CHARS_PER_DOC: int = 12000
    CHUNK_SIZE_CHARS: int = 5000
    CHUNK_OVERLAP_CHARS: int = 300
    MAX_PDF_SIZE_MB: int = 20
    SUMMARY_SENTENCES: int = 5

    # --- Telemetry only (set to real numbers if you want) ---
    COST_FLASH_PER_1K: float = 0.0
    COST_PRO_PER_1K: float = 0.0


settings = Settings()