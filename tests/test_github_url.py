"""Tests that do not require Ollama or a network clone."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from backend.github_processor import ProcessingError, build_repo_context, validate_github_url
from backend.main import app


def test_valid_github_urls() -> None:
    assert validate_github_url("https://github.com/pallets/flask") == ("pallets", "flask")
    assert validate_github_url("https://github.com/pallets/flask.git") == ("pallets", "flask")
    assert validate_github_url("https://github.com/pallets/flask/") == ("pallets", "flask")


def test_empty_url() -> None:
    with pytest.raises(ProcessingError) as exc:
        validate_github_url("   ")
    assert "enter" in exc.value.message.lower()


def test_invalid_url() -> None:
    with pytest.raises(ProcessingError):
        validate_github_url("https://gitlab.com/foo/bar")
    with pytest.raises(ProcessingError):
        validate_github_url("not-a-url")


def test_build_context_prioritizes_readme(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\nA tiny app.", encoding="utf-8")
    (tmp_path / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "ignored.js").write_text("should not appear", encoding="utf-8")

    context = build_repo_context(tmp_path, "https://github.com/example/demo")
    assert "README.md" in context
    assert "app.py" in context
    assert "should not appear" not in context


def test_fastapi_health_and_invalid_url() -> None:
    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"
    response = client.post("/explain", json={"repo_url": "not-a-github-url"})
    assert response.status_code == 400
    assert "Invalid GitHub URL" in response.json()["detail"]


def test_no_source_files(tmp_path: Path) -> None:
    (tmp_path / "photo.png").write_bytes(b"\x89PNG\r\n\x00\x00")
    with pytest.raises(ProcessingError) as exc:
        build_repo_context(tmp_path, "https://github.com/example/emptyish")
    assert "source" in exc.value.message.lower()
