from typing import Optional

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    error: str
    error_code: str
    details: Optional[dict] = None
