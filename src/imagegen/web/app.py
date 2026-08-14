from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from ..bundle import generate_event_bundle
from ..config import CTAVariants
from ..google_slides import (
    GoogleSlidesError,
    generate_google_slides,
    google_configuration_value,
)
from ..loader import find_event, load_events, load_template
from ..renderer import render_event
from ..slides import generate_slide_deck
from ..social import generate_social_bundle


class BundleRequest(BaseModel):
    id: int
    template: str | None = None
    speaker_template: str = "assets/templates/speaker.yaml"
    width: int | None = None
    format: str | None = None
    out: str = "artifacts"
    include_social: bool = True
    include_slides: bool = True
    animation_presets: list[str] = Field(default_factory=list)


class SlidesRequest(BaseModel):
    id: int
    width: int | None = None
    out: str = "artifacts"


class RegenerateRequest(BaseModel):
    id: int
    kind: str
    talk_index: int | None = None


class SocialRequest(BaseModel):
    id: int


class GoogleSlidesRequest(BaseModel):
    id: int
    out: str = "artifacts"


class SaveSocialRequest(BaseModel):
    id: int
    social: dict
    out: str = "artifacts"


class StudioSettings(BaseModel):
    cta_register: str = "Reserve your spot today."
    cta_attend: str = "Join us at the meetup and bring your questions."
    cta_recap: str = "Follow for recap highlights after the event."
    width: int | None = Field(default=None, ge=320)
    image_format: Literal["jpg", "png"] = "jpg"
    google_slides_template: str = ""


def _default_settings() -> StudioSettings:
    return StudioSettings()


def _load_settings(path: Path) -> StudioSettings:
    if not path.exists() or not path.is_file():
        return _default_settings()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return _default_settings()

    try:
        return StudioSettings.model_validate(payload)
    except ValidationError:
        return _default_settings()


def _save_settings(path: Path, settings: StudioSettings) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(settings.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _settings_cta_defaults(settings: StudioSettings) -> CTAVariants:
    return CTAVariants(
        register_cta=settings.cta_register,
        attend=settings.cta_attend,
        recap=settings.cta_recap,
    )


def _event_summary(event) -> dict:
    return {
        "id": event.id,
        "title": event.title,
        "date": str(event.date or ""),
        "host": event.host,
        "talk_count": len(event.talks),
    }


def _artifact_url(path_text: str) -> str:
    cleaned = path_text.replace("\\", "/")
    marker = "artifacts/"
    idx = cleaned.find(marker)
    if idx >= 0:
        return "/" + cleaned[idx:]
    return "/" + Path(cleaned).name


def _read_json_file(path: Path) -> dict | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None


def _bundle_snapshot(event_id: int, out_dir: str = "artifacts") -> dict:
    event_dir = Path(out_dir) / str(event_id)
    images: list[dict] = []

    if event_dir.exists() and event_dir.is_dir():
        for item in sorted(event_dir.iterdir()):
            if item.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                continue
            images.append({"name": item.name, "url": _artifact_url(item.as_posix())})

    social = _read_json_file(event_dir / "social-edited.json")
    if social is None:
        social = _read_json_file(event_dir / "social.json")

    return {
        "event_id": event_id,
        "output_dir": event_dir.as_posix(),
        "images": images,
        "slides": _slides_snapshot(event_dir),
        "google_slides": _read_json_file(event_dir / "google-slides.json"),
        "animations": _animations_snapshot(event_dir),
        "social": social,
    }


def _slides_snapshot(event_dir: Path) -> dict:
    pdf_path = event_dir / "slides.pdf"
    slides_dir = event_dir / "slides"
    pages: list[dict] = []

    if slides_dir.exists() and slides_dir.is_dir():
        for item in sorted(slides_dir.iterdir()):
            if item.suffix.lower() != ".png":
                continue
            pages.append({"name": item.name, "url": _artifact_url(item.as_posix())})

    return {
        "pdf": _artifact_url(pdf_path.as_posix()) if pdf_path.exists() else None,
        "pages": pages,
    }


def _animations_snapshot(event_dir: Path) -> list[dict]:
    animations_dir = event_dir / "animations"
    clips: list[dict] = []

    if animations_dir.exists() and animations_dir.is_dir():
        for item in sorted(animations_dir.iterdir()):
            if item.suffix.lower() not in {".mp4", ".gif"}:
                continue
            clips.append({"name": item.name, "url": _artifact_url(item.as_posix())})

    return clips


def create_app(
    template_path: str, events_file: str, initial_event_id: int | None = None
) -> FastAPI:
    app = FastAPI(
        title="imagegen social studio",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    artifacts_dir = Path("artifacts")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    settings_file = artifacts_dir / "studio-settings.json"
    app.mount("/artifacts", StaticFiles(directory=str(artifacts_dir)), name="artifacts")

    templates_dir = Path(__file__).parent / "templates"
    templates = Jinja2Templates(directory=str(templates_dir))

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        events = load_events(events_file)
        selected = initial_event_id or (events[0].id if events else None)
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "events": events,
                "template": template_path,
                "speaker_template": "assets/templates/speaker.yaml",
                "selected": selected,
                "events_file": events_file,
            },
        )

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request) -> HTMLResponse:
        settings = _load_settings(settings_file)
        return templates.TemplateResponse(
            request=request,
            name="settings.html",
            context={
                "settings": settings.model_dump(),
            },
        )

    @app.get("/api/settings")
    async def get_settings_api() -> JSONResponse:
        settings = _load_settings(settings_file)
        return JSONResponse({"settings": settings.model_dump()})

    @app.post("/api/settings")
    async def save_settings_api(payload: StudioSettings) -> JSONResponse:
        _save_settings(settings_file, payload)
        return JSONResponse({"saved": True, "settings": payload.model_dump()})

    @app.get("/api/events")
    async def list_events_api() -> JSONResponse:
        events = load_events(events_file)
        return JSONResponse({"events": [_event_summary(event) for event in events]})

    @app.get("/api/events/{event_id}")
    async def event_details_api(event_id: int) -> JSONResponse:
        events = load_events(events_file)
        event = find_event(events, event_id)
        return JSONResponse(event.model_dump())

    @app.get("/api/bundle/{event_id}")
    async def bundle_snapshot_api(
        event_id: int, out: str = Query(default="artifacts")
    ) -> JSONResponse:
        return JSONResponse(_bundle_snapshot(event_id, out_dir=out))

    @app.get("/render")
    async def render(
        id: int = Query(..., description="Event ID"),
        template: str = Query(default=template_path),
        width: int | None = Query(default=None),
        format: str = Query(default="png"),
    ) -> StreamingResponse:
        fmt = format.lower()
        if fmt not in {"png", "jpg"}:
            raise HTTPException(status_code=400, detail="format must be png or jpg")

        events = load_events(events_file)
        event = find_event(events, id)
        template_obj = load_template(template)
        rendered = render_event(template_obj, event, width=width, output_format=fmt)

        from io import BytesIO

        buffer = BytesIO()
        pil_format = "JPEG" if fmt == "jpg" else "PNG"
        rendered.save(buffer, format=pil_format, quality=95)
        buffer.seek(0)
        media = "image/png" if fmt == "png" else "image/jpeg"
        return StreamingResponse(buffer, media_type=media)

    @app.post("/api/generate-bundle")
    async def generate_bundle_api(payload: BundleRequest) -> JSONResponse:
        settings = _load_settings(settings_file)
        fmt = (payload.format or settings.image_format).lower()
        if fmt not in {"png", "jpg"}:
            raise HTTPException(status_code=400, detail="format must be png or jpg")

        events = load_events(events_file)
        event = find_event(events, payload.id)
        bundle = generate_event_bundle(
            event,
            meetup_template_path=payload.template or template_path,
            speaker_template_path=payload.speaker_template,
            output_dir=payload.out,
            width=payload.width if payload.width is not None else settings.width,
            output_format=fmt,
            include_social=payload.include_social,
            include_slides=payload.include_slides,
            animation_presets=payload.animation_presets,
            cta_defaults=_settings_cta_defaults(settings),
        )
        response = bundle.model_dump(by_alias=True)
        response["snapshot"] = _bundle_snapshot(event.id, out_dir=payload.out)
        return JSONResponse(response)

    @app.post("/api/generate-slides")
    async def generate_slides_api(payload: SlidesRequest) -> JSONResponse:
        settings = _load_settings(settings_file)
        events = load_events(events_file)
        event = find_event(events, payload.id)
        deck = generate_slide_deck(
            event,
            output_dir=payload.out,
            width=payload.width if payload.width is not None else settings.width,
        )
        return JSONResponse(
            {
                "event_id": event.id,
                "slides": deck.model_dump(),
                "snapshot": _bundle_snapshot(event.id, out_dir=payload.out),
            }
        )

    @app.post("/api/generate-google-slides")
    async def generate_google_slides_api(payload: GoogleSlidesRequest) -> JSONResponse:
        settings = _load_settings(settings_file)
        if not settings.google_slides_template.strip():
            raise HTTPException(
                status_code=400,
                detail="Configure a Google Slides template URL or ID in Studio Settings",
            )

        events = load_events(events_file)
        event = find_event(events, payload.id)
        try:
            deck = await run_in_threadpool(
                generate_google_slides,
                event,
                template=settings.google_slides_template,
                output_dir=payload.out,
                folder_id=google_configuration_value("GOOGLE_DRIVE_FOLDER_ID") or None,
            )
        except GoogleSlidesError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        return JSONResponse(
            {
                "event_id": event.id,
                "google_slides": deck.model_dump(),
                "snapshot": _bundle_snapshot(event.id, out_dir=payload.out),
            }
        )

    @app.post("/api/generate-social")
    async def generate_social_api(payload: SocialRequest) -> JSONResponse:
        events = load_events(events_file)
        event = find_event(events, payload.id)
        settings = _load_settings(settings_file)
        social = generate_social_bundle(event, cta_defaults=_settings_cta_defaults(settings))
        return JSONResponse(
            {
                "event_id": event.id,
                "social": social.model_dump(by_alias=True),
            }
        )

    @app.post("/api/generate-images")
    async def generate_images_api(payload: BundleRequest) -> JSONResponse:
        settings = _load_settings(settings_file)
        fmt = (payload.format or settings.image_format).lower()
        if fmt not in {"png", "jpg"}:
            raise HTTPException(status_code=400, detail="format must be png or jpg")

        events = load_events(events_file)
        event = find_event(events, payload.id)
        bundle = generate_event_bundle(
            event,
            meetup_template_path=payload.template or template_path,
            speaker_template_path=payload.speaker_template,
            output_dir=payload.out,
            width=payload.width if payload.width is not None else settings.width,
            output_format=fmt,
            include_social=False,
            include_slides=False,
        )
        return JSONResponse(
            {
                "event_id": event.id,
                "images": bundle.images.model_dump(),
                "snapshot": _bundle_snapshot(event.id, out_dir=payload.out),
            }
        )

    @app.post("/api/save-social")
    async def save_social_api(payload: SaveSocialRequest) -> JSONResponse:
        event_dir = Path(payload.out) / str(payload.id)
        event_dir.mkdir(parents=True, exist_ok=True)
        destination = event_dir / "social-edited.json"
        destination.write_text(
            json.dumps(payload.social, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return JSONResponse(
            {
                "saved": True,
                "path": destination.as_posix(),
                "snapshot": _bundle_snapshot(payload.id, out_dir=payload.out),
            }
        )

    @app.post("/api/regenerate-social")
    async def regenerate_social_api(payload: RegenerateRequest) -> JSONResponse:
        events = load_events(events_file)
        event = find_event(events, payload.id)
        settings = _load_settings(settings_file)
        social = generate_social_bundle(event, cta_defaults=_settings_cta_defaults(settings))

        kind = payload.kind.strip().lower()
        if kind == "meetup":
            return JSONResponse(
                {"kind": "meetup", "draft": social.meetup.model_dump(by_alias=True)}
            )

        if kind == "talk":
            if payload.talk_index is None:
                raise HTTPException(
                    status_code=400, detail="talk_index is required for talk regeneration"
                )
            if payload.talk_index < 0 or payload.talk_index >= len(social.talks):
                raise HTTPException(status_code=404, detail="talk_index out of range")
            return JSONResponse(
                {
                    "kind": "talk",
                    "draft": social.talks[payload.talk_index].model_dump(by_alias=True),
                }
            )

        raise HTTPException(status_code=400, detail="kind must be meetup or talk")

    return app
