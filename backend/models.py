"""
Pydantic request / response models for the API.
"""

from pydantic import BaseModel


class AskRequest(BaseModel):
    question: str
    session_id: str | None = None
    provider: str = "anthropic"
    api_key: str = ""
    model: str = "claude-sonnet-4-6"


class AskResponse(BaseModel):
    text: str
    image: str | None = None
    session_id: str


class ModelsRequest(BaseModel):
    provider: str = "anthropic"
    api_key: str = ""
