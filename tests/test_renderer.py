from pathlib import Path

from PIL import Image

from imagegen.config import Event
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


def test_render_save_the_date_template(monkeypatch) -> None:
    sponsor_image = Image.new("RGBA", (300, 300), "#000066")
    monkeypatch.setattr(
        "imagegen.renderer.load_source_image", lambda source, cache_dir: sponsor_image
    )
    monkeypatch.setattr("imagegen.text._download_emoji_asset", lambda emoji, cache_dir: None)

    template = load_template("assets/templates/save-the-date.yaml")
    event = Event(
        id=100,
        title="Save the Date",
        date="2026-09-16",
        time="17:30",
        venue="Netcetera",
        address="Example Street 1, 4020 Linz",
        host="Netcetera",
        sponsor_logo="sponsor.png",
    )

    rendered = render_event(template=template, event=event, output_format="png")

    assert rendered.size == (1200, 1200)
    assert rendered.getpixel((251, 803))[:3] == (0, 0, 0)
    assert rendered.getpixel((376, 899))[:3] == (0, 0, 0)
    assert rendered.getpixel((850, 500))[:3] == (0, 0, 102)


def test_render_speaking_at_template(monkeypatch) -> None:
    speaker_cutout = Image.new("RGBA", (586, 727), (0, 0, 102, 255))
    monkeypatch.setattr(
        "imagegen.renderer.load_source_image",
        lambda source, cache_dir: speaker_cutout if source else None,
    )
    monkeypatch.setattr("imagegen.text._download_emoji_asset", lambda emoji, cache_dir: None)

    template = load_template("assets/templates/speaker.yaml")
    event = Event(
        id=101,
        title="Speaker Event",
        date="2026-05-26",
        time="17:30",
        host="Dynatrace",
        talks=[
            {
                "title": "SBOBs: Shipping Intended Behavior",
                "speaker": "Constanze B. Roedig",
                "image": "speaker.jpg",
                "cutout": "speaker.png",
            }
        ],
    )

    rendered = render_event(
        template=template,
        event=event,
        output_format="png",
        extra_context={"talk_index": 0},
    )

    assert rendered.size == (1200, 1200)
    assert rendered.getpixel((493, 166))[:3] == (0, 0, 102)
    assert rendered.getpixel((298, 803))[:3] == (0, 0, 0)


def test_render_speaking_at_template_with_regular_portrait(monkeypatch) -> None:
    portrait = Image.new("RGBA", (400, 400), (0, 0, 102, 255))
    monkeypatch.setattr(
        "imagegen.renderer.load_source_image", lambda source, cache_dir: portrait if source else None
    )
    monkeypatch.setattr("imagegen.text._download_emoji_asset", lambda emoji, cache_dir: None)

    template = load_template("assets/templates/speaker.yaml")
    event = Event(
        id=102,
        title="Speaker Event",
        date="2026-04-21",
        time="17:30",
        host="karriere.at",
        talks=[
            {
                "title": "What Going Cloud Native Taught Us About Developer Experience",
                "speaker": "Thomas Schuetz",
                "image": "speaker.jpg",
            }
        ],
    )

    rendered = render_event(
        template=template,
        event=event,
        output_format="png",
        extra_context={"talk_index": 0},
    )

    assert rendered.getpixel((650, 360))[:3] == (0, 0, 102)
    assert rendered.getpixel((500, 200))[:3] == (255, 255, 255)
