from __future__ import annotations

from collections.abc import Iterable

from PIL import ImageDraw, ImageFont


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
