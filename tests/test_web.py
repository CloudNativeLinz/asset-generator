from pathlib import Path

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