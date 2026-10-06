"""Pydantic request and response models for the FastAPI API."""

from pydantic import BaseModel, Field


class ExplainRequest(BaseModel):
    """Incoming JSON body for POST /explain."""

    repo_url: str = Field(..., min_length=1, description="Public GitHub repository URL")


class ExplainResponse(BaseModel):
    """Successful explanation returned to the Streamlit frontend."""

    explanation: str
