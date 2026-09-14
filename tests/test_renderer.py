from pathlib import Path

import pytest
from PIL import Image

from imagegen.config import Event, Template
from imagegen.loader import find_event, load_events, load_template
from imagegen.renderer import render_event
from imagegen.text import resolve_font_path


def test_render_polygon_image_uses_template_coordinates(tmp_path: Path) -> None:
    background = tmp_path / "background.png"
    portrait = tmp_path / "portrait.png"
    Image.new("RGB", (100, 60), "white").save(background)
    Image.new("RGB", (40, 60), "red").save(portrait)
    template = Template.model_validate(
        {
            "name": "polygon-test",
            "background": str(background),
            "elements": [
                {
                    "id": "portrait",
                    "type": "image",
                    "source": str(portrait),
                    "box": {"x": 10, "y": 0, "w": 40, "h": 60},
                    "shape": "polygon",
                    "polygon_points": [[10, 0], [40, 0], [30, 60], [0, 60]],
                }
            ],
        }
    )

    rendered = render_event(template, Event(id=1), output_format="png")

    assert rendered.getpixel((11, 1))[:3] == (255, 255, 255)
    assert rendered.getpixel((25, 1))[:3] == (255, 0, 0)
    assert rendered.getpixel((15, 58))[:3] == (255, 0, 0)
    assert rendered.getpixel((49, 58))[:3] == (255, 255, 255)


def test_image_templates_do_not_force_uppercase() -> None:
    for template_path in Path("assets/templates").glob("*.yaml"):
        template_source = template_path.read_text(encoding="utf-8")
        assert "| upper" not in template_source, f"{template_path} forces uppercase text"


@pytest.mark.parametrize("template_path", sorted(Path("assets/templates").glob("*.yaml")))
def test_shipped_template_background_is_available(template_path: Path) -> None:
    template = load_template(str(template_path))
    if template.background is None:
        assert template.size is not None, f"{template_path} requires an explicit canvas size"
        Image.new("RGBA", (1, 1), template.background_color)
        return
    background = Path(template.background)

    assert background.is_file(), f"{template_path} references missing background {background}"
    with Image.open(background) as image:
        image.verify()


@pytest.mark.parametrize("output_format", ["png", "jpg"])
def test_render_solid_background_without_image(output_format: str) -> None:
    template = Template.model_validate(
        {
            "name": "solid-background",
            "background_color": "#26272B",
            "size": {"width": 100, "height": 60},
            "elements": [
                {
                    "id": "header",
                    "type": "rectangle",
                    "box": {"x": 0, "y": 0, "w": 100, "h": 20},
                    "color": "#FFFFFF",
                }
            ],
        }
    )
    image = render_event(template, Event(id=1), output_format=output_format)

    assert image.size == (100, 60)
    assert image.mode == ("RGBA" if output_format == "png" else "RGB")
    assert image.getpixel((50, 10))[:3] == (255, 255, 255)
    assert image.getpixel((50, 40))[:3] == (38, 39, 43)
    resized = render_event(template, Event(id=1), width=50)
    assert resized.size == (50, 30)


def test_solid_background_requires_size() -> None:
    with pytest.raises(ValueError, match="require an explicit size"):
        Template(name="missing-size", elements=[])


def test_explicit_missing_background_is_not_silently_replaced(tmp_path: Path) -> None:
    template = Template(
        name="missing-image",
        background=str(tmp_path / "missing.png"),
        elements=[],
    )
    with pytest.raises(FileNotFoundError):
        render_event(template, Event(id=1))


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
    speaker_portrait = Image.new("RGBA", (586, 727), (0, 0, 102, 255))
    monkeypatch.setattr(
        "imagegen.renderer.load_source_image",
        lambda source, cache_dir: speaker_portrait if source else None,
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
    assert rendered.getpixel((650, 360))[:3] == (0, 0, 102)
    assert rendered.getpixel((298, 803))[:3] == (0, 0, 0)


def test_render_speaking_at_template_with_regular_portrait(monkeypatch) -> None:
    portrait = Image.new("RGBA", (400, 400), (0, 0, 102, 255))
    monkeypatch.setattr(
        "imagegen.renderer.load_source_image",
        lambda source, cache_dir: portrait if source else None,
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


def test_render_single_speaker_diamond_template(monkeypatch) -> None:
    portrait = Image.new("RGBA", (400, 400), (0, 0, 102, 255))
    monkeypatch.setattr(
        "imagegen.renderer.load_source_image",
        lambda source, cache_dir: portrait if source else None,
    )
    monkeypatch.setattr("imagegen.text._download_emoji_asset", lambda emoji, cache_dir: None)
    template = load_template("assets/templates/speaker-diamond-1.yaml")
    event = Event(id=104, title="Event", date="2026-04-21", talks=[])

    rendered = render_event(
        template=template,
        event=event,
        output_format="png",
        extra_context={
            "diamond_title": "A talk",
            "diamond_speaker_names": "A speaker",
            "diamond_images": ["speaker.jpg"],
        },
    )

    assert rendered.getpixel((700, 350))[:3] == (0, 0, 102)
    assert rendered.getpixel((500, 350))[:3] != (0, 0, 102)
    assert rendered.getpixel((160, 803))[:3] == (0, 0, 0)


def test_render_two_speaker_diamond_template(monkeypatch) -> None:
    portraits = {
        "first.jpg": Image.new("RGBA", (400, 400), (102, 0, 0, 255)),
        "second.jpg": Image.new("RGBA", (400, 400), (0, 0, 102, 255)),
    }
    monkeypatch.setattr(
        "imagegen.renderer.load_source_image",
        lambda source, cache_dir: portraits.get(source),
    )
    monkeypatch.setattr("imagegen.text._download_emoji_asset", lambda emoji, cache_dir: None)
    template = load_template("assets/templates/speaker-diamond-2.yaml")
    event = Event(id=105, title="Event", date="2026-04-21", talks=[])

    rendered = render_event(
        template=template,
        event=event,
        output_format="png",
        extra_context={
            "diamond_title": "A shared talk",
            "diamond_speaker_names": "First & Second",
            "diamond_images": ["first.jpg", "second.jpg"],
        },
    )

    assert rendered.getpixel((650, 350))[:3] == (102, 0, 0)
    assert rendered.getpixel((930, 350))[:3] == (0, 0, 102)
    assert rendered.getpixel((870, 350))[:3] != (102, 0, 0)
