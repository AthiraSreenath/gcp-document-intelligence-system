"""API request/response models (minimal)."""

from typing import Literal, Optional
from pydantic import BaseModel


class RunHNRequest(BaseModel):
    model: Literal["flash", "pro"] = "flash"


class RunResponse(BaseModel):
    run_id: str
    status: str = "RUNNING"
    message: Optional[str] = None