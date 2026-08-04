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

Four things the product does are invisible on the current site. Three are transformations *over
time* that a static screenshot cannot express; the fourth is the reason the product exists at all:

1. Mixed, hostile-format evidence becoming a queryable model.
2. An overwhelming graph being reduced to the things that matter.
3. An agent that asks a clarifying question and returns work product rather than prose.
4. **Cross-source corroboration** — a fact no single document establishes, held up by several
   independent sources that the model resolved into the same objects. See §4.1.

A fifth capability, speaker-separated audio transcription, is claimed in a bullet on the current
site and illustrated nowhere, despite being one of the best-evidenced things in the product.

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
| Cellebrite / UFDR | **Rebuilt from the real components, not screenshotted.** No demo extraction exists and real ones are live federal matters |
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

**Demo-case numbers** (121 nodes, 212 edges, 12 entity types) may appear **only** as pixels inside
a screenshot, where the existing "Interface shown with illustrative case data" caption carries them.
They must never be promoted to headline or stat-strip copy — a three-figure entity count reads as a
toy and caps the reader's sense of the product two orders of magnitude below where it operates.

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

**Audio**: `AudioTranscriptViewer` renders a speaker-attributed, timestamped, in-place-searchable
transcript with a two-lane conversation map showing speaker turns across the recording, playback
speed control, and turn-level seeking. The demo case holds `call_20231219_chen_blackwood.mp3` —
4:29, 133 turns, 3 speakers.

**Deployment**: single-tenant, one isolated stack per customer, in-jurisdiction or on-premises,
per-case membership enforced per API route.

### 4.1 The finding the demonstration builds to

The demo case contains a genuine six-source convergence. This is the payoff the entire
demonstration act is structured to reach, and it replaces abstract capability claims with a single
piece of investigative reasoning the reader can follow.

**The call.** In `call_20231219_chen_blackwood.mp3` at 00:35, Victoria Blackwood says:

> "We said we'd vary the amounts — one twenty five, one eighty, ninety five, two ten, one fifty."

At 00:18–00:28 the two speakers argue about a sixth payment of "two seventy five", with Marcus Chen
arguing it is safe because *"it's year end; everyone's clearing budget in December; it's the least
strange month of the whole year to move a number like that."* Blackwood objects: *"that is a line
going up. A first year analyst draws that on a napkin."*

**The ledger.** Independently extracted from `03_bank_statement_nexus.pdf`, the monthly payment
totals to Nexus Trading across 2023 are €125,000 · €180,000 · €95,000 · €210,000 · €150,000 —
the same five figures in the same order — followed by €275,000 in December. The chart artifact
shows a line going up. Blackwood's objection is visible in the bar heights.

**The interviews.** Marcus Chen says on the call that *"David releases it Wednesday."* In
`07_interview_david_okonkwo.pdf`, Okonkwo says Chen told him *"if I helped, there would be
something in it for me — a promotion, a bonus."* The call's own summary records David being
promised *"a bonus and an increase in the January cycle."*

**The pass-through.** From the agent's report artifact: the six wires total €1,035,000 in; six
matching transfers total €1,000,000 out to Sapphire Investments, two to five days after each
credit — 96.6%. The FCIB suspicious activity report, filed independently, characterises the same
pattern as 97% rapid pass-through with one income source and one outgoing destination.

**The phrase.** The December invoice description is *"Year-End Advisory Services"*, dated
20 December. On the call recorded **19 December**, Marcus Chen says at 00:21 — *"Year end
advisory."* — and at 00:23, *"It goes in tomorrow."* The words spoken on the phone are the invoice
description filed the next day. This is the tightest corroboration in the case and the one the
page should land last.

Six independent sources — a recorded call, a bank statement, two interview transcripts, a
regulator's own filing, and an invoice description — resolved into the same objects and agreeing on
one arrangement. No single source establishes it; the model does.

### 4.2 The limit the product states about itself

The report artifact says, unprompted, that the materials *"do not prove that the entire €2.45
million purchase price derived solely from GlobalTech's €1.035 million"*, and carries a section
headed **"Evidentiary caveats and open questions."**

An AI declaring the boundary of its own answer is the most valuable trust asset in the product, and
it is the GTM position — *source-backed outputs, not AI certainty* — demonstrated rather than
claimed. Every competitor demo shows confident answers; showing a limit is the stronger move to a
buyer who gets cross-examined. This belongs in Act III alongside the deployment content, not buried
in the agent beat.

**Presentation constraint.** This is fictional demo data and must carry the standing "illustrative
case data" caption wherever it appears. The capability it demonstrates — cross-source corroboration
between audio, financial records and documents, with every element citing its origin — is real, and
that is what the copy claims. The copy must never imply this is a real matter.

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
they do — `Victoria Blackwood · Person`, `Nexus Trading Ltd · Organization`, `€125,000 · Transaction` —
each carrying its source quote. The point that must land: a fact exists here only if it has a
verbatim quote, a page and a file. Unsupported paraphrase is rejected, not published.

Amounts and names must come from the current case (EUR, Nexus/Sapphire/Azure Horizon), not the
earlier ingest. Do not reuse `$41,000` or other figures from superseded screenshots.

**5. Now reduce it.** *Rebuilt. The hinge of the act.* A field dense enough to read as
*thousands* of nodes — an unreadable swarm, which is honest, because the graph being enormous is
the problem and not the pitch. Then the reduction: the swarm collapses to the few dozen things
that matter, and the same reduction propagates in step across timeline, map and table.

Copy must survive Significant → groups/Loupes. Use "mark what matters", "the case narrows with
you". Do not name the current implementation. The durable point: judgment becomes an object in
the case, not a filter rebuilt every session.

This beat is the reason rebuild beat screenshot. A twelve-file demo case cannot depict the swarm.

**6. Work it from every angle.** *Screenshots, full-bleed, annotated.* Not a tab strip. A sequence
where each surface gets real size, with callouts pointing at the specific thing that matters:

- **Graph with the entity detail panel open.** The highest-value single screenshot in the set —
  every sentence of the Nexus Trading summary terminating in a source link. The callout does no
  more than point at them.
- **The audio transcript viewer.** Speaker attribution, the two-lane conversation map, timestamps,
  in-transcript search. Previously unillustrated and now among the strongest assets.
- **Timeline, map, table, financial.** Subject to what the live data supports; verify before
  committing page space.
- **Cellebrite Comms Center.** Rebuilt from `CommsTab.tsx` / `CommsThreadList.tsx` /
  `CommsThreadView.tsx` with fictional thread content, per §2.

**7. The convergence.** *Hybrid, and the payoff of the whole act.* Three panels resolving in
sequence against the material in §4.1: the transcript turn where Blackwood recites the five
amounts; the chart artifact showing the same five amounts extracted independently from the bank
statement; the interview quote corroborating the promise made to the payment processor. Then the
line the entire page has been earning:

> No single source establishes this. Each one is unremarkable alone. The model is what makes them
> the same arrangement.

This beat is the answer to "what does your product actually *do*", and it is the reason the page
follows one case rather than listing features.

**8. Ask it, and get work back.** *Rebuilt, with real artifact screenshots.* The investigator's
loop closes: having seen the convergence, they ask the agent to formalise it. A question types in;
the agent **asks a clarifying question with options** rather than guessing; the user picks; an
artifact materialises. Two artifacts carry this beat:

- The **contradiction table** — four material conflicts between the Chen and Okonkwo interviews,
  each with quote and source. Capture from the artifact panel, not the chat column, where the
  column widths are cramped.
- The agent's **own statement of scope** — its note that it excluded Okonkwo's unopposed claims
  because they are not conflicting accounts. An AI declaring the boundary of its own answer is
  unusual and directly evidences "proposes while the investigator disposes." Worth its own callout.

Caption: eighteen tools over the case model, returning tables, charts, subgraphs, maps and reports
that stay part of the investigation.

**9. The work product.** Short. Report, export, notebook.

### Act III — Argument (~3 screens)

**10. Why this isn't a chatbot.** The existing comparison table, moved to *after* the
demonstration where it has teeth. Scale row rewritten per §3.

**11. Capability.** Retained content, restyled as a dense datasheet — mono, tight, technical.
This is the "prove you do X" section and should read as a spec sheet, not airy cards.

**12. Deployment and isolation.** Retained, tightened.

**13. Who it's for.** Retained, tightened to three.

**14. CTA and footer.** Retained.

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

Captured 2026-08-05. Full detail in `docs/superpowers/plans/capture-manifest.md`.

Fixed 2560×1440 viewport, consistent across every shot, driven via Playwright against the live
stack. Frontend on `:5174`, backend on `:8002`.

**Case state — confirmed present:**

- Nexus Trading demo case processed: 121 nodes, 212 edges, 12 entity types
- 12 entities marked Significant, reducing to 12 nodes / 24 edges / 6 types
- `call_20231219_chen_blackwood.mp3` processed — 4:29, 133 turns, 3 speakers
- Evidence folders created (Bank Records, Disclosure — tranche 1, Interviews, Phone Calls)
- Agent threads: key players (with clarification), contradiction table, paths graph, payments
  chart, report

**Still to verify before committing page space to them:** map geocoding, timeline density,
financial view content, report rendering. Anything thin gets rebuilt rather than shot.

**Graph capture requires two passes at different force settings**, because the two shots make
opposite arguments:

| Shot | Link distance | Repulsion | Purpose |
|---|---|---|---|
| The swarm | ~80–100 | ~-200 | Dense, hairball, deliberately overwhelming — the problem |
| The structure | 160 | ~-550 to -600 | Separated and legible — the resolution |

At the default -440 the top cluster labels collide (`CNB-449827156`, `2020-03-20 transfe…`,
`Approximate €1,000…`, `FCIB-7729384756`). Zoom-to-fit after settling so nothing clips at the
bottom edge. In the Significant view, `Marcus Wei Chen` and `David Okonkwo meet…` overlap and need
a manual nudge.

**Capture the contradiction table from the artifact panel, not the chat column** — chat-column
rendering wraps mid-word (`deliverabl es existed`, `procedure s applied`).

---

## 8. Out of scope

- Any change to `frontend_v2`, `backend`, or `evidence-engine`
- Workspace (witnesses, theories, findings, tasks, witness matrix)
- Contact form backend — the existing mailto flow in `ContactModal` is retained
- Renaming or rebranding — Loupe is settled
