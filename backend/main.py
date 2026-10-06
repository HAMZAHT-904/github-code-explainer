"""FastAPI backend: clone a public GitHub repo, read source as text, explain with Ollama."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.github_processor import (
    ProcessingError,
    build_repo_context,
    cleanup_clone,
    clone_repository,
    validate_github_url,
)
from backend.llm_service import LLMError, generate_explanation
from backend.models import ExplainRequest, ExplainResponse

app = FastAPI(
    title="GitHub Repository Code Explainer",
    description="Clone a public GitHub repo locally and explain it with a local Ollama LLM.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/explain", response_model=ExplainResponse)
def explain_repository(payload: ExplainRequest) -> ExplainResponse:
    repo_path = None
    try:
        validate_github_url(payload.repo_url)
        repo_path = clone_repository(payload.repo_url)
        context = build_repo_context(repo_path, payload.repo_url)
        explanation = generate_explanation(context)
        return ExplainResponse(explanation=explanation)
    except ProcessingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except LLMError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Something went wrong while explaining the repository.",
        ) from exc
    finally:
        cleanup_clone(repo_path)
