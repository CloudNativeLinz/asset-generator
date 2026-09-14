from pathlib import Path

import pytest
from PIL import Image

from imagegen.bundle import _has_two_speakers, generate_event_bundle
from imagegen.config import Event, Talk
from imagegen.loader import find_event, load_events


def test_generate_event_bundle_creates_images_and_social(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)

    event = find_event(load_events("_data/sample-events.yml"), 32)

    bundle = generate_event_bundle(
        event,
        meetup_template_path="assets/templates/meetup.yaml",
        speaker_template_path="assets/templates/speaker.yaml",
        output_dir=str(tmp_path),
        output_format="jpg",
    )

    assert bundle.images.meetup_image is not None
    assert Path(bundle.images.meetup_image).exists()
    assert bundle.images.meetup_diamond_image is not None
    assert Path(bundle.images.meetup_diamond_image).exists()
    assert len(bundle.images.speaker_images) == len(event.talks) * 2
    assert Path(bundle.output_dir, "32-meetup-diamond.jpg").exists()
    assert Path(bundle.output_dir, "32-speaker-1-portrait.jpg").exists()
    assert Path(bundle.output_dir, "32-speaker-1-diamond.jpg").exists()
    assert Path(bundle.output_dir, "social.json").exists()


@pytest.mark.parametrize("output_format", ["jpg", "png"])
def test_bundle_generates_only_portrait_and_diamond_speaker_cards(
    tmp_path: Path, monkeypatch, output_format: str
) -> None:
    from imagegen import bundle as bundle_module

    render_contexts: list[dict] = []

    def fake_render(**kwargs) -> Image.Image:
        render_contexts.append(kwargs.get("extra_context", {}))
        return Image.new("RGB", (64, 64))

    monkeypatch.setattr(bundle_module, "render_event", fake_render)
    portrait = tmp_path / "portrait.png"
    Image.new("RGB", (64, 64), "blue").save(portrait)
    event = Event(
        id=1,
        talks=[
            Talk(speaker="First", image=str(portrait)),
            Talk(speaker="Second", image=str(portrait)),
        ],
    )
    original = event.model_dump()

    bundle = generate_event_bundle(
        event,
        meetup_template_path="assets/templates/save-the-date.yaml",
        speaker_template_path="assets/templates/speaker.yaml",
        output_dir=str(tmp_path),
        output_format=output_format,
        include_social=False,
        include_slides=False,
        promotion_formats=[],
    )

    expected_names = {
        f"1-speaker-{number}-{variant}.{output_format}"
        for number in (1, 2)
        for variant in ("portrait", "diamond")
    }
    assert {Path(path).name for path in bundle.images.speaker_images} == expected_names
    assert {path.name for path in Path(bundle.output_dir).rglob("1-speaker-*")} == expected_names
    assert len(render_contexts) == 6
    assert event.model_dump() == original


def test_generate_event_bundle_preserves_other_speaker_images(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    event = find_event(load_events("_data/sample-events.yml"), 32)
    event_dir = tmp_path / str(event.id)
    event_dir.mkdir()
    existing = event_dir / "speaker-legacy.jpg"
    existing.write_bytes(b"existing-image")

    generate_event_bundle(
        event,
        meetup_template_path="assets/templates/meetup.yaml",
        speaker_template_path="assets/templates/speaker.yaml",
        output_dir=str(tmp_path),
        output_format="jpg",
        include_social=False,
        include_slides=False,
    )

    assert existing.read_bytes() == b"existing-image"


def test_two_speaker_diamond_selection_uses_speaker_names() -> None:
    assert _has_two_speakers(Talk(speaker="First Speaker & Second Speaker"))
    assert _has_two_speakers(Talk(speaker="First Speaker and Second Speaker"))
    assert not _has_two_speakers(
        Talk(speaker="Solo Speaker", images=["first-angle.jpg", "second-angle.jpg"])
    )


def test_bundle_adds_native_promotions_without_changing_legacy_width(tmp_path, monkeypatch) -> None:
    from imagegen import bundle as bundle_module

    monkeypatch.setattr(bundle_module, "render_event", lambda **kwargs: Image.new("RGB", (64, 64)))
    result = generate_event_bundle(
        Event(id=1),
        meetup_template_path="assets/templates/save-the-date.yaml",
        speaker_template_path="assets/templates/speaker.yaml",
        output_dir=str(tmp_path),
        width=64,
        include_social=False,
        include_slides=False,
    )
    assert Path(result.images.meetup_image).name == "1-meetup.jpg"
    assert len(result.images.promotions) == 3
    assert [(image.width, image.height) for image in result.images.promotions] == [
        (1080, 610),
        (341, 200),
        (1166, 200),
    ]
    with Image.open(result.images.meetup_image) as image:
        assert image.size == (64, 64)
