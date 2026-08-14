from __future__ import annotations

import json
import re
import time
from os import getenv
from pathlib import Path
from typing import Any

import jwt
import requests

from .config import Event, GoogleSlideDeck

DRIVE_API = "https://www.googleapis.com/drive/v3"
SLIDES_API = "https://slides.googleapis.com/v1"
DEFAULT_GOOGLE_SLIDES_TEMPLATE = (
    "https://docs.google.com/presentation/d/" "1GPgXC7C3l5c3eJ8dR9TjjY7UDrqSrA3Tn5BmUWK6JQo/edit"
)
PRESENTATION_ID_PATTERN = re.compile(r"/presentation/d/([A-Za-z0-9_-]+)")
GOOGLE_API_SCOPES = (
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/presentations",
)


class GoogleSlidesError(RuntimeError):
    pass


class GoogleDriveStorageQuotaError(GoogleSlidesError):
    pass


def _dotenv_value(name: str, path: Path = Path(".env")) -> str:
    if not path.exists() or not path.is_file():
        return ""

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise GoogleSlidesError(f"Unable to read {path}: {exc}") from exc

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        if key.strip() != name:
            continue
        resolved = value.strip()
        if len(resolved) >= 2 and resolved[0] == resolved[-1] and resolved[0] in {'"', "'"}:
            resolved = resolved[1:-1]
        return resolved
    return ""


def google_configuration_value(name: str) -> str:
    return (getenv(name, "") or _dotenv_value(name)).strip()


def resolve_google_access_token(
    *,
    access_token: str | None = None,
    credentials_file: str | None = None,
) -> str:
    token = (access_token or "").strip()
    if token:
        return token

    key_path = (
        credentials_file or google_configuration_value("GOOGLE_APPLICATION_CREDENTIALS")
    ).strip()
    if not key_path:
        raise GoogleSlidesError("Set GOOGLE_APPLICATION_CREDENTIALS to a service-account JSON file")

    try:
        service_account = json.loads(Path(key_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise GoogleSlidesError(
            f"Unable to load Google service-account credentials: {exc}"
        ) from exc

    client_email = service_account.get("client_email")
    private_key = service_account.get("private_key")
    token_uri = service_account.get("token_uri", "https://oauth2.googleapis.com/token")
    if not isinstance(client_email, str) or not isinstance(private_key, str):
        raise GoogleSlidesError("Service-account credentials are missing email or private key")

    now = int(time.time())
    try:
        assertion = jwt.encode(
            {
                "iss": client_email,
                "scope": " ".join(GOOGLE_API_SCOPES),
                "aud": token_uri,
                "iat": now,
                "exp": now + 3600,
            },
            private_key,
            algorithm="RS256",
        )
        response = requests.post(
            token_uri,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
            timeout=30,
        )
    except (jwt.PyJWTError, requests.RequestException) as exc:
        raise GoogleSlidesError(f"Unable to authenticate with Google: {exc}") from exc

    if response.status_code >= 400:
        detail = response.text.strip()[:500]
        raise GoogleSlidesError(
            f"Google service-account authentication failed ({response.status_code}): {detail}"
        )
    try:
        token_payload = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        raise GoogleSlidesError("Google authentication returned a non-JSON response") from exc
    resolved_token = token_payload.get("access_token")
    if not isinstance(resolved_token, str) or not resolved_token:
        raise GoogleSlidesError("Google authentication returned no access token")
    return resolved_token


def extract_presentation_id(template: str) -> str:
    value = template.strip()
    match = PRESENTATION_ID_PATTERN.search(value)
    if match:
        return match.group(1)
    if value and "/" not in value and re.fullmatch(r"[A-Za-z0-9_-]+", value):
        return value
    raise GoogleSlidesError("Google Slides template must be a presentation URL or file ID")


def _text(value: object | None) -> str:
    return "" if value is None else str(value)


def event_replacements(event: Event) -> dict[str, str]:
    replacements = {
        "event.id": str(event.id),
        "event.title": event.title,
        "event.date": _text(event.date),
        "event.time": event.time,
        "event.venue": event.venue,
        "event.address": event.address,
        "event.host": event.host,
        "event.event_link": _text(event.event_link),
        "event.registrations": _text(event.registrations),
        "event.participants": _text(event.participants),
        "event.talk_count": str(len(event.talks)),
    }

    for index, talk in enumerate(event.talks, start=1):
        replacements[f"talks.{index}.title"] = talk.title
        replacements[f"talks.{index}.speaker"] = talk.speaker
        replacements[f"talks.{index}.social"] = _text(talk.social)

    for index, sponsor in enumerate(event.sponsors, start=1):
        replacements[f"sponsors.{index}.name"] = sponsor.name
        replacements[f"sponsors.{index}.tier"] = sponsor.tier

    return replacements


def _replace_text_requests(event: Event) -> list[dict[str, Any]]:
    requests_payload: list[dict[str, Any]] = []
    for key, value in event_replacements(event).items():
        for placeholder in (f"{{{{{key}}}}}", f"{{{{ {key} }}}}"):
            requests_payload.append(
                {
                    "replaceAllText": {
                        "containsText": {
                            "text": placeholder,
                            "matchCase": True,
                        },
                        "replaceText": value,
                    }
                }
            )
    return requests_payload


def agenda_items(event: Event) -> list[tuple[str, str]]:
    def talk_text(index: int) -> str:
        if index >= len(event.talks):
            return "Talk details to be announced"
        talk = event.talks[index]
        details = [part for part in (talk.title, talk.speaker) if part]
        return "\n".join(details) or "Talk details to be announced"

    return [
        ("18:00", "Opening"),
        ("18:10", talk_text(0)),
        ("18:55", "5-minute break"),
        ("19:00", talk_text(1)),
        ("19:45", "Raffle + networking"),
    ]


def _agenda_requests(event: Event, presentation: dict[str, Any]) -> list[dict[str, Any]]:
    existing_slides = presentation.get("slides", [])
    object_prefix = f"imagegenAgenda{event.id}"
    requests_payload: list[dict[str, Any]] = []

    if len(existing_slides) < 3:
        for insertion_index in range(len(existing_slides), 3):
            generated_slide_id = (
                f"{object_prefix}Slide"
                if insertion_index == 2
                else f"imagegenReserved{event.id}Slide{insertion_index + 1}"
            )
            requests_payload.append(
                {
                    "createSlide": {
                        "objectId": generated_slide_id,
                        "insertionIndex": insertion_index,
                        "slideLayoutReference": {"predefinedLayout": "BLANK"},
                    }
                }
            )
        slide_id = f"{object_prefix}Slide"
        agenda_slide: dict[str, Any] = {}
    else:
        agenda_slide = existing_slides[2]
        slide_id = agenda_slide.get("objectId")
        if not isinstance(slide_id, str) or not slide_id:
            raise GoogleSlidesError("Google Slides template slide 3 has no object ID")

    requests_payload.extend(
        [
            {"deleteObject": {"objectId": element["objectId"]}}
            for element in agenda_slide.get("pageElements", [])
            if isinstance(element.get("objectId"), str)
            and element["objectId"].startswith(object_prefix)
        ]
    )
    requests_payload.extend(
        [
            {
                "createShape": {
                    "objectId": f"{object_prefix}Title",
                    "shapeType": "TEXT_BOX",
                    "elementProperties": {
                        "pageObjectId": slide_id,
                        "size": {
                            "width": {"magnitude": 620, "unit": "PT"},
                            "height": {"magnitude": 42, "unit": "PT"},
                        },
                        "transform": {
                            "scaleX": 1,
                            "scaleY": 1,
                            "translateX": 50,
                            "translateY": 28,
                            "unit": "PT",
                        },
                    },
                }
            },
            {
                "insertText": {
                    "objectId": f"{object_prefix}Title",
                    "text": "Agenda",
                }
            },
            {
                "updateTextStyle": {
                    "objectId": f"{object_prefix}Title",
                    "style": {
                        "bold": True,
                        "fontSize": {"magnitude": 28, "unit": "PT"},
                    },
                    "textRange": {"type": "ALL"},
                    "fields": "bold,fontSize",
                }
            },
        ]
    )

    for index, (start_time, description) in enumerate(agenda_items(event), start=1):
        y_position = 82 + ((index - 1) * 60)
        time_id = f"{object_prefix}Time{index}"
        detail_id = f"{object_prefix}Detail{index}"
        requests_payload.extend(
            [
                {
                    "createShape": {
                        "objectId": time_id,
                        "shapeType": "TEXT_BOX",
                        "elementProperties": {
                            "pageObjectId": slide_id,
                            "size": {
                                "width": {"magnitude": 75, "unit": "PT"},
                                "height": {"magnitude": 45, "unit": "PT"},
                            },
                            "transform": {
                                "scaleX": 1,
                                "scaleY": 1,
                                "translateX": 55,
                                "translateY": y_position,
                                "unit": "PT",
                            },
                        },
                    }
                },
                {"insertText": {"objectId": time_id, "text": start_time}},
                {
                    "updateTextStyle": {
                        "objectId": time_id,
                        "style": {
                            "bold": True,
                            "fontSize": {"magnitude": 16, "unit": "PT"},
                        },
                        "textRange": {"type": "ALL"},
                        "fields": "bold,fontSize",
                    }
                },
                {
                    "createShape": {
                        "objectId": detail_id,
                        "shapeType": "TEXT_BOX",
                        "elementProperties": {
                            "pageObjectId": slide_id,
                            "size": {
                                "width": {"magnitude": 510, "unit": "PT"},
                                "height": {"magnitude": 50, "unit": "PT"},
                            },
                            "transform": {
                                "scaleX": 1,
                                "scaleY": 1,
                                "translateX": 145,
                                "translateY": y_position,
                                "unit": "PT",
                            },
                        },
                    }
                },
                {"insertText": {"objectId": detail_id, "text": description}},
                {
                    "updateTextStyle": {
                        "objectId": detail_id,
                        "style": {"fontSize": {"magnitude": 16, "unit": "PT"}},
                        "textRange": {"type": "ALL"},
                        "fields": "fontSize",
                    }
                },
            ]
        )
    return requests_payload


def _post_json(url: str, *, access_token: str, payload: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=45)
    except requests.RequestException as exc:
        raise GoogleSlidesError(f"Failed to reach Google APIs: {exc}") from exc

    if response.status_code >= 400:
        detail = response.text.strip()[:500]
        if "storageQuotaExceeded" in detail:
            raise GoogleDriveStorageQuotaError(
                "Google Drive rejected the copy because service accounts have no My Drive "
                "storage quota. Use a Shared Drive destination folder or domain-wide delegation."
            )
        raise GoogleSlidesError(f"Google API request failed ({response.status_code}): {detail}")

    try:
        body = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        raise GoogleSlidesError("Google API returned a non-JSON response") from exc
    if not isinstance(body, dict):
        raise GoogleSlidesError("Google API returned an invalid response")
    return body


def _get_presentation(presentation_id: str, access_token: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        response = requests.get(
            f"{SLIDES_API}/presentations/{presentation_id}",
            headers=headers,
            timeout=45,
        )
    except requests.RequestException as exc:
        raise GoogleSlidesError(f"Failed to read Google Slides presentation: {exc}") from exc
    if response.status_code >= 400:
        detail = response.text.strip()[:500]
        raise GoogleSlidesError(f"Google Slides request failed ({response.status_code}): {detail}")
    try:
        body = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        raise GoogleSlidesError("Google Slides returned a non-JSON response") from exc
    if not isinstance(body, dict):
        raise GoogleSlidesError("Google Slides returned an invalid response")
    return body


def _slide_count(presentation: dict[str, Any]) -> int:
    slides = presentation.get("slides", [])
    return len(slides) if isinstance(slides, list) else 0


def _find_existing_event_presentation(
    *,
    event_id: int,
    folder_id: str,
    access_token: str,
) -> dict[str, Any] | None:
    escaped_name = str(event_id).replace("'", "\\'")
    escaped_folder = folder_id.replace("'", "\\'")
    query = (
        f"name = '{escaped_name}' and '{escaped_folder}' in parents and "
        "mimeType = 'application/vnd.google-apps.presentation' and trashed = false"
    )
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        response = requests.get(
            f"{DRIVE_API}/files",
            headers=headers,
            params={
                "q": query,
                "fields": "files(id,name)",
                "pageSize": 2,
                "includeItemsFromAllDrives": "true",
                "supportsAllDrives": "true",
            },
            timeout=45,
        )
    except requests.RequestException as exc:
        raise GoogleSlidesError(f"Failed to search Google Drive: {exc}") from exc

    if response.status_code >= 400:
        detail = response.text.strip()[:500]
        raise GoogleSlidesError(f"Google Drive search failed ({response.status_code}): {detail}")
    try:
        files = response.json().get("files", [])
    except requests.exceptions.JSONDecodeError as exc:
        raise GoogleSlidesError("Google Drive search returned a non-JSON response") from exc
    return files[0] if files else None


def generate_google_slides(
    event: Event,
    *,
    template: str,
    access_token: str | None = None,
    credentials_file: str | None = None,
    output_dir: str = "artifacts",
    folder_id: str | None = None,
) -> GoogleSlideDeck:
    resolved_access_token = resolve_google_access_token(
        access_token=access_token,
        credentials_file=credentials_file,
    )

    template_id = extract_presentation_id(template)
    presentation_name = f"{event.title} - {_text(event.date) or event.id}"
    copy_payload: dict[str, Any] = {"name": presentation_name}
    if folder_id:
        copy_payload["parents"] = [folder_id]

    try:
        destination = _post_json(
            f"{DRIVE_API}/files/{template_id}/copy?supportsAllDrives=true",
            access_token=resolved_access_token,
            payload=copy_payload,
        )
    except GoogleDriveStorageQuotaError:
        if not folder_id:
            raise
        destination = _find_existing_event_presentation(
            event_id=event.id,
            folder_id=folder_id,
            access_token=resolved_access_token,
        )
        if destination is None:
            raise GoogleDriveStorageQuotaError(
                f"Cannot copy into this My Drive folder. Create a Google presentation named "
                f"'{event.id}' in the configured folder, or use a true Shared Drive folder."
            ) from None

    presentation_id = destination.get("id")
    if not isinstance(presentation_id, str) or not presentation_id:
        raise GoogleSlidesError("Google Drive copy response did not include a presentation ID")
    if presentation_id == template_id:
        raise GoogleSlidesError("Refusing to modify the Google Slides source template")
    resolved_name = destination.get("name")
    if isinstance(resolved_name, str) and resolved_name:
        presentation_name = resolved_name

    presentation = _get_presentation(presentation_id, resolved_access_token)
    if destination.get("name") == str(event.id):
        template_presentation = _get_presentation(template_id, resolved_access_token)
        if _slide_count(presentation) < _slide_count(template_presentation):
            raise GoogleDriveStorageQuotaError(
                f"The existing presentation '{event.id}' is not a complete copy of template "
                f"'{template_presentation.get('title', template_id)}'. In the configured My Drive "
                f"folder, make a copy of the template and name it '{event.id}', replacing the "
                "incomplete presentation, or configure a Shared Drive folder."
            )
    _post_json(
        f"{SLIDES_API}/presentations/{presentation_id}:batchUpdate",
        access_token=resolved_access_token,
        payload={
            "requests": [
                *_replace_text_requests(event),
                *_agenda_requests(event, presentation),
            ]
        },
    )

    deck = GoogleSlideDeck(
        event_id=event.id,
        presentation_id=presentation_id,
        name=presentation_name,
        url=f"https://docs.google.com/presentation/d/{presentation_id}/edit",
    )
    metadata_path = Path(output_dir) / str(event.id) / "google-slides.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(deck.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return deck
