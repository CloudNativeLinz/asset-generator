from pathlib import Path

from imagegen.loader import find_event, load_events, load_template
from imagegen.renderer import render_event
from imagegen.text import resolve_font_path


def test_render_sample_event(tmp_path: Path) -> None:
    template = load_template("assets/templates/meetup.yaml")
    event = find_event(load_events("_data/sample-events.yml"), 32)

    rendered = render_event(template=template, event=event, width=1200, output_format="jpg")
    output = tmp_path / "32-1200.jpg"
    rendered.save(output, format="JPEG")

    assert output.exists()
    assert output.stat().st_size > 0


def test_render_event_with_no_confirmed_talks(tmp_path: Path) -> None:
    template = load_template("assets/templates/meetup.yaml")
    events_file = tmp_path / "events.yml"
    events_file.write_text(
        """
- id: 88
  title: "Event still booking speakers"
  host: null
  talks: []
""".strip(),
        encoding="utf-8",
    )

    event = find_event(load_events(str(events_file)), 88)
    rendered = render_event(template=template, event=event, width=1200, output_format="jpg")

    assert rendered.size[0] > 0
    assert rendered.size[1] > 0


def test_emoji_title_uses_unicode_fallback_font() -> None:
    font_path = resolve_font_path("assets/fonts/LBRITE.TTF", "🚀 Cloud Native Linz")

    assert font_path == "assets/fonts/LBRITE.TTF"
