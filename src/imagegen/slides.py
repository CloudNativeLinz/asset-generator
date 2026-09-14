from __future__ import annotations

from pathlib import Path

from PIL import Image

from .config import Event, SlideDeck
from .loader import load_template
from .renderer import render_event

DEFAULT_SLIDE_TEMPLATES: dict[str, str] = {
    "title": "assets/templates/slide-title.yaml",
    "agenda": "assets/templates/slide-agenda.yaml",
    "speaker": "assets/templates/slide-speaker.yaml",
    "sponsors": "assets/templates/slide-sponsors.yaml",
    "cta": "assets/templates/slide-cta.yaml",
}


def _render_slide(
    template_path: str,
    event: Event,
    width: int | None,
    extra_context: dict | None = None,
) -> Image.Image:
    template = load_template(template_path)
    rendered = render_event(
        template=template,
        event=event,
        width=width,
        output_format="png",
        extra_context=extra_context,
    )
    return rendered.convert("RGB")


def _slide_order(event: Event, templates: dict[str, str]) -> list[tuple[str, str, dict | None]]:
    order: list[tuple[str, str, dict | None]] = [
        ("title", templates["title"], None),
        ("agenda", templates["agenda"], None),
    ]
    for index in range(len(event.talks)):
        order.append((f"speaker-{index + 1}", templates["speaker"], {"talk_index": index}))
    order.append(("sponsors", templates["sponsors"], None))
    order.append(("cta", templates["cta"], None))
    return order


def generate_slide_deck(
    event: Event,
    *,
    output_dir: str = "artifacts",
    templates: dict[str, str] | None = None,
    width: int | None = None,
) -> SlideDeck:
    resolved = {**DEFAULT_SLIDE_TEMPLATES, **(templates or {})}

    event_dir = Path(output_dir) / str(event.id)
    slides_dir = event_dir / "slides"
    slides_dir.mkdir(parents=True, exist_ok=True)

    slide_paths: list[str] = []
    pages: list[Image.Image] = []

    for position, (name, template_path, extra_context) in enumerate(
        _slide_order(event, resolved), start=1
    ):
        image = _render_slide(template_path, event, width, extra_context)
        png_path = slides_dir / f"{event.id}-{position:02d}-{name}.png"
        image.save(png_path, format="PNG")
        slide_paths.append(png_path.as_posix())
        pages.append(image)

    pdf_path = event_dir / "slides.pdf"
    if pages:
        pages[0].save(pdf_path, format="PDF", save_all=True, append_images=pages[1:])

    return SlideDeck(
        event_id=event.id,
        slides=slide_paths,
        pdf=pdf_path.as_posix() if pages else None,
    )
