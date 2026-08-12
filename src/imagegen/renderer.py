from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment
from PIL import Image, ImageDraw

from .config import Event, ImageElement, RectangleElement, Template, TextElement
from .images import apply_shape, fit_image, load_source_image
from .text import (
    draw_text_with_emoji,
    fit_text,
    line_height,
    load_font,
    resolve_font_path,
    wrap_text,
)


def _slug(value: Any) -> str:
    raw = str(value or "").strip().lower()
    chars = [ch if ch.isalnum() else "-" for ch in raw]
    slug = "".join(chars)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def _date_filter(value: Any, fmt: str = "%d %b %Y") -> str:
    if isinstance(value, date):
        return value.strftime(fmt)

    text = str(value or "").strip()
    if not text:
        return ""

    for candidate in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(text, candidate).replace(tzinfo=UTC)
            return parsed.strftime(fmt)
        except ValueError:
            continue
    return text


def _default_filter(value: Any, fallback: Any = "") -> Any:
    return value if value not in (None, "") else fallback


def _jinja_env() -> Environment:
    env = Environment(autoescape=False)
    env.filters["slug"] = _slug
    env.filters["date"] = _date_filter
    env.filters["default"] = _default_filter
    env.filters["upper"] = lambda value: str(value).upper()
    env.filters["lower"] = lambda value: str(value).lower()
    return env


def _render_template_string(value: str, context: dict[str, Any], env: Environment) -> str:
    return env.from_string(value).render(**context).strip()


def _event_context(event: Event) -> dict[str, Any]:
    context = event.model_dump()
    talks = context.get("talks")
    if not isinstance(talks, list):
        talks = []

    padded_talks = [dict(talk) if isinstance(talk, dict) else {} for talk in talks]
    while len(padded_talks) < 2:
        padded_talks.append(
            {"title": "", "speaker": "", "image": "", "cutout": "", "social": None}
        )

    context["talks"] = padded_talks
    return context


def _draw_text_element(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    element: TextElement,
    text: str,
    default_font: str,
    default_color: str,
    default_size: int,
) -> None:
    font_path = element.font or default_font
    if not font_path:
        raise ValueError(
            f"Element {element.id} requires a font in template.defaults.font or element.font"
        )

    font_path = resolve_font_path(font_path, text)
    font_size = element.size or default_size
    color = element.color or default_color

    if element.fit == "shrink":
        font, lines = fit_text(
            draw=draw,
            text=text,
            font_path=font_path,
            start_size=font_size,
            box_width=element.box.w,
            box_height=element.box.h,
            wrap_enabled=element.wrap,
            line_spacing=element.line_spacing,
        )
    else:
        font = load_font(font_path, font_size)
        lines = wrap_text(draw, text, font, element.box.w) if element.wrap else [text]

    lh = line_height(font)
    total_height = int(len(lines) * lh * element.line_spacing)

    if element.valign == "middle":
        start_y = element.box.y + max((element.box.h - total_height) // 2, 0)
    elif element.valign == "bottom":
        start_y = element.box.y + max(element.box.h - total_height, 0)
    else:
        start_y = element.box.y

    for index, line in enumerate(lines):
        left, _, right, _ = draw.textbbox((0, 0), line, font=font)
        width = right - left

        if element.align == "center":
            x = element.box.x + max((element.box.w - width) // 2, 0)
        elif element.align == "right":
            x = element.box.x + max(element.box.w - width, 0)
        else:
            x = element.box.x

        y = start_y + int(index * lh * element.line_spacing)
        if any(ord(ch) > 127 for ch in line):
            draw_text_with_emoji(
                canvas=canvas,
                draw=draw,
                x=x,
                y=y,
                text=line,
                font=font,
                fill=color,
                cache_dir=Path(".cache/images"),
            )
        else:
            draw.text((x, y), line, fill=color, font=font)


def _draw_image_element(
    canvas: Image.Image,
    element: ImageElement,
    source: str,
    cache_dir: Path,
) -> None:
    image = load_source_image(source, cache_dir)
    if image is None:
        return

    fitted = fit_image(image, element.box.w, element.box.h, element.fit)
    shaped = apply_shape(fitted, element.shape, corner_radius=element.corner_radius)
    canvas.alpha_composite(shaped, (element.box.x, element.box.y))


def render_event(
    template: Template,
    event: Event,
    width: int | None = None,
    output_format: str = "jpg",
    cache_dir: str = ".cache/images",
    extra_context: dict[str, Any] | None = None,
) -> Image.Image:
    background = Image.open(template.background).convert("RGBA")

    if template.size is not None:
        canvas_size = (template.size.width, template.size.height)
        if background.size != canvas_size:
            background = background.resize(canvas_size, resample=Image.Resampling.LANCZOS)
    else:
        canvas_size = background.size

    canvas = Image.new("RGBA", canvas_size)
    canvas.alpha_composite(background)

    env = _jinja_env()
    context = {"event": _event_context(event)}
    if extra_context:
        context.update(extra_context)
    draw = ImageDraw.Draw(canvas)

    default_font = template.defaults.font or ""
    default_color = template.defaults.color
    default_size = template.defaults.size

    for element in template.elements:
        if isinstance(element, RectangleElement):
            draw.rectangle(
                (
                    element.box.x,
                    element.box.y,
                    element.box.x + element.box.w - 1,
                    element.box.y + element.box.h - 1,
                ),
                fill=element.color,
            )
        elif isinstance(element, TextElement):
            rendered_value = _render_template_string(element.value, context, env)
            _draw_text_element(
                canvas=canvas,
                draw=draw,
                element=element,
                text=rendered_value,
                default_font=default_font,
                default_color=default_color,
                default_size=default_size,
            )
        else:
            rendered_source = _render_template_string(element.source, context, env)
            _draw_image_element(
                canvas=canvas, element=element, source=rendered_source, cache_dir=Path(cache_dir)
            )

    if width and width > 0 and width != canvas.width:
        height = round(width * canvas.height / canvas.width)
        canvas = canvas.resize((width, height), resample=Image.Resampling.LANCZOS)

    if output_format.lower() == "png":
        return canvas

    return canvas.convert("RGB")
