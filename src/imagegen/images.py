from __future__ import annotations

import hashlib
from collections import deque
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageOps, UnidentifiedImageError


class ImageFetchError(RuntimeError):
    pass


def _cache_path(url: str, cache_dir: Path) -> Path:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    suffix = Path(urlparse(url).path).suffix or ".img"
    return cache_dir / f"{digest}{suffix}"


def resolve_source_path(source: str) -> Path:
    if source.startswith("/"):
        absolute = Path(source)
        if absolute.exists():
            return absolute
        return Path(source[1:])
    return Path(source)


def load_source_image(source: str, cache_dir: Path) -> Image.Image | None:
    source = (source or "").strip()
    if not source:
        return None

    cache_dir.mkdir(parents=True, exist_ok=True)

    if source.startswith(("http://", "https://")):
        cache_file = _cache_path(source, cache_dir)
        if not cache_file.exists():
            try:
                response = requests.get(source, timeout=15)
            except requests.RequestException:
                return None
            if response.status_code != 200:
                return None
            cache_file.write_bytes(response.content)
        try:
            return Image.open(cache_file).convert("RGBA")
        except (OSError, UnidentifiedImageError):
            return None

    local_path = resolve_source_path(source)
    if not local_path.exists() or local_path.is_dir():
        return None
    try:
        return Image.open(local_path).convert("RGBA")
    except (OSError, UnidentifiedImageError):
        return None


def fit_image(image: Image.Image, width: int, height: int, mode: str) -> Image.Image:
    if mode == "fill":
        return image.resize((width, height), resample=Image.Resampling.LANCZOS)

    if mode in {"contain", "contain-bottom"}:
        if mode == "contain-bottom" and image.mode == "RGBA":
            alpha_bounds = image.getchannel("A").getbbox()
            if alpha_bounds is not None:
                image = image.crop(alpha_bounds)

        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        fitted = ImageOps.contain(image, (width, height), method=Image.Resampling.LANCZOS)
        x = (width - fitted.width) // 2
        y = height - fitted.height if mode == "contain-bottom" else (height - fitted.height) // 2
        canvas.alpha_composite(fitted, (x, y))
        return canvas

    return ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS)


def apply_shape(image: Image.Image, shape: str, corner_radius: int = 24) -> Image.Image:
    if shape == "rect":
        return image

    mask = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(mask)

    if shape == "circle":
        draw.ellipse((0, 0, image.width, image.height), fill=255)
    else:
        draw.rounded_rectangle((0, 0, image.width, image.height), radius=corner_radius, fill=255)

    shaped = image.copy()
    shaped.putalpha(mask)
    return shaped


def generate_speaker_cutout(source: str, destination: Path, cache_dir: Path) -> str | None:
    image = load_source_image(source, cache_dir)
    if image is None:
        return None

    rgb = image.convert("RGB")
    width, height = rgb.size
    pixels = rgb.load()
    corner_size = max(2, min(width, height) // 20)
    corner_boxes = (
        (0, 0, corner_size, corner_size),
        (width - corner_size, 0, width, corner_size),
        (0, height - corner_size, corner_size, height),
        (width - corner_size, height - corner_size, width, height),
    )
    background_colors: list[tuple[int, int, int]] = []
    for left, top, right, bottom in corner_boxes:
        samples = [pixels[x, y] for y in range(top, bottom) for x in range(left, right)]
        background_colors.append(
            tuple(sorted(sample[channel] for sample in samples)[len(samples) // 2] for channel in range(3))
        )
    candidate_background = bytearray(width * height)
    maximum_color_distance = 42**2
    for y in range(height):
        for x in range(width):
            red, green, blue = pixels[x, y]
            color_distance = min(
                (red - bg_red) ** 2 + (green - bg_green) ** 2 + (blue - bg_blue) ** 2
                for bg_red, bg_green, bg_blue in background_colors
            )
            if color_distance <= maximum_color_distance:
                candidate_background[y * width + x] = 1

    background = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()
    for x in range(width):
        queue.extend(((x, 0), (x, height - 1)))
    for y in range(height):
        queue.extend(((0, y), (width - 1, y)))

    while queue:
        x, y = queue.popleft()
        index = y * width + x
        if background[index] or not candidate_background[index]:
            continue
        background[index] = 1
        for next_x, next_y in (
            (x - 1, y),
            (x + 1, y),
            (x, y - 1),
            (x, y + 1),
            (x - 1, y - 1),
            (x + 1, y - 1),
            (x - 1, y + 1),
            (x + 1, y + 1),
        ):
            if 0 <= next_x < width and 0 <= next_y < height:
                queue.append((next_x, next_y))

    alpha = Image.new("L", (width, height), 255)
    alpha_pixels = alpha.load()
    for y in range(height):
        for x in range(width):
            if background[y * width + x]:
                alpha_pixels[x, y] = 0

    alpha = alpha.filter(ImageFilter.GaussianBlur(0.8))
    histogram = alpha.histogram()
    pixel_count = width * height
    transparent_ratio = sum(histogram[:16]) / pixel_count
    opaque_ratio = sum(histogram[240:]) / pixel_count
    if transparent_ratio < 0.05 or opaque_ratio < 0.05:
        return None

    cutout = image.copy()
    cutout.putalpha(alpha)
    destination.parent.mkdir(parents=True, exist_ok=True)
    cutout.save(destination, format="PNG")
    return destination.as_posix()
