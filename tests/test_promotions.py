from pathlib import Path

import pytest
from PIL import Image

from imagegen.config import Event, ImageElement
from imagegen.promotions import (
    PROMOTION_FORMATS,
    PROMOTION_SIZES,
    generate_promotions,
    promotion_context,
    render_promotion,
)


@pytest.mark.parametrize(
    "preset,size",
    [("meetup-website", (1080, 610)), ("mobile-website", (341, 200)), ("teaser", (1166, 200))],
)
def test_promotion_native_dimensions(preset: str, size: tuple[int, int]) -> None:
    event = Event(id=1, date="2026-09-16", time="17:30", host="Netcetera")
    image = render_promotion(event, preset)
    assert image.size == size
    assert image.size == PROMOTION_SIZES[preset]
    assert image.mode == "RGBA"
    with Image.open(f"assets/backgrounds/{preset}.png") as background:
        assert image.getpixel((0, 0))[:3] == background.convert("RGB").getpixel((0, 0))


def test_promotion_slot_selection_preserves_order_and_event() -> None:
    event = Event(id=1, talks=[{}, {"speaker": "Second speaker", "title": "Second talk"}])
    original = event.model_dump()
    context = promotion_context(event)
    assert context["promotion_variant"] == "second-slot"
    assert context["slots"][0]["speaker"] == "To be announced"
    assert context["slots"][1]["speaker"] == "Second speaker"
    hidden = promotion_context(event, "save-the-date")
    assert hidden["slots"][1]["speaker"] == "You?"
    assert event.model_dump() == original


@pytest.mark.parametrize(
    "speaker,count", [("First & Second", 2), ("First and Second", 2), ("Solo", 1)]
)
def test_promotion_copresenters_are_not_separate_talks(speaker: str, count: int) -> None:
    event = Event(id=1, talks=[{"speaker": speaker, "images": ["a.png", "b.png"]}])
    context = promotion_context(event)
    assert len(context["slots"][0]["images"]) == count
    assert context["promotion_variant"] == "first-slot"
    assert context["slots"][1]["images"] == []


@pytest.mark.parametrize("fmt", ["jpg", "png"])
def test_generate_promotions_distinct_outputs(tmp_path: Path, fmt: str) -> None:
    event = Event(id=7)
    images = generate_promotions(event, output_dir=str(tmp_path), output_format=fmt)
    assert len(images) == len(PROMOTION_FORMATS)
    assert len({image.path for image in images}) == len(images)
    for result in images:
        with Image.open(result.path) as image:
            assert image.size == (result.width, result.height)
            assert image.format == ("JPEG" if fmt == "jpg" else "PNG")
    assert generate_promotions(event, output_dir=str(tmp_path), output_format=fmt) == images


@pytest.mark.parametrize("preset", list(PROMOTION_FORMATS))
@pytest.mark.parametrize("counts", [(1, 1), (1, 2), (2, 1), (2, 2)])
def test_promotion_masks_cover_correct_talk_slots(
    tmp_path: Path, preset: str, counts: tuple[int, int]
) -> None:
    portraits = []
    for color in ["red", "blue", "green", "yellow"]:
        path = tmp_path / f"{color}.png"
        Image.new("RGB", (200, 300), color).save(path)
        portraits.append(str(path))
    event = Event(
        id=1,
        talks=[
            {
                "speaker": "First & Partner" if counts[0] == 2 else "First",
                "images": portraits[: counts[0]],
            },
            {
                "speaker": "Second & Partner" if counts[1] == 2 else "Second",
                "images": portraits[2 : 2 + counts[1]],
            },
        ],
    )
    before = event.model_dump()
    points = {
        "meetup-website": [(145, 180), (240, 180), (875, 180), (970, 180)],
        "mobile-website": [(15, 100), (65, 100), (266, 100), (320, 100)],
        "teaser": [(40, 100), (215, 100), (950, 100), (1100, 100)],
    }[preset]
    image = render_promotion(event, preset)
    expected = [
        (255, 0, 0),
        (0, 0, 255) if counts[0] == 2 else (255, 0, 0),
        (0, 128, 0),
        (255, 255, 0) if counts[1] == 2 else (0, 128, 0),
    ]
    assert [image.getpixel(point)[:3] for point in points] == expected
    hidden = render_promotion(event, preset, "second-slot")
    with Image.open(f"assets/backgrounds/{preset}.png") as background:
        assert hidden.getpixel(points[0])[:3] == background.convert("RGB").getpixel(points[0])
    assert event.model_dump() == before


def test_promotion_missing_photo_keeps_background(tmp_path: Path) -> None:
    event = Event(id=1, talks=[{"speaker": "Speaker", "image": str(tmp_path / "missing.png")}])
    image = render_promotion(event, "meetup-website")
    with Image.open("assets/backgrounds/meetup-website.png") as background:
        assert image.getpixel((145, 180))[:3] == background.convert("RGB").getpixel((145, 180))


def test_mobile_small_type_is_not_enlarged() -> None:
    from PIL import ImageDraw

    from imagegen.text import fit_text

    draw = ImageDraw.Draw(Image.new("RGB", (341, 200)))
    font, lines = fit_text(
        draw, "Netcetera", "assets/fonts/DejaVuSans.ttf", 9, 170, 15, False, 1.15
    )
    assert font.size == 9
    assert lines == ["Netcetera"]


def test_promotion_custom_width_and_validation() -> None:
    assert render_promotion(Event(id=1), "meetup-website", width=540).size == (540, 305)
    with pytest.raises(ValueError, match="Unknown promotion format"):
        render_promotion(Event(id=1), "../unknown")
    with pytest.raises(ValueError, match="Unknown promotion variant"):
        promotion_context(Event(id=1), "unknown")
    with pytest.raises(ValueError, match="polygon_points"):
        ImageElement(id="bad", source="", box={"x": 0, "y": 0, "w": 10, "h": 10}, shape="polygon")
