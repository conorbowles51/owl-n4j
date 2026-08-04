# Loupe landing page redesign — design

**Date:** 2026-08-04
**Status:** Approved for planning
**Scope:** `landing/` only. No changes to `frontend_v2`, `backend`, or `evidence-engine`.

---

## 1. Why

The current site is well-branded and well-written, and it does not sell the product.

Measured, not asserted — the live page at 1440px is **10,579px tall across ten sections**, and
nine of those ten share one shape: mono eyebrow → large headline → lede paragraph → grid of
text cards. There is **one product image module** (`ProductExplorer`), placed fifth, rendering a
2557px-wide screenshot into roughly 1200px so the interface is illegible. Several section gaps
run to ~500px of empty page because section padding is a constant rather than a response to
content weight.

The consequence is that every claim on the page is an assertion the reader cannot check.
"Bring every source into one connected investigation" is true — the code does exactly that —
but with nothing on screen to attach it to, it reads as the same noise every AI company emits.

Three things the product does are invisible on the current site, and all three are
transformations *over time* that a static screenshot cannot express:

1. Mixed, hostile-format evidence becoming a queryable model.
2. An overwhelming graph being reduced to the things that matter.
3. An agent that asks a clarifying question and returns work product rather than prose.

### What survives

- The brand system. Space Grotesk / IBM Plex Sans / IBM Plex Mono, obsidian + Loupe red, the
  shared entity-colour palette. It is distinctive and appropriately serious.
- The prose quality. Sentences are good; there are simply far too many of them doing work that
  images should do.
- The comparison table's argument.
- The deployment / single-tenant trust content.
- The 3D lens as an identity asset — demoted from hero payload to mark and ambient element.

---

## 2. Decisions taken

| Decision | Choice |
|---|---|
| Imagery strategy | **Hybrid** — rebuilt components for the three motion beats, real screenshots for proof beats |
| Screenshots | Captured fresh from a live stack against the re-ingested demo case |
| Scope | **Aggressive reshape** — keep brand tokens and the best copy, rebuild section architecture and module vocabulary |
| Reduction beat naming | **Show the mechanic, name it loosely.** Language must survive Significant → groups/Loupes |
| Workspace | **Omitted entirely.** Revisit when it ships |
| Ingest duration | **Stated plainly.** "Runs unattended overnight" |

### Honesty constraint on rebuilt components

Every rebuilt component must use the app's real design tokens (`loupe-brand.css` values, the
entity-colour palette, the type stack, 4px spacing) and real demo-case data — Victoria Blackwood,
Nexus Trading Ltd, Cayman National Bank, the actual transaction amounts. A rebuilt component is a
faithful reduction of a real surface, never an invention. Where a rebuild depicts scale beyond the
demo case (see §5, beat 3), the density is representative and must be captioned as illustrative.

---

## 3. Verified claim set

Only these figures may appear as fact. Every one is directly observed in production use.

| Claim | Status |
|---|---|
| 30,000 entities and 90,000 relationships in a single matter | Observed |
| Five matters at approximately that scale on one instance concurrently | Observed |
| Five phone extractions in a single case | Observed |
| A few hundred documents per matter | Observed |
| Ingest of a few hundred documents takes 12–24 hours | Observed |
| Many hours of audio per matter | Observed |

**Retired claims.** The following appear on the current site and are **not** supported. They must
be removed, not softened:

- "two hundred thousand documents" (`DifferenceSection`, Scale row)
- "five hundred hours of audio" (same row)
- "Ten phones" → becomes five

**Demo-case numbers** (104 nodes, 135 edges, 13 entity types) may appear **only** as pixels inside
a screenshot, where the existing "Interface shown with illustrative case data" caption carries them.
They must never be promoted to headline or stat-strip copy — 104 reads as a toy and caps the
reader's sense of the product two orders of magnitude below where it operates.

---

## 4. Product facts the page is built on

Established by reading the codebase, not from existing marketing copy.

**Intake** (`evidence-engine/app/pipeline/extract_text.py`): PDF via PyMuPDF with automatic
per-page Tesseract OCR fallback for scanned and mixed documents; DOCX; XLSX/CSV per sheet;
HTML/Markdown; EML; images via Tesseract or OpenAI Vision plus EXIF; audio via Whisper with
FFmpeg chunking above 25MB; video via keyframe extraction plus audio transcription. Unknown
binaries are rejected rather than decoded as garbage. Cellebrite UFDR parsed to first-class
records.

**Pipeline** (`app/pipeline/orchestrator.py`): seven sequential stages — text extraction →
chunking and embedding → two-pass entity then relationship extraction → three-phase entity
resolution (blocking, embedding similarity, LLM confirmation) → relationship resolution →
summary generation → graph write. Geocoding and RAG embedding alongside.

**Evidence boundary**: only source-grounded verbatim quotations become claims. A bounded
entailment verifier labels claims verified, rejected or uncertain. Rejected and uncertain claims
remain auditable but are quarantined from summaries and graph projection. Projected nodes and
edges carry `source_claim_ids`.

**Views** (`frontend_v2/src/app/routes.tsx`): graph, timeline, map, table, financial, cellebrite,
profiles, evidence, chat, agent, reports. Cellebrite alone has nine tabs including Comms Center,
unified contacts, locations, cross-phone graph and intersections.

**Reduction**: `CaseLayerSwitcher` toggles between "All data" and "Significant", and the choice
follows the user across graph, timeline, map and table. Backed by `SignificantEntity` in Postgres —
a durable curation manifest over canonical Neo4j data. Successor design in `docs/loupes-design.md`.

**Agent** (`backend/services/agent/tools.py`): eighteen tools. Notably `request_clarification`,
which pauses and asks the user a question with 2–4 options when a request is ambiguous, rather
than guessing. Produces graph, table, chart, map and report **artifacts**.

**Deployment**: single-tenant, one isolated stack per customer, in-jurisdiction or on-premises,
per-case membership enforced per API route.

---

## 5. Page architecture

Three acts: setup → demonstration → argument. The demonstration is the bulk of the page and
follows **one case** end to end — the same names, files and amounts in every module.

### Act I — Setup (~1.5 screens)

**1. Hero.** Full-bleed dark. Headline top-left. The real graph view bleeds off the right and
bottom edge **at true scale**, so the reader sees genuine interface density rather than a shrunk
thumbnail. Headline "Query the whole case." is retained. Stat strip replaces the current
"Every source, connected. Every finding, traceable.":

> One matter: thirty thousand entities, ninety thousand relationships, every fact citing its page.

3D lens demoted to mark and ambient element.

**2. The problem, as a scene.** One tight module, no card grid. Sourced from
`20-platform-market-fit-comparison.md`, which contains the strongest writing in the repo:

> You receive the evidence. You didn't collect it and you can't. Five phones, hundreds of
> documents, formats built by the other side, and a court date. What wins is frequently what is
> *absent* — the message that puts someone somewhere else, the date that doesn't line up.

Replaces the current `ProblemSection`, which is a four-card feature list, not a problem statement.

### Act II — Demonstration (~5 screens, sticky-pinned scroll sequences)

**3. Everything goes in.** *Rebuilt.* A mixed, heavy intake streams into an evidence list —
UFDR alongside scanned discovery alongside audio — with type badges resolving as rows land. The
claim here is **format variety, not file count**. Caption names the real machinery: UFDR parsed to
individual calls and messages; scanned PDFs OCR'd page by page; audio transcribed and
speaker-separated. Includes the ingest-window line: *runs unattended overnight*.

**4. It becomes a model.** *Rebuilt.* Seven stages tick through one file. Entity chips emerge as
they do — `Victoria Blackwood · Person`, `Nexus Trading Ltd · Organization`, `$41,000 · Transaction` —
each carrying its source quote. The point that must land: a fact exists here only if it has a
verbatim quote, a page and a file. Unsupported paraphrase is rejected, not published.

**5. Now reduce it.** *Rebuilt. The centre of the page.* A field dense enough to read as
*thousands* of nodes — an unreadable swarm, which is honest, because the graph being enormous is
the problem and not the pitch. Then the reduction: the swarm collapses to the few dozen things
that matter, and the same reduction propagates in step across timeline, map and table.

Copy must survive Significant → groups/Loupes. Use "mark what matters", "the case narrows with
you". Do not name the current implementation. The durable point: judgment becomes an object in
the case, not a filter rebuilt every session.

This beat is the reason rebuild beat screenshot. A twelve-file demo case cannot depict the swarm.

**6. Work it from every angle.** *Screenshots, full-bleed, annotated.* Not a tab strip. A sequence
where graph, timeline, map, table, financial and Cellebrite Comms Center each get real size, with
callouts pointing at the specific thing that matters — a claim quoting `02_company_registry_nexus.pdf`,
a speaker-attributed transcript, resolved counterparties.

**7. Ask it, and get work back.** *Rebuilt.* The agent exchange plays: a question types in; the
agent **asks a clarifying question with options** rather than guessing; the user picks; a table
artifact materialises with real rows. Caption: eighteen tools over the case model, returning
tables, charts, subgraphs, maps and reports that stay part of the investigation.

**8. The work product.** Short. Report, export, notebook.

### Act III — Argument (~3 screens)

**9. Why this isn't a chatbot.** The existing comparison table, moved to *after* the
demonstration where it has teeth. Scale row rewritten per §3.

**10. Capability.** Retained content, restyled as a dense datasheet — mono, tight, technical.
This is the "prove you do X" section and should read as a spec sheet, not airy cards.

**11. Deployment and isolation.** Retained, tightened.

**12. Who it's for.** Retained, tightened to three.

**13. CTA and footer.** Retained.

---

## 6. Craft rules

These address the "it looks alright but it's mid" problem directly.

- **No two adjacent sections share a module shape.** Define distinct archetypes — full-bleed
  product frame, split annotated screenshot, sticky step sequence, dark inversion, dense spec
  table, quiet single statement — and alternate deliberately.
- **Vertical rhythm responds to content weight.** Replace the constant section padding that
  produces the current ~500px voids.
- **Product frames go edge-to-edge or near it.** The existing fake window chrome eats width and
  adds nothing; drop it or make it earn its place.
- **Scroll choreography is the content.** Replace the blanket fade-up applied by `Reveal` to
  every element with pinned sequences where scroll position drives the transformation being
  described.
- **Dark/light alternation carries meaning.** Dark is the case and the machine; light is the
  paper and the argument.
- **Entity-colour dots recur as a motif**, tying the site visually to the application.
- **Copy reduces by roughly half.** Most current sections state their point three times — in the
  heading, in the lede, and again in the card bodies. Pick one.
- **Type scale gains real hierarchy.** Current h2s are uniform regardless of section importance.

---

## 7. Screenshot capture

Fixed 2560×1440 viewport, consistent across every shot, driven via Playwright against the live
stack. Required case state:

- Nexus Trading demo case fully processed (the twelve PDFs in `evidence-data/`)
- Six to ten entities marked Significant — required for the reduction reference
- A Cellebrite extraction loaded, for Comms Center — currently no imagery of this exists anywhere
- Financial transactions categorised; map locations geocoded
- One agent thread with a table artifact, one with a chart artifact
- One report built

Any state that cannot be produced becomes a rebuilt component instead.

---

## 8. Out of scope

- Any change to `frontend_v2`, `backend`, or `evidence-engine`
- Workspace (witnesses, theories, findings, tasks, witness matrix)
- Contact form backend — the existing mailto flow in `ContactModal` is retained
- Renaming or rebranding — Loupe is settled
