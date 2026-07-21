# Image Generator

Template-driven event image renderer using Python, Pillow, and YAML templates.

## Quick Start

### Devcontainer

This repository is set up for VS Code Dev Containers and GitHub Codespaces.

1. Open the repo in VS Code.
2. Run "Dev Containers: Reopen in Container".
3. The post-create hook installs dependencies with `pip install -e .[dev]`.

### Local install

```bash
python -m pip install --upgrade pip
pip install -e .[dev]
```

## Commands

### Generate images

Render all events:

```bash
imagegen generate --template assets/templates/meetup.yaml
```

Render one event:

```bash
imagegen generate --template assets/templates/meetup.yaml --id 44
```

Render resized output:

```bash
imagegen generate --template assets/templates/meetup.yaml --width 550
```

Render from a specific event source:

```bash
imagegen generate --template assets/templates/meetup.yaml --file _data/sample-events.yml
```

Render PNG:

```bash
imagegen generate --template assets/templates/meetup.yaml --format png
```

### Generate full social bundle

Render meetup image, one speaker card per talk, and LinkedIn draft copy:

```bash
imagegen generate-bundle \
   --template assets/templates/meetup.yaml \
   --speaker-template assets/templates/speaker.yaml \
   --id 44
```

Output is written to `artifacts/<event-id>/` and includes:

- `meetup.jpg` or `meetup.png`
- `speaker-<n>.jpg` or `speaker-<n>.png`
- `social.json` (meetup + per-talk LinkedIn drafts)

If Azure OpenAI is configured, social copy uses the deployed model. Otherwise, rule-based fallback copy is generated.

Set environment variables for Azure OpenAI:

```bash
export AZURE_OPENAI_ENDPOINT="https://<resource>.openai.azure.com"
export AZURE_OPENAI_API_KEY="<api-key>"
export AZURE_OPENAI_DEPLOYMENT="<deployment-name>"
# optional
export AZURE_OPENAI_API_VERSION="2024-06-01"
```

### List events

```bash
imagegen list-events --file _data/events.yml
```

### Preview web UI

```bash
imagegen preview --template assets/templates/meetup.yaml --id 44
```

Preview runs on `http://localhost:8000` by default.

The web UI now supports:

- social-first studio workflow (event context, action board, drafts editor, assets panel)
- separate generation actions: social only, images only, or full bundle
- editable LinkedIn meetup and per-talk drafts with CTA fields
- regenerate actions for meetup and individual talk drafts
- save edited drafts to `artifacts/<event-id>/social-edited.json`
- load existing generated bundles from disk and preview/download image assets

## Template Format

Templates are YAML files with ordered `elements`.

- `type: text`
   - `value`: Jinja2 expression, for example `{{ event.title }}`
   - `box`: `{x, y, w, h}` in pixels
   - styling: `font`, `size`, `color`, `align`, `valign`, `wrap`, `fit: shrink`
- `type: image`
   - `source`: local path or URL (supports Jinja2)
   - `fit`: `cover`, `contain`, or `fill`
   - `shape`: `rect`, `rounded`, or `circle`

Built-in Jinja filters:

- `date`
- `slug`
- `upper`
- `lower`
- `default`

## Project Layout

```text
.
├── _data/
├── assets/
│   ├── backgrounds/
│   ├── fonts/
│   ├── overlays/
│   ├── speaker-images/
│   └── templates/
│       └── meetup.yaml
├── src/imagegen/
│   ├── cli.py
│   ├── config.py
│   ├── loader.py
│   ├── renderer.py
│   ├── text.py
│   ├── images.py
│   └── web/
│       ├── app.py
│       └── templates/
│           ├── index.html
│           └── settings.html
└── tests/
```

## Testing

```bash
pytest
```

## CI

GitHub Actions workflow [`.github/workflows/generate-image.yml`](.github/workflows/generate-image.yml) installs Python dependencies, renders images via `imagegen generate`, and uploads artifacts.