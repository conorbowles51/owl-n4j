# Landing rebuild v2 — spec

Date: 2026-08-05. Supersedes `2026-08-04-landing-page-redesign-design.md` for page
architecture; that document's §3 claim set and §4 product facts remain binding.

## 1. Why v1 failed (user review, confirmed by inspection)

1. **Pipeline-first structure.** Seven mechanism beats before any product value.
   "Chunking and embedding" was on the page. Nobody buying casework software cares.
2. **The case was cited before it was introduced.** Entity cards quoted
   `02_company_registry_nexus.pdf` to a reader who had never heard of Nexus. The
   filenames are the *proof* device; v1 used them as the *introduction*.
3. **Full-bleed whole-app screenshots.** 2560-wide captures at 100vw: taller than the
   viewport, so the reader only ever saw horizontal slices of UI bounded by hard
   border lines; app text rendered at ~0.78× native → unreadable.
4. **Scroll-jacking everywhere.** Six pinned sections, each costing 2–3 screens of
   scroll to deliver one small change. Felt broken, not choreographed.
5. **Sparse pinned frames.** 3 viewport-heights reserved, ~400px of content centred
   in them. Voids above and below.
6. **Hero plate upscaled.** 1600px bitmap stretched to 2560+ → pixelation.
7. **Intake read as a directory listing.** Twelve identical "Document" rows + one
   "Audio" row looked like a data-entry error, and `4.2 KB` file sizes undercut the
   scale story.

## 2. Design system (binding for every section)

### Identity

- **Grounds carry meaning.** `--obsidian` = inside the case / the machine.
  `--paper` = the analyst's desk / the argument. Alternation is deliberate:
  Hero (obsidian) → Case (paper) → Ingest+Graph (obsidian) → Agent (paper) →
  Finding (obsidian) → Sourced (obsidian, continuous with Finding) → Surfaces (paper)
  → Act III (paper) → CTA (obsidian).
- **The signature element is the red receipt.** A mono, `--accent`-coloured source
  reference — `03_bank_statement_nexus.pdf, p.1` — treated as a first-class
  typographic object. It appears in every act: the case file list, the agent's
  answers, under each amount in the finding, in the real UI crop, in the closing
  argument. By the end of the page the reader has been taught: red mono = receipt.
  This is drawn from the product's actual details panel, not invented.
  Shared classes live in `src/styles/base.css` (`.receipt` — see §6); use them,
  do not restyle per section.
- **One aesthetic risk, spent once:** the hero is a live-rendered constellation of
  the real case (DOM/SVG, not bitmap) that the reader can watch settle. Everything
  else stays disciplined.

### Type

- Display: `var(--loupe-font-display)` (Space Grotesk 500–700). Headlines only.
  Tight leading (0.98–1.05), letter-spacing −0.02 to −0.03em.
- Body: `var(--loupe-font-body)` (IBM Plex Sans). 1rem–1.1875rem, line-height 1.6.
- Evidence/annotation: `var(--loupe-font-evidence)` (IBM Plex Mono). Eyebrows,
  captions, receipts, data. 0.6875–0.8125rem, tracking 0.08–0.14em for uppercase.
- Section pattern: mono uppercase eyebrow in `--accent-bright` (dark ground) or
  `--accent` (paper) → display H2 → body lede at `--measure` max.

### Rhythm and size discipline

- Section paddings from `--sec-pad-xs/sm/md/lg` only. Default `--sec-pad-md`.
- **No section taller than ~120svh** except the one pinned graph track.
- Content must fill the section. If a composition is 400px tall, the section is
  ~600px tall, not 100svh.
- Container: `width: var(--page); margin-inline: auto`.

### Imagery rules (hard)

- **No full-bleed screenshots. Ever.** Product crops sit in a contained frame:
  1px `--rule` (paper) / `--rule-dark` (obsidian) border, `--loupe-radius-panel`,
  soft shadow, caption below.
- **Never display a crop above its native pixel width.** Cap with
  `max-width: min(100%, <native>px)`. Downscaling is allowed; upscaling is not.
- Every frame containing product imagery or reconstructed product UI carries the
  mono caption `Illustrative case data` (comms: `Comms Center — illustrative
  extraction data`).
- Frames never exceed `max-height: 78vh`; crop the plate, don't scale it to fit.

### Motion rules (hard)

- Scroll-pinning: **GraphReduce only.** Every other section is normal flow.
- In-flow reveals: opacity/translate ≤ 16px, 300–500ms, `var(--loupe-ease)`,
  triggered once via IntersectionObserver. Use the shared `Reveal` primitive
  (`src/components/primitives/Reveal.tsx` — see §6).
- `prefers-reduced-motion: reduce` → everything static and complete. Test it.
- Nothing animates continuously except the hero field's ambient drift (which must
  also stop under reduced motion).

### Claims

- Scale/verified figures come from `src/data/claims.ts` only. The retired-phrase
  test scans `src/`; do not write "two hundred thousand documents", "five hundred
  hours", "ten phones".
- Case facts come from `src/data/case.ts` only. Do not invent new amounts, names,
  dates or filenames.
- Known product defects must not appear: the Financial view's `$`-symbol bug
  (no Financial screenshot anywhere) and the agent's "could not produce an
  answer" message (no chat-column text in agent crops).

## 3. Page architecture — the story

A new reader must be able to answer, in order: *what is this → what does a case
look like inside it → what did it find → can I trust that → what else does it do →
is it for me.*

| # | id | Component | Ground | Job |
|---|----|-----------|--------|-----|
| 1 | `top` | `Hero` | obsidian | What this is, in one screen |
| 2 | `case` | `TheCase` | paper | Introduce the demonstration case as a story |
| 3 | `ingest` | `Ingest` | obsidian | Folder in → model out, overnight |
| 4 | `graph` | `GraphReduce` | obsidian | 121 nodes → the 12 that matter (pinned) |
| 5 | `agent` | `AgentDialogue` | paper | Ask in English, answers with receipts |
| 6 | `finding` | `Finding` | obsidian | The six-source convergence — the payoff |
| 7 | `sourced` | `Sourced` | obsidian | Real UI proof: every statement cites file+page |
| 8 | `surfaces` | `Surfaces` | paper | Timeline, map, audio, comms — one structure |
| 9 | — | Act III (`NarrativeSections`) | paper | Why not a chatbot; deployment; audience |
| 10 | — | `FinalCta` | obsidian | Walkthrough CTA |

Deleted from v1: ProblemScene, IntakeStream, ModelResolve, Lenses, Convergence
(replaced by Finding), AgentExchange (replaced by AgentDialogue), WorkProduct
(folded into AgentDialogue), ProductFrame/Callout primitives (full-bleed pattern).

## 4. Section briefs

### 4.1 Hero — edit `sections/Hero.tsx` + `Hero.module.css`

Keep: eyebrow, `Query the whole case.`, the lede, both CTAs, `scaleLine` stat,
copy-left composition, obsidian ground.

Replace the bitmap `.shot` entirely with a **live-rendered graph field**: DOM/SVG
nodes (absolutely-positioned circles + mono labels) using real case entities and
`entityColours` from `case.ts` — Nexus Trading Ltd (selected, ringed in
`--accent`), Victoria Blackwood, Marcus Chen, GlobalTech Industries, Sapphire
Investments Ltd, Cayman National Bank, FCIB-7729384756, dated transactions, BVI /
Cayman / Monaco locations, emails, the +44 handle. 25–40 nodes, hand-composed
layout (denser toward the right edge, sparse near the copy), hairline SVG edges
connecting the money path. Crisp at every DPI — this *is* the pixelation fix.

Ambient motion: nodes drift ±3px on slow individual periods (CSS animations,
staggered delays); a settle-in on load (scale/opacity, 600ms, staggered). All
static under reduced motion. Field sits behind the copy with the same
column-tracking fade mask as now (`calc(50% + Nrem)` stops). On <1280px the field
becomes the band below the copy (keep current turn behaviour); on mobile it's a
short band, still DOM-rendered, still crisp.

Delete the `<img>` and its webp references. Keep `.grid`, actions, stat, caption
(`Illustrative case data`).

### 4.2 TheCase — new `sections/TheCase.tsx`

Eyebrow: `The demonstration`. H2: `Thirteen files. One question.`
Lede (direction, refine): "A procurement manager. A vendor with no office, no
staff, no website. And €1.03 million that left the account as fast as it arrived.
This is the case the rest of this page works — twelve PDFs and one recorded call."

Composition — a dossier, not a file manager:
- **The cast**, three cards: Marcus Chen (Procurement, GlobalTech Industries),
  Victoria Blackwood (CEO, Nexus Trading Ltd), Nexus Trading Ltd (BVI company,
  registered Craigmuir Chambers, Tortola). Entity-coloured dots matching product.
- **The files**, from `evidenceFiles` + `folders`, grouped by folder with the
  format mix stated in words ("twelve PDFs · one recorded call · 2.1 MB of audio
  that becomes 133 searchable turns" — check counts against `case.ts`). File names
  set in mono; **no size column, no type column** — the point is what they are,
  not their bytes. The MP3 gets explicitly named as the recorded call so the mix
  reads as deliberate.
- **The question**, set large: "Where did €1.03 million go, and who sent it?"
  (verify the total against `chartTotal`).
- Mono caption: `Illustrative case data`.

This section must feel like opening a case file: paper ground, hairline rules,
mono annotations. No screenshots. No scroll effects beyond a Reveal.

### 4.3 Ingest — new `sections/Ingest.tsx`

Compact — one screen or less. Eyebrow: `Intake`. H2 direction: `Drop the folder
in. Come back to a model.` Body: one sentence covering extraction → entities →
resolution → sourcing, in product terms, not pipeline terms ("Loupe reads every
page, finds the people, companies, accounts and transactions, works out which
mentions are the same thing, and ties every fact to the page it came from.")

One designed visual, no bitmap: format chips (`PDF · MP3 · UFDR · XLSX`) flowing
into a single node, then a stat strip of three figures set in display type:
`13 files → 212 sourced facts → 121 entities · 212 relationships` (labels in
mono under each). Numbers from `case.ts` (`evidenceTotalEntities`, `graphCounts`).
Closing mono line (verified claim): "A few hundred documents takes twelve to
twenty-four hours. It runs unattended overnight."

Static or single-Reveal. No pinning. No counters that require scroll to advance.

### 4.4 GraphReduce — edit in place (the keeper)

Keep the canvas, the seeded PRNG, the 1400→40 reduction mechanic, PinnedSequence.
Tighten:
- `steps` cut so the full beat costs ≤ 3 viewport-heights of scroll.
- Label the two states explicitly on screen with product vocabulary: `All data —
  121 nodes · 212 edges` → `Significant — 12 nodes · 24 edges` (from
  `graphCounts`; the canvas dramatises the real matter's density, the labels tell
  the truth about the demo case — keep the existing framing device if it already
  handles this).
- The composition must fill the pinned viewport: headline + canvas + layer label
  visible together, no dead margins above/below.
- Mobile/reduced-motion: completed state, canvas static at the significant layer,
  both counts shown.

### 4.5 AgentDialogue — new `sections/AgentDialogue.tsx` (replaces AgentExchange + WorkProduct)

Eyebrow: `Interrogation`. H2 direction: `Ask in English. Every answer carries
receipts.`

A designed conversation (component-built, not screenshots) using `case.ts` data:
1. Analyst asks: "Show me every payment from GlobalTech to Nexus Trading in 2023."
2. The agent **asks back** (from `clarification`) — the clarifying-question moment
  is a differentiator; give it visual weight.
3. Answer: total + the monthly series (`chartMonths`), rendered as a small clean
  chart component (SVG bars, entity-financial colour), with red receipts under it
  (`chartSource`). Include `agentTrail` ("22 steps · 3.7s") as a mono badge and
  `agentCaveat` as an honest footnote — honesty is part of the pitch.
4. Close with the work product: one framed **real crop** `plates/agent-report.webp`
  (report artifact with sections + citations), captioned; one line: the same
  thread ends in a cited report you can export.

Real crop `plates/agent-chart.webp` may be used instead of / beside the SVG chart
if it reads better in the frame — builder's judgment, caps at native width.
No chat-column text from captures (defect). Paper ground. ≤ 120svh total.

### 4.6 Finding — new `sections/Finding.tsx` (replaces Convergence)

The climax. Eyebrow: `The finding`. H2 direction: `Five amounts. Six sources.
One story.`

In-flow (no pinning), obsidian. Composition: the five recited amounts
(`recitedAmounts`) as a central spine set in display type; around/under each,
the sources that independently confirm it, each as a red receipt:
- the call (`transcript` — Blackwood recites the amounts, 00:35),
- the bank statement rows (same five, same order),
- the "Year-End Advisory Services" invoice filed 20 Dec vs the phrase spoken on
  the call of the 19th (`invoiceDescriptions`, `transcript`),
- the pass-through rate (`passThrough` — 96.6% gone in 2–5 days) vs the SAR's
  independent "97% rapid pass-through",
- the interviews corroborating the promise to the payment processor.

The reader should be able to trace every connection without scrolling sideways or
hovering. Dense but ordered — this is the page's proof of value. End with one
line: direction — "No single file contains this. The model does."

### 4.7 Sourced — new `sections/Sourced.tsx`

Short. Obsidian, continuous with Finding. Eyebrow: `Provenance`. H2 direction:
`Every statement ends in a file and a page.`

One framed **real crop**: `plates/sourced-panel.webp` — the product's details
panel for Nexus Trading Ltd, red source links visible, shown ≤ native width
(~698px), centred or offset with copy beside it. Body copy (from v1, keep): "A
fact exists here only if it has a verbatim quote, a page and a file. Paraphrase
the model cannot ground is rejected, not published." Caption: `Loupe — actual
product interface`. This is the only place the page says "this is the real UI" —
say it.

### 4.8 Surfaces — new `sections/Surfaces.tsx` (replaces Lenses)

Eyebrow: `One structure`. H2 direction: `The same case, from every angle.` Lede:
finding in one view is the same object in every other.

Four exhibits, alternating or stacked with generous space — each a contained
frame + one-line body stating what to notice:
1. `plates/timeline.webp` — one chronology across every source, citations inline.
2. `plates/map.webp` — geocoded locations with confidence shown honestly.
3. `plates/audio.webp` — speaker-separated transcript, conversation map, seekable.
4. `CommsCenter` component (exists, keep as-is) — phone extractions kept whole.

No Financial exhibit (product defect). All plates ≤ native width, framed,
captioned. Mobile: stacked, natural downscale, captions carry the meaning.

### 4.9 Act III — edit `NarrativeSections.tsx`, `narrative.css`, `FinalCta.tsx`

Keep the four arguments (difference / capability / proof / audience) and CTA but:
- Cut total Act III length by ~a third; merge or shorten anything restating Act II.
- DifferenceSection leads with the bounded-claims argument (rejected claims are
  quarantined, the agent asks before guessing, answers refuse to exceed sources).
- Ensure `id="deployment"` exists for nav. Verify no retired phrases. Tighten
  spacing to the rhythm scale; kill any 100svh min-heights.

## 5. Plates (real-capture crops)

Sources: `landing/captures/*.png`, 2560×1440 @1×. Output:
`landing/public/product/plates/<name>.webp`, quality 82–86. Never upscale. Choose
windows with the largest legible UI text; verify by reading the result. Exact
target widths (px, native):

| Plate | Source | Width | Content |
|---|---|---|---|
| `sourced-panel.webp` | graph-detail-light.png | 698 | Details panel: title, Overview, red source links |
| `timeline.webp` | timeline-light.png | 1400 | Dated groups, entity chips, inline citations |
| `map.webp` | map-light.png | 1400 | European cluster + confidence legend |
| `audio.webp` | audio-transcript-light.png | 1500 | Transcript turns + conversation map + search |
| `agent-chart.webp` | agent-chart-light.png | 1000 | Chart artifact panel only, no chat column |
| `agent-report.webp` | agent-report-light.png | 1000 | Report artifact: sections, citations, export |

## 6. Shared primitives (assembler provides — build against these contracts)

- `Reveal` (`src/components/primitives/Reveal.tsx`): `<Reveal delay={ms}>` wraps
  children, fades/translates in once on intersection, inert under reduced motion.
- `.receipt` class in `base.css`: mono, 0.75rem, `--accent` on paper /
  `--accent-bright` on dark via `.receipt` + `.receiptOnDark`, underline on the
  file part. Usage: `<span className="receipt">03_bank_statement_nexus.pdf, p.1</span>`.
- `PinnedSequence`, `CommsCenter`, `useScrollProgress`/`segment`,
  `useMediaQuery`/`useIsNarrow`/`usePrefersReducedMotion` as today.

## 7. Definition of done (every section)

- Fills its height; no voids; ≤ ~120svh except the graph track.
- Legible at 2560, 1440, 1024, 768, 390. No horizontal overflow.
- Reduced motion: complete and static. Keyboard focus visible on interactives.
- No retired phrases; no invented case facts; captions on all product imagery.
- `npm test` invariants hold (do not edit `claims.ts`, `case.ts`, or their tests).
