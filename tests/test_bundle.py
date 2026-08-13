from pathlib import Path

from imagegen.bundle import _has_two_speakers, generate_event_bundle
from imagegen.config import Talk
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
    assert len(bundle.images.speaker_images) == len(event.talks) * 3
    assert Path(bundle.output_dir, "meetup-diamond.jpg").exists()
    assert Path(bundle.output_dir, "speaker-1-cutout.jpg").exists()
    assert Path(bundle.output_dir, "speaker-1-portrait.jpg").exists()
    assert Path(bundle.output_dir, "speaker-1-diamond.jpg").exists()
    assert Path(bundle.output_dir, "cutouts", "speaker-1.png").exists()
    assert Path(bundle.output_dir, "social.json").exists()


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
