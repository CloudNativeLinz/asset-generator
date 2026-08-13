from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from imagegen.web.app import create_app


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
