import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from jinja2 import Environment, FileSystemLoader

from imagegen.github_publish import GitHubPublishError
from imagegen.web import app as web_app
from imagegen.web.app import PublishImageRequest, create_app

EVENTS_FILE = Path(__file__).parent / "fixtures" / "events.yml"


@pytest.fixture
def studio(monkeypatch, tmp_path) -> FastAPI:
    monkeypatch.delenv("IMAGEGEN_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    event_dir = tmp_path / "artifacts" / "32"
    event_dir.mkdir(parents=True)
    (event_dir / "meetup.png").write_bytes(b"binary-image")
    (event_dir / "social.json").write_text("{}", encoding="utf-8")
    return create_app(
        template_path="assets/templates/save-the-date.yaml",
        events_file=str(EVENTS_FILE),
    )


def _endpoint(app: FastAPI, path: str, method: str) -> Callable[..., Any]:
    for route in app.routes:
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            return route.endpoint
    raise AssertionError(f"route {method} {path} is not registered")


def _json_body(response: Any) -> dict:
    return json.loads(response.body)


def _publish(app: FastAPI, name: str, event_id: int = 32, out: str = "artifacts") -> dict:
    endpoint = _endpoint(app, "/api/publish-image", "POST")
    payload = PublishImageRequest(id=event_id, name=name, out=out)
    return _json_body(asyncio.run(endpoint(payload)))


def test_studio_hides_api_discovery_but_registers_ui() -> None:
    events_file = Path(__file__).parent / "fixtures" / "events.yml"
    app = create_app(
        template_path="assets/templates/save-the-date.yaml",
        events_file=str(events_file),
    )

    route_paths = {route.path for route in app.routes}

    assert "/" in route_paths
    assert "/docs" not in route_paths
    assert "/redoc" not in route_paths
    assert "/openapi.json" not in route_paths


def test_index_serializes_template_paths_for_javascript() -> None:
    templates_dir = Path("src/imagegen/web/templates")
    environment = Environment(loader=FileSystemLoader(templates_dir), autoescape=True)

    rendered = environment.get_template("index.html").render(
        events=[],
        selected=0,
        template='assets/templates/"quoted".yaml',
        speaker_template="assets/templates/speaker.yaml",
    )

    assert 'template: "assets/templates/\\"quoted\\".yaml"' in rendered
    assert "dom.eventMeta.innerHTML" not in rendered


def test_generation_controls_share_busy_and_hover_states() -> None:
    templates_dir = Path("src/imagegen/web/templates")
    index_source = (templates_dir / "index.html").read_text(encoding="utf-8")
    settings_source = (templates_dir / "settings.html").read_text(encoding="utf-8")

    assert "dom.btnGenerateSocial.disabled = loading" in index_source
    assert 'setArtifactsLoading(true, "Generating social drafts...")' in index_source
    assert "button:not(:disabled):hover" in index_source
    assert ".btn:not(:disabled):hover" in settings_source


def test_google_slides_are_available_for_browser_inspection() -> None:
    index_source = Path("src/imagegen/web/templates/index.html").read_text(encoding="utf-8")

    assert 'id="googleSlidesSection"' in index_source
    assert 'id="btnGenerateGoogleSlides"' in index_source
    assert "async function generateGoogleSlides()" in index_source
    assert 'dom.btnGenerateGoogleSlides.addEventListener("click", async () =>' in index_source
    assert "include_slides: false" in index_source
    assert 'id="googleSlidesEmbed"' in index_source
    assert "encodeURIComponent(googleSlides.presentation_id)" in index_source
    assert "?embedded=true" not in index_source


def test_settings_report_github_availability(studio, monkeypatch) -> None:
    get_settings = _endpoint(studio, "/api/settings", "GET")

    assert _json_body(asyncio.run(get_settings()))["github_enabled"] is False

    monkeypatch.setenv("IMAGEGEN_GITHUB_TOKEN", "studio-token")
    payload = _json_body(asyncio.run(get_settings()))

    assert payload["github_enabled"] is True
    assert payload["settings"]["github_repo"] == "CloudNativeLinz/cloudnativelinz.github.io"
    assert "token" not in json.dumps(payload["settings"]).lower()


def test_publish_image_commits_the_requested_asset(studio, monkeypatch) -> None:
    monkeypatch.setenv("IMAGEGEN_GITHUB_TOKEN", "studio-token")
    captured: dict[str, object] = {}

    def fake_publish(source, *, repository, branch, repo_path, message, token=None):
        captured.update(
            {
                "source": Path(source).as_posix(),
                "repository": repository,
                "branch": branch,
                "repo_path": repo_path,
                "message": message,
            }
        )
        return {
            "repository": repository,
            "branch": branch,
            "path": repo_path,
            "updated": False,
            "url": "https://github.com/owner/repo/blob/main/path.png",
            "commit_url": "https://github.com/owner/repo/commit/abc123",
        }

    monkeypatch.setattr(web_app, "publish_file", fake_publish)

    body = _publish(studio, "meetup.png")

    assert body["published"] is True
    assert body["commit_url"] == "https://github.com/owner/repo/commit/abc123"
    assert captured["repo_path"] == "assets/images/events/32/meetup.png"
    assert captured["source"].endswith("artifacts/32/meetup.png")
    assert "32" in str(captured["message"])


def test_publish_image_maps_publish_errors_to_bad_gateway(studio, monkeypatch) -> None:
    monkeypatch.setenv("IMAGEGEN_GITHUB_TOKEN", "studio-token")

    def failing_publish(*args, **kwargs):
        raise GitHubPublishError("GitHub rejected the request (403)")

    monkeypatch.setattr(web_app, "publish_file", failing_publish)

    with pytest.raises(HTTPException) as error:
        _publish(studio, "meetup.png")

    assert error.value.status_code == 502
    assert "403" in error.value.detail


def test_publish_image_without_token_is_reported(studio) -> None:
    with pytest.raises(HTTPException) as error:
        _publish(studio, "meetup.png")

    assert error.value.status_code == 502
    assert "IMAGEGEN_GITHUB_TOKEN" in error.value.detail


@pytest.mark.parametrize(
    ("name", "status_code"),
    [
        ("missing.png", 404),
        ("../32/meetup.png", 400),
        ("social.json", 400),
    ],
)
def test_publish_image_rejects_unknown_and_traversal_names(
    studio, monkeypatch, name: str, status_code: int
) -> None:
    monkeypatch.setenv("IMAGEGEN_GITHUB_TOKEN", "studio-token")

    with pytest.raises(HTTPException) as error:
        _publish(studio, name)

    assert error.value.status_code == status_code


def test_publish_image_rejects_output_directories_outside_the_workspace(
    studio, monkeypatch
) -> None:
    monkeypatch.setenv("IMAGEGEN_GITHUB_TOKEN", "studio-token")

    with pytest.raises(HTTPException) as error:
        _publish(studio, "meetup.png", out="/etc")

    assert error.value.status_code == 400


def test_save_button_is_wired_to_the_publish_endpoint() -> None:
    index_source = Path("src/imagegen/web/templates/index.html").read_text(encoding="utf-8")

    assert "async function publishImage(asset, button)" in index_source
    assert 'apiPost("/api/publish-image"' in index_source
    assert "save.disabled = !state.githubEnabled;" in index_source
