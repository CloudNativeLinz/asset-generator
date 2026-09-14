from pathlib import Path

import pytest
from PIL import Image

from imagegen.animate import generate_animations
from imagegen.loader import find_event, load_events


def test_speaker_spotlight_emits_gif_per_talk(tmp_path: Path) -> None:
    event = find_event(load_events("_data/sample-events.yml"), 32)

    bundle = generate_animations(
        event,
        preset="speaker-spotlight",
        output_dir=str(tmp_path),
        prefer_mp4=False,
    )

    assert bundle.preset == "speaker-spotlight"
    assert len(bundle.clips) == len(event.talks)

    for clip in bundle.clips:
        assert clip.mp4 is None
        assert clip.gif is not None
        gif_path = Path(clip.gif)
        assert gif_path.exists()
        assert gif_path.name.startswith(f"{event.id}-")
        with Image.open(gif_path) as img:
            assert getattr(img, "is_animated", False)


def test_event_teaser_emits_single_clip(tmp_path: Path) -> None:
    event = find_event(load_events("_data/sample-events.yml"), 32)

    bundle = generate_animations(
        event,
        preset="event-teaser",
        output_dir=str(tmp_path),
        prefer_mp4=False,
    )

    assert len(bundle.clips) == 1
    gif_path = Path(bundle.clips[0].gif)
    assert gif_path.exists()
    assert gif_path.name == f"{event.id}-event-teaser.gif"


def test_invalid_preset_raises(tmp_path: Path) -> None:
    event = find_event(load_events("_data/sample-events.yml"), 32)

    with pytest.raises(ValueError):
        generate_animations(event, preset="unknown", output_dir=str(tmp_path))
