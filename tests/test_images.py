from PIL import Image

from imagegen.images import apply_shape, fit_image


def test_fit_image_contain_bottom_anchors_visible_alpha_to_edge() -> None:
    image = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    image.paste((20, 40, 80, 255), (25, 10, 75, 80))

    fitted = fit_image(image, width=100, height=100, mode="contain-bottom")

    alpha_bounds = fitted.getchannel("A").getbbox()
    assert alpha_bounds is not None
    assert alpha_bounds[3] == 100


def test_apply_shape_masks_slanted_diamond_photo() -> None:
    image = Image.new("RGBA", (585, 548), (20, 40, 80, 255))

    shaped = apply_shape(image, "parallelogram")

    assert shaped.getpixel((0, 0))[3] == 0
    assert shaped.getpixel((200, 0))[3] == 255
    assert shaped.getpixel((0, 547))[3] == 255
    assert shaped.getpixel((584, 547))[3] == 0


def test_apply_shape_masks_two_diamond_photo_panels() -> None:
    image = Image.new("RGBA", (665, 548), (20, 40, 80, 255))

    shaped = apply_shape(image, "parallelogram-pair")

    assert shaped.getpixel((200, 0))[3] == 255
    assert shaped.getpixel((405, 0))[3] == 0
    assert shaped.getpixel((500, 0))[3] == 255
    assert shaped.getpixel((260, 547))[3] == 0
