from pathlib import Path

from PIL import Image

from imagegen.loader import find_event, load_events
from imagegen.slides import generate_slide_deck


def test_generate_slide_deck_creates_pdf_and_pngs(tmp_path: Path) -> None:
    event = find_event(load_events("_data/sample-events.yml"), 32)

    deck = generate_slide_deck(event, output_dir=str(tmp_path))

    # title + agenda + one slide per talk + sponsors + cta
    expected = 2 + len(event.talks) + 2
    assert len(deck.slides) == expected

    assert deck.pdf is not None
    assert Path(deck.pdf).exists()

    for slide_path in deck.slides:
        path = Path(slide_path)
        assert path.exists()
        assert path.name.startswith(f"{event.id}-")
        with Image.open(slide_path) as img:
            assert img.size == (1920, 1080)


def test_generate_slide_deck_respects_width(tmp_path: Path) -> None:
    event = find_event(load_events("_data/sample-events.yml"), 32)

    deck = generate_slide_deck(event, output_dir=str(tmp_path), width=960)

    with Image.open(deck.slides[0]) as img:
        assert img.width == 960
