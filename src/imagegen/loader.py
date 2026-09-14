from __future__ import annotations

from pathlib import Path
from typing import Any

import requests
import yaml

from .config import Event, Template

EVENTS_URL = "https://raw.githubusercontent.com/CloudNativeLinz/cloudnativelinz.github.io/refs/heads/main/_data/events.yml"
SPEAKER_IMAGES_URL = (
    "https://raw.githubusercontent.com/CloudNativeLinz/"
    "cloudnativelinz.github.io/refs/heads/main/images/speakers"
)


def _safe_yaml_load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or []


def load_template(template_path: str) -> Template:
    path = Path(template_path)
    raw = _safe_yaml_load(path)
    return Template.model_validate(raw)


def _fetch_remote_events() -> list[dict[str, Any]]:
    response = requests.get(EVENTS_URL, timeout=15)
    response.raise_for_status()
    parsed = yaml.safe_load(response.text) or []
    if not isinstance(parsed, list):
        raise TypeError("Remote events payload is not a list")
    return parsed


def _resolve_speaker_image_urls(raw_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for event in raw_events:
        talks = event.get("talks")
        if not isinstance(talks, list):
            continue

        for talk in talks:
            if not isinstance(talk, dict):
                continue

            image = str(talk.get("image") or "").strip()
            for prefix in ("/assets/speaker-images/", "/images/speakers/"):
                if image.startswith(prefix):
                    talk["image"] = f"{SPEAKER_IMAGES_URL}/{image.removeprefix(prefix)}"
                    break

    return raw_events


def _normalize_null_fields(raw_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for event in raw_events:
        if not isinstance(event, dict):
            continue

        item = dict(event)
        if item.get("time") is None:
            item["time"] = item.get("doors_open") or ""

        for field in ("host", "venue", "address"):
            if item.get(field) is None:
                item[field] = ""
        normalized.append(item)

    return normalized


def load_events(events_file: str = "_data/events.yml") -> list[Event]:
    path = Path(events_file)
    raw: list[dict[str, Any]]

    if path.exists():
        loaded = _safe_yaml_load(path)
        raw = loaded if isinstance(loaded, list) else []
    else:
        raw = []

    if not raw:
        raw = _fetch_remote_events()

    normalized = _normalize_null_fields(_resolve_speaker_image_urls(raw))
    events = [Event.model_validate(item) for item in normalized]
    return sorted(events, key=lambda event: event.id, reverse=True)


def find_event(events: list[Event], event_id: int) -> Event:
    for event in events:
        if event.id == event_id:
            return event
    raise ValueError(f"Event with id={event_id} not found")
