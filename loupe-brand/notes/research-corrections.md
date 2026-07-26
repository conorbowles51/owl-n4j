# What the competitive research implies for the product brief

**Status: proposals for approval. Do not apply these as part of a skinning job.**

Comparing the **accelerator application brief** (internal draft, 25 Jul 2026) against the
**competitive landscape** (compiled 26 Jul 2026). The research postdates the brief by one
day, and it comments on it directly:

> §01 — "It found something more useful and less comfortable, and it forces a correction to
> how the product has been described."

> §10 — "Two headline capabilities are not shipped. Loupes are in build and uncommitted. The
> disconfirmation agent is a design. **Both appear in positioning material.**"

> Register — "This document is written in the candid internal register… External material —
> the accelerator brief, the deck — follows the finished-product rule instead. Do not paste
> from here into either without translating."

So: yes, the brief needs updating. Twelve items, ranked by how much they change it.

---

## C1 — The headline leads with the commoditised layer · **highest impact**

The brief's H1, its one-liner, its ~50-word and its ~100-word blocks all lead with
source-linking and citations:

> "Loupe turns raw case evidence into connected, **source-linked** intelligence."
> "…where AI answers questions **with citations** and every fact links back to its source page."
> §06 — "…where **every claim carries its receipt**…"

Research F1: between Nov 2025 and Feb 2026 every major platform shipped cited AI answers and
most made them free. Relativity folded aiR into base rate; Everlaw bundled three AI features;
DISCO shipped agentic AI at no additional cost; Reveal gave `aji` away. Relativity's aiR
refuses to emit a fact it cannot match to source text. Everlaw's Deep Dive answers
"insufficient evidence" rather than confabulate.

> "Pricing power has moved off the citation layer entirely, and any pitch that leads with
> provenance is arguing about a free feature."

**Proposed:** demote provenance to a qualifying condition and lead with grounding. The claim
the research says survives:

> "Loupe is the only platform where a call at 02:14, a transfer of $8,400 and a line in a
> subpoena return are the same kind of object — resolved into one graph, each citable back to
> the artifact it came from."

**Note this also affects the brand kit.** §09 lists the proof promise as "Every claim carries
its receipt" and puts "Links every answer to the exact source" under *Prefer*. Both predate
F1. The *Differentiator* line — "The model is a component. The evidence layer is the
product" — is aligned and should carry more weight. Worth a v1.1 to brand kit §09 before
either artifact is reskinned, or the superseded messaging gets baked into both.

## C2 — The brief is fighting ChatGPT; the real field is elsewhere

§06 is a nine-row table comparing Loupe to "a straight LLM." Every row is true. Almost none
of them differentiates against the actual competitive set: Relativity, Everlaw and Harvey all
have persistent case models, citation discipline, audit logs and single-tenant or
deployment-flexible options. On "Where the case lives," "Scale," "Answers," "Hallucination,"
"Confidentiality" and "Output," an informed reader scores them roughly level with Loupe.

Research F2 supplies the row that does differentiate, and the brief does not contain it:

> "Across all twenty-six platforms the mechanism is identical: retrieve candidate passages,
> place them in a context window, ask a model to reason over them… A graph changes what a
> question is… 'who contacted this person in the fortnight before that transfer' stops being
> a search and becomes a traversal with a definite answer over everything ingested."

With the published limits as evidence: Relativity caps at 300k documents per index and 5k
per fact-extraction job; CoCounsel ~200 documents per comparison run with quality degrading
at volume; Reveal states Ask is "designed for precision, not recall"; Harvey runs a prompt
per document and aggregates.

**Proposed:** add **retrieval vs. traversal** as the first row, and reframe the table's
opponent from ChatGPT to the category. Keep the LLM comparison as a shorter secondary block —
it answers "isn't this just ChatGPT with files?", which is still asked, but it is not the
differentiation argument.

## C3 — Unshipped capabilities are written in the present tense · **most urgent before submission**

Research §10 names both. In the brief:

- **Loupes** get all of §04, a card in §03, a stage in §02's "Prove", and a dedicated
  "The namesake feature" paste block. All present tense.
- **The disconfirmation agent** appears as "Hunt what breaks it" and "Loupe looks for what
  breaks your theory" in §05. Present tense. "Find what isn't there" and "Hypotheses that
  stay open" are in the same block and are likely the same status.

The brief's own governing rule, per research §10:

> "nothing enters a deck until it has demoed clean once, and anything unshipped on submission
> day becomes the roadmap answer instead."

**Proposed:** mark all four as roadmap, or cut them, before submission. This is an accuracy
question in a funding application, not a positioning preference — it should be settled first.

## C4 — The buyer list contradicts the beachhead finding

§09 "Who buys this" lists: financial-crime & fraud units, law enforcement & prosecutors, law
firms & disputes teams, corporate investigations & compliance.

Research §02 rules out three of those four as the first market, and the one it picks is
absent from the brief entirely:

| Segment | Research verdict |
|---|---|
| Police & prosecution | "the market every incumbent was built for… fighting on their ground with none of their advantages" |
| Financial crime | "Quantexa, DataWalk and Siren are entrenched… the buyer is a bank. Wrong fight." |
| Corporate investigations | "The right **second** market… will not close in the first year" |
| **Defence-side PI & criminal-defence boutiques, 5–50 people** | **The beachhead. 9.5 fit / 8.5 entry — highest on both axes.** |

The defining characteristic, per §02: "this buyer **receives** evidence rather than collecting
it, receives it in formats built by the other side, and has no way to analyse it properly."

**Proposed:** replace §09 with the beachhead as the named first market and the others as
sequence, with the reasoning. An accelerator will ask "who first, and why not the others" —
the research answers it and the brief currently doesn't.

## C5 — Loupes are framed as novel; the research says reframe, not retract

§04 calls Loupes "the platform's namesake object… A first-class object, not a filter."

Research F10: Everlaw's Storybuilder Fact Management (Dec 2025, now bundled free), DISCO
Timelines, Relativity's aiR for Case Strategy, Casefleet's approved-facts model, and CaseMap
since 1998 all have durable narrative objects.

> "Every one of them is document-scoped. None can cite a phone event as a timeline fact,
> because none models one. The differentiated claim is not the container — it is what is
> allowed inside it… Describe them as the only evidence collection that can contain a call, a
> transfer and a document line at once."

**Proposed:** keep §04, change its claim. One sentence added, one superlative removed.

## C6 — The unification claim is buried

The research calls this the sentence to own (F6): "a call at 02:14 and a wire transfer and a
paragraph of a police report are the same kind of citable object here. No competitor in the
set can say it." Evidence: Relativity flattens calls, contacts, calendar, locations, web
history and installed apps into Excel in an "Other Data" folder, with multi-device extractions
unsupported outright; Everlaw splits conversations every 1,000 messages; Reveal slices them
into 24-hour blocks; i2 removed native UFED import at 9.1.0. Harvey, Hebbia, CoCounsel,
Clearbrief and CaseMap have no phone support at all.

In the brief this exists only as an ingest list in §02 and separate phone and financial
subsections in §08. It is never stated as the claim.

**Proposed:** promote to §01 or §02 as a headline. It is the strongest line in the research
and it costs nothing to say.

## C7 — F7 is unused, and it is the best narrative in the research

> "The defence cannot buy the analytics the prosecution runs on."

GrayKey restricted to law enforcement, with agency-email vetting; Magnet states plainly it is
not available to the private sector. Cellebrite Pathfinder marketed solely to law
enforcement, government, intelligence and corporate investigators. And the sharpest artifact
in the whole research set: a Florida State Attorney's office publishing instructions for
defence counsel on how to receive phone extractions through read-only Guardian share links —
"the defence reviews the prosecution's evidence inside the prosecution's tool, with the
prosecution's permissions."

> "'Levelling the evidentiary playing field' is not a slogan here, it is a description of a
> licensing structure. It should be said plainly and sourced."

**Proposed:** add to §01. Documentable, specific, and it makes the problem statement concrete
in a way "modern casework is a data problem" does not.

## C8 — "Why now" argues against a competitor that no longer exists

§09: "bare LLMs remain unusable in evidence contexts — no provenance, no audit, no
confidentiality. The gap between those last two facts is exactly where Loupe sits."

F1 removes this. The incumbents have provenance, audit and confidentiality, and give them
away. The gap the brief names has closed.

**Proposed:** rewrite as — the evidence categories converged on cited document Q&A and
stopped there; nobody models the case. Per F3, that is structural rather than an oversight:
eDiscovery is a *reductive* discipline (Nuix markets cutting review volumes 40–60%; success
is fewer documents to read) and investigation is *constructive*. "If the job is to cull toward
a reviewable set, a call log is noise… If the job is to build a model, that same call log is
connective tissue."

## C9 — Transcription is listed prominently; the research says never sell it

§02 Ingest leads with "audio — transcribed and speaker-diarized, with investigator-editable
speaker naming."

F4: transcription is near-universal in 2026 — JusticeText is built on it, Longeye does it in
real time, Harvey returns speaker labels and timestamps, Hebbia bulk-transcribes 100 files
across 60 languages, Casepoint added it in March 2026. "Anyone claiming transcription as a
moat will be corrected in the first demo."

**Proposed:** keep the capability, change the emphasis. "Never sell transcription. Sell what
transcription becomes: a name spoken in a call and a name written in a statement are the same
entity in the case model."

## C10 — §05's ingestion-time configuration is the load-bearing mechanism and reads as a feature

F5 identifies AI processing profiles at the ingestion step as what makes the rest possible —
competitors configure at *review* time, on a corpus whose shape is already fixed. "You can
only traverse a model you actually built, and you only get a model worth traversing if
extraction was directed at ingestion. It is also the honest answer to 'couldn't you just point
an LLM at the files?' — you could, and you would get a pile of text."

In the brief this appears as "Folder processing profiles" in §08, in a list of forty other
capabilities.

**Proposed:** promote into §02 as part of the mechanism, not §08 as a feature.

## C11 — No pricing or business model

The brief mentions "pilot commercial terms" once, in §08. Research §08 supplies a full model:
per matter, **$6,000–24,000** per major matter, benchmarked against junior-investigator hours,
with the argument that per-gigabyte pricing "charges by evidence volume, which means it pays
the customer to keep evidence out of the platform." Also: the lead prospect (ex-FBI principal)
made the labour-substitution comparison unprompted, and Everlaw for Good "cannot be undercut,
but it can be out-scoped."

**Proposed:** add. An accelerator application without a business model is an obvious gap, and
this one is well argued.

## C12 — Weaknesses absent, and diligence will find them

Research §10, written "to be uncomfortable, because an investor's diligence will find all of
these." Most load-bearing:

> "Matey — selling to the same buyer, in the same country, with the same provenance pitch —
> holds SOC 2 Type II and ISO 27001 today. Loupe holds neither. In this segment that is not a
> procurement detail; it is the first question a firm's counsel asks, and it gates the pilot."

Also: no published scale proof, no iManage/NetDocuments/Clio/Westlaw integrations, no
acquisition capability, and Harvey at $1B+ raised against Loupe pre-seed.

**Proposed:** SOC 2 as a stated near-term milestone rather than an omission. The compensating
argument is already available and strong — the product was built inside live federal casework
rather than from a market hypothesis, with three cases gone to trial.

---

## Two things the brief already gets right and should keep

1. **Model-agnosticism.** §06's last row — "Models are interchangeable components… The moat
   is the evidence layer, not the model" — matches brand kit §09's *Differentiator* and is
   exactly what research threat T2 recommends. Claude for Legal launched May 2026 with 20+
   connectors including Relativity and Everlaw; Everlaw shipped its own MCP integration;
   CoCounsel was rebuilt on the Claude Agent SDK. "Competing at the agent layer is competing
   with the labs." Being the grounded substrate is the right posture. Make it louder.

2. **The confirmation-bias answer.** §05's "Hunt what breaks it" pre-empts the sharpest
   objection to hypothesis-led work, and F11 confirms nothing in 26 platforms markets
   contradiction detection. It is the only genuinely unclaimed idea in the category. Subject
   to C3 — it has to ship or be marked roadmap.

## One unverified superlative to watch

The brief says twice: "Loupe is the first tool where the unit of work is a hypothesis rather
than a query." The research does not verify this, and its Apparatus section is careful about
exactly this kind of claim. F11 supports the narrower version — nobody markets disconfirmation
— which is defensible and sourced. The broader "first tool" claim is not.
