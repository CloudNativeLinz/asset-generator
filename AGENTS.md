# AGENTS.md

Guidance for coding agents working in this repository.

## Scope

This is a Python project for event image, social copy, slide deck, and animation generation.

Main code locations:
- `src/imagegen/` for CLI and rendering logic
- `src/imagegen/web/` for preview UI
- `src/imagegen/google_slides.py` and `src/imagegen/github_publish.py` for external integrations
- `assets/templates/` for image and slide templates
- `tests/` for automated checks

## Working rules

- Prefer minimal, targeted edits.
- Preserve public CLI behavior unless change is requested.
- Avoid introducing new dependencies unless necessary.
- Keep code compatible with Black and Ruff defaults configured in `pyproject.toml`.
- Keep changed Python code typed where practical and lines within 100 characters.
- Prefer an existing Make target over spelling out its underlying `pip`, `imagegen`, Ruff, Black,
  or pytest command. Run `make help` to discover supported workflows.

## Verification

Run the smallest relevant checks first, then broader checks if needed:
- `make lint`
- `make test`

For formatting changes:
- `make format`

Current generation entry points:
- `make generate EVENT_ID=44` for one image
- `make generate-bundle EVENT_ID=44` for images, social copy, and slides
- `make generate-slides EVENT_ID=44` for a deck only
- `make generate-google-slides EVENT_ID=44` to populate the configured presentation
- `make generate-animations EVENT_ID=44 PRESET=speaker-spotlight` for animation only
- `make run EVENT_ID=44` for the preview studio (`make web` is an alias)
- `make azure-deploy` to deploy the preview app to Azure Container Apps

## Data and assets

- Treat `assets/` and `artifacts/` as important directories; avoid destructive changes.
- Do not edit generated output under `artifacts/` unless the task explicitly requires it.
- Keep template and renderer changes synchronized.
- When output schemas change (for example social JSON, slides, or animations), update tests and
  docs.
- Never read, print, or commit service-account JSON files, API keys, or access tokens. Use
  environment variables for credentials and mocks in tests.
