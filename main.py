"""FastAPI app entrypoint (kept intentionally small)."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.logging_config import setup_logging


def create_app() -> FastAPI:
    setup_logging()

    app = FastAPI(title="NLP Cloud Intelligence API")

    # Helpful for local dev (Streamlit -> FastAPI). Safe default: allow all.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    return app


app = create_app()