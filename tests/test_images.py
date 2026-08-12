from pathlib import Path

from PIL import Image

from imagegen.images import generate_speaker_cutout


def test_generate_speaker_cutout_removes_corner_background(tmp_path: Path) -> None:
    source = tmp_path / "speaker.png"
    image = Image.new("RGB", (100, 100), "white")
    for x in range(30, 70):
        for y in range(15, 100):
            image.putpixel((x, y), (20, 40, 80))
    image.save(source)

    destination = tmp_path / "cutout.png"
    result = generate_speaker_cutout(str(source), destination, tmp_path / "cache")

    assert result == destination.as_posix()
    with Image.open(destination) as cutout:
        assert cutout.getpixel((0, 0))[3] == 0
        assert cutout.getpixel((50, 50))[3] == 255


def test_generate_speaker_cutout_rejects_fully_removed_image(tmp_path: Path) -> None:
    source = tmp_path / "speaker.png"
    Image.new("RGB", (100, 100), "white").save(source)
    destination = tmp_path / "cutout.png"

    result = generate_speaker_cutout(str(source), destination, tmp_path / "cache")

    assert result is None
    assert not destination.exists()