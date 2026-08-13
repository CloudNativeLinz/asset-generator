from pathlib import Path

from PIL import Image

from imagegen.images import fit_image, generate_speaker_cutout


def test_fit_image_contain_bottom_anchors_visible_alpha_to_edge() -> None:
    image = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    image.paste((20, 40, 80, 255), (25, 10, 75, 80))

    fitted = fit_image(image, width=100, height=100, mode="contain-bottom")

    alpha_bounds = fitted.getchannel("A").getbbox()
    assert alpha_bounds is not None
    assert alpha_bounds[3] == 100


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


def test_generate_speaker_cutout_follows_gradient_without_removing_subject(tmp_path: Path) -> None:
    source = tmp_path / "speaker-gradient.png"
    image = Image.new("RGB", (100, 100))
    for y in range(100):
        background = 180 + y // 3
        for x in range(100):
            image.putpixel((x, y), (background, background, background))

    for x in range(30, 70):
        for y in range(20, 70):
            image.putpixel((x, y), (205, 165, 145))
    for x in range(28, 72):
        for y in range(15, 25):
            image.putpixel((x, y), (35, 25, 20))
    for x in range(20, 80):
        for y in range(65, 100):
            image.putpixel((x, y), (130, 20, 35))
    image.save(source)

    destination = tmp_path / "cutout.png"
    result = generate_speaker_cutout(str(source), destination, tmp_path / "cache")

    assert result == destination.as_posix()
    with Image.open(destination) as cutout:
        assert cutout.getpixel((5, 50))[3] == 0
        assert cutout.getpixel((50, 18))[3] == 255
        assert cutout.getpixel((50, 45))[3] == 255
        assert cutout.getpixel((50, 95))[3] == 255


def test_generate_speaker_cutout_rejects_fully_removed_image(tmp_path: Path) -> None:
    source = tmp_path / "speaker.png"
    Image.new("RGB", (100, 100), "white").save(source)
    destination = tmp_path / "cutout.png"

    result = generate_speaker_cutout(str(source), destination, tmp_path / "cache")

    assert result is None
    assert not destination.exists()
