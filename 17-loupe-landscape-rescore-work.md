# Loupe competitive landscape — honest rescore (working file)

**Trigger: "continue landscape" / "continue rescore" → read this file, resume from ▶ NEXT.**
Keep this file updated at every step.

Started 2026-07-27. Owner: Neil. Register: **candid internal** (unshipped marked unshipped).

---

## Why this rework exists

The published matrix scored Loupe **99/120 capability, 5/40 readiness**. Neil's call, and it's
correct: **nine of the twelve capability axes were restatements of Loupe's own thesis**
(auto-built case graph, phone-as-structured-evidence, cross-source unification, whole-corpus
traversal, multimodal entities, AI-at-ingestion, constructive workspace, durable judgment
objects, disconfirmation). That is a spec sheet with competitors scored against it, not a market
comparison. 99/120 was the arithmetic consequence of axis selection. The four readiness axes were
a patch on a structural problem, not a fix.

Two triggering inputs:
- **Alex Solórzano** (she/her) surfaced an entire missing category — Case & Investigation
  Management — and Neil agreed to add it. She also misread the doc three ways (thought Loupe
  intended to give the platform to public defenders free; it says **Longeye** does, and recommends
  *against* that market for that reason). Neil conceded "**so it is misleading in that sense**".
- Neil: *"you need to include more than just a few things we do well… Siren doesn't even have a
  case workflow. Nuix is all about that. These things matter."* Both confirmed true — see chunk 2.

**Working constraints (Neil, explicit):** throttle research, **no agent fleets / no parallel
sweeps** (a previous run killed his quota), post an update per chunk so he isn't blocked waiting.
Do research sequentially with WebSearch, prefer reading `16-loupe-competitor-dossiers.md` over
re-searching.

---

## The 28-axis frame (APPROVED by Neil 2026-07-27)

280 points. Neil explicitly required **processing & format breadth** be included. Commercial
accessibility reinstated (the old "purchasable by this buyer" axis — the market-lens gating
depends on it). Vendor viability added.

**A. Evidence modelling /60**
1. Auto-built case graph
2. Device/phone data as structured evidence
3. Cross-source unification (phone + docs + financial)
4. Whole-corpus relational query (traversal vs retrieval)
5. Multimodal entities into the model
6. Per-claim provenance

**B. Investigative analysis /50**
7. Link/network analysis maturity
8. Timeline & chronology
9. Geospatial analysis
10. Financial/transaction analysis
11. OSINT & external enrichment

**C. Processing & casework /70**
12. Processing & format breadth  ← *Neil's required addition*
13. Case & investigation workflow management
14. Review workflow at scale (batching, coding, QC)
15. Disclosure & production mechanics (redaction, privilege log, Bates, load files)
16. Analytics/TAR (active learning, threading, near-dupe)
17. Collaboration & permission granularity
18. Durable judgment/narrative objects

**D. AI layer /30**
19. Cited document Q&A quality
20. Agentic task execution
21. Disconfirmation/contradiction detection

**E. Readiness & commercial /70**
22. Certifications & compliance
23. Proven scale
24. Ecosystem integrations
25. Evidence acquisition
26. Forensic validation & courtroom defensibility
27. Vendor viability & support
28. Commercial accessibility to the buyer

**Scoring bands (unchanged from v1):** 8–10 shipped & evidenced · 3–7 partial/gated/unverified ·
0–2 no public evidence. "No public evidence" = searched product pages, docs, release notes, press
and not found — flag absence-of-evidence vs proven-absence per vendor.

---

## Chunk plan & status

| # | Chunk | Status |
|---|---|---|
| 0 | Axis frame + rubric | ✅ done, approved |
| 1 | Case & investigation management (9 platforms) | ✅ done |
| 1b | Second sweep of the same category — 9 new candidates found via Gartner category + ShadowDragon integrators | ✅ done |
| 2 | eDiscovery (7 platforms) | ✅ done |
| 3 | Forensics/DFIR — Cellebrite Pathfinder, Cellebrite Guardian Investigate, Magnet Axiom/One, Exterro FTK/ARMOUR (+ axis 26) | ✅ done |
| 4 | Graph, link & enterprise intel — Siren, Octostar, Linkurious, Maltego, DataWalk, Palantir, IBM i2, Babel Street | ✅ done |
| 5 | Legal AI + AI-native defence — Harvey, Hebbia, CoCounsel, Clearbrief, CaseMap+, Casefleet, TrialKit, Matey/CrimD, JusticeText, Longeye | ✅ done |
| 6a | Requirement profiles — the 7 existing lenses, re-authored for 28 axes | ✅ done (+ axis 29 added) |
| 6b | Requirement profiles — the 8 new markets | ✅ done |
| 7a | Axis 29 scored for all 47 · totals recomputed on 29-axis/290 basis · Loupe rescored (151) · **market+price lens BUILT & PUBLISHED** | ✅ done |
| 7b | All 9 edits merged into the narrative artifact + republished to the same URL | ✅ done |
| 7c | Axis-26 split approved by Neil and applied — frame is now **30 axes / 300** | ✅ done |

Chunks 4–5 are mostly **rescoring against evidence already in `16-loupe-competitor-dossiers.md`** —
far less new searching than chunk 1 needed.

---

## Scores so far — 16 platforms / 280

| Platform | A /60 | B /50 | C /70 | D /30 | E /70 | **Total** |
|---|---:|---:|---:|---:|---:|---:|
| Palantir Gotham / AIP | 40 | 40 | 41 | 16 | 49 | **186** |
| Magnet Axiom / Magnet One | 38 | 27 | 40 | 12 | 57 | **174** |
| Cellebrite Guardian Investigate | 35 | 29 | 37 | 11 | 54 | **166** |
| Everlaw | 24 | 16 | 60 | 17 | 48 | **165** |
| Relativity (aiR) | 20 | 16 | 61 | 16 | 51 | **164** |
| Cellebrite Pathfinder | 37 | 31 | 30 | 7 | 56 | **161** |
| Exterro FTK / ARMOUR | 31 | 20 | 40 | 16 | 52 | **159** |
| Cognyte NEXYTE | 33 | 35 | 34 | 13 | 43 | **158** |
| Nuix Neo | 27 | 19 | 54 | 11 | 46 | **157** |
| Axon (Records / Evidence / Draft One) | 25 | 18 | 40 | 10 | 54 | **147** |
| **Loupe** (provisional) | **55** | **30** | **22** | **19** | **16** | **142** |
| NICE Investigate | 28 | 21 | 41 | 6 | 46 | **142** |
| Babel Street | 25 | 33 | 25 | 12 | 43 | **138** |
| DISCO (Cecilia) | 20 | 12 | 52 | 15 | 36 | **135** |
| Reveal / Logikcull | 19 | 13 | 52 | 11 | 40 | **135** |
| Hubstream | 24 | 31 | 36 | 8 | 35 | **134** |
| DataWalk | 33 | 34 | 28 | 8 | 30 | **133** |
| CaseMap+ AI (LexisNexis) | 19 | 18 | 41 | 10 | 43 | **131** |
| Altia | 17 | 37 | 30 | 6 | 40 | **130** |
| CoCounsel (Thomson Reuters) | 18 | 12 | 35 | 16 | 48 | **129** |
| Matey / CrimD | 30 | 14 | 37 | 11 | 37 | **129** |
| Casepoint | 16 | 9 | 49 | 12 | 41 | **127** |
| Blackdot Videris | 19 | 33 | 25 | 10 | 38 | **125** |
| IBM i2 (i2 Group) | 18 | 35 | 28 | 0 | 44 | **125** |
| JusticeText | 23 | 11 | 35 | 16 | 38 | **123** |
| Longeye | 32 | 15 | 30 | 11 | 35 | **123** |
| Neotas | 16 | 28 | 25 | 10 | 41 | **120** |
| Casefleet | 19 | 16 | 36 | 12 | 37 | **120** |
| Ontic | 16 | 24 | 32 | 6 | 41 | **119** |
| TrialKit | 33 | 12 | 33 | 11 | 29 | **118** |
| Harvey | 17 | 10 | 35 | 17 | 38 | **117** |
| Siren | 29 | 30 | 19 | 9 | 27 | **114** |
| Maltego | 9 | 31 | 20 | 5 | 48 | **113** |
| Kaseware | 15 | 26 | 30 | 4 | 37 | **112** |
| Hebbia | 20 | 7 | 35 | 16 | 34 | **112** |
| Comtrac | 16 | 13 | 40 | 10 | 32 | **111** |
| Resolver (Kroll) | 9 | 17 | 33 | 8 | 40 | **107** |
| Clearbrief | 15 | 10 | 26 | 16 | 40 | **107** |
| Case IQ | 9 | 14 | 33 | 7 | 41 | **104** |
| Octostar | 28 | 25 | 21 | 8 | 18 | **100** |
| Linkurious | 19 | 25 | 18 | 5 | 30 | **97** |
| ShadowDragon | 14 | 27 | 13 | 4 | 38 | **96** |
| Case Closed Software | 13 | 16 | 27 | 2 | 32 | **90** |
| HR Acuity | 9 | 9 | 30 | 5 | 37 | **90** |
| Omnigo | 8 | 14 | 27 | 3 | 34 | **86** |
| CROSStrax | 6 | 14 | 20 | 2 | 27 | **69** |
| Trackops | 6 | 11 | 19 | 2 | 26 | **64** |

**47 platforms scored. Loupe is 11th.** Still #1 on Group A by a wide margin (55 vs Palantir 40),
but only **6th on Group B** — investigative analysis is not a Loupe strength once OSINT and mature
link-analysis UX are on the board.

### Chunk 1b findings
- **NICE Investigate ties Loupe at 142 — and scores 8/10 on disclosure mechanics**, the axis Loupe
  scores ~2 on. Disclosure to justice partners, against deadlines, is a *designed core feature*.
  A police platform is built around disclosing evidence to the defence; the defence-side product
  has no disclosure capability at all. Worth stating plainly in the doc.
- **Axon scores 147 and beats Loupe.** Draft One (report drafting from body-cam audio) reports
  **50–80% reduction in admin time**; Axon Evidence spans "capturing, reviewing and disclosing";
  acquisition 9/10 because the body-cams *are* the acquisition. Scored as a matrix row (it is a
  real competitor in the `prosecution` and `ukpolice` lenses) **and flagged for the threat
  register** — same shape as T1 Cellebrite, from the opposite direction: Axon moving *up* from
  records into investigation.
- **The two most commercially accessible platforms in all 37 are Trackops ($99/mo) and CROSStrax
  ($35/mo)** — both serving *exactly* Loupe's beachhead buyer, and both with essentially no
  evidence-analysis capability (Trackops 6/60 on Group A, the lowest score in the study). **This is
  the whitespace claim proven precisely:** the beachhead buyer already has cheap workflow tooling
  and nothing that analyses evidence. Use these two as the anchor, not i2/Logikcull.
- **Ontic holds SOC 2 Type II and is FedRAMP "In Process"** — another certified competitor Loupe
  cannot match. Case workflow 9/10.
- **Hubstream (134)** is more capable than expected: AI link analysis, DataSpace adapting between
  maps/link-analysis/timelines, 28 CFR Part 23 compliance.
- **Blackdot Videris (125)** — OSINT-led link analysis for financial crime; 9/10 OSINT, 8/10
  financial. Another platform beating Loupe on Group B.
- Honest low-evidence flags: Case Closed, Trackops and HR Acuity have thin public technical
  documentation. Their low Group A/B scores are **absence of evidence**, not proven absence —
  though for PI billing tools the inference is safe.

**Loupe is 5th, not 1st.** 55/60 on evidence modelling (next best 33). **22/70 on process — last in
the set.** 16/70 readiness. This is the honest shape and it must stay.

**All scores except Loupe's are provisional single-sweep estimates, not dossier-grade.**
Loupe's own row still needs a proper rescore in chunk 7.

---

## Findings so far

### Chunk 1 — case & investigation management
- **Kaseware** — built by ex-FBI agents. Case management *plus* link analysis, timelines, entity
  recognition, geospatial. Not just workflow.
- **Altia** — 300+ LE/intel agencies **since 1996**. OSINT Investigator module, 50+ public data
  feeds, AI analytics, geospatial, financial crime. Most analytically capable of the nine.
- **Comtrac** — "Elementising Evidence™" maps exhibits to **offence elements**, auto-populates an
  investigation matrix with what must be proven, AI-assisted, generates court-ready briefs. Closest
  shipped analogue anywhere to Loupe's Significant layer + Loupes + report builder. Needs a full
  dossier.
- **Case IQ** — SOC 2 Type II + ISO/IEC 27001:2022.
- **Resolver (a Kroll business)** — 1,000+ global companies, $6.5T market cap protected.
- **Neotas** — 600B+ archived pages, 1.8B+ court records, 198M+ corporate filings, 40k+ media
  sources, entity network analysis, ongoing monitoring. Dominates axis 11 where Loupe is 0.
- **Omnigo** — incident/public safety. Lower relevance.
- **CROSStrax** — built for private investigators. **$35/month entry plan.**
- **Cognyte NEXYTE** — already in matrix at 65/120; **its case-management capability was missed**
  (compartmentalised case policies, segmented access, full user auditing, agentic decision flows).

**Doc consequences:** (1) the §08 pricing-whitespace claim needs qualifying — CROSStrax at
$35/mo serves the exact beachhead buyer, so "real evidence capability at an accessible price"
survives but the buyer's price anchor does not; possible integration partner. (2) "nobody else
builds a graph" needs tightening — Kaseware and Altia ship link analysis/entity recognition.
(3) Comtrac cuts both ways on F10.

### Chunk 1b — second sweep of the category (queued, not yet scored)

Alex's seven were all covered in chunk 1. Chasing the `[gartner]` tags on her list revealed the
source: **Gartner Peer Insights runs a named market category, "Investigation Management
Software"** — https://www.gartner.com/reviews/market/investigation-management-software — that
several competitors are listed in and **Loupe is not**. Peer Insights listings are largely
self-serve, unlike a Magic Quadrant. Cheap credibility gap to close; raise with Neil separately.

**Useful taxonomy found (worth putting in the doc).** This category is sold through *three
different procurement motions*, which is why it looked invisible from an eDiscovery/forensics
vantage point:
1. **Police RMS modules** — Hexagon, Mark43, Omnigo, Axon Records, CentralSquare
2. **Standalone investigation CMS** — Kaseware, Case Closed, NICE Investigate
3. **Private-investigator tools** — CROSStrax, Trackops

**New candidates to score (score these, they are real platforms):**
- **Ontic** — AI "Connected Intelligence Platform"; corporate + government security, threat and
  protective intelligence; Fortune 500 and federal agencies. Maps to the proposed `corpsec` market.
- **Blackdot Solutions (Videris)** — digital-investigations software, link analysis + OSINT;
  financial crime, due diligence, law enforcement. The one genuine competitor on the ShadowDragon
  integrator list.
- **Hubstream** — investigation platform for major-crime LE work (trafficking, IP crime, child
  protection).
- **Case Closed Software** — standalone investigation CMS.
- **NICE Investigate** — DEMS-led digital evidence management + investigation.
- **ShadowDragon** (SocialNet / Horizon) — OSINT collection; integrates *into* Kaseware, i2,
  Maltego. Scores on axis 11 where Loupe is 0.
- **HR Acuity** — **#1 in G2's Winter 2026 Enterprise Investigation Management Grid**. Employee
  relations / workplace investigations → the proposed `ethics` market.
- **Trackops** — private-investigator tooling, direct CROSStrax competitor, **same beachhead buyer
  as Loupe**.
- **Axon (Records / Draft One / evidence.com)** — ⚠️ **flag as a probable threat-register entry.**
  Owns the body-cam + DEMS ecosystem, pushing hard into AI report writing and records. Enormous,
  fast-moving, and **completely absent from the study**.

**NOT competitors — do not pad the matrix with these.** Data providers: DomainTools, Anomaly Six,
District4. Services/integrators: CACI, Bantam-Tech, BeAFuture, Indicium. Compliance/EHS adjacents:
ComplianceQuest, EHS Insight, VisiumKMS, FaceUp, Case Jacket, CaseGuide. Authentic8 (managed
attribution) is investigator tooling, not a platform — mention only.

Sources: [Gartner Peer Insights market page](https://www.gartner.com/reviews/market/investigation-management-software),
[ShadowDragon integrators](https://shadowdragon.io/partner-category/integrators/),
[Case IQ alternatives](https://www.krowdbase.com/alternatives/case-iq).

### Chunk 2 — eDiscovery
- **The dossiers barely cover the new axes**: `privilege log` 0 hits, `near-dupe` 0, `Bates` 2,
  `redaction` 6 across 356 KB. The original research had the same blind spot as the matrix.
- **Group C is a rout.** Loupe 22/70 vs Relativity 61, Everlaw 60, Nuix 54. Loupe last in the set.
- **Disclosure & production mechanics (axis 15): Loupe ~2, majors 7–10.** Relativity has production
  sets, Bates, confidentiality stamping, Relativity Redact, automated privilege-log generation.
  **The current doc never mentions this gap at all.**
- **Nuix confirms Neil's point** — 1,000+ file types (10/10 processing breadth), Neo Investigations
  purpose-built (9/10 case workflow). Siren's own dossier note: *"no case object exists in the user
  guide"* → ~2. Exactly the spread Neil described.
- **Everlaw is the strongest challenge to F2** and should be named as such. Deep Dive genuinely
  reaches whole corpora, tens of millions of docs, confidence-ranked, refuses to confabulate.
  F2 survives only in its precise form: it still cannot answer a question whose answer is a
  *relationship*. Do not overstate this one.
- **Casepoint holds the strongest certifications in the study** — FedRAMP High + DOD IL5/IL6.
- **Loupe still wins Group A outright**: 55/60 vs best-competitor 27.

**The three zeros survive both chunks:** none answers by traversal, none models phone + financial +
document as one citable object set, none markets disconfirmation. Relativity's helpful/harmful +
gap-spotting remains the nearest approach anywhere (scored 2).

### Chunk 3 — forensics/DFIR
**All four score above Loupe. Loupe falls to 9th of 20.**
- **Cellebrite Pathfinder scores 37/60 on Group A — the closest anything has come to Loupe's 55.**
  It has genuine entity resolution ("correlate phone numbers, user IDs and usernames across
  platforms"), multi-device analysis, cross-case identifier search, location intelligence, CDR
  ingest. **Pathfinder does build a case graph.** What it does not do is documents or financial
  records. The "nobody else builds a graph" line needs its most careful qualification here — the
  honest claim is *cross-evidence-type*, never *graph*.
- **Axis 28 is what saves Loupe: Pathfinder 1, Guardian 1.** The dossier's defence-access table
  (§3 cross-cutting) is the single most valuable asset in the entire research corpus and should be
  **promoted into the main document**, not left in an appendix. GrayKey explicitly not sold to the
  private sector; Pathfinder has no defence sales channel found; defence gets read-only Guardian
  share links from prosecutors.
- **Magnet AI is the clearest incumbent provenance statement anywhere**: "citations and direct
  links to source evidence," "verification and decision making firmly in human hands" (Apr 2026).
  Scores 7 on axis 6 against Loupe's 9 — the narrowest gap on Loupe's strongest axis.
- **Exterro ARMOUR (launched 9 Jul 2026 — three weeks before this rescore) is the biggest agentic
  threat in the study.** Ask → plan → execute → correlate → review → document, producing "an
  auditable evidence record designed to withstand legal and regulatory scrutiny." Scores **9 on
  axis 20 against Loupe's 8** — the only platform to beat Loupe on an AI axis. Above the Law:
  *"fast, auditable, and about to bloody Daubert."* Not in the published doc's threat register at
  all. **Should be a new threat entry, arguably T2.**
- **NIST CFTT nuance worth using:** CFTT reports cover specific tool versions and **lag production
  releases by 12–24 months**; known error rate is "the factor most consistently absent from
  government digital forensic reports." So the incumbents' "forensically validated" claim is
  softer than assumed — but they still have published test reports and decades of court
  acceptance, and Loupe has neither.

### Chunk 4 — graph, link & enterprise intelligence
**Palantir Gotham/AIP scores 186 — the highest in the study, ahead of Loupe by 44.** 40/60 on
Group A (second only to Loupe's 55), **40/50 on Group B — the best investigative-analysis score
anywhere** — and 49/70 readiness. The *only* thing keeping Palantir out of Loupe's market is
axis 28: average deal >$1M, no self-serve tier. The old matrix's "Loupe and Palantir tie at 104
from opposite directions" was directionally right but flattered Loupe; on honest axes Palantir
simply wins and is then gated out commercially.

- **Neil's Siren example is confirmed and scored. Siren case workflow = 2** — its own dossier note
  reads *"Saved searches, dashboards and graphs — tool artifacts, not judgment artifacts. **No case
  object in the user guide.**"* Against Nuix Neo at 9. Exactly the spread Neil described, now
  visible in the matrix instead of invisible. Siren total 114 → 19th.
- **IBM i2 scores 0/30 across the entire AI group** — the plans page shows no LLM capability in any
  tier — **and simultaneously scores 8/10 on commercial accessibility** (~$7,160/yr single-seat,
  explicitly marketed as affordable, the one legacy vendor a small firm can actually buy). That
  single row is the market gap in miniature: *the affordable option has no AI, and the AI options
  are not affordable.* Use it in the pricing section.
- **Maltego is the most lopsided profile in the study**: 9/60 Group A, 31/50 Group B, **10/10
  OSINT**, 48/70 readiness. An OSINT analyst canvas, not an evidence platform. Confirms OSINT and
  evidence modelling are different products, which supports treating axis 11 as **N/A for criminal
  defence** in the market profiles.
- **Loupe is only 6th on Group B (30/50)** — behind Palantir 40, i2 35, DataWalk 34, Babel Street
  33, Maltego 31. OSINT 0 and link-analysis UX 7 against i2's 10. Investigative analysis is *not*
  a Loupe strength and the doc should stop implying it is.
- **Babel Street scores 8/10 on per-claim provenance** — "results are fully cited with data
  provenance showing all sources of the data points" — second only to Loupe's 9. Provenance is
  genuinely contested, not owned.
- First-hand corrections already embedded in the research and carried forward: Siren's Cellebrite
  path is "a thin Python script whose output is poorly represented in-platform" (founder knowledge,
  seven years inside Siren); Octostar **does** perform Cellebrite phone analysis despite zero public
  trace across its site bundle, 11 repos and six npm packages.

**PROPOSED: split axis 26 into two (would make 29 axes) — needs Neil's call.**
Evidence for the split: axis 26 currently conflates (a) *acquisition/parsing tool validation*
— NIST CFTT, court-tested, where Cellebrite/Magnet/FTK score 9 and Loupe scores ~1 because it
does not acquire — with (b) *defensibility of AI output*, where Loupe is genuinely strong
(grounded-claims ledger with quote + location + confidence + review status, AI content visually
distinguished in every deliverable, immutable audit trail) and the incumbents are weak: Cellebrite's
GenAI press release "contains **no** explicit statements about audit trails or citation mechanisms";
Nuix's Discover page "does **not** document citation/provenance mechanics for generative output."
Scored as one axis, Loupe gets ~2 and the distinction is lost. Split, it is 1 and 8.

**Factual error found in the published doc:** threat T4 states the Nuix/Linkurious acquisition
completed **April 2026**. The dossier says signed **4 Dec 2025**, closed **Dec 2025** with French
FDI approval. Fix in chunk 7.

---

### Chunk 5 — legal AI + AI-native defence  ⚠️ **the most uncomfortable chunk**

All ten score below Loupe. But two of them beat Loupe **on Loupe's own flagship differentiators**,
because both of Loupe's are unshipped:

- **⚠️ Disconfirmation: JusticeText scores 6, Clearbrief 5, Loupe 3.** Miranda AI "identifies
  inconsistencies across evidence"; Clearbrief's cite-checking catches fabricated citations.
  **F11's claim that disconfirmation is "unclaimed by all 26" must be softened to: unclaimed as
  marketing *positioning*, while two competitors ship the nearest capability and Loupe ships
  none.** This is currently the doc's single strongest whitespace claim and it does not survive
  contact with the defence-native set intact.
- **⚠️ Durable judgment objects: CaseMap+ 9, Casefleet 9, Loupe 5.** CaseMap has had facts, issues
  and objects since 1998 and AI now proposes facts for human conversion; Casefleet has the best
  human-in-the-loop pattern in the study (AI proposes, attorney approves, only then does it enter
  the record). Loupes are still uncommitted.
- **⚠️ Longeye's Group A = 32 — the highest of any AI-native defence startup — and cross-source
  = 7.** It is *the only competitor whose own copy names phone extractions AND bank records AND
  documents together*. That is the closest footprint claim to Loupe's in the entire 47, held by an
  a16z-funded startup giving the product to public defenders free. **The most dangerous single
  competitive claim in the study.**
- **TrialKit scores 7 on device data** — explicitly processes phone extractions alongside bodycam,
  audio and handwritten notes. Second-closest footprint.
- **CoCounsel runs a dedicated criminal-defence page with 75+ prebuilt defence workflows at
  $225–639/user/mo** — affordable, credible, Thomson Reuters-backed, sitting directly in Loupe's
  beachhead. Accessibility 7. Badly under-weighted in the current doc.
- Harvey and Hebbia are strong on AI and provenance, near-nil on anything evidence-shaped —
  Hebbia scores **0 on timeline** (no timeline feature at all) and 7/50 on Group B, the lowest
  analysis score in the study. Harvey's accessibility is 1 (~$360K/yr entry).
- Clearbrief scores **10/10 on per-claim provenance** — the only perfect score on that axis
  anywhere, above Loupe's 9. "Provenance is the product's core identity."

**Net:** Loupe's Group A lead is real and holds (55; next best Palantir 40, Longeye 32, TrialKit
33). But **three of the four claims the published doc leads with are now contested**: provenance
(Clearbrief 10, Babel Street 8, Magnet 7), disconfirmation (JusticeText 6 > Loupe 3) and durable
judgment objects (CaseMap+/Casefleet 9 > Loupe 5). Only **cross-source unification** is
uncontested — and Longeye is claiming it in copy.

## ⚠️ AXIS FRAME CORRECTION — deployment control was dropped by mistake

Authoring the profiles exposed it: the old 16-axis matrix had **"Single-tenant / on-prem"** as
axis 12, and **two of the seven existing lenses gate on it** (`fincrime` and `ukpolice`, both
"has no sovereign or on-premises deployment"). When I built the 28-axis frame I folded it away
and there is now **no axis for deployment control at all**. That is a load-bearing omission: it
is a gate in at least four markets, it is central to Loupe's own pitch (single-tenant, evidence
never leaves the instance), and Relativity's Server sunset makes it a live differentiator.

**Added as axis 29 — Deployment control (single-tenant / on-prem / sovereign).** Loupe scores 9.
Frame is now **29 axes / 290**, or **30 / 300** if Neil approves the axis-26 split still pending
from chunk 3. All 47 platform totals in the table above are on the 28-axis basis and must be
recomputed with axis 29 in chunk 7 — it will lift Loupe and the on-prem-capable vendors (Nuix,
Magnet, Exterro, Casepoint, Longeye) relative to the cloud-only ones (Everlaw, DISCO, Harvey).

---

## Chunk 6a — requirement profiles, the seven existing lenses

Banding: **G**n = Gate with threshold n (below = disqualified) · **C**n = Core with threshold n
(heavy weight) · **U** = Useful (light weight) · **–** = N/A, excluded from the denominator.

| # | Axis | defence | corporate | prosecution | insurance | journalism | fincrime | ukpolice |
|---|---|---|---|---|---|---|---|---|
| 1 | Auto-built case graph | C6 | C6 | C7 | C6 | C6 | C7 | C7 |
| 2 | Device data as structured evidence | C7 | U | C8 | U | U | – | C8 |
| 3 | Cross-source unification | C7 | C6 | C6 | C6 | C6 | C6 | C6 |
| 4 | Whole-corpus relational query | C6 | C7 | C6 | C6 | C7 | C8 | C6 |
| 5 | Multimodal entities | C5 | U | C6 | U | C5 | U | C6 |
| 6 | Per-claim provenance | C8 | C7 | C7 | C6 | C8 | C6 | C7 |
| 7 | Link/network analysis | U | C5 | C7 | C6 | C6 | C7 | C7 |
| 8 | Timeline & chronology | C6 | C6 | C7 | C6 | C6 | C6 | C7 |
| 9 | Geospatial | U | U | C7 | C6 | C5 | U | C7 |
| 10 | Financial/transaction | C5 | C6 | U | C7 | C5 | C8 | U |
| 11 | OSINT & external enrichment | **–** | C5 | C5 | C7 | C6 | C6 | C5 |
| 12 | Processing & format breadth | C5 | C6 | C6 | C5 | C6 | C5 | C6 |
| 13 | Case & investigation workflow | U | C7 | C8 | C7 | U | C6 | C8 |
| 14 | Review workflow at scale | **–** | U | U | U | U | U | U |
| 15 | Disclosure & production | U | U | C7 | U | **–** | U | **C8** |
| 16 | Analytics/TAR | **–** | U | U | U | U | C5 | U |
| 17 | Collaboration & permissions | U | C6 | C6 | C5 | C5 | C5 | C6 |
| 18 | Durable judgment objects | C5 | C5 | C5 | U | C6 | U | C5 |
| 19 | Cited document Q&A | C6 | C6 | C5 | C5 | C6 | C5 | C5 |
| 20 | Agentic execution | U | U | U | U | U | C5 | U |
| 21 | Disconfirmation | **C4** | U | U | U | C5 | U | U |
| 22 | Certifications & compliance | **G3** | **G6** | **G7** | C5 | U | **G7** | **G7** |
| 23 | Proven scale | U | C6 | C7 | C5 | U | C7 | C6 |
| 24 | Ecosystem integrations | U | C5 | C6 | C5 | U | C6 | C6 |
| 25 | Evidence acquisition | **–** | – | C6 | – | – | – | C6 |
| 26 | Forensic validation | U | U | C8 | U | – | U | C8 |
| 27 | Vendor viability | U | C6 | C6 | C5 | U | C6 | C6 |
| 28 | Commercial accessibility | **G5** | U | U | C6 | **G4** | U | U |
| 29 | Deployment control | **G6** | **G5** | **G6** | U | C6 | **G5** | **G7** |

### Rationale per market (source text for the lens's on-screen explanation)

- **defence** — This buyer *receives* evidence and never collects it, so OSINT, acquisition,
  review-at-scale and TAR are genuinely N/A rather than weaknesses. What remains is narrow and
  deep: the phone extraction that arrives in nearly every case, all of it in one model with the
  documents and bank records, every claim traceable to a page, and a chronology that can go in
  front of a judge. Disconfirmation is Core here and nowhere else at this weight — breaking the
  prosecution's theory *is* the job. Gated on certifications, purchasability and single-tenant
  deployment, because privileged material under a protective order fails all three tests
  otherwise.
- **corporate** — A workflow market first. Case management, collaboration across legal/HR/security
  and enterprise procurement discipline dominate; phone evidence is incidental. Certifications
  gate hard at 6 and deployment at 5 — the security team has to sign it off.
- **prosecution** — Owns the extraction, so device data and acquisition are Core, and disclosure
  to the defence is a legal duty rather than a nice-to-have. Forensic validation gates the
  courtroom. Certifications at 7 (CJIS/FedRAMP class).
- **insurance** — The only market with **no hard gate**: SIU teams buy tools without federal
  certification regimes. Financial analysis and OSINT dominate because the claim and the claimant's
  public footprint are the case.
- **journalism** — Excellent proof, terrible revenue. Provenance at 8 and disconfirmation Core
  because publication standards demand verification. Accessibility gated at 4 — there is no budget.
  Deployment matters for source protection. Disclosure and acquisition are N/A.
- **fincrime** — Whole-corpus query at 8 and financial analysis at 8; phone evidence is genuinely
  N/A. Gated on certifications and sovereign deployment, per the existing lens.
- **ukpolice** — Prosecution's shape plus stricter obligations: **disclosure at C8** (CPIA duties
  are harder than the US equivalent) and **deployment gated at 7** — data must stay in
  jurisdiction.

### ⚠️ The output that matters: Loupe clears the gates in 2 of 7 markets

Running Loupe's scores against the gates above:

| Market | Gates | Loupe | Verdict |
|---|---|---|---|
| defence | certs G3, access G5, deploy G6 | 1, 7, 9 | ❌ **certifications** |
| corporate | certs G6, deploy G5 | 1, 9 | ❌ certifications |
| prosecution | certs G7, deploy G6 | 1, 9 | ❌ certifications |
| insurance | *none* | — | ✅ **pass** |
| journalism | access G4 | 7 | ✅ **pass** |
| fincrime | certs G7, deploy G5 | 1, 9 | ❌ certifications |
| ukpolice | certs G7, deploy G7 | 1, 9 | ❌ certifications |

**Certifications alone gate Loupe out of five of seven markets. It is the only failed gate in every
one of them.** Loupe passes every other gate in every market — accessibility and deployment control
are both strengths. This renders the SOC 2 recommendation quantitatively for the first time:
**one certification unlocks five markets.** That single table is the strongest argument the
document will contain, and it should appear near the front.

## Chunk 6b — requirement profiles, the eight new markets

Same banding. 29 axes.

| # | Axis | pubdef | civil | regulator | corpsec | ethics | diligence | natsec | pubfraud |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Auto-built case graph | C5 | C5 | C6 | C6 | C4 | C6 | C8 | C6 |
| 2 | Device data structured | C6 | U | C6 | U | – | – | C7 | U |
| 3 | Cross-source unification | C6 | C5 | C7 | C5 | C4 | C5 | C7 | C6 |
| 4 | Whole-corpus relational query | C5 | C7 | C6 | C6 | C5 | C6 | C8 | C8 |
| 5 | Multimodal entities | **C8** | U | C5 | C5 | C5 | U | C7 | U |
| 6 | Per-claim provenance | C8 | C7 | **C8** | C6 | C7 | C7 | C6 | C7 |
| 7 | Link/network analysis | U | U | C6 | C7 | U | C7 | **C8** | C7 |
| 8 | Timeline & chronology | C6 | C7 | C7 | C6 | C6 | U | C7 | C6 |
| 9 | Geospatial | U | – | U | C7 | – | U | **C8** | C5 |
| 10 | Financial/transaction | U | C5 | C7 | U | C5 | C7 | C6 | **C8** |
| 11 | OSINT & external enrichment | – | U | C5 | **C8** | U | **C9** | C7 | C6 |
| 12 | Processing & format breadth | C5 | **C8** | C6 | C5 | C5 | C4 | C7 | C6 |
| 13 | Case & investigation workflow | C6 | C6 | **C8** | **C8** | **C9** | C6 | C6 | C7 |
| 14 | Review workflow at scale | – | **C9** | U | – | U | U | U | U |
| 15 | Disclosure & production | U | **C9** | **C8** | U | U | U | U | C6 |
| 16 | Analytics/TAR | – | **C8** | U | U | U | U | U | C6 |
| 17 | Collaboration & permissions | C6 | C7 | C6 | C7 | **C8** | C5 | C7 | C6 |
| 18 | Durable judgment objects | C5 | C6 | **C7** | C5 | C5 | C5 | C5 | C5 |
| 19 | Cited document Q&A | C6 | C7 | C6 | C5 | C5 | C6 | C5 | C5 |
| 20 | Agentic execution | U | C5 | U | C5 | U | C6 | C6 | C6 |
| 21 | Disconfirmation | C4 | U | C5 | U | U | U | U | C5 |
| 22 | Certifications | **G4** | **G5** | **G6** | **G6** | **G7** | **G6** | **G8** | **G6** |
| 23 | Proven scale | C6 | C8 | C6 | C6 | C6 | C6 | C8 | **C8** |
| 24 | Ecosystem integrations | U | C7 | C5 | C6 | C6 | C6 | C6 | C6 |
| 25 | Evidence acquisition | – | – | U | U | – | **C8** | **G6** | U |
| 26 | Forensic validation | U | U | C7 | U | U | – | U | C6 |
| 27 | Vendor viability | C5 | C7 | C6 | C6 | C6 | C6 | C7 | C6 |
| 28 | Commercial accessibility | **G8** | U | U | U | U | C6 | U | U |
| 29 | Deployment control | C5 | C4 | **G6** | **G5** | **G6** | C5 | **G8** | **G6** |

**Rationale per market:**
- **pubdef** — Same evidence problem as private defence, different economics. **Multimodal at 8**
  because bodycam and jail-call volume is the defining burden (JusticeText's entire business).
  **Accessibility gated at 8** — Longeye intends to give it away and Everlaw for Good already covers
  CJA panel attorneys; anything not free-or-near-free loses.
- **civil** — The eDiscovery majors' home turf and **the market Loupe is furthest from serving**.
  Review at scale 9, disclosure and production 9, TAR 8, processing breadth 8. Nothing about
  Loupe's evidence model matters if you cannot batch, code, QC, redact, log privilege and produce.
- **regulator** — Comtrac's market. Provenance 8 and durable judgment objects 7, because mapping
  evidence to *offence elements* is the work product; disclosure 8 because the brief of evidence
  goes to prosecution.
- **corpsec** — Ontic/Kaseware's market. **OSINT at 8** (threat-actor research, social listening,
  public records) and workflow at 8 (incident→investigation lifecycle). Geospatial matters —
  facilities, travel, executive protection.
- **ethics** — **Workflow at 9 and collaboration at 8**: intake→triage→investigate→resolve *is* the
  product, and anonymity plus need-to-know segregation is non-negotiable. Certifications gated at 7
  — the most privacy-sensitive market in the set.
- **diligence** — **OSINT at 9 and acquisition at 8.** You must go and collect; nothing is handed
  to you. Structurally the wrong shape for Loupe.
- **natsec** — Highest bar anywhere: certifications gated at 8, deployment gated at 8 (sovereign,
  air-gapped), and **acquisition gated at 6** — an analysis-only tool cannot serve this buyer.
- **pubfraud** — Population-scale: whole-corpus query 8, financial 8, proven scale 8.

### ⚠️ THE HEADLINE OF THE ENTIRE RESCORE

Loupe's gate results across **all fifteen markets**:

| Result | Markets |
|---|---|
| ✅ **Clears all gates** | insurance, journalism — **2 of 15** |
| ❌ Fails **certifications only** | defence, corporate, prosecution, fincrime, ukpolice, civil, regulator, corpsec, ethics, diligence, pubfraud — **11** |
| ❌ Fails **two gates** | pubdef (certs + accessibility 7 vs 8), natsec (certs + acquisition 0 vs 6) — **2** |

**Certifications is the failed gate in 13 of 15 markets, and in 11 of those it is the ONLY failed
gate.** SOC 2 alone takes Loupe from serving 2 markets to being eligible in 13.

Nothing else in this document comes close to that as an argument, and it is arithmetic rather than
opinion. **Put this table near the front of the artifact.**

**Worked example of gates-as-advisory (Neil's instruction), `defence` market.** Core requirements
met, out of 12:

| Platform | Core met | Gate status |
|---|---|---|
| **Loupe** | **11 / 12** (misses only disconfirmation, 3 vs 4) | ❌ certifications 1, needs 3 |
| Matey / CrimD | 6 / 12 | ✅ certs 9 · ❌ deployment ~3, needs 6 *(axis 29 pending)* |

Enforce the gates and both drop out and you learn nothing. Advisory, and the picture is
immediate: **Loupe is far and away the best fit for its own beachhead and one certification
away from being buyable**, while the best-funded defence-native rival clears the certification
bar and meets half the requirements. That comparison is the pitch.

Caveat to state alongside it, or the table overclaims: **clearing a gate is eligibility, not fit.**
Even post-SOC 2, Loupe misses Core badly in `civil` (review 1 vs 9, disclosure 2 vs 9, TAR 0 vs 8),
`diligence` (OSINT 0 vs 9, acquisition 0 vs 8), `corpsec` (OSINT 0 vs 8) and `ethics` (workflow 4
vs 9). The fit % is what separates *eligible* from *competitive* — which is exactly what the new
lens is for.

## New feature spec — market + price lens (Neil, 2026-07-27)

Requested: select a **market** and a **price range** → highlight the features most needed, state
the **minimum score** per feature, explain **in English why that combination** is needed; then
select one or more platforms → comparison against the market profile and against each other, with
a readable analysis piece.

**Core design decision — a market needs a requirement *profile*, not a flat minimum.** Each of the
28 axes is banded per market:

| Band | Meaning | Effect on fit |
|---|---|---|
| **Gate** | Below threshold = cannot serve this market | Hard fail, reported separately |
| **Core** | What the buyer is actually buying | Heavy weight |
| **Useful** | Real value, not decisive | Light weight |
| **N/A** | Market doesn't need it | **Excluded from the denominator** |

The N/A band is what makes it honest: for criminal defence, **evidence acquisition** and **OSINT**
are genuinely N/A (the buyer receives evidence, doesn't collect it), so Loupe's zeros shouldn't
count against it and Cellebrite's tens shouldn't count for it.

**REVISED 2026-07-27 on Neil's instruction — gates are ADVISORY, never eliminating.**
> *"for something like certifications that disqualify platforms, show the best fit even if
> platforms miss on some criteria like certs. We can use that info to assess whether getting
> certified is needed."*

Correct, and it fixes a flaw in the original design: a gate that removes a platform from the
ranking destroys exactly the information you would use to justify closing it. So:

- **Fit % is computed on Core + Useful only. Gates are excluded from the fit maths entirely** and
  reported alongside as a separate pass/fail badge naming the axis and the delta
  (e.g. *"certifications 1, needs 3"*).
- **Every platform stays in the ranking**, sorted by fit, with gate failures marked rather than
  hidden. Nothing greys out or disappears.
- The derived number that matters: **rank on fit vs eligibility today.** "Ranked 1st on fit in this
  market, blocked by one gate" is the business case for the certification, stated as arithmetic.
- Optional toggle: *enforce gates* / *advisory* — default **advisory**.

A platform can therefore show 91% fit and one failed gate, and the reader can see precisely what
that gate is worth. That is the whole point of the feature.

**Price is a separate filter** — market sets what's needed, price sets what's reachable. Target
on-screen sentence: *"31 platforms. 12 clear the criminal-defence gates. 4 of those are under
$25,000 a year."*

**Prose is generated from templates + data** (threshold vs actual, gate pass/fail, ranked deltas,
axis rationale text supplying the "why") — hand-writing every market × price × platform
combination isn't possible. The artifact already does this for click-to-compare.

**Worked example — criminal defence, under $25k.** Illustrative gates: commercial accessibility ≥5,
single-tenant ≥6, certifications ≥3.
- Relativity — fails accessibility (2, channel-only) + single-tenant (Server sunset). Out.
- Everlaw — accessibility 5 passes via Everlaw for Good; single-tenant 1, cloud-only. Out.
- Cognyte / Altia / Kaseware — accessibility ~2, LE channel. Out.
- **Loupe — accessibility 7 ✓, single-tenant 9 ✓, certifications 1 ✗. High fit, one gate failed.**

That single screen is the entire GTM argument: best fit for the target market, disqualified from it
by one missing certification. Far more persuasive than 99/120.

### DECIDED by Neil 2026-07-27

**Price bands — APPROVED as proposed:** `<$10k` · `$10–50k` · `$50–300k` · `$300k+` per year.
Per-matter pricing converted at an assumed matters/year so comparison is apples to apples.
Loupe's $6–24k per-matter band sits inside band 2.

**Markets — DO NOT REDUCE. Neil: *"I want as many considered as possible."*** So the existing
seven are retained and the set is **expanded to 15 real markets** (+ the unweighted baseline).

**Existing lenses in the published artifact** (`var MKT`, weights are the old 16-axis vectors —
must be re-authored for 28 axes):

| key | label | old gate |
|---|---|---|
| `thesis` | Loupe's thesis (unweighted baseline) | — |
| `defence` | Criminal defence & PI | axis 6 min 4 — "cannot be bought by a defence practice" |
| `corporate` | Corporate & internal investigations | — |
| `prosecution` | Prosecution & law enforcement | — |
| `insurance` | Insurance SIU / fraud | — |
| `journalism` | Investigative journalism | — |
| `fincrime` | Financial-crime units | axis 11 min 5 — "no sovereign or on-premises deployment" |
| `ukpolice` | UK / EU policing | axis 11 min 5 — as above |

**Eight markets to ADD** — each a genuinely distinct buyer with different gates, not a slice of an
existing one:

| key | label | why distinct |
|---|---|---|
| `pubdef` | Public defender offices | Different funding + procurement from private defence; Longeye and Everlaw for Good give it away — the free-tier gate lives here, not in `defence` |
| `civil` | Law firms & civil disputes | The largest actual spend pool and **currently missing entirely**; the eDiscovery majors' home market |
| `regulator` | Regulators & govt enforcement | Comtrac's market; brief-of-evidence and offence-element workflows, not policing |
| `corpsec` | Corporate security & insider threat | Kaseware/Omnigo/Resolver corporate side; physical + insider, not financial |
| `ethics` | Ethics, compliance & whistleblower | Case IQ/Resolver hotline-driven intake; certifications gate hard here |
| `diligence` | Due diligence / KYC / third-party risk | Neotas/Xapien; OSINT-led, axis 11 dominates, phone evidence irrelevant |
| `natsec` | Intelligence & national security | Palantir/Cognyte/Babel Street; sovereign deployment + acquisition gates |
| `pubfraud` | Public-sector fraud (benefits/tax/immigration) | High volume, document+financial heavy, government procurement |

**Authoring cost — flag before starting chunk 6:** 15 markets × 28 axes = **420 banded decisions**
plus 15 rationale pieces plus gate thresholds. Likely needs splitting into **6a** (the seven
existing lenses re-authored for 28 axes) and **6b** (the eight new markets).

Requirement profiles are market judgement, not score-dependent → **can be authored in parallel**
with chunks 3–5.

---

## Open questions / to verify

- [ ] **Kaseware + Altia link analysis — auto-built from ingested evidence, or analyst-charted?**
      Highest-priority open item. Determines whether "nobody else builds a graph" can stand.
- [ ] **Is Loupe's lack of production/redaction/privilege-log capability a deal-breaker or out of
      scope for defence-side buyers?** Ask the ex-FBI lead prospect directly. Changes whether
      axis 15 is a gap to close or a gap to declare N/A.
- [ ] **Comtrac** needs a full dossier, not a paragraph — closest analogue to the Loupes thesis.
- [ ] **Platform count** — published doc says "26 platforms"; matrix had 30 rows; new set is ~39.
      Every "of 26" claim, tile number and masthead figure must be recomputed in chunk 7.
- [ ] **TAM framing** — Alex found an article claiming the global investigations market hits $3.5B
      by 2030. Doesn't match anything: published estimates are **$7.5–21B today → $11–27B by
      2030–32** at ~5% CAGR. Her figure is likely a narrow software/regional sub-segment. Get the
      link. **Per-matter pricing puts Loupe against the services spend, not the software spend** —
      that's the right TAM frame. Neither artifact currently has a TAM section.

## Clarity fixes owed to the published doc (Neil conceded "misleading in that sense")

- [ ] Free-tier attribution — F8 table and the "one to watch" callout describe rivals' free tiers in
      the same register used for Loupe's own strategy. Add an explicit "this is what *they* do,
      which is why we don't go there."
- [ ] §08 never plainly states *what* the three pricing models are before arguing between them.
- [ ] "Architecture claim" used as a term of art with no gloss.

---

## ✅ SHIPPED — Market Fit Lens (chunk 7a)

**https://claude.ai/code/artifact/52e0afe2-11ef-4bd7-93dc-f47ce252d538**
Source: `app-v3/owl-n4j/loupe-fit-lens.html` — **republish that same path to keep the URL.**

Contains: all 47 platforms × 29 axes, the 15 banded market profiles with rationale prose, market
and budget filters, **advisory gates** (fail badges shown, platform stays ranked), fit % on
Core+Useful with N/A axes excluded from the denominator, multi-select platform comparison with a
per-axis hit/miss table and generated analysis prose. Loupe brand tokens, both themes.

**Final totals on the 29-axis / 290 basis** (axis 29 lifted the on-prem-capable vendors):
Palantir 195 · Magnet 182 · Guardian 172 · Exterro 168 · Everlaw 167 · Relativity 167 ·
Pathfinder 167 · Cognyte 166 · Nuix 166 · Axon 153 · **Loupe 151 (11th)** · NICE 148 ·
Babel Street 143 · Hubstream 141 · DataWalk 141 · Reveal 138 · DISCO 137 · Altia 137 ·
Casepoint 135 · CaseMap+ 134 · i2 133 · CoCounsel 132 · Matey 132 · Longeye 131 · Videris 130 ·
JusticeText 126 · Neotas 124 · Ontic 123 · Casefleet 122 · Siren 122 · TrialKit 121 · Harvey 120 ·
Maltego 119 · Kaseware 119 · Comtrac 117 · Hebbia 115 · Resolver 111 · Clearbrief 109 ·
Case IQ 108 · Octostar 107 · Linkurious 104 · ShadowDragon 101 · Case Closed 98 · HR Acuity 93 ·
Omnigo 91 · CROSStrax 72 · Trackops 67

## ✅ CHUNK 7b COMPLETE — all nine edits merged and republished (2026-07-27)

Narrative artifact **https://claude.ai/code/artifact/f65cdf4e-fc35-432c-b52e-360fd3d15682** republished from `loupe-landscape.html`. All nine landed: F11 softened (JusticeText 6 / Clearbrief 5 > Loupe 3), F10 gained Comtrac, the graph claim qualified for Pathfinder/Kaseware/Altia, Exterro ARMOUR added as **T2** and Axon as **T3** (later threats renumbered T4–T8), pricing anchor changed to CROSStrax $35/mo and Trackops $99/mo, Nuix/Linkurious date corrected to signed 4 Dec 2025, all counts 26→47, the three clarity fixes added (free-tier attribution now says plainly that giving Loupe away is *not* the plan; the three pricing models defined before §08 argues between them; "architecture claim" glossed), and the **defence-access table promoted into F7** with its own styling.

**Axis-26 split shipped too** — Neil approved mid-run. Axis 26 became *Acquisition & parsing validation* and *Defensibility of AI output*. **Loupe goes from 2 to 2-and-8**; Clearbrief 10, Casefleet 9, Exterro 9, Relativity 9 lead AI-defensibility while Cellebrite scores 2–3 (its GenAI launch documents no audit trail or citation mechanism). Frame is now **30 axes / 300**, Loupe **159**.

### Superseded — the nine edits as originally listed

The lens was shipped as a **separate** artifact rather than replacing the landscape doc
(f65cdf4e). Deliberate: that doc is a 216 KB narrative whose value is the eleven findings, the
threat register, the beachhead and pricing analysis and the 26 dossiers, and whose renderer is
hard-wired to 16 axes. Replacing it wholesale would destroy the prose. The two should live side by
side — narrative doc for the argument, lens for the tool.

Outstanding edits to f65cdf4e:
1. **F11 must be softened** — "disconfirmation unclaimed by all 26" is false. JusticeText 6,
   Clearbrief 5, **Loupe 3**. Unclaimed as *positioning*, shipped by two competitors, not by Loupe.
2. **F10 adjusted for Comtrac** — "Elementising Evidence™" maps exhibits to offence elements.
3. **"Nobody else builds a graph" qualified** — Pathfinder does (Group A 37), and Kaseware/Altia
   ship link analysis. The honest claim is *cross-evidence-type*, never *graph*.
4. **Threat register: add Exterro ARMOUR** (launched 9 Jul 2026, agentic, scores 9 on axis 20 vs
   Loupe 8 — the only platform to beat Loupe on an AI axis) **and Axon** (up from records into
   investigation; scores 153).
5. **§08 pricing anchor → Trackops ($99/mo) and CROSStrax ($35/mo)**, not i2/Logikcull. They serve
   the exact beachhead buyer and have no evidence-analysis capability — the whitespace proven.
6. **Fix the Nuix/Linkurious date**: doc says completed April 2026; signed 4 Dec 2025, closed Dec
   2025 with French FDI approval.
7. **Every "of 26" claim, tile figure and masthead count → 47.**
8. The three clarity fixes Neil conceded: free-tier attribution, a plain statement of the three
   pricing models before §08 argues between them, a gloss on "architecture claim".
9. **Promote the defence-access table** (dossiers §3 cross-cutting) into the main document — it is
   the single most valuable asset in the corpus and it is currently buried in an appendix.

## Context — what this work is FOR (Neil, 2026-07-27)

**Loupe is pre-GTM. The immediate goal is acceptance into an accelerator programme.** Gartner Peer
Insights listing is explicitly **deferred** — "we will apply to this when ready." Do not raise it
again as a near-term action.

That reframes the rescore's value. An accelerator panel discounts a self-serving matrix on sight;
99/120 across axes chosen to describe your own product reads as marketing. The honest version is
the stronger diligence artifact:
- *Ten platforms beat Loupe overall and not one of them can be sold to a defence practice.*
- *Certifications is the only failed gate in 11 of 15 markets — one certification unlocks five.*
- *Loupe is behind on two of its four headline claims, and both only because they have not shipped.*

Those are the three sentences to carry into the application. The first two are strengths disguised
as concessions; the third is a roadmap answer, which is what an accelerator wants to hear anyway.

## SETTLED — scoring basis (Neil, 2026-07-27). Do not reopen.

**Score the platform as it will be at the imminent release, not as it is today.** Neil, verbatim:
*"It's important we consider our platform where it will be in just a few weeks. There's no point
disregarding features. We need to find a market fit based on what we will release. Stop asking me
about this."*

Applied: **Loupes → axis 18 = 9** (was 5) and **disconfirmation agent → axis 21 = 8** (was 3).
Loupe **168/300, 10th of 47**. Competitors are scored on shipped-and-announced capability, which
is the symmetric treatment — several of theirs are announced-not-GA too (DISCO's scaled agentic AI
is "generally available later in 2026"). The lens footer states the basis plainly; that is
disclosure, not hedging.

**Roadmap language belongs in the accelerator application, not in the analysis.** Neil:
*"when it comes to the actual application for the accelerator, THEN we can use roadmap etc."*
So: the landscape and the lens assess the near-term platform; the application handles staging of
claims at the time it is written. **Do not raise the unshipped-features question again.**

F11 in the landscape was reframed accordingly — it no longer says Loupe is behind. The precise,
survivable claim is now: *no platform runs disconfirmation over a structured claims ledger, and
the ledger is the difference between flagging an inconsistency and enumerating what would break a
theory — including the document that does not exist.* JusticeText and Clearbrief are named as
narrow adjacent cases so the claim holds up to a five-minute check.

## Locations

- Published artifacts (both **updated 2026-07-26**, confirmed current 2026-07-27):
  - Landscape — https://claude.ai/code/artifact/f65cdf4e-fc35-432c-b52e-360fd3d15682
  - Product brief — https://claude.ai/code/artifact/98befc56-cc47-44ac-8a8c-591ce8a7d0b5
  - **Republish to the same file path / `url` param to keep these URLs.**
- Source: `app-v3/owl-n4j/loupe-landscape.html` (216 KB)
- Prior research: `15-loupe-competitive-landscape-work.md`, `16-loupe-competitor-dossiers.md` (356 KB)
- Matrix score data lives in the artifact's inline `<script>`: `const SC` (12 capability) and
  `const RD_SC` (4 readiness), plus per-axis note objects (`CQ`, `MM`, `IG`, `WS`, `CERT`, `SCALE`,
  `ECO`, `ACQ`). These must be restructured for 28 axes in chunk 7.
- Voice rules for **external** material (Neil): finished-product tense; no status markers; never
  mention ticket counts or board mechanics; **one product, no v1/v2 language ever**; "read-only"
  only for database access; capacities as "designed for", results as "has processed".
  **This landscape doc is internal candid register — different rules.**

---

## ▶ NEXT

**Session 2026-07-28 — narrative docs written, false headlines fixed, brief updated. All published.**

⚠️ **SOURCE FILES: the published artifacts are the `-branded` HTML files.**
`loupe-landscape.html` is a STALE pre-branding copy — do not edit it. Verified byte-identical to
the live artifacts: `loupe-landscape-branded.html` → f65cdf4e, `loupe-fit-lens.html` → 52e0afe2,
`loupe-accelerator-brief-branded.html` → 98befc56.

**Shipped this session:**
- `18-market-fit-lens-narrative.md` (1,033 lines) — https://claude.ai/code/artifact/0f5dde93-39f2-4fa2-aff4-05759b715176
- `19-competitive-landscape-narrative.md` (817 lines) — https://claude.ai/code/artifact/e9400d50-6b96-4859-9025-6d5e622bca3d
  Both computed from the published score arrays, not from recollection.
- **Lens headline corrected** — was "Ten platforms beat Loupe. None of them can be sold to a defence
  practice." Recomputation: **nine** beat Loupe (Loupe 168, **10th** not 11th), and **two of the nine
  clear every defence gate** (Magnet accessibility 5, Exterro 6). New headline: "Nine platforms beat
  Loupe. Seven of them cannot be sold to a defence practice." mRank static fallback 11th→10th.
- **Landscape stale-frame headlines killed** — 99/120 tile → 55/60 evidence modelling; 5/40 tile →
  33/90 readiness; "Loupe and Palantir tie on 104" callout rewritten on the 30-axis basis; three
  "twenty-six platforms" → forty-seven; "Twelve of the twenty-six structurally unavailable" →
  twenty-three of forty-seven (computed); filter "All 26" → "All 30".
- **Brief updated** — market #3 was "Law firms & disputes teams", which contradicted the lens (civil
  is Loupe's WORST market, 20th of 47). Now #3 = Insurance SIU (only ungated market); civil demoted
  to "Later" with the honest reason. Added a competitive section (defence-access asymmetry, the
  capability/price gap, the four funded rivals) and a market-size paragraph framing per-matter
  pricing against the **services** spend. "First tool where the unit of work is a hypothesis"
  superlative tightened per F11.
- **Kaseware/Altia open question CLOSED by research.** Kaseware's graph IS auto-built from ingested
  documents and audio (AI page: OCR, speech-to-text, entity extraction across documents and data
  feeds, relationship mapping) — no device or financial parsing. Altia FIT has real per-claim
  provenance over financial evidence ("every transaction, source, and disclosure can be traced back
  to its origin"; ingestion auto-logged with timestamps and source references) — financial-only,
  siloed from Insight. **Kills the loose "nobody auto-builds a graph" claim; confirms the precise
  cross-evidence-type claim.** Proposed rescores documented in doc 18 §9 and doc 19 §10,
  **NOT applied** — pending Neil's sign-off.

**Matrix REBUILT 2026-07-29** (Neil reversed his earlier decline). Landscape section 03 is now
47 platforms x 30 axes, /300, driven by the same score arrays as the lens — all 47 totals verified
identical across the two artifacts. Two-row thead with the five band headers; 7th category
"investigative case management" added for Kaseware/Hubstream/Ontic/Comtrac/Resolver/Case IQ/
Case Closed/HR Acuity/Omnigo/CROSStrax/Trackops. **All 420 per-cell research notes carried over**
onto mapped axes (IG + WS had no equivalent axis — merged into auto-built graph / durable judgment).
**The in-matrix 7-market weighting was REMOVED** — it ran on 16 axes and would have disagreed with
the lens; section now links to the lens instead. One market engine, one answer. The GTM sentence
"set the matrix to the criminal-defence lens" was repointed to the lens artifact.
Note coverage: 420 of 1,410 cells have researched notes; the rest show the axis definition.

**Also 2026-07-29 (Neil's direction):** certifications are no longer a gate anywhere — de-gated in
all 15 market profiles for all 47 platforms, axis still scored/visible in the matrix. Loupe now
clears every gate in 13 of 15 markets (only pubdef accessibility + natsec acquisition remain).
Lens headline replaced with a market-agnostic one: "No platform fits every buyer. Change the market
and the field reorders." Both narrative docs rebuilt on the recomputed basis (new §6 "reach").


**2026-07-29 (later): market sizing + internal caveats.**
- **New §7a in doc 18 sizes all 15 markets** from published analyst research (sequential WebSearch,
  no fleets). Headline: the two BIGGEST markets are the two Loupe fits worst — law enforcement
  software $22.0–22.9B (Loupe 15th) and eDiscovery $20.7B total / $8.6B software (Loupe 20th).
  **Insurance SIU is the standout**: $8.5–11.3B at 23.2% CAGR, fastest-growing category in the set,
  no gate for anyone, Loupe 7th at 77% — only OSINT (0) holds it back. Investigation management
  $8.1B/14.8%. Insider threat $5.7–6.6B. AML $2.8–4.0B. KYC $2.5–7.8B. Whistleblowing only $0.28B.
  OSINT $8.7–23B (widest analyst spread). **Beachhead has NO software category** — sized instead as
  services substitution: US criminal-defence firm revenue >$15B/yr across ~252k practitioners; PI
  services ~$22B globally 2026. That is the honest TAM frame for per-matter pricing.
  **The internal $3.5B-by-2030 figure matches nothing published — flagged as unusable in both docs.**
- **INTERNAL banner added to the top of docs 18 and 19**, addressed to an AI assistant drafting
  external material: don't copy sentences, use as evidence/structure, plus the voice rules, the two
  unshipped capabilities, the two unciteable founder-knowledge entries, and re-verify anything
  load-bearing.
- **Matey funding VERIFIED** from primary announcements: $7.5M seed led by Timespan Ventures with
  Neo + Streamlined Ventures, Aug 2025, Austin, product CrimD. Removed from the unverified list.
- Still unverified: BlueLight Commercial's UK procurement role, FRE 707, Cellebrite's formal
  defence-sales policy, third-party seat-price estimates.


**2026-07-29 (evening): market sizing, per-matter economics, regional plans.**
- **§7a (doc 18) / §6a (doc 19) / artifact 08a** now carry: opportunity-in-one-page summary,
  15-market sizing table WITH Loupe's fit rank per market, per-matter displacement economics at
  realistic case volumes, and the Ireland/UK/Europe sizing + regional plan.
- **Per-matter model:** RETAINED extraction ($3,650 + $600/device beyond 2) · DISPLACED processing
  ($3–10/GB), hosting ($5–15/GB/MONTH — $104k on a 435GB 24-month case), examiner analysis
  ($300–500/h) · RELEASED investigator/paralegal hours (RAND workload study: 35/57/99/167/248/286h
  by severity; PI $85–225, paralegal $100–200). Displaceable value **$5.8k–$138k per matter**.
  **A flat $6–24k band is wrong at both ends — 205% of a small case, 9% of a large one. 24x spread.**
- **US funnel:** 1.6–2.5M felony filings → ~20% privately retained → 15–25% evidence-heavy →
  48k–125k matters/yr × $20–60k = **$1.0–7.5B**. NOTE: BJS no longer publishes a national felony
  total (series closed 2006); CSP has it but only via a Tableau dashboard — **Explore court caseload
  data → Criminal → Incoming → Felony** is the two-minute human fix. Tried 3 fetch routes, all dead.
- **Europe:** digital forensics $2.41B→$3.89B (UK 21.76% ≈ $525M); legal tech $6.81B→$15.45B, EU =
  25% of global. Crown Court open caseload ~80,200 → 99–114k by 2029, +£92M legal aid. Ireland
  criminal legal aid €123M, Courts Service €215M.
- **Regional sequence:** Ireland = reference not revenue; UK = first European revenue + policy
  tailwind, DEFENCE BEFORE POLICING (CPIA disclosure gated 8, Loupe scores 2); Europe = partner-led,
  advantage is deployment control (9 vs 2-6 for US-owned rivals under GDPR).
- **NDRC pack Part 6** extended with the Irish/European case for slide 6.
- **Deck re-branded** to the brand kit: obsidian/red replacing blue-black/amber (the old amber sat on
  --loupe-financial, reserved for entity meaning), Space Grotesk + IBM Plex Sans/Mono replacing
  Helvetica Neue, knockout lockup on the cover. Audited: 0 off-brand colours. **PDF must be exported
  on a machine with the brand fonts — this box has neither LibreOffice nor the fonts.**


**2026-07-29 (late): conclusions rewritten + growth path built through everything.**
- Neil, three times: the docs read as "a load of numbers" with no conclusion. **Fixed by REPLACING
  the numbered summary with written argument**, not by adding more. Two prose conclusions now open
  the sizing section: (1) *the field splits into two halves that never meet and the buyer sits in
  the gap* — one half models evidence and won't sell to defence, the other serves defence and
  treats a phone as an attachment; the intersection of 47 platforms is empty and that is structural,
  not a scoring artifact. (2) *this budget is already being spent* — the buyer chooses between Loupe
  and paying a vendor + per-GB-per-month hosting + examiner hours + its own people; so the sale is
  "you already pay for this" not "find budget". **CAUTION: my first replacement pass deleted the
  sizing tables too — restored, and consolidated into one 4-column per-matter table.**
- **GROWTH STAIRCASE — new §08b in the landscape artifact (CSS staircase, 4 steps, nav entry), table
  in both narratives, new SLIDE 7 in the deck (`slide6b()` in build_deck.py), cards in the
  accelerator brief, Part 2 + Part 6 of the NDRC pack (deck is now TEN slides, later slides
  renumbered 8/9/10).**
  Model: blended $12k/matter; typical boutique 8 matters/yr = $96k; active 20 = $240k.
  | Stage | ARR | Customers | Matters/yr | Share of US pool |
  | 1 Owl+Ireland (proof, NOT revenue) | $0.5M | 5 | 42 | — |
  | 2 United States (the engine) | $5M | 52 | 417 | 0.3–0.9% |
  | 3 + United Kingdom | $10M | 104 | 833 | 0.7–1.7% |
  | 4 + Europe | $25M | 260 | 2,083 | 1.7–4.3% |
  **The pitch line: $10M ARR = 104 firms + 833 matters = under 2% of the US pool alone.** Each stage
  gated on ONE thing: 1 validated price · 2 bar channel converts · 3 model rebuilt on UK/LAA rates ·
  4 partners. Customer counts swing 2.5x on firm mix (42 firms not 104 at the active-practice rate).

**Outstanding:**
1. Apply or reject the Kaseware/Altia rescores (Kaseware 122→128, Altia 140→145; no market outcome changes).
2. Note coverage: 990 of 1,410 matrix cells show the axis definition rather than researched evidence.
3. Dossiers missing for **Kaseware, Altia, Comtrac** — Comtrac is the closest shipped analogue to the
   Loupes thesis and has a paragraph.
4. TAM has a paragraph in the brief now but no sourced figure. Alex's $3.5B-by-2030 article still not
   obtained; published estimates are $7.5–21B → $11–27B by 2030–32.

Post an update per chunk. Do not spawn agent fleets.

---

## Superseded — earlier ▶ NEXT (chunk 7b, now complete)


**ALL SCORING CHUNKS COMPLETE — 47 platforms.**

**Chunk 7b — merge the nine outstanding edits into the narrative artifact f65cdf4e** (listed in
full under "STILL OWED" above), then republish `app-v3/owl-n4j/loupe-landscape.html` to the same
URL. The scoring work is finished; this is prose surgery on an existing 216 KB file, so edit the
source in place rather than regenerating it.

Optional follow-ons Neil has not yet ruled on: the **axis-26 split** (acquisition validation vs
AI-output defensibility — would take the frame to 30 axes and move Loupe from ~2 to 1-and-8), and
the **Gartner Peer Insights listing** gap (competitors are in the "Investigation Management
Software" category and Loupe is not; listings are largely self-serve).

*Superseded plan (chunk 7 original, now split into 7a done / 7b outstanding):*

1. **Score axis 29 (deployment control) for all 46 non-Loupe platforms** — the only scoring gap
   left. Known anchors: Nuix has an explicit on-prem Neo Discover offering; Magnet Axiom is
   desktop/on-prem with offline Copilot; Exterro FTK is on-prem lab; Casepoint and Longeye are
   GovCloud; Relativity Server sunsets to cloud-only by 2028; Everlaw, DISCO, Harvey, Hebbia and
   most defence-native startups are cloud-only.
2. **Recompute all 47 totals on the 29-axis / 290 basis.**
3. **Rescore Loupe honestly** against all 29 axes (current row is provisional).
4. **Rebuild the artifact data structures**: `SC`/`RD_SC` → new 29-axis shape; `AX` → 29 labels;
   `MKT` → 15 banded profiles (not weight vectors); `D` → 47 rows with per-axis notes; add price
   band per platform.
5. **Build the market + price lens** per the spec above — **gates advisory, never eliminating**.
6. **Fix everything under "Open questions"**: the Nuix/Linkurious April-2026 date error, every
   "of 26" claim and tile figure → 47, F11 softened (JusticeText 6 / Clearbrief 5 > Loupe 3),
   F10 adjusted for Comtrac, the "nobody builds a graph" line qualified for Pathfinder/Kaseware/
   Altia, Exterro ARMOUR and Axon added to the threat register, §08 pricing anchor changed to
   Trackops/CROSStrax, the three clarity fixes Neil conceded.
7. **Republish to the same file path / `url` param** so the existing URL survives.

Post an update per chunk. Do not spawn agent fleets.

**Awaiting Neil's call (non-blocking):** the axis-26 split proposed in the chunk 3 findings above.
