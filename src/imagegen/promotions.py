from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from PIL import Image

from .config import Event, PromotionImage, Talk
from .loader import load_template
from .renderer import render_event

PromotionFormat = Literal["meetup-website", "mobile-website", "teaser"]
PromotionVariant = Literal["auto", "save-the-date", "first-slot", "second-slot", "both-slots"]

PROMOTION_PRESETS = {
    "meetup-website": ("Meetup & Website", 1080, 610),
    "mobile-website": ("Mobile Website", 341, 200),
    "teaser": ("Teaser", 1166, 200),
}
PROMOTION_FORMATS = {
    preset: f"{label} ({width} x {height})"
    for preset, (label, width, height) in PROMOTION_PRESETS.items()
}
PROMOTION_SIZES = {
    preset: (width, height) for preset, (_, width, height) in PROMOTION_PRESETS.items()
}
PROMOTION_VARIANTS = {
    "auto": "Current lineup",
    "save-the-date": "Save the date",
    "first-slot": "First talk only",
    "second-slot": "Second talk only",
    "both-slots": "Both talks",
}


def _slot(talk: Talk | None) -> dict:
    if talk is None:
        return {"speaker": "", "title": "", "images": []}
    images = [str(source) for source in talk.images if source]
    if not images and talk.image:
        images = [str(talk.image)]
    names = re.split(r"\s+(?:&|and)\s+", talk.speaker.strip(), flags=re.IGNORECASE)
    return {
        "speaker": talk.speaker.strip(),
        "title": talk.title.strip(),
        "images": images[:2] if len(names) == 2 else images[:1],
    }


def promotion_context(event: Event, variant: str = "auto") -> dict:
    if variant not in PROMOTION_VARIANTS:
        raise ValueError(f"Unknown promotion variant: {variant}")
    slots = [_slot(event.talks[index] if index < len(event.talks) else None) for index in range(2)]
    if variant == "save-the-date":
        slots = [_slot(None), _slot(None)]
    elif variant == "first-slot":
        slots[1] = _slot(None)
    elif variant == "second-slot":
        slots[0] = _slot(None)

    occupied = [bool(slot["speaker"] or slot["title"] or slot["images"]) for slot in slots]
    resolved = variant
    if variant == "auto":
        resolved = (
            "both-slots"
            if all(occupied)
            else "first-slot" if occupied[0] else "second-slot" if occupied[1] else "save-the-date"
        )
    for index, slot in enumerate(slots):
        slot["speaker"] = slot["speaker"] or (
            "To be announced" if index == 0 or occupied[index] else "You?"
        )
        slot["title"] = slot["title"] or (
            "Just reach out." if index == 1 and not occupied[1] else ""
        )
    return {"slots": slots, "promotion_variant": resolved}


def render_promotion(
    event: Event,
    preset: str,
    variant: str = "auto",
    *,
    width: int | None = None,
    output_format: str = "png",
) -> Image.Image:
    if preset not in PROMOTION_FORMATS:
        raise ValueError(f"Unknown promotion format: {preset}")
    if output_format not in {"jpg", "png"}:
        raise ValueError("output_format must be jpg or png")
    if width is not None and width < 1:
        raise ValueError("width must be positive")
    return render_event(
        load_template(f"assets/templates/{preset}.yaml"),
        event,
        width=width,
        output_format=output_format,
        extra_context=promotion_context(event, variant),
    )


def generate_promotions(
    event: Event,
    *,
    presets: list[str] | None = None,
    variant: str = "auto",
    output_dir: str = "artifacts",
    width: int | None = None,
    output_format: str = "jpg",
) -> list[PromotionImage]:
    selected = list(dict.fromkeys(PROMOTION_FORMATS if presets is None else presets))
    for preset in selected:
        if preset not in PROMOTION_FORMATS:
            raise ValueError(f"Unknown promotion format: {preset}")
    context = promotion_context(event, variant)
    results: list[PromotionImage] = []
    for preset in selected:
        image = render_promotion(event, preset, variant, width=width, output_format=output_format)
        suffix = f"-{width}" if width is not None else ""
        destination = (
            Path(output_dir)
            / str(event.id)
            / (f"{preset}-{context['promotion_variant']}{suffix}.{output_format}")
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination, format="PNG" if output_format == "png" else "JPEG", quality=95)
        results.append(
            PromotionImage(
                preset=preset,
                variant=context["promotion_variant"],
                path=destination.as_posix(),
                width=image.width,
                height=image.height,
            )
        )
    return results
