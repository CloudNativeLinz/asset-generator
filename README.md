[![Lint, Build, Test](https://github.com/CloudNativeLinz/asset-generator/actions/workflows/ci.yml/badge.svg)](https://github.com/CloudNativeLinz/asset-generator/actions/workflows/ci.yml)

# Cloud-Native Linz Social Media Asset Generation

Template-driven event asset generation using Python, Pillow, and YAML. The project produces event and speaker images, social copy, PDF slide decks, and optional animated clips from the event data in `_data/events.yml`.

## Quick Start

The repository supports VS Code Dev Containers and GitHub Codespaces. Opening it in the container installs the development dependencies automatically. For a local checkout with Python 3.11 or newer:

```bash
make install-dev
```

Use Make targets for normal development and generation workflows. Run `make help` to see all targets and their common overrides.

## Generate Assets

List available events:

```bash
make list-events
```

Generate a full event bundle. Images, social copy, and slides are included by default:

```bash
make generate-bundle EVENT_ID=44
```

The bundle is written to `artifacts/<event-id>/` and contains:

- `meetup.jpg` or `meetup.png`
- `meetup-diamond.<format>`
- `speaker-<n>-cutout.<format>`, `speaker-<n>-portrait.<format>`, and
  `speaker-<n>-diamond.<format>`
- `social.json` with LinkedIn meetup and talk drafts, CTA variants, post variants, and short-form copy
- `slides/` with title, agenda, speaker, sponsor, and CTA PNGs
- `slides.pdf`
- `animations/` when animation presets are requested

Azure OpenAI is used for social copy when configured. Otherwise, deterministic rule-based copy is generated.

Generate one image with the default save-the-date template:

```bash
make generate EVENT_ID=44
```

Select another template or output size with Make variables:

```bash
make generate EVENT_ID=44 TEMPLATE=assets/templates/meetup.yaml WIDTH=550 FORMAT=png
```

Generate the default image for every event:

```bash
make generate-all TEMPLATE=assets/templates/meetup.yaml
```

Use another event source or output directory by setting `EVENTS_FILE` or `OUT_DIR` on any generation target.

## Slides And Animations

Generate only the PDF slide deck and its PNG pages:

```bash
make generate-slides EVENT_ID=44
```

To use a Google Slides presentation as the visual template, create text placeholders such as
`{{ event.title }}`, `{{ event.date }}`, `{{ event.host }}`, `{{ talks.1.title }}`, and
`{{ talks.1.speaker }}` in the presentation. Share the template and destination folder with a
service account as an editor, then point the generator at its JSON key:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/absolute/path/to/service-account.json"
make generate-google-slides \
	EVENT_ID=44 \
	GOOGLE_SLIDES_TEMPLATE="https://docs.google.com/presentation/d/<presentation-id>/edit"
```

The source presentation is never modified. The generated presentation URL is saved in
`artifacts/<event-id>/google-slides.json`. The preview studio can configure the template URL under
Settings, generate a copy, preview it inline via an embedded iframe, and open it directly from the
Artifact Wall. Set `GOOGLE_DRIVE_FOLDER_ID` to place generated presentations in a specific Drive
folder.
The legacy `GOOGLE_DRIVE_ACCESS_TOKEN` option remains available for short-lived user OAuth.

To restrict a service account to one folder, do not enable domain-wide delegation. Share only the
template and destination folder with the service account's `client_email`, using Editor access, and
set `GOOGLE_DRIVE_FOLDER_ID` to the folder ID from its Drive URL. Google OAuth scopes are not
folder-level permissions; the Drive ACL is the security boundary. The destination must be in a
Shared Drive because service accounts do not have personal My Drive storage quota. Add the service
account only to a limited-access destination folder in that Shared Drive and do not enable
domain-wide delegation. If a Shared Drive is unavailable, domain-wide delegation that impersonates
a Workspace user is required to create files against that user's quota.

Animations require the optional dependencies:

```bash
make install-animations
make generate-animations EVENT_ID=44 PRESET=speaker-spotlight
```

Available presets are `speaker-spotlight` and `event-teaser`. GIF output is always produced; MP4 is
also produced when the optional encoder is available. `FPS` defaults to `12`.

Include one or both presets in a full bundle:

```bash
make generate-bundle EVENT_ID=44 ANIMATIONS="speaker-spotlight event-teaser"
```

## Speaker Images

Speaker cards use `assets/templates/speaker.yaml`. Each talk produces a large cutout version and a rounded portrait fallback. Curated transparent PNGs can be placed at `assets/speaker-cutouts/<event-id>-<talk-number>.png`, for example `assets/speaker-cutouts/49-2.png`.

When no curated cutout exists, bundle generation derives a transparent candidate under `artifacts/<event-id>/cutouts/` while preserving the original image for the portrait version.

Bundles also include diamond speaker cards and a diamond meetup banner. A talk with two speaker
names separated by `&` or `and` uses the two-photo diamond layout. Supply two distinct portraits
with the optional `images` list; otherwise the talk's combined `image` is fitted across both
diamond panels.

## Preview Studio

Start the local web studio and optionally select an initial event:

```bash
make run EVENT_ID=44
```

Open <http://localhost:8000>. Override `HOST`, `PORT`, `EVENTS_FILE`, or `TEMPLATE` through Make variables when needed.

The studio supports:

- social-only, image-only, and combined generation actions
- editable meetup and per-talk LinkedIn drafts
- meetup and individual talk regeneration
- edited draft storage in `artifacts/<event-id>/social-edited.json`
- existing bundle loading and image preview/download
- Google Slides generation and presentation links
- persistent CTA, image width, and image format settings

## Azure Container Apps

The included `Dockerfile` runs the preview studio on port 8000. Azure Container Apps can build it
remotely, so a local Docker daemon is not required.

Install the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli), sign in, and deploy:

```bash
az login
az extension add --name containerapp --upgrade
make azure-deploy \
	AZURE_APP=cloudnative-asset-generator \
	AZURE_RESOURCE_GROUP=rg-cloudnative-asset-generator \
	AZURE_LOCATION=swedencentral
```

`az containerapp up` creates or reuses the resource group, Container Apps environment, registry,
and app, then prints the public URL. Run the same target after code or data changes to deploy a new
revision.

The `CI/CD` GitHub Actions workflow runs linting, a package build, and tests for pull requests and
pushes to `main`. After those checks pass on `main`, it authenticates to Azure with GitHub OIDC,
pushes a commit-tagged image to Azure Container Registry, updates the existing Container App, and
checks the public endpoint. The `production` GitHub environment holds these non-secret variables:
`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`,
`AZURE_CONTAINER_REGISTRY`, `AZURE_CONTAINER_APP`, and `AZURE_CONTAINER_APP_URL`.

Generated files and studio settings live in the container's local `artifacts/` directory. The
deployment is limited to one replica to keep that local state consistent, but the files do not
survive a replacement revision. Use an Azure Files volume before relying on the studio for durable
generated assets. Azure OpenAI variables can be configured after deployment without storing secrets
in the image:

```bash
az containerapp secret set \
	--name cloudnative-asset-generator \
	--resource-group rg-cloudnative-asset-generator \
	--secrets azure-openai-api-key='<api-key>'

az containerapp update \
	--name cloudnative-asset-generator \
	--resource-group rg-cloudnative-asset-generator \
	--set-env-vars \
		AZURE_OPENAI_ENDPOINT='https://<resource>.openai.azure.com' \
		AZURE_OPENAI_DEPLOYMENT='<deployment-name>' \
		AZURE_OPENAI_API_KEY=secretref:azure-openai-api-key
```

## Azure OpenAI

Copy the relevant values from `env.sample` into your environment:

```bash
export AZURE_OPENAI_ENDPOINT="https://<resource>.openai.azure.com"
export AZURE_OPENAI_API_KEY="<api-key>"
export AZURE_OPENAI_DEPLOYMENT="<deployment-name>"
```

`AZURE_OPENAI_API_VERSION`, `IMAGEGEN_LLM_TEMPERATURE`, and `IMAGEGEN_LLM_MAX_TOKENS` are optional. Do not commit API keys.

## Template Format

Templates are YAML files with a canvas background and ordered `elements`.

- `type: text` supports Jinja2 `value`, pixel `box`, font styling, alignment, wrapping, and `fit: shrink`.
- `type: image` supports local or remote Jinja2 `source` values, `cover`, `contain`, `contain-bottom`, or `fill` fitting, and rectangular, rounded, or circular shapes.
- `type: rectangle` adds a solid-color region.

Built-in Jinja filters are `date`, `slug`, `upper`, `lower`, and `default`.

## Project Layout

```text
_data/                  Event YAML data
assets/                 Templates, fonts, backgrounds, logos, and speaker inputs
artifacts/              Generated event bundles and studio settings
src/imagegen/           CLI, rendering, social, slide, animation, and bundle logic
src/imagegen/web/       FastAPI preview studio
tests/                  Automated tests and fixtures
```

## Development

```bash
make format
make lint
make test
```

GitHub Actions runs lint, package build, and tests on pushes and pull requests to `main`. The generation workflow renders meetup images at full size and width 550, commits changed generated assets, and uploads them as workflow artifacts.
