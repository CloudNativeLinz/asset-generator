from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
import yaml

from .config import Event, Template

EVENTS_URL = "https://raw.githubusercontent.com/CloudNativeLinz/cloudnativelinz.github.io/refs/heads/main/_data/events.yml"
SPEAKER_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".avif")
SPEAKER_IMAGES_DIR = Path("assets/speaker-images")


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


def _find_local_speaker_image(event_id: int, talk_index: int) -> str | None:
    directory = SPEAKER_IMAGES_DIR
    for extension in SPEAKER_IMAGE_EXTENSIONS:
        candidate = directory / f"{event_id}-{talk_index}{extension}"
        if candidate.exists() and candidate.is_file():
            return f"/{candidate.as_posix()}"
    return None


def _speaker_image_extension(url: str, content_type: str | None) -> str:
    content_type_map = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/avif": ".avif",
    }

    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime in content_type_map:
        return content_type_map[mime]

    url_suffix = Path(urlparse(url).path).suffix.lower()
    if url_suffix in SPEAKER_IMAGE_EXTENSIONS:
        return url_suffix

    return ".jpg"


def _download_speaker_image(url: str, event_id: int, talk_index: int) -> str | None:
    try:
        response = requests.get(url, timeout=20)
    except requests.RequestException:
        return None

    if response.status_code != 200 or not response.content:
        return None

    extension = _speaker_image_extension(url, response.headers.get("content-type"))
    SPEAKER_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    destination = SPEAKER_IMAGES_DIR / f"{event_id}-{talk_index}{extension}"

    try:
        destination.write_bytes(response.content)
    except OSError:
        return None

    return f"/{destination.as_posix()}"


def _apply_speaker_image_fallbacks(raw_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for event in raw_events:
        event_id = event.get("id")
        if not isinstance(event_id, int):
            continue

        talks = event.get("talks")
        if not isinstance(talks, list):
            continue

        for index, talk in enumerate(talks, start=1):
            if not isinstance(talk, dict):
                continue

            image = str(talk.get("image") or "").strip()
            fallback = _find_local_speaker_image(event_id, index)

            if image.startswith(("http://", "https://")):
                if fallback is None:
                    fallback = _download_speaker_image(image, event_id, index)
                if fallback is not None:
                    talk["image"] = fallback
                continue

            if not fallback:
                continue

            if image.startswith("/assets/speaker-images/"):
                referenced = Path(image.lstrip("/"))
                if not referenced.exists() or referenced.is_dir():
                    talk["image"] = fallback

    return raw_events


def _normalize_null_fields(raw_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for event in raw_events:
        if not isinstance(event, dict):
            continue

        item = dict(event)
        if item.get("host") is None:
            item["host"] = ""
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

    normalized = _normalize_null_fields(_apply_speaker_image_fallbacks(raw))
    events = [Event.model_validate(item) for item in normalized]
    return sorted(events, key=lambda event: event.id, reverse=True)


def find_event(events: list[Event], event_id: int) -> Event:
    for event in events:
        if event.id == event_id:
            return event
    raise ValueError(f"Event with id={event_id} not found")
