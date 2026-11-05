from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from .config import Event
from .loader import load_event_data, resolve_event_images
from .promotions import render_promotion


@dataclass
class WebsiteImagesResult:
    generated: list[int] = field(default_factory=list)
    skipped: dict[int, str] = field(default_factory=dict)


def _normalized_data(raw: Any, canonical: Any) -> Any:
    if isinstance(raw, dict) and isinstance(canonical, dict):
        return {
            **raw,
            **{key: _normalized_data(raw.get(key), value) for key, value in canonical.items()},
        }
    if isinstance(raw, list) and isinstance(canonical, list):
        return [_normalized_data(item, value) for item, value in zip(raw, canonical)]
    return canonical


def _events_by_id(events_file: str) -> dict[int, dict[str, Any]]:
    events: dict[int, dict[str, Any]] = {}
    for raw in load_event_data(events_file, allow_remote=False):
        event = Event.model_validate(raw)
        if event.id in events:
            raise ValueError(f"Duplicate event id={event.id} in {events_file}")
        # Include website-only metadata alongside canonical model fields in comparisons.
        normalized = _normalized_data(raw, event.model_dump(mode="json"))
        normalized.pop("doors_open", None)
        events[event.id] = normalized
    return events


def generate_website_images(
    events_file: str,
    out_dir: str,
    *,
    base_events_file: str | None = None,
    site_root: str | None = None,
    today: date | None = None,
    event_ids: list[int] | None = None,
) -> WebsiteImagesResult:
    current = _events_by_id(events_file)
    requested = set(event_ids or [])
    unknown = requested - current.keys()
    if unknown:
        raise ValueError("Unknown --event-id: " + ", ".join(map(str, sorted(unknown))))
    base = _events_by_id(base_events_file) if base_events_file and not requested else {}
    cutoff = today if today is not None else date.today()
    result = WebsiteImagesResult()

    for event_id, raw in current.items():
        if requested and event_id not in requested:
            result.skipped[event_id] = "not requested"
            continue
        if not raw["generate_images"]:
            result.skipped[event_id] = "generate_images: false"
            continue
        event_date = raw.get("date")
        if event_date:
            try:
                parsed_date = date.fromisoformat(event_date)
            except ValueError as exc:
                raise ValueError(
                    f"Event id={event_id} has invalid date {event_date!r}; expected YYYY-MM-DD"
                ) from exc
            if parsed_date < cutoff:
                result.skipped[event_id] = "past event"
                continue
        if not requested and base.get(event_id) == raw:
            result.skipped[event_id] = "unchanged"
            continue

        event = Event.model_validate(resolve_event_images([raw], site_root)[0])
        destination = Path(out_dir)
        destination.mkdir(parents=True, exist_ok=True)
        for preset, suffix in (("meetup-website", ""), ("teaser", "-teaser")):
            image = render_promotion(event, preset, variant="auto", output_format="jpg")
            image.save(destination / f"{event_id}{suffix}.jpg", format="JPEG", quality=95)
        result.generated.append(event_id)

    return result
