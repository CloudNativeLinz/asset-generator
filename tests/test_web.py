import asyncio
import json
from collections.abc import Callable
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from jinja2 import Environment, FileSystemLoader
from PIL import Image

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
    Image.new("RGB", (16, 9), "navy").save(event_dir / "meetup.png")
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


def _publish(app: FastAPI, name: str, event_id: int = 32) -> dict:
    endpoint = _endpoint(app, "/api/publish-image", "POST")
    payload = PublishImageRequest(id=event_id, name=name)
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


def test_index_defaults_to_images_with_other_workspaces_hidden() -> None:
    class ElementsById(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.elements: dict[str, dict[str, str | None]] = {}

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            attributes = dict(attrs)
            element_id = attributes.get("id")
            if element_id:
                assert element_id not in self.elements
                self.elements[element_id] = attributes

    environment = Environment(
        loader=FileSystemLoader("src/imagegen/web/templates"), autoescape=True
    )
    rendered = environment.get_template("index.html").render(
        events=[],
        selected=0,
        template="assets/templates/save-the-date.yaml",
        speaker_template="assets/templates/speaker.yaml",
    )
    parser = ElementsById()
    parser.feed(rendered)
    elements = parser.elements

    for name, selected in (
        ("images", True),
        ("social", False),
        ("slides", False),
        ("settings", False),
    ):
        tab = elements[f"{name}Tab"]
        panel = elements[f"{name}Panel"]
        assert tab["role"] == "tab"
        assert tab["data-workspace-target"] == name
        assert tab["aria-selected"] == str(selected).lower()
        assert tab["tabindex"] == ("0" if selected else "-1")
        assert tab["aria-controls"] == panel["id"]
        assert panel["role"] == "tabpanel"
        assert panel["aria-labelledby"] == tab["id"]
        assert ("hidden" in panel) is not selected

    for control in ("btnGenerateSocial", "btnGenerateBundle"):
        assert elements[control]["data-workspace"] == "social"
        assert "hidden" in elements[control]
    assert elements["btnGenerateImages"]["data-workspace"] == "images"
    assert "hidden" not in elements["btnGenerateImages"]
    assert elements["btnGenerateGoogleSlides"]["data-workspace"] == "slides"
    assert "hidden" in elements["btnGenerateGoogleSlides"]
    assert "hidden" not in elements["googleSlidesEmpty"]
    assert "hidden" not in elements["btnLoadSnapshot"]
    assert "meetupPost" in elements
    assert "talkEditors" in elements
    assert elements["btnSaveSettings"]["type"] == "submit"
    assert "disabled" in elements["settingsFields"]
    assert 'href="/settings"' not in rendered
    setting_names = {attributes.get("name") for attributes in elements.values()} - {None}
    assert setting_names == set(web_app.StudioSettings.model_fields)


def test_generation_controls_share_busy_and_hover_states() -> None:
    templates_dir = Path("src/imagegen/web/templates")
    index_source = (templates_dir / "index.html").read_text(encoding="utf-8")

    assert "dom.btnGenerateSocial.disabled = loading" in index_source
    assert 'setArtifactsLoading(true, "Generating social drafts...")' in index_source
    assert "button:not(:disabled):hover" in index_source
    assert (
        "dom.btnSaveSettings.disabled = loading || state.savingSettings || !state.settings"
        in index_source
    )


def test_google_slides_are_available_for_browser_inspection() -> None:
    index_source = Path("src/imagegen/web/templates/index.html").read_text(encoding="utf-8")

    assert index_source.index('id="slidesPanel"') < index_source.index('id="googleSlidesEmbed"')
    assert 'id="slidesSurface" aria-busy="false"' in index_source
    assert "dom.slidesLoadingText.textContent = message" in index_source
    assert 'id="googleSlidesSection"' in index_source
    assert 'id="btnGenerateGoogleSlides"' in index_source
    assert "async function generateGoogleSlides()" in index_source
    assert 'dom.btnGenerateGoogleSlides.addEventListener("click", async () =>' in index_source
    assert "include_slides: false" in index_source
    assert 'id="googleSlidesEmbed"' in index_source
    assert "encodeURIComponent(googleSlides.presentation_id)" in index_source
    assert "?embedded=true" not in index_source


def test_settings_page_redirects_to_studio_tab(studio) -> None:
    settings_page = _endpoint(studio, "/settings", "GET")

    response = asyncio.run(settings_page())

    assert response.status_code == 307
    assert response.headers["location"] == "/#settings"


def test_settings_save_and_load_all_form_values(studio) -> None:
    payload = web_app.StudioSettings(
        cta_register="Register now",
        cta_attend="Attend the meetup",
        cta_recap="Read the recap",
        width=640,
        image_format="png",
        google_slides_template="presentation-id",
        github_repo="owner/repository",
        github_branch="preview",
        github_path_prefix="assets/events",
    )
    save_settings = _endpoint(studio, "/api/settings", "POST")
    get_settings = _endpoint(studio, "/api/settings", "GET")

    saved = _json_body(asyncio.run(save_settings(payload)))
    loaded = _json_body(asyncio.run(get_settings()))

    assert saved["saved"] is True
    assert saved["settings"] == loaded["settings"] == payload.model_dump()


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
        with Image.open(source) as image:
            uploaded_format = image.format
        captured.update(
            {
                "source": Path(source).as_posix(),
                "source_name": Path(source).name,
                "uploaded_format": uploaded_format,
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
    assert captured["repo_path"] == "images/events/32.jpg"
    assert captured["source_name"] == "32.jpg"
    assert captured["uploaded_format"] == "JPEG"
    assert captured["repository"] == "CloudNativeLinz/cloudnativelinz.github.io"
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


def test_publish_image_rejects_unknown_events(studio, monkeypatch) -> None:
    monkeypatch.setenv("IMAGEGEN_GITHUB_TOKEN", "studio-token")

    with pytest.raises(HTTPException) as error:
        _publish(studio, "meetup.png", event_id=999)

    assert error.value.status_code == 404


def test_save_button_is_wired_to_the_publish_endpoint() -> None:
    index_source = Path("src/imagegen/web/templates/index.html").read_text(encoding="utf-8")

    assert "async function publishImage(asset, button)" in index_source
    assert 'apiPost("/api/publish-image"' in index_source
    assert "save.disabled = !state.githubEnabled;" in index_source
    assert 'save.textContent = "Use on website"' in index_source


def test_bundle_snapshot_includes_current_website_image(studio) -> None:
    endpoint = _endpoint(studio, "/api/bundle/{event_id}", "GET")

    body = _json_body(asyncio.run(endpoint(32, "artifacts")))

    assert body["current_image"] == {
        "name": "32.jpg",
        "url": "https://raw.githubusercontent.com/CloudNativeLinz/cloudnativelinz.github.io/main/images/events/32.jpg",
        "page_url": "https://cloudnativelinz.at/",
        "repository": "CloudNativeLinz/cloudnativelinz.github.io",
        "path": "images/events/32.jpg",
    }


def test_comparison_and_publish_share_configured_target(studio, monkeypatch) -> None:
    settings = web_app.StudioSettings(
        github_repo="owner/images", github_branch="preview", github_path_prefix="event images"
    )
    web_app._save_settings(Path("artifacts/studio-settings.json"), settings)
    endpoint = _endpoint(studio, "/api/bundle/{event_id}", "GET")
    body = _json_body(asyncio.run(endpoint(32, "artifacts")))
    assert body["current_image"]["url"] == (
        "https://raw.githubusercontent.com/owner/images/preview/event%20images/32.jpg"
    )
    captured = {}

    def fake_publish(source, **kwargs):
        captured.update(kwargs)
        return {"updated": True}

    monkeypatch.setattr(web_app, "publish_file", fake_publish)
    assert _publish(studio, "meetup.png")["published"] is True
    assert captured["repository"] == "owner/images"
    assert captured["branch"] == "preview"
    assert captured["repo_path"] == "event images/32.jpg"


@pytest.mark.parametrize("suffix", ["png", "jpg"])
def test_publish_rejects_invalid_image_bytes(studio, monkeypatch, suffix) -> None:
    Path(f"artifacts/32/broken.{suffix}").write_bytes(b"not an image")

    def unexpected_publish(*args, **kwargs):
        pytest.fail("Invalid image must not be uploaded")

    monkeypatch.setattr(web_app, "publish_file", unexpected_publish)
    with pytest.raises(HTTPException) as error:
        _publish(studio, f"broken.{suffix}")
    assert error.value.status_code == 400
    assert "Regenerate" in error.value.detail


def test_publish_preserves_jpeg_bytes(studio, monkeypatch) -> None:
    source = Path("artifacts/32/meetup.jpg")
    Image.new("RGB", (16, 9), "navy").save(source)
    original_bytes = source.read_bytes()

    def fake_publish(upload_source, **kwargs):
        assert upload_source.read_bytes() == original_bytes
        assert kwargs["repo_path"] == "images/events/32.jpg"
        return {"updated": True}

    monkeypatch.setattr(web_app, "publish_file", fake_publish)
    assert _publish(studio, source.name)["published"] is True


def test_promotion_requests_validate_presets_and_variants() -> None:
    assert web_app.BundleRequest(id=1).promotion_formats is None
    assert web_app.BundleRequest(id=1, promotion_formats=[]).promotion_formats == []
    assert web_app.StudioSettings().width is None
    with pytest.raises(ValueError):
        web_app.PromotionsRequest(id=1, presets=["../template"])
    with pytest.raises(ValueError):
        web_app.PromotionsRequest(id=1, variant="unknown")


def test_main_generation_includes_landscapes_without_separate_controls() -> None:
    environment = Environment(
        loader=FileSystemLoader("src/imagegen/web/templates"), autoescape=True
    )
    rendered = environment.get_template("index.html").render(
        events=[],
        selected=0,
        template="assets/templates/save-the-date.yaml",
        speaker_template="assets/templates/speaker.yaml",
        promotion_formats=web_app.PROMOTION_FORMATS,
        promotion_variants=web_app.PROMOTION_VARIANTS,
    )
    for control in (
        "promotionCanvas",
        "promotionVariant",
        "includePromotions",
        "btnPreviewPromotions",
        "btnGeneratePromotions",
        "promotionPreview",
    ):
        assert control not in rendered
    assert "Landscape Graphics" not in rendered
    assert 'id="btnGenerateImages"' in rendered
    assert "promotion_formats: Object.keys(promotionFormats)" in rendered
    assert 'promotion_variant: "auto"' in rendered
    assert "download.download = asset.name" in rendered


def test_generate_promotions_api_ignores_legacy_width(studio, monkeypatch) -> None:
    from imagegen.config import PromotionImage

    captured = {}

    def fake_generate(event, **kwargs):
        captured.update(kwargs)
        path = Path("artifacts/32/teaser-first-slot.png")
        path.write_bytes(b"image")
        return [
            PromotionImage(
                preset="teaser", variant="first-slot", path=str(path), width=1166, height=200
            )
        ]

    monkeypatch.setattr(web_app, "generate_promotions", fake_generate)
    web_app._save_settings(
        Path("artifacts/studio-settings.json"), web_app.StudioSettings(width=900)
    )
    endpoint = _endpoint(studio, "/api/generate-promotions", "POST")
    body = _json_body(
        asyncio.run(
            endpoint(web_app.PromotionsRequest(id=32, presets=["teaser"], variant="first-slot"))
        )
    )
    assert captured["presets"] == ["teaser"]
    assert captured["variant"] == "first-slot"
    assert "width" not in captured
    assert body["images"][0]["width"] == 1166
    assert any(asset.get("preset") == "teaser" for asset in body["snapshot"]["images"])


def test_promotion_preview_returns_native_png(studio, monkeypatch) -> None:
    from io import BytesIO

    from PIL import Image

    monkeypatch.setattr(
        web_app, "render_promotion", lambda event, preset, variant: Image.new("RGB", (341, 200))
    )
    endpoint = _endpoint(studio, "/render-promotion", "GET")

    async def read_response():
        response = await endpoint(32, "mobile-website", "second-slot")
        assert response.media_type == "image/png"
        return b"".join([part async for part in response.body_iterator])

    with Image.open(BytesIO(asyncio.run(read_response()))) as image:
        assert image.size == (341, 200)
