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
- `meetup-website-<stage>.<format>`, `mobile-website-<stage>.<format>`, and
	`teaser-<stage>.<format>` at their native sizes
- `speaker-<n>-portrait.<format>` and `speaker-<n>-diamond.<format>`
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

## Landscape Graphics

The Canva exports provide three independent layouts, not resized square graphics:

| Canvas | Native Size | Content |
| --- | --- | --- |
| `meetup-website` | 1080 x 610 | Branding, two talk slots, portraits, date, time, location |
| `mobile-website` | 341 x 200 | Two talk slots and portraits, names, date, time, location; no talk titles |
| `teaser` | 1166 x 200 | Two talk slots and portraits, names, talk titles, date |

Generate all three without generating square images, social copy, or slides:

```bash
make generate-promotions EVENT_ID=49
make generate-promotions EVENT_ID=49 CANVAS=meetup-website PROMOTION_VARIANT=save-the-date
make generate-promotions EVENT_ID=49 CANVAS=mobile-website PROMOTION_VARIANT=second-slot FORMAT=png
```

`CANVAS` accepts `all` (default) or a canvas ID from the table. `PROMOTION_VARIANT` accepts:

- `auto` (default): show the current lineup in the first two talk slots.
- `save-the-date`: hide both talks and show the invitation placeholders.
- `first-slot`: show only `talks[0]`.
- `second-slot`: show only `talks[1]`; this does not move the first talk to the second slot.
- `both-slots`: show both slots, leaving placeholders for missing content.

The slot order is preserved, including an empty first talk. These designs have room for two talks;
additional talks remain in existing per-talk square outputs. One talk can have two co-presenters:
use speaker names separated by ` & ` or ` and ` and supply their portraits in `talk.images` in the
same order. This produces the three- and four-person layouts automatically. A single image can
instead contain both people; multiple photos of a solo speaker do not create extra presenters.
Missing portraits retain the cloud artwork. Missing dates show "Date coming soon".

Files are written to `artifacts/<event-id>/<canvas>-<stage>.<format>`. An explicit `WIDTH`
on `generate-promotions` scales proportionally and adds a width suffix to avoid overwriting
native-size exports. Bundle `WIDTH` and the studio's saved width still apply to legacy outputs;
landscape images in bundles always retain their native sizes. Existing square filenames are
unchanged. Use `PROMOTIONS=0` on `generate-bundle` to omit the additional graphics.

In the studio, **Landscape Graphics** selects the canvas and announcement stage. **Preview**
renders without saving, and **Generate Landscape** writes only the selected landscape images.
The checkbox includes or excludes the selection from image bundle actions. Downloads are grouped
by canvas and displayed without square cropping. JPG/PNG continues to use the existing format
setting. Canvas and announcement-stage selections are local to the current page, not persisted.

### Canva Export Inventory

All 25 exported pages were inspected. Page numbering below is the ZIP's original order.

| Archive | Reusable Background | Finished Examples |
| --- | --- | --- |
| Meetup & Website | Page 2, `Save the date (no speaker) - Template.png` | Pages 1 and 3-9 |
| Mobile Website | Page 2, `Save the date (no speaker) (2).png` | Pages 1 and 3-8 |
| Teaser | Page 2, `Save the date (no speaker) (2).png` | Pages 1 and 3-8 |

In each archive, page 1 is a populated save-the-date example; pages 3 and 4 demonstrate first-slot
and second-slot announcements; page 5 has both talks; pages 6 and 7 demonstrate co-presenters in
the second and first slots; page 8 has two co-presenters in each slot. Their example names, photos,
titles, and dates are not imported as backgrounds. The Meetup & Website page 9 is a separate
**Pub Quiz** finished example, not a reusable clean template. A clean export of that artwork is
needed before adding a dedicated quiz layout.

The original ZIPs remain untouched. Only page 2 from each archive is imported as
`assets/backgrounds/meetup-website.png`, `mobile-website.png`, and `teaser.png`. Each has a matching
YAML in `assets/templates/`. The original square template assets remain unchanged.

To add another format, export a clean background, add a native-size YAML with pixel coordinates,
and register its label/dimensions in `src/imagegen/promotions.py` (`PROMOTION_PRESETS` and the
`PromotionFormat` literal). The studio derives its menu and preview dimensions from that registry.
Image elements with `shape: polygon` accept `polygon_points` as pixel coordinates relative to
their own box, so clipped and slanted frames do not require a new renderer shape per format.

## Slides And Animations

Generate only the PDF slide deck and its PNG pages:

```bash
make generate-slides EVENT_ID=44
```

New Google Slides decks copy the configured Cloud Native Linz template and place the generated
agenda on slide 3 without modifying the source presentation. To use another Google Slides
presentation as the visual template, create text placeholders such as
`{{ event.title }}`, `{{ event.date }}`, `{{ event.host }}`, `{{ talks.1.title }}`, and
`{{ talks.1.speaker }}` in the presentation. Share the template and destination folder with a
service account as an editor, then point the generator at its JSON key:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/absolute/path/to/service-account.json"
make generate-google-slides \
	EVENT_ID=44 \
	GOOGLE_SLIDES_TEMPLATE="https://docs.google.com/presentation/d/<presentation-id>/edit"
```

In a Shared Drive, the source presentation is copied and never modified. In a shared My Drive
folder, pre-create a presentation named with the event ID; the generator updates that file because
service accounts have no personal storage quota. The presentation URL is saved in
`artifacts/<event-id>/google-slides.json`. The preview studio can configure the template URL under
Settings, generate or update the deck, preview it inline, and open it from the Artifact Wall. Set
`GOOGLE_DRIVE_FOLDER_ID` to the destination folder ID.

### Google Slides Generation Workflow

When using the currently configured My Drive folder:

1. Make a copy of the Google Slides template named `00`.
2. Move the copy into the folder configured by `GOOGLE_DRIVE_FOLDER_ID`.
3. Rename the copied presentation to the event ID, for example `49`.
4. In the preview studio, select that event and click **Generate Google Slides**.

The generator finds the presentation by event ID and populates it with the event data, including
the agenda on slide 3. Always copy `00`; never rename or edit the original template.

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

Speaker cards use `assets/templates/speaker.yaml`. Each talk produces a rounded portrait card
and a diamond card. Bundle generation does not create plain `speaker-<n>.png` files,
`speaker-<n>-cutout.<format>` cards, or intermediate images under `cutouts/`.
Previously generated files are left untouched.

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
- per-image "Save to GitHub" commits into a configured repository

### Saving Images To GitHub

Each generated image can be committed to a GitHub repository from the studio. Set a fine-grained
personal access token with `Contents: write` permission on the target repository before starting the
studio:

```bash
export IMAGEGEN_GITHUB_TOKEN="<github-token>"
export DEFAULT_GITHUB_REPO="CloudNativeLinz/cloudnativelinz.github.io"
export DEFAULT_GITHUB_BRANCH="main"
export DEFAULT_GITHUB_PATH_PREFIX="assets/images/events"
```

`GITHUB_TOKEN` is also accepted. The token is only read server-side, is never sent to the browser,
and is never written to `artifacts/studio-settings.json`. Do not commit it.

The environment values provide defaults for the destination repository, branch, and path prefix.
They can be changed on the settings page. Files are committed to
`<path-prefix>/<event-id>/<file-name>`; saving the same image again updates the existing file.
Without a configured token the save buttons stay disabled.

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

Set `background` to an image path, or omit it and provide an explicit `size` plus an optional
`background_color` (default: white). Missing image paths raise an error; they do not silently
fall back to a solid color. For example:

```yaml
name: simple-slide
size: {width: 1920, height: 1080}
background_color: "#26272B"
elements: []
```

The legacy meetup and slide templates now use solid-color backgrounds and rectangle elements,
so they no longer depend on the removed legacy background image. The Canva templates continue
to use their exported PNG backgrounds.

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
