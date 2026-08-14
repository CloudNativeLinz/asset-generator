from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from .animate import ANIMATION_PRESETS, generate_animations
from .bundle import generate_event_bundle
from .google_slides import (
    DEFAULT_GOOGLE_SLIDES_TEMPLATE,
    GoogleSlidesError,
    generate_google_slides,
    google_configuration_value,
)
from .loader import find_event, load_events, load_template
from .renderer import render_event
from .slides import generate_slide_deck
from .web.app import create_app

app = typer.Typer(help="Template-driven event image generator")
ANIMATION_PRESETS_TEXT = ", ".join(ANIMATION_PRESETS)


def _save_rendered_image(
    template_path: str,
    events_file: str,
    output_dir: str,
    event_id: int,
    width: int | None,
    output_format: str,
) -> Path:
    template = load_template(template_path)
    event = find_event(load_events(events_file), event_id)
    rendered = render_event(
        template=template, event=event, width=width, output_format=output_format
    )

    ext = output_format.lower()
    if width and width > 0:
        output_name = f"{event.id}-{width}.{ext}"
    else:
        output_name = f"{event.id}.{ext}"

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    destination = output_path / output_name
    pil_format = "JPEG" if ext == "jpg" else "PNG"
    rendered.save(destination, format=pil_format, quality=95)
    return destination


@app.command("generate")
def generate(
    template: str = typer.Option(..., help="Path to YAML template"),
    id: int | None = typer.Option(None, "--id", help="Single event ID to render"),
    file: str = typer.Option("_data/events.yml", "--file", help="Path to events YAML"),
    out: str = typer.Option("artifacts", "--out", help="Output directory"),
    width: int | None = typer.Option(None, "--width", help="Optional output width"),
    format: str = typer.Option("jpg", "--format", help="Output format: jpg or png"),
) -> None:
    fmt = format.lower()
    if fmt not in {"jpg", "png"}:
        raise typer.BadParameter("--format must be jpg or png")

    events = load_events(file)
    selected = [find_event(events, id)] if id is not None else events

    for event in selected:
        result = _save_rendered_image(
            template_path=template,
            events_file=file,
            output_dir=out,
            event_id=event.id,
            width=width,
            output_format=fmt,
        )
        typer.echo(f"Rendered {result}")


@app.command("list-events")
def list_events(
    file: str = typer.Option("_data/events.yml", "--file", help="Path to events YAML")
) -> None:
    events = load_events(file)
    for event in events:
        typer.echo(f"{event.id}\t{event.date}\t{event.title}")


@app.command("preview")
def preview(
    template: str = typer.Option(..., help="Path to YAML template"),
    id: int | None = typer.Option(None, "--id", help="Initial selected event ID"),
    file: str = typer.Option("_data/events.yml", "--file", help="Path to events YAML"),
    host: str = typer.Option("0.0.0.0", "--host", help="Preview server host"),
    port: int = typer.Option(8000, "--port", help="Preview server port"),
) -> None:
    app_instance = create_app(template_path=template, events_file=file, initial_event_id=id)
    uvicorn.run(app_instance, host=host, port=port)


@app.command("generate-bundle")
def generate_bundle(
    template: str = typer.Option(..., help="Path to meetup YAML template"),
    speaker_template: str = typer.Option(
        "assets/templates/speaker.yaml",
        "--speaker-template",
        help="Path to speaker YAML template",
    ),
    id: int | None = typer.Option(None, "--id", help="Single event ID to render"),
    file: str = typer.Option("_data/events.yml", "--file", help="Path to events YAML"),
    out: str = typer.Option("artifacts", "--out", help="Output directory"),
    width: int | None = typer.Option(None, "--width", help="Optional output width"),
    format: str = typer.Option("jpg", "--format", help="Output format: jpg or png"),
    no_social: bool = typer.Option(False, "--no-social", help="Skip social copy generation"),
    no_slides: bool = typer.Option(False, "--no-slides", help="Skip slide deck generation"),
    animations: Annotated[
        list[str] | None,
        typer.Option(
            "--animation",
            help=f"Animation preset to include ({ANIMATION_PRESETS_TEXT}); repeatable",
        ),
    ] = None,
) -> None:
    fmt = format.lower()
    if fmt not in {"jpg", "png"}:
        raise typer.BadParameter("--format must be jpg or png")

    selected_animations = list(animations or [])

    for preset in selected_animations:
        if preset not in ANIMATION_PRESETS:
            raise typer.BadParameter(f"--animation must be one of {', '.join(ANIMATION_PRESETS)}")

    events = load_events(file)
    selected = [find_event(events, id)] if id is not None else events

    for event in selected:
        bundle = generate_event_bundle(
            event,
            meetup_template_path=template,
            speaker_template_path=speaker_template,
            output_dir=out,
            width=width,
            output_format=fmt,
            include_social=not no_social,
            include_slides=not no_slides,
            animation_presets=selected_animations,
        )
        typer.echo(f"Bundle ready at {bundle.output_dir}")


@app.command("generate-slides")
def generate_slides(
    id: int | None = typer.Option(None, "--id", help="Single event ID to render"),
    file: str = typer.Option("_data/events.yml", "--file", help="Path to events YAML"),
    out: str = typer.Option("artifacts", "--out", help="Output directory"),
    width: int | None = typer.Option(None, "--width", help="Optional output width"),
) -> None:
    events = load_events(file)
    selected = [find_event(events, id)] if id is not None else events

    for event in selected:
        deck = generate_slide_deck(event, output_dir=out, width=width)
        typer.echo(f"Deck ready: {deck.pdf} ({len(deck.slides)} slides)")


@app.command("generate-google-slides")
def generate_google_slides_command(
    template: str = typer.Option(
        "",
        "--template",
        help="Google Slides template URL or file ID",
    ),
    id: int | None = typer.Option(None, "--id", help="Single event ID to render"),
    file: str = typer.Option("_data/events.yml", "--file", help="Path to events YAML"),
    out: str = typer.Option("artifacts", "--out", help="Output directory"),
) -> None:
    resolved_template = (
        template.strip()
        or google_configuration_value("GOOGLE_SLIDES_TEMPLATE_ID")
        or DEFAULT_GOOGLE_SLIDES_TEMPLATE
    )

    events = load_events(file)
    selected = [find_event(events, id)] if id is not None else events
    for event in selected:
        try:
            deck = generate_google_slides(
                event,
                template=resolved_template,
                output_dir=out,
                folder_id=google_configuration_value("GOOGLE_DRIVE_FOLDER_ID") or None,
            )
        except GoogleSlidesError as exc:
            raise typer.ClickException(str(exc)) from exc
        typer.echo(f"Google Slides ready: {deck.url}")


@app.command("generate-animations")
def generate_animations_command(
    id: int | None = typer.Option(None, "--id", help="Single event ID to render"),
    file: str = typer.Option("_data/events.yml", "--file", help="Path to events YAML"),
    out: str = typer.Option("artifacts", "--out", help="Output directory"),
    width: int | None = typer.Option(None, "--width", help="Optional output width"),
    preset: str = typer.Option(
        "speaker-spotlight",
        "--preset",
        help=f"Animation preset ({', '.join(ANIMATION_PRESETS)})",
    ),
    fps: int = typer.Option(12, "--fps", help="Frames per second"),
    no_mp4: bool = typer.Option(False, "--no-mp4", help="Only emit GIF output"),
) -> None:
    if preset not in ANIMATION_PRESETS:
        raise typer.BadParameter(f"--preset must be one of {', '.join(ANIMATION_PRESETS)}")

    events = load_events(file)
    selected = [find_event(events, id)] if id is not None else events

    for event in selected:
        bundle = generate_animations(
            event,
            preset=preset,
            output_dir=out,
            width=width,
            fps=fps,
            prefer_mp4=not no_mp4,
        )
        for clip in bundle.clips:
            typer.echo(f"Animation {clip.name}: mp4={clip.mp4 or '-'} gif={clip.gif or '-'}")


if __name__ == "__main__":
    app()
