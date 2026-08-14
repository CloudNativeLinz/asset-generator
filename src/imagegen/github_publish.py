from __future__ import annotations

import base64
from os import getenv
from pathlib import Path
from typing import Any

import requests

GITHUB_API = "https://api.github.com"
DEFAULT_GITHUB_REPO = "CloudNativeLinz/cloudnativelinz.github.io"
DEFAULT_GITHUB_BRANCH = "main"
DEFAULT_GITHUB_PATH_PREFIX = "assets/images/events"
GITHUB_TOKEN_VARIABLES = ("IMAGEGEN_GITHUB_TOKEN", "GITHUB_TOKEN")
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class GitHubPublishError(RuntimeError):
    pass


def _dotenv_value(name: str, path: Path = Path(".env")) -> str:
    if not path.exists() or not path.is_file():
        return ""

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise GitHubPublishError(f"Unable to read {path}: {exc}") from exc

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        if key.strip() != name:
            continue
        resolved = value.strip()
        if len(resolved) >= 2 and resolved[0] == resolved[-1] and resolved[0] in {'"', "'"}:
            resolved = resolved[1:-1]
        return resolved
    return ""


def github_configuration_value(name: str) -> str:
    return (getenv(name, "") or _dotenv_value(name)).strip()


def resolve_github_token(token: str | None = None) -> str:
    resolved = (token or "").strip()
    if resolved:
        return resolved

    for variable in GITHUB_TOKEN_VARIABLES:
        value = github_configuration_value(variable)
        if value:
            return value

    raise GitHubPublishError(
        "Set IMAGEGEN_GITHUB_TOKEN (or GITHUB_TOKEN) to a token with Contents: write access"
    )


def github_publishing_enabled() -> bool:
    return any(github_configuration_value(variable) for variable in GITHUB_TOKEN_VARIABLES)


def normalize_repository(repository: str) -> str:
    value = repository.strip().strip("/")
    owner, _, name = value.partition("/")
    if not owner or not name or "/" in name:
        raise GitHubPublishError("Repository must use the owner/name format")
    return f"{owner}/{name}"


def build_repository_path(prefix: str, event_id: int, file_name: str) -> str:
    parts = [part for part in prefix.strip().strip("/").split("/") if part]
    if any(part == ".." for part in parts):
        raise GitHubPublishError("Repository path prefix must not contain '..'")
    parts.extend([str(event_id), file_name])
    return "/".join(parts)


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _failure_message(action: str, status_code: int, detail: str) -> str:
    if status_code in {401, 403}:
        return (
            f"GitHub rejected the request ({status_code}). Check that the token is valid and "
            f"has Contents: write access to the repository: {detail}"
        )
    if status_code == 404:
        return (
            f"GitHub could not find the repository or branch ({status_code}). Check the "
            f"repository, branch, and token access: {detail}"
        )
    if status_code in {409, 422}:
        return (
            f"GitHub reported a conflict ({status_code}). The branch may have moved on; "
            f"retry the save: {detail}"
        )
    return f"GitHub {action} failed ({status_code}): {detail}"


def _existing_file_sha(*, repository: str, repo_path: str, branch: str, token: str) -> str | None:
    url = f"{GITHUB_API}/repos/{repository}/contents/{repo_path}"
    try:
        response = requests.get(url, headers=_headers(token), params={"ref": branch}, timeout=30)
    except requests.RequestException as exc:
        raise GitHubPublishError(f"Failed to reach GitHub: {exc}") from exc

    if response.status_code == 404:
        return None
    if response.status_code >= 400:
        raise GitHubPublishError(
            _failure_message("lookup", response.status_code, response.text.strip()[:500])
        )

    try:
        body = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        raise GitHubPublishError("GitHub returned a non-JSON response") from exc
    if not isinstance(body, dict):
        raise GitHubPublishError("GitHub returned an unexpected contents response")

    sha = body.get("sha")
    return sha if isinstance(sha, str) and sha else None


def publish_file(
    source: Path,
    *,
    repository: str = DEFAULT_GITHUB_REPO,
    branch: str = DEFAULT_GITHUB_BRANCH,
    repo_path: str,
    message: str,
    token: str | None = None,
) -> dict[str, Any]:
    resolved_token = resolve_github_token(token)
    target_repository = normalize_repository(repository)
    target_branch = branch.strip() or DEFAULT_GITHUB_BRANCH

    if not source.exists() or not source.is_file():
        raise GitHubPublishError(f"File not found: {source.as_posix()}")

    payload_bytes = source.read_bytes()
    if len(payload_bytes) > MAX_UPLOAD_BYTES:
        raise GitHubPublishError(
            f"File is too large for the GitHub contents API ({len(payload_bytes)} bytes)"
        )

    existing_sha = _existing_file_sha(
        repository=target_repository,
        repo_path=repo_path,
        branch=target_branch,
        token=resolved_token,
    )

    payload: dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(payload_bytes).decode("ascii"),
        "branch": target_branch,
    }
    if existing_sha:
        payload["sha"] = existing_sha

    url = f"{GITHUB_API}/repos/{target_repository}/contents/{repo_path}"
    try:
        response = requests.put(url, headers=_headers(resolved_token), json=payload, timeout=60)
    except requests.RequestException as exc:
        raise GitHubPublishError(f"Failed to reach GitHub: {exc}") from exc

    if response.status_code >= 400:
        raise GitHubPublishError(
            _failure_message("commit", response.status_code, response.text.strip()[:500])
        )

    try:
        body = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        raise GitHubPublishError("GitHub returned a non-JSON response") from exc
    if not isinstance(body, dict):
        raise GitHubPublishError("GitHub returned an unexpected commit response")

    content = body.get("content") if isinstance(body.get("content"), dict) else {}
    commit = body.get("commit") if isinstance(body.get("commit"), dict) else {}

    return {
        "repository": target_repository,
        "branch": target_branch,
        "path": repo_path,
        "updated": existing_sha is not None,
        "url": content.get("html_url"),
        "commit_url": commit.get("html_url"),
    }
