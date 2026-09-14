from __future__ import annotations

from pathlib import Path

from PIL import Image

from .config import AnimationBundle, AnimationClip, Event
from .loader import load_template
from .renderer import render_event

ANIMATION_PRESETS = ("speaker-spotlight", "event-teaser")

SPEAKER_SLIDE_TEMPLATE = "assets/templates/slide-speaker.yaml"
TEASER_SLIDE_TEMPLATES = (
    "assets/templates/slide-title.yaml",
    "assets/templates/slide-agenda.yaml",
    "assets/templates/slide-cta.yaml",
)

DEFAULT_FRAMES = 24
DEFAULT_FPS = 12


def _render_frame(
    template_path: str, event: Event, width: int | None, extra_context: dict | None = None
) -> Image.Image:
    template = load_template(template_path)
    rendered = render_event(
        template=template,
        event=event,
        width=width,
        output_format="png",
        extra_context=extra_context,
    )
    return rendered.convert("RGB")


def _ken_burns_frames(
    base: Image.Image,
    num_frames: int = DEFAULT_FRAMES,
    zoom_start: float = 1.0,
    zoom_end: float = 1.08,
) -> list[Image.Image]:
    width, height = base.size
    frames: list[Image.Image] = []
    span = max(num_frames - 1, 1)

    for index in range(num_frames):
        progress = index / span
        zoom = zoom_start + (zoom_end - zoom_start) * progress
        crop_w = int(width / zoom)
        crop_h = int(height / zoom)

        left = (width - crop_w) // 2
        top = int((height - crop_h) * progress)

        frame = base.crop((left, top, left + crop_w, top + crop_h))
        if frame.size != (width, height):
            frame = frame.resize((width, height), resample=Image.Resampling.LANCZOS)
        frames.append(frame)

    return frames


def _save_gif(frames: list[Image.Image], destination: Path, fps: int) -> str:
    duration_ms = int(1000 / max(fps, 1))
    destination.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        destination,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=duration_ms,
        loop=0,
        optimize=True,
    )
    return destination.as_posix()


def _save_mp4(frames: list[Image.Image], destination: Path, fps: int) -> str | None:
    try:
        import imageio.v2 as imageio
    except ImportError:
        return None

    try:
        import numpy as np
    except ImportError:
        return None

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with imageio.get_writer(destination, fps=fps, codec="libx264", quality=8) as writer:
            for frame in frames:
                writer.append_data(np.asarray(frame))
    except (OSError, RuntimeError, ValueError):
        return None

    return destination.as_posix() if destination.exists() else None


def _export_clip(
    frames: list[Image.Image],
    event_dir: Path,
    name: str,
    *,
    fps: int,
    prefer_mp4: bool,
) -> AnimationClip:
    gif_path = _save_gif(frames, event_dir / f"{name}.gif", fps)
    mp4_path = _save_mp4(frames, event_dir / f"{name}.mp4", fps) if prefer_mp4 else None
    return AnimationClip(name=name, mp4=mp4_path, gif=gif_path)


def _speaker_spotlight(
    event: Event, event_dir: Path, width: int | None, fps: int, prefer_mp4: bool
) -> list[AnimationClip]:
    clips: list[AnimationClip] = []
    for index in range(len(event.talks)):
        base = _render_frame(SPEAKER_SLIDE_TEMPLATE, event, width, {"talk_index": index})
        frames = _ken_burns_frames(base)
        clips.append(
            _export_clip(
                frames,
                event_dir,
                f"{event.id}-speaker-spotlight-{index + 1}",
                fps=fps,
                prefer_mp4=prefer_mp4,
            )
        )
    return clips


def _event_teaser(
    event: Event, event_dir: Path, width: int | None, fps: int, prefer_mp4: bool
) -> list[AnimationClip]:
    frames: list[Image.Image] = []
    for template_path in TEASER_SLIDE_TEMPLATES:
        base = _render_frame(template_path, event, width)
        frames.extend(_ken_burns_frames(base, num_frames=DEFAULT_FRAMES // 2, zoom_end=1.05))
    clip = _export_clip(
        frames, event_dir, f"{event.id}-event-teaser", fps=fps, prefer_mp4=prefer_mp4
    )
    return [clip]


def generate_animations(
    event: Event,
    *,
    preset: str = "speaker-spotlight",
    output_dir: str = "artifacts",
    width: int | None = None,
    fps: int = DEFAULT_FPS,
    prefer_mp4: bool = True,
) -> AnimationBundle:
    if preset not in ANIMATION_PRESETS:
        raise ValueError(f"preset must be one of {', '.join(ANIMATION_PRESETS)}")

    event_dir = Path(output_dir) / str(event.id) / "animations"
    event_dir.mkdir(parents=True, exist_ok=True)

    if preset == "speaker-spotlight":
        clips = _speaker_spotlight(event, event_dir, width, fps, prefer_mp4)
    else:
        clips = _event_teaser(event, event_dir, width, fps, prefer_mp4)

    return AnimationBundle(preset=preset, clips=clips)
