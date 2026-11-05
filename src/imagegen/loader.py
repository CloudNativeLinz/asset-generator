from __future__ import annotations

from copy import deepcopy
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


def _resolve_website_image(source: Any, site_root: str | None) -> Any:
    image = str(source or "").strip()
    relative = image.removeprefix("/")
    if image.startswith("/assets/speaker-images/"):
        relative = "images/speakers/" + image.removeprefix("/assets/speaker-images/")

    if site_root and image.startswith(("/images/", "/assets/speaker-images/")):
        root = Path(site_root).resolve()
        candidate = (root / relative).resolve()
        if not candidate.is_relative_to(root):
            raise ValueError(f"Website image path escapes --site-root: {image}")
        if candidate.is_file():
            return str(candidate)

    if image.startswith(("/images/speakers/", "/assets/speaker-images/")):
        return f"{SPEAKER_IMAGES_URL}/{relative.removeprefix('images/speakers/')}"
    return source


def resolve_event_images(
    raw_events: list[dict[str, Any]], site_root: str | None = None
) -> list[dict[str, Any]]:
    raw_events = deepcopy(raw_events)
    for event in raw_events:
        if event.get("sponsor_logo"):
            event["sponsor_logo"] = _resolve_website_image(event["sponsor_logo"], site_root)
        for sponsor in event.get("sponsors") or []:
            if isinstance(sponsor, dict) and sponsor.get("logo"):
                sponsor["logo"] = _resolve_website_image(sponsor["logo"], site_root)
        talks = event.get("talks")
        if not isinstance(talks, list):
            continue

        for talk in talks:
            if not isinstance(talk, dict):
                continue

            if talk.get("image"):
                talk["image"] = _resolve_website_image(talk["image"], site_root)
            if isinstance(talk.get("images"), list):
                talk["images"] = [
                    _resolve_website_image(image, site_root) for image in talk["images"]
                ]

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


def load_event_data(
    events_file: str = "_data/events.yml", *, allow_remote: bool = True
) -> list[dict[str, Any]]:
    path = Path(events_file)
    raw: list[dict[str, Any]]

    if not allow_remote or path.exists():
        if allow_remote:
            loaded = _safe_yaml_load(path)
        else:
            with path.open("r", encoding="utf-8") as handle:
                loaded = yaml.safe_load(handle)
            if loaded is None:
                loaded = []
        if not allow_remote and not isinstance(loaded, list):
            raise ValueError(f"Events file must contain a YAML list: {path}")
        if not allow_remote and any(not isinstance(item, dict) for item in loaded):
            raise ValueError(f"Events file must contain event mappings: {path}")
        raw = loaded if isinstance(loaded, list) else []
    else:
        raw = []

    if not raw and allow_remote:
        raw = _fetch_remote_events()

    return _normalize_null_fields(raw)


def load_events(
    events_file: str = "_data/events.yml", *, site_root: str | None = None
) -> list[Event]:
    normalized = resolve_event_images(load_event_data(events_file), site_root)
    events = [Event.model_validate(item) for item in normalized]
    return sorted(events, key=lambda event: event.id, reverse=True)


def find_event(events: list[Event], event_id: int) -> Event:
    for event in events:
        if event.id == event_id:
            return event
    raise ValueError(f"Event with id={event_id} not found")
