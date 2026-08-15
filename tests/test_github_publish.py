import base64
import json
from pathlib import Path

import pytest

from imagegen import github_publish
from imagegen.github_publish import (
    DEFAULT_GITHUB_BRANCH,
    DEFAULT_GITHUB_PATH_PREFIX,
    DEFAULT_GITHUB_REPO,
    GitHubPublishError,
    build_repository_path,
    github_configuration_value,
    github_publishing_enabled,
    normalize_repository,
    publish_file,
    resolve_github_token,
)


class FakeResponse:
    def __init__(self, body: dict | None = None, status_code: int = 200) -> None:
        self._body = body if body is not None else {}
        self.status_code = status_code
        self.text = json.dumps(self._body)

    def json(self) -> dict:
        return self._body


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("IMAGEGEN_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)


def _image(tmp_path: Path) -> Path:
    source = tmp_path / "meetup.png"
    source.write_bytes(b"binary-image")
    return source


def test_github_destination_has_builtin_fallbacks() -> None:
    assert DEFAULT_GITHUB_REPO == "CloudNativeLinz/cloudnativelinz.github.io"
    assert DEFAULT_GITHUB_BRANCH == "main"
    assert DEFAULT_GITHUB_PATH_PREFIX == "assets/images/events"


def test_normalize_repository_requires_owner_and_name() -> None:
    assert normalize_repository(" CloudNativeLinz/site/ ") == "CloudNativeLinz/site"

    with pytest.raises(GitHubPublishError):
        normalize_repository("site")


def test_build_repository_path_joins_event_and_file() -> None:
    assert build_repository_path("/assets/images/", 44, "meetup.png") == (
        "assets/images/44/meetup.png"
    )
    assert build_repository_path("", 44, "meetup.png") == "44/meetup.png"

    with pytest.raises(GitHubPublishError):
        build_repository_path("assets/../../etc", 44, "meetup.png")


def test_token_resolution_prefers_imagegen_variable(monkeypatch) -> None:
    assert not github_publishing_enabled()
    with pytest.raises(GitHubPublishError):
        resolve_github_token()

    monkeypatch.setenv("GITHUB_TOKEN", "fallback-token")
    assert github_publishing_enabled()
    assert resolve_github_token() == "fallback-token"

    monkeypatch.setenv("IMAGEGEN_GITHUB_TOKEN", "studio-token")
    assert resolve_github_token() == "studio-token"


def test_configuration_prefers_environment_over_dotenv(monkeypatch, tmp_path) -> None:
    (tmp_path / ".env").write_text("DEFAULT_GITHUB_REPO=dotenv/repo\n", encoding="utf-8")

    assert github_configuration_value("DEFAULT_GITHUB_REPO") == "dotenv/repo"

    monkeypatch.setenv("DEFAULT_GITHUB_REPO", "environment/repo")
    assert github_configuration_value("DEFAULT_GITHUB_REPO") == "environment/repo"


def test_publish_file_creates_new_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("IMAGEGEN_GITHUB_TOKEN", "studio-token")
    source = _image(tmp_path)
    calls: dict[str, dict] = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        calls["get"] = {"url": url, "params": params}
        return FakeResponse({"message": "Not Found"}, status_code=404)

    def fake_put(url, headers=None, json=None, timeout=None):
        calls["put"] = {"url": url, "payload": json}
        return FakeResponse(
            {
                "content": {
                    "html_url": "https://github.com/owner/repo/blob/main/img/44/meetup.png"
                },
                "commit": {"html_url": "https://github.com/owner/repo/commit/abc123"},
            },
            status_code=201,
        )

    monkeypatch.setattr(github_publish.requests, "get", fake_get)
    monkeypatch.setattr(github_publish.requests, "put", fake_put)

    result = publish_file(
        source,
        repository="owner/repo",
        branch="main",
        repo_path="img/44/meetup.png",
        message="Add generated asset",
    )

    assert result["updated"] is False
    assert result["path"] == "img/44/meetup.png"
    assert result["commit_url"] == "https://github.com/owner/repo/commit/abc123"
    assert calls["get"]["params"] == {"ref": "main"}
    payload = calls["put"]["payload"]
    assert base64.b64decode(payload["content"]) == b"binary-image"
    assert payload["branch"] == "main"
    assert "sha" not in payload


def test_publish_file_updates_existing_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("IMAGEGEN_GITHUB_TOKEN", "studio-token")
    source = _image(tmp_path)
    captured: dict[str, dict] = {}

    monkeypatch.setattr(
        github_publish.requests,
        "get",
        lambda *args, **kwargs: FakeResponse({"sha": "existing-sha"}),
    )

    def fake_put(url, headers=None, json=None, timeout=None):
        captured["payload"] = json
        return FakeResponse({"content": {}, "commit": {}})

    monkeypatch.setattr(github_publish.requests, "put", fake_put)

    result = publish_file(
        source,
        repository="owner/repo",
        repo_path="img/44/meetup.png",
        message="Update generated asset",
    )

    assert result["updated"] is True
    assert captured["payload"]["sha"] == "existing-sha"


def test_publish_file_reports_permission_errors(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("IMAGEGEN_GITHUB_TOKEN", "studio-token")
    source = _image(tmp_path)

    monkeypatch.setattr(
        github_publish.requests,
        "get",
        lambda *args, **kwargs: FakeResponse({}, status_code=404),
    )
    monkeypatch.setattr(
        github_publish.requests,
        "put",
        lambda *args, **kwargs: FakeResponse({"message": "Resource not accessible"}, 403),
    )

    with pytest.raises(GitHubPublishError, match="Contents: write"):
        publish_file(
            source,
            repository="owner/repo",
            repo_path="img/44/meetup.png",
            message="Add generated asset",
        )


def test_publish_file_rejects_oversized_files(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("IMAGEGEN_GITHUB_TOKEN", "studio-token")
    source = _image(tmp_path)
    monkeypatch.setattr(github_publish, "MAX_UPLOAD_BYTES", 4)

    with pytest.raises(GitHubPublishError, match="too large"):
        publish_file(
            source,
            repository="owner/repo",
            repo_path="img/44/meetup.png",
            message="Add generated asset",
        )


def test_publish_file_requires_existing_source(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("IMAGEGEN_GITHUB_TOKEN", "studio-token")

    with pytest.raises(GitHubPublishError, match="File not found"):
        publish_file(
            tmp_path / "missing.png",
            repository="owner/repo",
            repo_path="img/44/missing.png",
            message="Add generated asset",
        )
