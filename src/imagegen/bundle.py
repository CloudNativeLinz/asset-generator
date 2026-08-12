from __future__ import annotations

import json
from pathlib import Path

from .animate import generate_animations
from .config import (
    AnimationBundle,
    CTAVariants,
    Event,
    GeneratedBundle,
    ImageBundle,
    SlideDeck,
)
from .images import generate_speaker_cutout
from .loader import load_template
from .renderer import render_event
from .slides import generate_slide_deck
from .social import generate_social_bundle


def _save_image(image, destination: Path, output_format: str) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    pil_format = "PNG" if output_format == "png" else "JPEG"
    image.save(destination, format=pil_format, quality=95)
    return destination.as_posix()


def generate_event_bundle(
    event: Event,
    *,
    meetup_template_path: str,
    speaker_template_path: str,
    output_dir: str = "artifacts",
    width: int | None = None,
    output_format: str = "jpg",
    include_social: bool = True,
    include_slides: bool = True,
    animation_presets: list[str] | None = None,
    cta_defaults: CTAVariants | None = None,
) -> GeneratedBundle:
    fmt = output_format.lower()
    if fmt not in {"jpg", "png"}:
        raise ValueError("output_format must be jpg or png")

    meetup_template = load_template(meetup_template_path)
    speaker_template = load_template(speaker_template_path)

    event_dir = Path(output_dir) / str(event.id)

    meetup_image = render_event(
        template=meetup_template, event=event, width=width, output_format=fmt
    )
    meetup_destination = event_dir / f"meetup.{fmt}"
    meetup_path = _save_image(meetup_image, meetup_destination, fmt)

    speaker_paths: list[str] = []
    for existing in event_dir.glob("speaker-*.*"):
        if existing.suffix.lower() in {".jpg", ".png"}:
            existing.unlink()

    for index, talk in enumerate(event.talks):
        if not talk.cutout and talk.image:
            generated_cutout = generate_speaker_cutout(
                str(talk.image),
                event_dir / "cutouts" / f"speaker-{index + 1}.png",
                Path(".cache/images"),
            )
            if generated_cutout is not None:
                talk.cutout = generated_cutout

        cutout_image = render_event(
            template=speaker_template,
            event=event,
            width=width,
            output_format=fmt,
            extra_context={"talk_index": index, "speaker_variant": "cutout"},
        )
        cutout_destination = event_dir / f"speaker-{index + 1}-cutout.{fmt}"
        speaker_paths.append(_save_image(cutout_image, cutout_destination, fmt))

        portrait_image = render_event(
            template=speaker_template,
            event=event,
            width=width,
            output_format=fmt,
            extra_context={"talk_index": index, "speaker_variant": "portrait"},
        )
        portrait_destination = event_dir / f"speaker-{index + 1}-portrait.{fmt}"
        speaker_paths.append(_save_image(portrait_image, portrait_destination, fmt))

    social = generate_social_bundle(event, cta_defaults=cta_defaults) if include_social else None

    if social is not None:
        social_destination = event_dir / "social.json"
        social_destination.parent.mkdir(parents=True, exist_ok=True)
        social_destination.write_text(
            json.dumps(social.model_dump(by_alias=True), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    slides: SlideDeck | None = None
    if include_slides:
        slides = generate_slide_deck(event, output_dir=output_dir, width=width)

    animations: list[AnimationBundle] = []
    for preset in animation_presets or []:
        animations.append(
            generate_animations(event, preset=preset, output_dir=output_dir, width=width)
        )

    return GeneratedBundle(
        event_id=event.id,
        output_dir=event_dir.as_posix(),
        images=ImageBundle(meetup_image=meetup_path, speaker_images=speaker_paths),
        social=social,
        slides=slides,
        animations=animations,
    )
