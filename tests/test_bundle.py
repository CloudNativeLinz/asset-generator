from pathlib import Path

from imagegen.bundle import generate_event_bundle
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
    assert len(bundle.images.speaker_images) == len(event.talks) * 2
    assert Path(bundle.output_dir, "speaker-1-cutout.jpg").exists()
    assert Path(bundle.output_dir, "speaker-1-portrait.jpg").exists()
    assert Path(bundle.output_dir, "cutouts", "speaker-1.png").exists()
    assert Path(bundle.output_dir, "social.json").exists()
