# Loupe brand skinning — instructions

You are applying the **Loupe Brand System v1.0 (July 2026)** to two existing HTML artifacts.
Everything you need is in this directory. Read this file fully before editing anything.

> If you haven't already, read `HANDOFF.md` first — it covers where the artifacts are, what
> order to work in, and two decisions that are Neil's rather than yours.

## The two targets

| Artifact | What it is | ID |
|---|---|---|
| Competitive landscape | 26-platform competitive assessment, interactive capability matrix, positioning map, pricing ladder | `f65cdf4e-fc35-432c-b52e-360fd3d15682` |
| Accelerator application brief | Product description, 10 sections, comparison table, capability surface, ready-to-paste blocks | `98befc56-cc47-44ac-8a8c-591ce8a7d0b5` |

Both were authored as single-file HTML artifacts. They stay single-file: **inline everything.**

## Hard rule: this is a skinning job, not an editing job

Do not change wording, claims, numbers, scores, table data, or section order.
If you believe a factual change is needed, stop and say so — do not make it.

The one exception is `notes/research-corrections.md`, which lists content changes the
competitive research implies for the product brief. Those are **proposals for Neil to
approve**, not instructions for you. Leave them alone unless told otherwise.

---

## 1. Tokens

Copy the `:root` block from `brand/loupe-brand.css` into each artifact's `<style>`.
Replace every hard-coded colour, font stack, radius and spacing value with the token.
There should be no raw hex left in the CSS except inside the token declarations themselves.

Core palette — do not invent values outside this set:

```
--loupe-obsidian  #0b0c0f   page background
--loupe-red       #b41624   Loupe red — signal, action, active state
--loupe-signal    #e33b4c   Signal red — brighter accent, small marks
--loupe-white     #f7f7f8   Evidence white
```

Surfaces step; they never use opacity:
`#07080a` → `#111216` → `#17181c` → `#202126` → `#25272d`

Text steps: `#f7f7f8` ink → `#bfc1c8` ink-soft → `#9a9da5` muted → `#71747c` muted-strong
Borders: `#292b32` default, `#3b3d44` stronger

**Entity semantics.** Reserve these for entity and data meaning. Never decorative, never
randomly assigned, and stable across every view — a person is the same blue in a graph, a
timeline, a table and a report.

```
person #5571c8   organisation #8060a9   location #238a88   financial #b37a2e
document #72757e event #c25778          communication #2c8197  success #4fa477
```

## 2. Type

Three families, loaded from Google Fonts (the `@import` is already in `brand/loupe-brand.css`):

- **Space Grotesk** 500–700 — display and headings only. Tighten tracking as size increases.
- **IBM Plex Sans** 400 body / 500 labels / 600 controls — all reading text.
- **IBM Plex Mono** 400–500 — used *sparingly*: eyebrows, section numbers, source lines,
  identifiers, dates, statuses, provenance. 9px, `letter-spacing: 0.12em`, uppercase.

Scale (size / leading / tracking):

```
Display XL  52 / 50 / -5.5%      Heading  26 / 30 / -3.5%
Display L   38 / 39 / -4.5%      Lead     18 / 25 / -1%
                                 Body     14 / 22 / 0
```

Mono is the tell of this brand. Overusing it makes the page look like a terminal; the rule
is metadata only, never sentences.

## 3. Logo

`brand/logo/` — SVG is authoritative, PNG is fallback.

| File | Use |
|---|---|
| `loupe-lockup-knockout.svg` | full lockup on dark surfaces |
| `loupe-lockup.svg` | full lockup on light surfaces |
| `loupe-mark-knockout.svg` / `loupe-mark.svg` | lens mark alone — favicon, compact signature |

Rules, from brand kit §02:

- Full wordmark whenever space allows. The mark may stand alone only after Loupe has been
  clearly identified elsewhere on the page.
- **Clear space** = one signal-dot diameter on every side. This is already baked into the
  SVG viewBox — do not add the artwork to a container that crops it.
- **Digital minimum 24px** height. Print minimum 8mm.
- Choose the version with strongest contrast against its ground. If the artifact has a
  light/dark toggle, swap the `src` — do **not** apply a CSS `filter` to recolour it.
- Never recolour individual letterforms, add effects, outlines or shadows, or stretch,
  rotate or place it on busy imagery.

To inline in a single-file artifact, paste the SVG markup directly into the DOM (each file
is ~5KB, smaller than a base64 PNG and it scales):

```html
<span class="loupe-lockup" aria-label="Loupe" role="img">
  <!-- contents of loupe-lockup-knockout.svg, minus the outer <?xml?> if present -->
</span>
```

Then size the container, not the paths: `.loupe-lockup svg { width: 106px; height: auto; display: block; }`

**Known issue with the source artwork.** The light-ground JPEG Neil was given
(`brand/logo/source/logo-original-light-ground-BROKEN.jpeg`) is the wordmark at `#F5F5F5`
on a `#F7F7F7` field — two levels of contrast, effectively invisible. It was exported onto
a white artboard instead of transparent. Everything in `brand/logo/` was derived from the
dark-ground JPEG instead: background keyed to transparency, then traced to vector, with the
letterforms remapped to Evidence white and accents to Signal red for the knockout version.
See `brand/logo/LOGO-NOTES.md`. These are faithful but they are *derived*, not official
artwork — if real vector artwork arrives, swap it in.

## 4. Layout

- 12-column grid, 24px desktop gutters, collapsing to 6 then 2 columns.
- 1240px content maximum, 48px desktop page margins, 28px on narrow screens.
- Prefer asymmetric spans — 7/5 and 8/4 — over equal three-column compositions.
- Spacing scale only: 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64.
- 1px hairline dividers to show systems, boundaries and progression.
- Generous negative space around decisive statements, then controlled density for evidence,
  data and comparison. That contrast is deliberate — it is part of the brand.

## 5. Interface language

- 4–8px radius. `5px` controls, `8px` panels. Nothing softer — it reads consumer.
- Subtle elevation: prefer tonal separation and long restrained shadows over floating cards.
- **One primary red action or state per composition.** Secondary actions stay present
  without competing.
- Signal dots mark active state, verified status and meaningful nodes:
  `7px` circle, `--loupe-signal`, `box-shadow: 0 0 0 6px rgba(227,59,76,.11), 0 0 18px rgba(227,59,76,.6)`
- Cite at the point of claim. Source name, page or row, quote reference *beside* the
  finding — mono, muted, small.

## 6. Data visualisation

Both artifacts contain charts. Read brand kit §07 before touching them.

1. **Semantic colours stay stable.** A person is blue in a graph, timeline, table and report.
2. **Loupe red means focus** — selection, investigative significance, primary action.
   Never an entity type.
3. **Lines remain subordinate.** Relationships support nodes and labels; they don't
   overwhelm them.
4. **Never rely on colour alone.** Pair it with labels, shapes, patterns or text.

Specific to the competitive landscape artifact:

- The capability matrix shading is proportional to score. Keep the existing scale but drive
  it from `--loupe-red` at varying alpha, and keep the outlined "leads its column" treatment
  as a 1px `--loupe-signal` border rather than a fill.
- Capability subtotal and readiness subtotal are deliberately *not* summed. If the original
  used teal and orange for those two halves, map them to `--loupe-location` (#238a88) and
  `--loupe-financial` (#b37a2e) so they sit inside the semantic palette.
- The positioning map, pricing ladder and beachhead chart are comparison surfaces: neutral
  marks, red only for the Loupe point.

## 7. Light and dark

Brand kit §10: **light pages for reading, dark fields for covers and section dividers.**

Both artifacts already have a light/dark toggle — keep it. Implement as a single
`html[data-theme="light"]` block that overrides the token values only; no component
should need theme-specific rules. `reference/branded-sheet-example.html` shows this.

In light mode, `--brand-soft` collapses to `#b41624` — the pale accent tints have
insufficient contrast on white, so eyebrows and small mono labels use full Loupe red.
Gradient display text also flattens to solid `#b41624`.

## 8. Print / PDF

Both artifacts have a "Print / Save PDF" control. Brand kit §10:

```
A4 · 14mm outer margin · 11pt body · 15pt leading
Red limited to headings, rules and evidence emphasis
```

Force the light reading surface in `@media print`. Hide the topbar, nav rail, theme toggle
and any copy buttons. Set `-webkit-text-fill-color` on gradient text or it prints as
transparent. Repeat document controls — confidentiality, case identity, version, pagination —
in headers and footers.

The competitive landscape doc is marked **Internal — candid register**. That label must
survive into print. Do not drop it.

## 9. Accessibility

Contrast ratios the brand kit publishes, which the skin must not regress:

```
18.27:1  ink on obsidian          6.82:1  white on Loupe red
10.88:1  ink-soft on obsidian     6.14:1  signal-soft on obsidian
 7.21:1  muted on obsidian
```

All five were re-measured against WCAG 2.1 and match the published figures exactly.

Light mode needs its own set, because the dark-mode accents do not survive on paper. Measured:

```
16.89:1  paper-ink #15161a on paper #f7f7f8     5.36:1  muted #63666e on paper
 9.83:1  ink-soft #3d3f45 on paper              3.40:1  muted-strong #83868e on paper
 6.37:1  Loupe red #b41624 on paper             2.97:1  signal-soft #f35d6d on paper — FAILS
```

That last line is why `--brand-soft` collapses to `#b41624` in light mode. Signal red and the
pale accent tints are dark-field colours; using them on paper drops eyebrows and small mono
labels below AA. Do not "fix" light mode by reintroducing them.

WCAG 2.1 AA and full keyboard operability. `:focus-visible` is a 2px `--loupe-signal-soft`
outline at 4px offset. Preserve every existing `aria-*` attribute, table `scope`, and the
interactive behaviour of the matrix (hover notes, click-to-compare, lens switching).

## 10. Procedure

1. Read `brand/brandkit.html` — it is the full system, rendered. Skim all 11 sections.
2. Open `reference/branded-sheet-example.html` — a worked example with the cover, three
   content sheets, and one instance of every component pattern both artifacts need
   (stat row, comparison table, claim callout, capability list, paste block, semantic
   colour note). Copy its structure; it is already compliant.
3. Skin the **accelerator brief** first — it is mostly prose and tables, so it is the
   cheaper place to get the system right.
4. Then the **competitive landscape**, preserving every interactive behaviour.
5. Verify with the checklist below.
6. Report what you changed and anything you could not do without a content decision.

## 11. Verification checklist

- [ ] No raw hex outside the token declarations
- [ ] Only the three brand families load; no other font requested
- [ ] Mono used for metadata only — no sentences set in mono
- [ ] Logo: correct version per ground, ≥24px, clear space intact, no CSS filter recolour
- [ ] One primary red action or state per composition
- [ ] Entity colours consistent across every view in the document
- [ ] Red never encodes an entity type in any chart
- [ ] Light mode: every surface legible, no pale accent on white
- [ ] Print: light surface, A4/14mm, gradient text renders, controls hidden, register label intact
- [ ] Matrix interactivity intact — hover notes, lens switching, click-to-compare
- [ ] Keyboard tab order works; focus rings visible in both themes
- [ ] Content unchanged — diff the text, not just the styles

---

## Contents of this directory

```
HANDOFF.md                             start here — context, order of work, open decisions
SKINNING.md                            this file
brand/
  brandkit.html                        the full brand system, rendered (v1.0, July 2026)
  loupe-brand.css                      tokens, type scale, component classes, print rules
  logo/
    loupe-lockup.svg                   primary lockup, light grounds
    loupe-lockup-knockout.svg          primary lockup, dark grounds
    loupe-mark.svg                     lens mark alone, light grounds
    loupe-mark-knockout.svg            lens mark alone, dark grounds
    loupe-lockup-primary.png           720px raster fallback, light grounds
    loupe-lockup-knockout.png          720px raster fallback, dark grounds
    loupe-mark-primary.png             256px raster, light grounds
    loupe-mark-knockout.png            256px raster, dark grounds
    LOGO-NOTES.md                      derivation, the broken source file, what to replace
    source/
      logo-original-dark-ground.jpeg   as supplied — usable
      logo-original-light-ground-BROKEN.jpeg   as supplied — white on white, do not use
reference/
  branded-sheet-example.html           worked example, both themes, all component patterns
  branded-sheet-example.pdf            the same file printed — the A4 path, rendered
notes/
  research-corrections.md              content changes the research implies — FOR APPROVAL,
                                       not for you to apply
```

18 files. If anything above is absent, the bundle was unpacked incompletely — stop and say so
rather than working around it.
