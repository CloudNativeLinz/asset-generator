from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

_EMOJI_RANGES = (
    (0x1F000, 0x1FAFF),
    (0x2600, 0x27BF),
)


def _contains_emoji(value: str) -> bool:
    return any(any(start <= ord(ch) <= end for start, end in _EMOJI_RANGES) for ch in value)


def resolve_font_path(font_path: str, text: str) -> str:
    if not _contains_emoji(text):
        return font_path
    return font_path


def _emoji_code(emoji: str) -> str:
    normalized = emoji.replace("\ufe0f", "").replace("\ufe0e", "")
    return "".join(f"{ord(ch):x}" for ch in normalized).lower()


def _download_emoji_asset(emoji: str, cache_dir: Path) -> Path | None:
    code = _emoji_code(emoji)
    if not code:
        return None

    destination = cache_dir / "emoji" / f"{code}.png"
    if destination.exists():
        return destination

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(
            f"https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/{code}.png",
            timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException:
        return None

    try:
        destination.write_bytes(response.content)
    except OSError:
        return None

    return destination


def draw_text_with_emoji(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: str,
    cache_dir: Path,
) -> None:
    cursor = x
    pending = ""

    for ch in text:
        if _contains_emoji(ch):
            if pending:
                draw.text((cursor, y), pending, font=font, fill=fill)
                left, _, right, _ = draw.textbbox((0, 0), pending, font=font)
                cursor += right - left
                pending = ""

            asset = _download_emoji_asset(ch, cache_dir)
            if asset is not None:
                try:
                    with Image.open(asset) as emoji_image:
                        emoji = emoji_image.convert("RGBA")
                        emoji_size = max(int(font.size * 1.25), 20)
                        emoji = emoji.resize((emoji_size, emoji_size), Image.Resampling.LANCZOS)
                        offset_y = y + max((font.getbbox("M")[3] - emoji_size) // 2, 0)
                        canvas.alpha_composite(emoji, (cursor, offset_y))
                        cursor += emoji_size + 4
                except OSError:
                    pass
            continue

        pending += ch

    if pending:
        draw.text((cursor, y), pending, font=font, fill=fill)


def load_font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(font_path, size=size)


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    left, _, right, _ = draw.textbbox((0, 0), text=text, font=font)
    return right - left


def line_height(font: ImageFont.FreeTypeFont) -> int:
    ascent, descent = font.getmetrics()
    return ascent + descent


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]

    for word in words[1:]:
        candidate = f"{current} {word}"
        if text_width(draw, candidate, font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word

    lines.append(current)
    return lines


def fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: str,
    start_size: int,
    box_width: int,
    box_height: int,
    wrap_enabled: bool,
    line_spacing: float,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    size = start_size
    while size >= 10:
        font = load_font(font_path, size)
        lines = wrap_text(draw, text, font, box_width) if wrap_enabled else [text]
        total_height = int(len(lines) * line_height(font) * line_spacing)
        max_line_width = max((text_width(draw, line, font) for line in lines), default=0)

        if total_height <= box_height and max_line_width <= box_width:
            return font, lines
        size -= 1

    fallback = load_font(font_path, 10)
    final_lines = wrap_text(draw, text, fallback, box_width) if wrap_enabled else [text]
    return fallback, final_lines


def block_height(font: ImageFont.FreeTypeFont, lines: Iterable[str], line_spacing: float) -> int:
    return int(len(list(lines)) * line_height(font) * line_spacing)
