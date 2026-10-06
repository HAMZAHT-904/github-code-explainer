"""Clone a public GitHub repository and extract a bounded text snapshot.

Security: repository files are treated as untrusted text. Nothing is executed,
imported, compiled, or run through a shell.
"""

from __future__ import annotations

import os
import re
import shutil
import uuid
from pathlib import Path

from backend.config import (
    MAX_CHARS_PER_FILE,
    MAX_CLONE_BYTES,
    MAX_FILES,
    MAX_TOTAL_CHARS,
    TEMP_REPOS_DIR,
)

GITHUB_URL_PATTERN = re.compile(
    r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)

SOURCE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".java",
    ".cpp",
    ".c",
    ".h",
    ".cs",
    ".go",
    ".rs",
    ".php",
    ".rb",
    ".html",
    ".css",
    ".sql",
}

# Project metadata files that help the LLM understand purpose and stack
PRIORITY_FILENAMES = {
    "readme.md",
    "package.json",
    "requirements.txt",
    "pom.xml",
    "build.gradle",
    "cargo.toml",
    "go.mod",
    "pyproject.toml",
}

SKIP_DIR_NAMES = {
    ".git",
    "node_modules",
    "__pycache__",
    "venv",
    ".venv",
    "env",
    "dist",
    "build",
    "target",
    ".idea",
    ".vscode",
    "images",
    "videos",
    "audio",
    ".next",
    "coverage",
}

MAIN_FILE_HINTS = {
    "main.py",
    "app.py",
    "index.js",
    "index.ts",
    "index.jsx",
    "index.tsx",
    "server.py",
    "manage.py",
    "main.go",
    "main.rs",
    "program.cs",
    "app.java",
}


class ProcessingError(Exception):
    """User-facing processing failure with a simple message."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def validate_github_url(repo_url: str) -> tuple[str, str]:
    """Return (owner, repo_name) or raise ProcessingError."""
    url = (repo_url or "").strip()
    if not url:
        raise ProcessingError("Please enter a GitHub repository URL.")

    match = GITHUB_URL_PATTERN.match(url)
    if not match:
        raise ProcessingError(
            "Invalid GitHub URL. Use a public URL like https://github.com/username/repository"
        )

    owner, name = match.group(1), match.group(2)
    if name.lower() in {".", ".."}:
        raise ProcessingError("Invalid repository URL.")
    return owner, name


def _https_clone_url(owner: str, name: str) -> str:
    return f"https://github.com/{owner}/{name}.git"


def _dir_size_bytes(path: Path) -> int:
    total = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIR_NAMES]
        for filename in files:
            try:
                total += (Path(root) / filename).stat().st_size
            except OSError:
                continue
    return total


def clone_repository(repo_url: str) -> Path:
    """Clone into a unique folder under temp_repos/. Never runs repo contents."""
    try:
        from git import GitCommandError, Repo
    except Exception as exc:
        raise ProcessingError(
            "Git is not working on this machine. Install Git (and Xcode Command Line Tools on macOS), then retry.",
            status_code=500,
        ) from exc

    owner, name = validate_github_url(repo_url)
    TEMP_REPOS_DIR.mkdir(parents=True, exist_ok=True)
    dest = TEMP_REPOS_DIR / f"{owner}_{name}_{uuid.uuid4().hex[:8]}"
    clone_url = _https_clone_url(owner, name)

    try:
        # depth=1 keeps clones small; we only need current source text
        Repo.clone_from(clone_url, dest, depth=1, multi_options=["--single-branch"])
    except GitCommandError as exc:
        stderr = (exc.stderr or str(exc)).lower()
        shutil.rmtree(dest, ignore_errors=True)
        if "not found" in stderr or "repository not found" in stderr:
            raise ProcessingError(
                "Repository not found. Check the URL, or the repo may be private.",
                status_code=404,
            ) from exc
        if "authentication" in stderr or "could not read from remote" in stderr:
            raise ProcessingError(
                "Could not clone the repository. It may be private or require login.",
                status_code=403,
            ) from exc
        raise ProcessingError(
            "Git clone failed. Check your internet connection and that the repository exists.",
            status_code=400,
        ) from exc
    except Exception as exc:  # GitPython / network surprises
        shutil.rmtree(dest, ignore_errors=True)
        raise ProcessingError(
            "Git clone failed. Check your internet connection and that Git is installed.",
            status_code=500,
        ) from exc

    if not any(dest.iterdir()):
        raise ProcessingError("The repository appears to be empty.")

    size = _dir_size_bytes(dest)
    if size > MAX_CLONE_BYTES:
        raise ProcessingError(
            "This repository is too large to process on this machine. Try a smaller public repo.",
            status_code=413,
        )
    return dest


def cleanup_clone(path: Path | None) -> None:
    if path is None:
        return
    shutil.rmtree(path, ignore_errors=True)


def _is_probably_binary(path: Path) -> bool:
    """Skip binaries and non-text files. Read-only check; never execute."""
    try:
        with path.open("rb") as handle:
            chunk = handle.read(2048)
        if b"\x00" in chunk:
            return True
    except OSError:
        return True
    return False


def _priority_score(rel_path: Path) -> int:
    """
    Lower score = higher priority for the LLM context window.

    Order:
    1. README.md
    2. package.json / requirements.txt / pom.xml / similar manifests
    3. Main application entry files
    4. Files under src/
    5. Other source files
    """
    name = rel_path.name.lower()
    parts = {p.lower() for p in rel_path.parts}

    if name == "readme.md":
        return 0
    if name in {"package.json", "requirements.txt", "pom.xml"}:
        return 1
    if name in PRIORITY_FILENAMES:
        return 2
    if name in MAIN_FILE_HINTS:
        return 3
    if "src" in parts:
        return 4
    if "app" in parts or "lib" in parts:
        return 5
    if rel_path.suffix.lower() in SOURCE_EXTENSIONS:
        return 6
    return 7


def collect_relevant_files(repo_root: Path) -> list[Path]:
    """Walk the clone and keep only readable source / project files."""
    candidates: list[Path] = []

    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIR_NAMES and not d.startswith(".")]
        for filename in files:
            path = Path(root) / filename
            rel = path.relative_to(repo_root)
            suffix = path.suffix.lower()
            lower_name = filename.lower()

            if lower_name in PRIORITY_FILENAMES or suffix in SOURCE_EXTENSIONS:
                if _is_probably_binary(path):
                    continue
                try:
                    if path.stat().st_size > 500_000:
                        continue  # skip huge generated / minified files
                except OSError:
                    continue
                candidates.append(rel)

    candidates.sort(key=_priority_score)
    return [repo_root / rel for rel in candidates]


def read_file_as_text(path: Path) -> str:
    """Read file as UTF-8 text only. Never execute."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ProcessingError(f"Could not read file {path.name}.") from exc
    if MAX_CHARS_PER_FILE and len(text) > MAX_CHARS_PER_FILE:
        text = text[:MAX_CHARS_PER_FILE] + "\n... [truncated for context limit]"
    return text


def build_repo_context(repo_root: Path, repo_url: str) -> str:
    """
    Build a structured snapshot for the LLM.

    Limits:
    - MAX_FILES: how many files are included
    - MAX_CHARS_PER_FILE: truncation per file
    - MAX_TOTAL_CHARS: overall prompt budget for file contents
    """
    files = collect_relevant_files(repo_root)
    if not files:
        raise ProcessingError(
            "No supported source files were found in this repository.",
            status_code=422,
        )

    selected: list[tuple[str, str]] = []
    total_chars = 0
    for path in files:
        if len(selected) >= MAX_FILES:
            break
        rel = path.relative_to(repo_root).as_posix()
        content = read_file_as_text(path)
        remaining = MAX_TOTAL_CHARS - total_chars
        if remaining <= 200:
            break
        if len(content) > remaining:
            content = content[:remaining] + "\n... [truncated for total context limit]"
        selected.append((rel, content))
        total_chars += len(content)

    if not selected:
        raise ProcessingError("No readable source files could be included.", status_code=422)

    lines = [
        f"Repository URL: {repo_url}",
        f"Local snapshot (read-only): {len(selected)} files, ~{total_chars} characters.",
        "Files were selected by priority (README, manifests, main/src files) and size limits.",
        "",
    ]
    for rel, content in selected:
        lines.append(f"===== FILE: {rel} =====")
        lines.append(content)
        lines.append("")
    return "\n".join(lines)
