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


def _color_distance(first: tuple[int, int, int], second: tuple[int, int, int]) -> int:
    return sum((first[channel] - second[channel]) ** 2 for channel in range(3))


def _fill_enclosed_foreground(alpha: Image.Image) -> Image.Image:
    closed = alpha.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))
    pixels = closed.load()
    width, height = closed.size
    exterior = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()
    for x in range(width):
        queue.extend(((x, 0), (x, height - 1)))
    for y in range(height):
        queue.extend(((0, y), (width - 1, y)))

    while queue:
        x, y = queue.popleft()
        index = y * width + x
        if exterior[index] or pixels[x, y] >= 128:
            continue
        exterior[index] = 1
        for next_x, next_y in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= next_x < width and 0 <= next_y < height:
                queue.append((next_x, next_y))

    filled = Image.new("L", (width, height), 255)
    filled_pixels = filled.load()
    for y in range(height):
        for x in range(width):
            if exterior[y * width + x]:
                filled_pixels[x, y] = 0
    return filled


def generate_speaker_cutout(source: str, destination: Path, cache_dir: Path) -> str | None:
    image = load_source_image(source, cache_dir)
    if image is None:
        return None

    segmentation_image = image.convert("RGB").filter(ImageFilter.GaussianBlur(1.0))
    width, height = segmentation_image.size
    pixels = segmentation_image.load()
    corner_size = max(2, min(width, height) // 20)
    corner_boxes = (
        (0, 0, corner_size, corner_size),
        (width - corner_size, 0, width, corner_size),
    )
    background_colors: list[tuple[int, int, int]] = []
    for left, top, right, bottom in corner_boxes:
        samples = [pixels[x, y] for y in range(top, bottom) for x in range(left, right)]
        background_colors.append(
            tuple(
                sorted(sample[channel] for sample in samples)[len(samples) // 2]
                for channel in range(3)
            )
        )

    background = bytearray(width * height)
    queued = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()
    border = (
        [(x, 0) for x in range(width)]
        + [(0, y) for y in range(height)]
        + [(width - 1, y) for y in range(height)]
    )
    maximum_seed_distance = 70**2
    for x, y in border:
        pixel = pixels[x, y]
        if (
            min(_color_distance(pixel, color) for color in background_colors)
            <= maximum_seed_distance
        ):
            queue.append((x, y))
            queued[y * width + x] = 1

    maximum_step_distance = 6**2
    while queue:
        x, y = queue.popleft()
        index = y * width + x
        background[index] = 1
        pixel = pixels[x, y]
        for next_x, next_y in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= next_x < width and 0 <= next_y < height:
                next_index = next_y * width + next_x
                if queued[next_index]:
                    continue
                next_pixel = pixels[next_x, next_y]
                if _color_distance(pixel, next_pixel) <= maximum_step_distance:
                    queued[next_index] = 1
                    queue.append((next_x, next_y))

    alpha = Image.new("L", (width, height), 255)
    alpha_pixels = alpha.load()
    for y in range(height):
        for x in range(width):
            if background[y * width + x]:
                alpha_pixels[x, y] = 0

    alpha = _fill_enclosed_foreground(alpha).filter(ImageFilter.GaussianBlur(0.7))
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
