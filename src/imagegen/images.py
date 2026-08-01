from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError


class ImageFetchError(RuntimeError):
    pass


def _cache_path(url: str, cache_dir: Path) -> Path:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    suffix = Path(urlparse(url).path).suffix or ".img"
    return cache_dir / f"{digest}{suffix}"


def resolve_source_path(source: str) -> Path:
    if source.startswith("/"):
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

    if mode == "contain":
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        fitted = ImageOps.contain(image, (width, height), method=Image.Resampling.LANCZOS)
        x = (width - fitted.width) // 2
        y = (height - fitted.height) // 2
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
