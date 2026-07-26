# Handoff — read this first

You have the Loupe repo. The session that produced this bundle did not, so nothing here has
been committed, and the two target artifacts have never been opened. Everything below is
context that session had and you don't.

## What this bundle is

The Loupe brand system (v1.0, July 2026) packaged for application to two existing HTML
artifacts, plus a separate set of *content* proposals that came out of comparing them.

| Artifact | What it is | ID |
|---|---|---|
| Competitive landscape | 26-platform competitive assessment. Interactive: capability matrix with hover notes, lens switching and click-to-compare; positioning map; pricing ladder; light/dark toggle | `f65cdf4e-fc35-432c-b52e-360fd3d15682` |
| Accelerator application brief | Product description, 10 sections, comparison table, capability surface, ready-to-paste blocks | `98befc56-cc47-44ac-8a8c-591ce8a7d0b5` |

Both are single-file HTML artifacts and must stay single-file — inline all CSS, JS and the
logo SVG markup. **Locate them in the repo before assuming anything about their structure.**
The previous session only ever saw them as pasted prose, so the descriptions above come from
that text, not from reading the source. If the interactive components differ from what's
described, trust the source.

## Do this in order

**1. Place and commit the bundle.**

```bash
unzip loupe-brand-kit.zip -d <repo-root>      # creates loupe-brand/
git add loupe-brand
git commit -m "Add Loupe brand kit and skinning instructions"
```

Commit before skinning, so the skin itself lands as a reviewable diff.

**2. Read `loupe-brand/SKINNING.md`.** That is the actual instruction file — tokens, type
scale, logo rules, layout, interface language, data-viz rules, light/dark, print,
accessibility, and a verification checklist. Do not start from this file; start from that one.

**3. Open `loupe-brand/reference/branded-sheet-example.html`.** A worked, compliant example:
cover, three content sheets, and one instance of every component pattern both artifacts need.
Copying its structure is faster and safer than working from the spec alone. There is a PDF
beside it showing the print path.

**4. Skin the accelerator brief first.** It is mostly prose and tables — the cheaper place to
get the system right before touching the interactive document.

**5. Then the competitive landscape.** Preserve every interactive behaviour: matrix hover
notes, lens switching, click-to-compare, and the light/dark toggle. The document is marked
**Internal — candid register**; that label must survive, including into print.

## Two boundaries

**Skinning only.** Do not change wording, claims, numbers, matrix scores, table data or
section order in either artifact. Diff the text as well as the styles when you verify.

**`notes/research-corrections.md` is not a task list.** It contains twelve proposed content
changes to the accelerator brief, derived from the competitive research. They are for Neil to
approve. Do not apply them as part of the skin. They are in the bundle so the reasoning is
recorded next to the material it concerns.

## Open decision, flagged for Neil — do not resolve it yourself

The brand kit's own messaging conflicts with the research it now sits alongside. Brand kit §09
lists the proof promise as "Every claim carries its receipt" and puts "Links every answer to
the exact source" under *Prefer*. The research's central finding (F1) is that the citation
layer became free across the category between Nov 2025 and Feb 2026, so leading with
provenance argues about a free feature.

This matters for sequencing: if §09 stands, the superseded messaging gets baked into both
artifacts during the skin. The brand kit's *Differentiator* line — "The model is a component.
The evidence layer is the product" — is aligned and unaffected.

If Neil hasn't ruled on this, skin to v1.0 as written and note it. Don't silently correct it.

## Known issue you'll inherit

The light-ground logo file Neil was supplied is unusable — the wordmark is `#F5F5F5` on a
`#F7F7F7` field, exported onto a white artboard instead of transparent. Everything in
`brand/logo/` was derived from the dark-ground JPEG instead and verified against it. The SVGs
are the authoritative versions and are ~5KB each, smaller than a base64 PNG and scalable,
which is what makes them right for single-file artifacts. `brand/logo/LOGO-NOTES.md` has the
derivation and the replacement contract: the filenames are stable, so when real vector
artwork arrives, swap the files and nothing downstream changes.

## One naming decision — resolved

The instruction file shipped as `CLAUDE.md`, which would have been auto-loaded as context for
the whole repo and pulled the brand rules into unrelated sessions here. Neil ruled on this at
commit time: it is now `loupe-brand/SKINNING.md` and must be referenced explicitly. Read it
when you start a skinning job; it is no longer loaded for you automatically.

## When you're done

Report what changed per artifact, anything the checklist in `SKINNING.md` failed on, and
anything you could not complete without a content decision.
