# Fonts

Generated image, promotion, and PDF slide templates use **Inter**, matching the
typography of <https://cloudnativelinz.at/> (checked September 16, 2026).

| File | Role | License |
| --- | --- | --- |
| Inter-Regular.ttf | Supporting text and agenda entries | [SIL OFL 1.1](LICENSE.txt) |
| Inter-SemiBold.ttf | Speaker names, labels, and prominent dates | [SIL OFL 1.1](LICENSE.txt) |
| Inter-Bold.ttf | Event and talk headlines | [SIL OFL 1.1](LICENSE.txt) |
| DejaVuSans.ttf | Retained for existing custom templates | [Bitstream Vera / Arev](DejaVu-LICENSE.txt) |
| DejaVuSans-Bold.ttf | Retained for existing custom templates | [Bitstream Vera / Arev](DejaVu-LICENSE.txt) |

## Sources

Inter's static TTF files and LICENSE.txt are extracted unchanged from the official
[Inter 4.1 release](https://github.com/rsms/inter/releases/tag/v4.1), archive
[Inter-4.1.zip](https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip).
The font files are in `extras/ttf/` inside that archive. Static weights work with
Pillow without conversion, variation-axis configuration, or network access.

The retained DejaVu files contain embedded copyright and license notices. The
standalone notice is the upstream
[DejaVu 2.37 LICENSE](https://github.com/dejavu-fonts/dejavu-fonts/blob/version_2_37/LICENSE).

## Redistribution

These fonts are copyrighted and openly licensed, not copyright-free. Preserve the
applicable copyright and license notices when bundling or redistributing them,
including in container images. The Inter license does not require rendered artwork
to use the OFL or display a font credit. Consult each license for modification,
reserved-name, and standalone font-sale restrictions.

The proprietary Lucida Bright files (`LBRITE*.TTF`) are no longer bundled. Custom
templates referencing them must choose an Inter file above. Old Git revisions and
previously built container images may still contain those files; this change does
not rewrite history or replace existing deployments.

Only dynamically rendered text changes font. Lettering already baked into the
exported background PNGs and logos is unchanged. External Google Slides templates
retain their own typography. The preview studio UI continues to use its existing
open-license Outfit and IBM Plex Mono fonts.