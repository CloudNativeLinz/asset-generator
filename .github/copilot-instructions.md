# Copilot Instructions for imagegen

## Project context

This repository is a Python 3.11+ project that generates event graphics, social copy, PDF slide
decks, and optional GIF/MP4 animations.

Core areas:
- CLI and domain logic: `src/imagegen/`
- Web preview UI: `src/imagegen/web/`
- Templates and assets: `assets/`
- Input data: `_data/`
- Output artifacts: `artifacts/`
- Tests: `tests/`

Primary libraries in use:
- Pillow, PyYAML, Pydantic, Requests, Typer/Click, FastAPI/Uvicorn, Jinja2
- Optional animations: ImageIO, imageio-ffmpeg, NumPy

## How to work in this repo

Before proposing large refactors, prefer incremental changes that preserve existing CLI and Make
target behavior. Use Make targets for standard repository tasks; invoke `imagegen` directly only
when no Make target exposes the needed option.

Use these commands:
- Install dev deps: `make install-dev`
- Install dev and animation deps: `make install-animations`
- Lint: `make lint`
- Format: `make format`
- Test: `make test`
- Preview app: `make run EVENT_ID=44`
- Generate one image: `make generate EVENT_ID=44`
- Generate a full bundle: `make generate-bundle EVENT_ID=44`
- Generate slides: `make generate-slides EVENT_ID=44`
- Generate animations: `make generate-animations EVENT_ID=44 PRESET=speaker-spotlight`

Run `make help` before writing out a manual command sequence. Common behavior is controlled with
Make variables including `EVENT_ID`, `EVENTS_FILE`, `OUT_DIR`, `TEMPLATE`, `WIDTH`, `FORMAT`,
`PRESET`, `FPS`, and `ANIMATIONS`.

## Coding expectations

- Keep line length compatible with Black and Ruff (100 chars).
- Maintain clear type hints for new or changed Python code where practical.
- Avoid introducing new dependencies unless clearly justified.
- Prefer small, composable functions over large monolithic blocks.
- Preserve public CLI commands and options unless explicitly asked to change them.

## Testing expectations

When behavior changes, update or add tests under `tests/`.

Focus tests on:
- YAML/data loading and validation
- Rendering behavior and edge cases
- Social copy generation fallbacks
- Bundle output structure
- Slide ordering and output structure
- Animation presets and optional MP4 fallback behavior

## Safety and file handling

- Treat `assets/` and `artifacts/` as potentially large/binary-heavy directories.
- Do not remove or rename template keys without checking renderer/template compatibility.
- Keep generated files deterministic where possible to reduce noisy diffs.
