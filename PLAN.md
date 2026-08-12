# Project Status

The meetup asset automation plan is implemented. This file records the current baseline and keeps optional follow-up work separate from shipped behavior.

## Shipped

- Template-driven meetup, save-the-date, and speaker image rendering
- Full event bundles containing meetup images, cutout and portrait speaker cards, social copy, and slide decks
- LinkedIn announce, reminder, recap, and thank-you variants plus short-form copy
- Rule-based social generation with optional Azure OpenAI generation
- Title, agenda, per-speaker, sponsor, and CTA slides exported as PNG and PDF
- `speaker-spotlight` and `event-teaser` animation presets with GIF output and optional MP4 output
- Web studio actions for social copy, images, and full bundles, with editable saved drafts
- Make targets for installation, validation, preview, image generation, bundles, slides, and animations

## Current Decisions

- Event YAML and YAML rendering templates remain the source of truth; there is no parallel Markdown content model.
- Slide output is PNG plus PDF. Editable PPTX and Google Slides export are not part of the current product.
- Animations remain limited to two presets instead of becoming a general animation framework.
- Curated speaker cutouts are preferred, with generated cutouts and portrait cards as fallbacks.
- Standard workflows are exposed through Make targets and documented with Make-first examples.

## Optional Follow-Up

- Add PPTX export only when an editing workflow requires it.
- Add Google Slides upload only when collaboration requirements justify external API credentials and maintenance.
- Expose slide and animation previews directly in the web studio asset gallery.
