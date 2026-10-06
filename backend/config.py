"""Simple environment-based configuration. No secrets are required."""

import os
from pathlib import Path

# Project root: github-code-explainer/
PROJECT_ROOT = Path(__file__).resolve().parent.parent

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
# Lightweight Qwen model suitable for a student laptop. Change with OLLAMA_MODEL.
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_TIMEOUT_SECONDS = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "180"))

BACKEND_HOST = os.getenv("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))

# Temporary clone location (cleaned up after each request)
TEMP_REPOS_DIR = PROJECT_ROOT / "temp_repos"

# Context limits so large repos do not overwhelm the local LLM
MAX_FILES = int(os.getenv("MAX_FILES", "25"))
MAX_CHARS_PER_FILE = int(os.getenv("MAX_CHARS_PER_FILE", "4000"))
MAX_TOTAL_CHARS = int(os.getenv("MAX_TOTAL_CHARS", "40000"))
MAX_CLONE_BYTES = int(os.getenv("MAX_CLONE_BYTES", str(80 * 1024 * 1024)))  # 80 MB working tree
