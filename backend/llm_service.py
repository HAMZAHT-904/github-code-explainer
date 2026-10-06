"""Talk to a local Ollama instance. No cloud LLM APIs are used."""

from __future__ import annotations

import requests

from backend.config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT_SECONDS

SYSTEM_PROMPT = """You are a software codebase analyst. Analyze the provided repository information and explain it in simple language for a college student.

The generated response MUST use these markdown headings:

## Project Overview
Explain what the repository does.

## Main Technologies
Identify programming languages, frameworks, libraries, databases, and tools.

## Main Features
List the important features.

## How It Works
Explain the application flow in simple language.

## Important Files
Identify important files and explain their purpose.

## Architecture
Explain the main components and how they communicate.

Rules:
- Be easy to understand.
- Do not invent functionality that cannot be reasonably inferred from the provided repository information.
- If something is unclear from the files, say so briefly instead of guessing.
"""


class LLMError(Exception):
    """Local LLM / Ollama failure with a user-friendly message."""

    def __init__(self, message: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _model_is_installed(installed_names: list[str], wanted: str) -> bool:
    """True if Ollama already has the configured model (exact or tagged variant)."""
    for name in installed_names:
        if name == wanted or name.startswith(wanted):
            return True
    return False


def check_ollama_ready() -> None:
    """Fail fast with a clear message if Ollama or the model is missing."""
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
    except requests.ConnectionError as exc:
        raise LLMError(
            "Ollama is not running. Start it with: ollama serve",
            status_code=503,
        ) from exc
    except requests.Timeout as exc:
        raise LLMError("Ollama timed out while checking available models.", status_code=504) from exc

    if response.status_code != 200:
        raise LLMError("Ollama is running but did not respond correctly. Try restarting Ollama.")

    data = response.json()
    models = data.get("models") or []
    names = [(item.get("name") or item.get("model") or "") for item in models]
    names = [n for n in names if n]

    if _model_is_installed(names, OLLAMA_MODEL):
        return

    installed = ", ".join(names) if names else "(none)"
    raise LLMError(
        f"Ollama model '{OLLAMA_MODEL}' is not installed. Run: ollama pull {OLLAMA_MODEL}. Installed: {installed}",
        status_code=503,
    )


def generate_explanation(repo_context: str) -> str:
    """Send the repository snapshot to the local LLM and return its explanation."""
    check_ollama_ready()

    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Analyze this GitHub repository snapshot (source files were read as text only):\n\n"
                    + repo_context
                ),
            },
        ],
    }

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
    except requests.ConnectionError as exc:
        raise LLMError("Ollama is not running. Start it with: ollama serve") from exc
    except requests.Timeout as exc:
        raise LLMError(
            "The local model took too long to respond. Try a smaller repository or a smaller model.",
            status_code=504,
        ) from exc

    if response.status_code == 404:
        raise LLMError(
            f"Ollama model '{OLLAMA_MODEL}' is not installed. Run: ollama pull {OLLAMA_MODEL}"
        )
    if response.status_code != 200:
        raise LLMError("The local LLM failed to generate an explanation. Check Ollama logs.")

    try:
        body = response.json()
        explanation = (body.get("message") or {}).get("content") or ""
    except ValueError as exc:
        raise LLMError("The local LLM returned an invalid response.") from exc

    explanation = explanation.strip()
    if not explanation:
        raise LLMError("The local LLM returned an empty explanation.")
    return explanation
