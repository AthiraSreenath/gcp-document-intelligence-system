"""FastAPI app entrypoint"""

from fastapi import FastAPI

from app.api.routes import router
from app.core.logging_config import setup_logging


def create_app() -> FastAPI:
    setup_logging()

    app = FastAPI(title="NLP Cloud Intelligence API")
    app.include_router(router)

    return app

app = create_app()