# Logo notes

## What was supplied

Two JPEGs, both 1600×800, both on a `#F7F7F7` field:

- `source/logo-original-dark-ground.jpeg` — obsidian letterforms, red accents. **Usable.**
- `source/logo-original-light-ground-BROKEN.jpeg` — **not usable.** This is the knockout
  version, but it was exported onto a white artboard rather than a transparent one. The
  wordmark sits at `#F5F5F5` on a `#F7F7F7` background — a two-level difference, which is
  invisible on screen and unrecoverable by keying. Only the red accents survived.

## What was derived, and how

Everything in this folder came from the dark-ground JPEG:

1. **Background keyed to transparency.** Alpha computed from the darkest channel per pixel,
   saturating so ink and red reach full opacity while antialiased edges keep partial alpha,
   then un-premultiplied against the known white background to recover clean colour. This
   correctly keys out the enclosed counters — the lens interior, and the gap inside the `o`.
2. **Knockout generated.** Pixels were classified by saturation: low-saturation (letterform)
   pixels remapped to Evidence white `#f7f7f8`, red accents remapped to Signal red `#e33b4c`
   so they hold up against an obsidian field.
3. **Traced to vector.** Two layers traced separately — letterforms and red accents — then
   composed as two paths in one SVG with `fill-rule="evenodd"`. 9 curves for the lockup
   letterforms, 3 for the accents. Verified against the source raster by overlay.

The SVGs are ~5KB each, so they are smaller than a base64 PNG *and* they scale. Use them.

## Status: derived, not official

These are faithful reproductions, but they are traced from a compressed 1600px raster, not
exported from the original vector artwork. Two consequences:

- Curve fitting is very close but not bit-identical to the designer's beziers.
- The brand kit says "use the supplied artwork" and sets an 8mm print minimum. For print, or
  for any use above ~720px, get the real SVG or a transparent PNG export from source.

**When proper artwork arrives, replace every file in this folder** and delete this note. The
filenames are the contract — keep them, and nothing downstream needs to change.

## Recolouring

The SVG paths carry `fill` attributes directly, so a theme swap is a `src` swap between the
`-knockout` and plain files. Do not apply a CSS `filter` to recolour — brand kit §02
prohibits recolouring letterforms, and a filter shifts the red accents too.

If you need the artwork to inherit a colour, the two paths are class-tagged in the source
files (`.loupe-ink`, `.loupe-signal` in the CSS-friendly variants) — but the two supplied
colourways cover both grounds and are the sanctioned options.

## Clear space

One signal-dot diameter on every side, per brand kit §02. This is already inside the SVG
viewBox. Do not crop it or place the artwork in a container with `overflow: hidden` and
tight bounds.
