from __future__ import annotations

import json
import re
from pathlib import Path

from .animate import generate_animations
from .config import (
    AnimationBundle,
    CTAVariants,
    Event,
    GeneratedBundle,
    ImageBundle,
    SlideDeck,
    Talk,
)
from .loader import load_template
from .promotions import PROMOTION_FORMATS, generate_promotions, promotion_context
from .renderer import render_event
from .slides import generate_slide_deck
from .social import generate_social_bundle

DIAMOND_SINGLE_TEMPLATE = "assets/templates/speaker-diamond-1.yaml"
DIAMOND_DOUBLE_TEMPLATE = "assets/templates/speaker-diamond-2.yaml"


def _save_image(image, destination: Path, output_format: str) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    pil_format = "PNG" if output_format == "png" else "JPEG"
    image.save(destination, format=pil_format, quality=95)
    return destination.as_posix()


def _talk_images(talk: Talk) -> list[str]:
    sources = [str(source) for source in talk.images if source]
    if not sources and talk.image:
        sources.append(str(talk.image))
    return sources


def _has_two_speakers(talk: Talk) -> bool:
    return len(re.split(r"\s+(?:&|and)\s+", talk.speaker.strip(), flags=re.IGNORECASE)) == 2


def _event_diamond_context(event: Event) -> dict[str, object]:
    talks = [talk for talk in event.talks if talk.speaker or _talk_images(talk)]
    images: list[str] = []
    for talk in talks:
        images.extend(_talk_images(talk))
        if len(images) >= 2:
            break

    return {
        "diamond_title": event.title,
        "diamond_speaker_names": " & ".join(talk.speaker for talk in talks[:2] if talk.speaker),
        "diamond_images": images[:2],
    }


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
    promotion_formats: list[str] | None = None,
    promotion_variant: str = "auto",
) -> GeneratedBundle:
    fmt = output_format.lower()
    if fmt not in {"jpg", "png"}:
        raise ValueError("output_format must be jpg or png")
    promotion_context(event, promotion_variant)
    if promotion_formats is not None and any(
        preset not in PROMOTION_FORMATS for preset in promotion_formats
    ):
        raise ValueError("Unknown promotion format")

    meetup_template = load_template(meetup_template_path)
    speaker_template = load_template(speaker_template_path)
    diamond_single_template = load_template(DIAMOND_SINGLE_TEMPLATE)
    diamond_double_template = load_template(DIAMOND_DOUBLE_TEMPLATE)

    event_dir = Path(output_dir) / str(event.id)

    meetup_image = render_event(
        template=meetup_template, event=event, width=width, output_format=fmt
    )
    meetup_destination = event_dir / f"{event.id}-meetup.{fmt}"
    meetup_path = _save_image(meetup_image, meetup_destination, fmt)

    meetup_diamond_image = render_event(
        template=diamond_double_template,
        event=event,
        width=width,
        output_format=fmt,
        extra_context=_event_diamond_context(event),
    )
    meetup_diamond_destination = event_dir / f"{event.id}-meetup-diamond.{fmt}"
    meetup_diamond_path = _save_image(meetup_diamond_image, meetup_diamond_destination, fmt)

    speaker_paths: list[str] = []
    for index, talk in enumerate(event.talks):
        portrait_image = render_event(
            template=speaker_template,
            event=event,
            width=width,
            output_format=fmt,
            extra_context={"talk_index": index},
        )
        portrait_destination = event_dir / f"{event.id}-speaker-{index + 1}-portrait.{fmt}"
        speaker_paths.append(_save_image(portrait_image, portrait_destination, fmt))

        diamond_template = (
            diamond_double_template if _has_two_speakers(talk) else diamond_single_template
        )
        diamond_image = render_event(
            template=diamond_template,
            event=event,
            width=width,
            output_format=fmt,
            extra_context={
                "diamond_title": talk.title,
                "diamond_speaker_names": talk.speaker,
                "diamond_images": _talk_images(talk),
            },
        )
        diamond_destination = event_dir / f"{event.id}-speaker-{index + 1}-diamond.{fmt}"
        speaker_paths.append(_save_image(diamond_image, diamond_destination, fmt))

    promotions = generate_promotions(
        event,
        presets=promotion_formats,
        variant=promotion_variant,
        output_dir=output_dir,
        output_format=fmt,
    )
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
        images=ImageBundle(
            meetup_image=meetup_path,
            meetup_diamond_image=meetup_diamond_path,
            speaker_images=speaker_paths,
            promotions=promotions,
        ),
        social=social,
        slides=slides,
        animations=animations,
    )
