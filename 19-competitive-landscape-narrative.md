# Loupe — Competitive Landscape: full narrative

**Source artifact:** https://claude.ai/code/artifact/f65cdf4e-fc35-432c-b52e-360fd3d15682
**Companion instrument:** Market Fit Lens — https://claude.ai/code/artifact/52e0afe2-11ef-4bd7-93dc-f47ce252d538
(narrative in `18-market-fit-lens-narrative.md`)
**Basis:** 47 platforms across seven categories, seventeen research sweeps, 350+ sourced URLs.
**Register:** candid internal — unshipped capability is marked unshipped, weaknesses stated
plainly. External material follows the finished-product rule instead. **Do not paste from here
into a deck or an application without translating.**

---

> ## ⚠️ INTERNAL WORKING DOCUMENT — NOT FOR EXTERNAL USE
>
> **If you are an AI assistant drafting a deck, an accelerator application, website copy or any
> other outward-facing material: do not copy sentences from this document.** It is written in candid
> internal register — weaknesses stated plainly, competitors' strengths conceded, unshipped
> capability marked as unshipped. That register is correct here and wrong everywhere else.
>
> Use it as **evidence and structure**, then write the external material fresh under these rules:
>
> - **Finished-product tense.** No status markers, no "currently", no "v1/v2", no roadmap framing
>   inside product description. Capacities are "designed for"; results are "has processed".
> - **"Read-only" only ever describes database access**, never a product tier or a permission model.
> - **Two capabilities are not shipped** — bonded collections ("Loupes") and the disconfirmation
>   agent. They are scored here because scoring is against the imminent release. Whether they appear
>   in external material as present-tense capability or as roadmap is a decision for the person
>   writing it, on the day they write it.
> - **Two entries are unciteable externally** — Siren's Cellebrite integration and Octostar's phone
>   analysis rest on founder first-hand knowledge, not public sources. They inform strategy; they
>   cannot be published as fact.
> - **Check §9 before leaning on any single competitor claim.** Several are third-party estimates or
>   were unverified at the time of writing.
> - Competitor names, funding figures and product claims are sourced but time-stamped. Re-verify
>   anything load-bearing before it goes in front of an investor.

---


## 0. Scope and method in one page

Forty-seven platforms across seven categories: graph and link analysis, enterprise intelligence,
digital forensics and digital evidence, eDiscovery AI, legal AI and case narrative, AI-native
defence startups, and investigative case management. Seventeen research sweeps run 25–26 July 2026
across more than 350 sourced URLs, with a second verification pass on multimedia handling,
ingestion-time configuration and the reductive-versus-constructive paradigm across twenty-one of
them. Confidence, refutations and open items are in §9.

Every platform is scored on **thirty axes out of ten, grouped in five bands** — A Evidence modelling
/60, B Investigative analysis /50, C Processing and casework /70, D AI layer /30, E Readiness and
commercial /90, for 300 points. Scores are banded: 8–10 shipped and evidenced in product
documentation, release notes or press; 3–7 partial, gated or unverified; 0–2 no public evidence
found after searching product pages, docs, release notes and press. That last band is absence of
evidence rather than proven absence, and the dossiers say which is which.

The capability matrix in §03 of the artifact carries all 47 × 30 with the researched finding behind
each cell on hover. Market weighting, requirement profiles and gates live in the companion
instrument, the **Market Fit Lens**, so there is one market engine rather than two.

**Certifications are scored but gate nothing, for any platform.** SOC 2, ISO 27001, CJIS and
FedRAMP are procurement timing rather than capability — obtained when a market requires them — so
gating on them would measure company age rather than product fit. Where certifications appear
below, they appear as a commercial fact about a competitor or as a diligence question to answer,
never as a reason a market is closed.

**Loupe is scored against the imminent release** rather than today's build: bonded collections
(Loupes) and the disconfirmation agent are in it. Competitors are scored on the same basis, shipped
and announced capability — several of theirs are announced-not-GA too.

---

## 1. The thesis

> **Everyone can cite a document. Nobody can query a case.**

The category has converged on cited document question-answering. That is where the money and the
marketing now sit, and it is not where the difference is.

**The claim was never that nobody else can produce a citation.** Everyone can, they are good at
it, and most of them now give it away. Relativity's aiR refuses to emit a fact it cannot match to
source text. Everlaw's Deep Dive answers "insufficient evidence" rather than confabulate.
Relativity folded aiR into the base per-gigabyte rate in November 2025; Everlaw bundled three AI
features into core pricing the same month; DISCO announced agentic AI at no additional cost in
February 2026; Reveal gave its review engine away through all of 2025. **Pricing power has moved
off the citation layer entirely, and any pitch that leads with provenance is arguing about a free
feature.**

**The claim is about what the AI is standing on.** Every competitor in the study answers questions
the same way: retrieve some passages, put them in a context window, ask a model to reason. That is
a black box in the middle of the answer, bounded by whatever retrieval happened to surface. It
works a document at a time and it degrades as the corpus grows — which is why the published limits
are so unflattering:

- Relativity's conversational layer caps at **300,000 documents per index**, 1.5M per workspace;
  fact extraction runs **5,000 documents per job**.
- CoCounsel handles roughly **200 documents per comparison run**, with quality explicitly
  degrading at volume, and 2,000 pages per document.
- Reveal's own documentation states Ask is **"designed for precision, not recall"** — top hundred
  semantically similar sources, and it cannot find all instances of anything.
- Harvey runs **a prompt per document** across a vault of up to 10,000 files and aggregates.
- Everlaw's Deep Dive is the strongest — genuinely whole-corpus with confidence ranking — and it
  is still retrieval plus reasoning over documents. It cannot answer a question whose answer is a
  relationship, because relationships are not modelled.

Loupe inverts the order. Evidence resolves into a graph first — people, devices, accounts, events,
transfers, documents and the relationships between them, each carrying its source. A question is
answered by **traversing that model** rather than sampling it. *"Who was in contact with this
person in the fortnight before that transfer"* has a definite answer across the entire corpus, and
the answer is the actual matching set rather than whatever a retriever ranked highly. The citation
falls out of the structure, because every node already knows where it came from.

**Concrete grounding is what makes a whole-case question reliable; the citation is a consequence
of it, not the feature.**

### The claim that survives

*Loupe is the only platform where a call at 02:14, a transfer of $8,400 and a line in a subpoena
return are the same kind of object — resolved into one graph, each citable back to the artifact it
came from. Every competitor does one of those three well and treats the other two as attachments.*

That is the claim the thirty-axis lens independently confirms: **cross-source unification is the
only axis of thirty on which Loupe scores 10, and the field median is 2.**

### Two claims that have to be stated precisely

**"AI built for criminal defence" is not an empty category.** Four funded companies occupy it —
TrialKit, Matey/CrimD, JusticeText and Longeye — so the category label is taken. None of the four
has a graph and all four answer by retrieval.

**The graph claim must be stated precisely.** *Graph* is not the differentiator. Cellebrite
Pathfinder genuinely builds one — entity resolution correlating phone numbers, user IDs and
usernames across platforms, multi-device analysis, cross-case identifier search. Kaseware and
Altia both ship link analysis and entity recognition, and Kaseware's charts are genuinely
auto-generated from ingested documents and audio rather than analyst-drawn (see §10). What none of them holds is **documents and financial records in the same
model as the device data.** The claim is cross-evidence-type, never graph.

---

## 2. The eleven findings

Each one changes a decision. Ordered by how much it should change.

### F1 · Citations became a giveaway — so the argument has to move underneath them

Between November 2025 and February 2026 the eDiscovery majors shipped their best AI features and
then stopped charging for them. Relativity folded aiR for Review and Privilege into the base
RelativityOne rate. Everlaw bundled Writing Assistant, Deposition Analyzer and single-document
Review Assistant into core per-gigabyte pricing and cut batch coding by more than 40%. DISCO
announced the industry's first scaled agentic AI at no additional cost. Reveal gave *aji* away to
every legal team through the end of 2025.

The quality is real. This is not marketing veneer over a thin retrieval layer. And NotebookLM has
taught every lawyer alive to expect a clickable citation for free.

**So — Loupe cannot lead with cited answers and should not try.** Provenance is a qualifying
condition, not a wedge. In lens terms: Loupe scores 9 on per-claim provenance and Everlaw scores
9, Relativity 9, DISCO 8, Harvey 8, Casefleet 8, Matey 8, Longeye 8 — and Clearbrief scores 10.
Provenance is a crowded 8-to-10 band. **Cross-source unification is a 10-versus-a-median-of-2.**
That is where the argument has to live.

### F2 · Every competitor answers by retrieval; none answers by traversal

The finding the product argument rests on, and it is verifiable from vendors' own documentation
rather than their marketing. Across the whole set the mechanism is identical — retrieve candidate
passages, place them in a context window, ask a model to reason. The differences are in retrieval
quality, not in kind, and answer completeness is therefore bounded by the retriever. Every vendor
who documents this honestly says so (the caps in §1).

A graph changes what a question *is*. Resolve evidence into people, devices, accounts, events and
transfers with a source on every node, and *"who contacted this person in the fortnight before
that transfer"* stops being a search and becomes a traversal with a definite answer over
everything ingested. Nothing is sampled, so nothing is silently missed.

**So — the sentence is not "we cite our answers." It is "we can put a question to the whole case
at once and the answer is grounded in a model of it, not assembled by a language model reading
documents one at a time."** Demonstrable in ten minutes on a real case; no competitor can run the
same demo.

*Lens cross-check:* whole-corpus relational query — Loupe 9, Palantir 9, Siren 9, DataWalk 8,
Linkurious 8, Octostar 8, field median 4. The four platforms that match Loupe here are an
enterprise intelligence platform at $300k+, a search-relevance company with case workflow 2, a
graph front end that needs a pre-populated database, and a federated-query tool designed
explicitly to *avoid* building a model. None of them can ingest a UFDR.

### F3 · The category exists to make a pile smaller. Investigation exists to build an account up.

The deepest difference in the document, and it explains several of the others.

eDiscovery is a **reductive** discipline. Early case assessment, culling, deduplication,
technology-assisted review, threading, per-gigabyte pricing — the entire apparatus exists to take
an enormous corpus and make it small enough that humans can read what remains. The verb is
*reduce*, and vendors say so: Nuix markets its enrichment as cutting review volumes 40–60%.
Success is defined as fewer documents to look at.

Investigation runs the opposite way. Nobody building a defence theory is trying to read less; they
are trying to assemble an account of what happened. Every artifact processed should make the model
richer, not shorter. The unit of progress is not "documents remaining in the queue" — it is "what
do we now know, what connects to what, and what still doesn't fit."

**This reframes the phone-data finding as a consequence rather than an oversight.** If the job is
to cull toward a reviewable set, a call log is noise — it isn't document-shaped, nobody is going
to read it, so flattening it into a spreadsheet is rational. If the job is to build a model, that
same call log is connective tissue. The majors are not failing at phone data because they lack
engineering. They are discarding it because their paradigm has no place to put it, **and their
pricing rewards having less of it.**

The constructive layers that do exist are bolted onto reductive platforms and inherit the limits —
Everlaw's Storybuilder, DISCO's Timelines, Relativity's aiR for Case Strategy, Casefleet's
approved-facts model. All real, all good, all document-scoped.

**So — the workspace framing is the product's thesis, not a UI preference. It also argues directly
for per-matter pricing: per-gigabyte pricing pays the customer to keep evidence out.**

### F4 · Everyone transcribes. Nobody turns what was said into evidence you can query.

The weak version of this claim is easy to disprove, so state the strong one. Transcription is
close to universal in 2026 — JusticeText is built on it, Longeye does real-time transcription and
translation, Matey transcribes at ingestion, Harvey returns speaker labels and timestamps, Hebbia
bulk-transcribes a hundred files across sixty languages, Casepoint added it in March 2026,
Cellebrite's Guardian summarises audio threads, Cognyte analyses speech down to accent and affect.
**Anyone claiming transcription as a moat will be corrected in the first demo.**

What happens next is where every one of them stops. The transcript becomes a *document* —
searchable text beside other searchable text. The name spoken in a jail call at 02:14 is a string
in a file. It is not the same object as that person's name on a bank statement, a contact record
in a phone extraction, or a line in a police report, and no question can traverse between them.

Loupe extracts entities out of transcripts, video and images and resolves them into the same case
graph as everything else — one identity, several sources, each citable back to the artifact and
timestamp. That makes cross-modal questions answerable: *who is mentioned in these calls who also
appears in the financial records but never in the disclosure?*

That nobody else does this follows from the structure already established: **the tools that
transcribe well have no graph to put entities in; the graph platforms that could hold them have no
ingestion pipeline for audio and video. The capability requires both halves and the two halves
live in different companies.**

*Lens cross-check:* multimodal entities into the model — Loupe 9 (sole leader), Cognyte 7, Axon 7,
Magnet 6, Pathfinder 6, JusticeText 8. Field median 2.

**So — never sell transcription. Sell what transcription becomes.**

### F5 · Configuration happens at review time everywhere else; Loupe configures the front door

Competitors let you tune how AI reviews material that is *already loaded*: Relativity's no-code
custom analyses for aiR, Reveal's AI Model Library transferable across matters, Everlaw's custom
extractions, Harvey's Agent Builder and five hundred prebuilt agents, Nuix's AI-tuned solution
packs. All of it operates after ingestion, on a corpus whose shape is fixed.

What eDiscovery calls a "processing profile" is a technical artifact, not an analytical one —
deduplication, OCR settings, time zone, container expansion. It governs how bytes are unpacked,
not what the system understands them to mean.

Loupe's AI processing profiles sit at the ingestion step and govern extraction itself: which
entity and event types matter for this matter, how this document family should be read, what a
financial record means here versus in a different case.

**So — this is the mechanism behind F2 and F4. You can only traverse a model you actually built,
and you only get a model worth traversing if extraction was directed at ingestion.** It is also
the honest answer to *"couldn't you just point an LLM at the files?"* — you could, and you would
get a pile of text.

### F6 · Phone evidence is the category's structural blind spot, and it is not closing

The finding that matters most, because nobody is fixing it.

Where phone support exists in the legal stack, only chats survive as reviewable objects — and even
those get chopped into artificial units. **Everlaw splits conversations every thousand messages.
Reveal slices them into 24-hour blocks, each block becoming "a document."**

Everything else is discarded into a spreadsheet. Relativity's own processing documentation is
explicit: calls, contacts, calendar, locations, web history and installed apps flatten into Excel
files in an "Other Data" folder; call logs emerge **"only as call log data in Excel format, not as
individual records"**; voicemail recordings are unsupported; **multi-device extractions are
unsupported outright.** DISCO and Casepoint show no Cellebrite documentation at all. i2 removed
native UFED import at version 9.1.0 and now instructs customers to export CSV and hand-write an
import spec.

The forensics vendors have the opposite problem — they model devices beautifully and documents
barely. Guardian's launch release claims documents, images, mobile data and CDRs but not audio
transcription, financial records or email. **Magnet unifies mobile, cloud, computer, drone and
vehicle — five kinds of device, no kinds of document.**

*Lens cross-check:* device data as structured evidence — Magnet 10, Guardian 10, Pathfinder 10,
Loupe 9, Exterro 7, TrialKit 7, Longeye 6. Field median **1**. Twenty-two of 47 platforms score 0
or 1.

**So — the sentence to own is not "we handle phone data." It is "a call at 02:14 and a wire
transfer and a paragraph of a police report are the same kind of citable object here."**

### F7 · The defence cannot buy the analytics the prosecution runs on

This asymmetry is documentable, which makes it usable.

- **GrayKey** is explicitly restricted to law enforcement, public safety and defence agencies,
  with agency-email vetting; Magnet states plainly it is not available to the private sector.
- **Cellebrite Pathfinder** — the analytics layer, not the extraction tool — is marketed solely to
  law enforcement, government, intelligence and corporate investigators. No defence sales channel
  surfaced anywhere in the research.
- **The sharpest artifact in the corpus:** a Florida State Attorney's office publishing
  instructions for defence counsel on how to receive phone extractions through **read-only
  Guardian share links.** The defence reviews the prosecution's evidence inside the prosecution's
  tool, with the prosecution's permissions.
- What defence teams *can* buy — Magnet Axiom, Exterro FTK, Cellebrite Physical Analyzer — is
  device-by-device examiner tooling with no cross-evidence analytical model.
- **Siren** has genuine native Cellebrite connectors and gates them to "qualifying organisations."

*Lens cross-check:* commercial accessibility — Pathfinder 1, Guardian 1, Palantir 1, Relativity 2,
Cognyte 2, Nuix 2, against Loupe 7. In the criminal-defence profile, accessibility is a hard gate
at 5 and it eliminates seven of the nine platforms that outscore Loupe.

**So — "levelling the evidentiary playing field" is not a slogan, it is a description of a
licensing structure. Say it plainly and source it.** This table is the single most valuable asset
in the corpus and it was buried in an appendix until July.

### F8 · AI for criminal defence is no longer whitespace — four funded companies are already there

The correction the plan needed.

| Company | Funding & scale | Sells to | Pricing |
|---|---|---|---|
| **TrialKit** | $4.25M seed Apr 2025 (UpWest, 97212, Kaedan, NYU Law venture programme). 20+ defence firms at launch. | Private criminal-defence firms. LA County Public Defender and Reed Smith named. **Closest to Loupe's stated buyer.** | Not published. Demo-led. |
| **Matey / CrimD** | $7.5M seed Aug 2025 (Timespan, Neo, Streamlined). Austin. Claims 90% time saved on discovery review, $40K+ saved per case. | Defence-only. **NACDL affinity partner and exclusive AI eDiscovery partner of the South Carolina defence bar.** | Not published. PD proof-of-concept as land-and-expand. |
| **JusticeText** | ~$2.2–2.5M seed (Bloomberg Beta, True, Reid Hoffman, Michael Tubbs) + Google Black Founders Fund. **$4.0M ARR, 4,100+ attorneys, 20 states, ~3,000 hours of footage weekly.** | Public-defender institutions first — 7 of 22 statewide PD systems, 70+ agencies — then ~300 private firms. | One public datapoint: **Cumberland County PA, $17,300/year**, grant-funded. |
| **Longeye** | $5M seed led by a16z American Dynamism, Sept 2025. Self-hosted on AWS GovCloud, no third-party AI APIs. | Both sides — prosecutors and public defenders. **The only competitor whose own copy names phone extractions, bank records and documents together.** | Free to public defenders by stated intent. Price is the wedge. |

Three of the four publish no pricing at all — this is demo-led relationship selling, not a
self-serve category. The single public number is JusticeText's **$17,300 county contract, paid by
a grant.** Against Loupe's proposed $6,000–24,000 per matter, that is the anchor a public-defence
buyer arrives with — and it is paid per *year*, not per case.

**Two of the four use free or subsidised access as the wedge**, which drags the segment's price
expectation down and is the strongest argument against entering public defence early. **Only Matey
targets the same buyer Loupe does** — private practices with their own budget — and it is also the
only one of the four holding both SOC 2 Type II and ISO 27001.

Keep scale in proportion: $2.5M–$7.5M seed rounds, not war chests. JusticeText's $4.0M ARR is the
only revenue figure disclosed. **The beachhead competitive set is four companies with one to two
years of runway each** — a very different fight from Relativity or Palantir, and a winnable one.

None of them has a knowledge graph. Only TrialKit claims phone extractions, and only as another
input type. But they have the category label, the bar associations, the certifications and the
logos.

**So — do not pitch "AI for criminal defence." That sentence is taken and better funded. Pitch the
evidence model, and treat these four as the comparison set rather than Palantir.**

### F9 · The two halves of the answer sit in different companies

Entity resolution across Relativity, Everlaw and Reveal is, without exception, **email-header
alias consolidation**: Name Normalization parses headers into Entity records; Everlaw's Entity
Management groups contact addresses by shared name words; Brainspace merges nodes manually.
Communication analysis exists at all three and is email-only — it does not span chat or phone
identities. Harvey, Hebbia, CoCounsel, Clearbrief and CaseMap build no entity model at all.

The graph vendors have the opposite problem. **Linkurious** is a front end requiring an
already-populated graph database; its only native ingestion is a CSV import added in 2026.
**Maltego's** graph is an analyst's canvas fed by outbound OSINT queries, with no path for
received discovery. **Octostar's** virtual graph over ClickHouse is explicitly designed to avoid
ETL — it federates databases an agency already owns, the exact inverse of a defence case where
nothing is modelled until you model it.

**So — the intersection of graph-native and pipeline-native is genuinely unoccupied, and it is
exactly what whole-corpus querying requires.**

This is an **architecture claim** — a statement about what the system is built on rather than what
features it has. A feature claim ("we have a timeline view") can be copied in a sprint and cannot
be proved in a meeting; an architecture claim can be tested live in ten minutes and takes a
competitor eighteen months to close.

### F10 · Durable narrative objects exist — but none of them can hold a phone call

The Loupes concept is less unique than it looked, and the precise version of it is more unique
than it looked.

The sharpest example is **Comtrac**, whose "Elementising Evidence" methodology maps exhibits
directly to the elements of an offence and auto-populates an investigation matrix with what must
be proven — the closest shipped analogue anywhere to a curated, evidenced collection assembled to
establish something. It is exhibit-scoped and cannot hold a call or a transfer.

**Everlaw's Storybuilder Fact Management** (shipped December 2025) makes facts first-class objects
linked to evidence, people, depositions and drafts — and it is now bundled free. **DISCO
Timelines** persist from case opening to trial with facts dragged from the document viewer.
**Relativity's aiR for Case Strategy** classifies facts as helpful or harmful and arranges them in
issue swim lanes. **Casefleet** has an approved-facts model. **CaseMap+** is built on the concept.

*Lens cross-check:* durable judgment objects — Loupe 9, Everlaw 9, CaseMap+ 9, Casefleet 9,
Comtrac 8, DISCO 8, Relativity 8. **This is the most crowded of Loupe's strong axes and the one
where the differentiator is narrowest.** The difference is not the object — it is what the object
can contain. Every competitor's collection holds documents and facts derived from documents.
Loupe's can hold a call, a transfer and a location as members.

### F11 · Disconfirmation is unclaimed — but narrow versions exist, so the claim must be precise

No platform in the set markets contradiction detection or disconfirmation as a headline
capability, and that remains true. But narrow versions exist and the claim must survive a demo:

- **JusticeText's Miranda AI** identifies inconsistencies across A/V discovery. Scores 6.
- **Clearbrief's** cite-checking catches fabricated citations inside your own filing. Scores 5.
- Relativity's helpful-versus-harmful fact classification and gap-spotting.
- NexLaw ChronoVault flags conflicting testimony and timeline gaps.
- Siren's K9 flags its own uncertainty.
- Octostar used the word "contradictions" once, on a conference booth sign, with no product
  behind it.

**Neither Miranda nor Clearbrief runs disconfirmation over a structured claims ledger — and the
ledger is the difference between flagging an inconsistency and enumerating what would break a
theory, including the document that does not exist.**

This is also the answer to the strongest objection the hypothesis framing invites. An investigator
who states a theory and has a machine populate it is doing confirmation bias at speed, and
opposing counsel will say exactly that. **A tool that systematically looks for what breaks the
theory is not a disclaimer bolted onto that risk — it is the inversion of it.**

*Lens cross-check:* disconfirmation detection — Loupe 8, JusticeText 6, Clearbrief 5, Palantir 2,
Relativity 2. **Thirty-three of 47 platforms score 0.** Field median 0.

**So — build it.** It is the only capability in the document no competitor has claimed, it answers
the sharpest question about the product, and it requires the claims ledger the provenance model
already implies.

---

## 3. Positioning — the top-right quadrant is empty

Two axes, both derived from the research rather than asserted: **how deep the evidence model
goes**, and **how small a buyer the commercial model can actually reach.**

> Every platform that handles evidence properly sells to agencies. Everything a small practice can
> buy handles documents only.

Vertical position is how much of the real evidence mix a platform models as structured, citable
objects rather than attachments. Horizontal position is the smallest customer that can realistically
buy and run it. **Loupe's own position is a claim about the product, not a measurement — the point
of the chart is the shape of everyone else.**

The thirty-axis lens confirms the shape numerically. Cross-tabulating group A (evidence modelling,
/60) against commercial accessibility:

| | Accessibility ≤ 2 (agency-only) | Accessibility 5–7 | Accessibility 8–10 (self-serve) |
|---|---|---|---|
| **Evidence modelling ≥ 35** | Palantir 40, Pathfinder 37, Guardian 35, Magnet 38 | **Loupe 55** | — |
| **20–34** | Cognyte 33, DataWalk 33, Nuix 27, Everlaw 24 | Exterro 31, Matey 30, Longeye 32 | TrialKit 33 |
| **≤ 19** | Relativity 20, Casepoint 16, Babel Street 25 | Reveal 19, CaseMap+ 19, Comtrac 16 | Clearbrief 15, Casefleet 19, CROSStrax 6, Trackops 6 |

The top-right cell is empty except for Loupe, and TrialKit at 33 is the nearest thing to a
neighbour. That is the whole positioning argument in one table, and unlike the chart in the
artifact it is computed rather than asserted.

---

## 4. Whitespace — what is actually unoccupied

Separating the genuinely empty from the merely crowded-but-winnable, because the two demand
different strategies.

**Genuinely empty.** Four things: whole-corpus questions answered by traversing a model rather
than retrieving passages; a case model holding phone, financial and document evidence as one
citable object set; disconfirmation as a first-class capability; and narrative collections whose
members can be *events* rather than only documents. Nothing in the research contradicts any of
these, and the first three were searched for specifically.

**Crowded but winnable.** Defence-side AI discovery has four funded entrants, none with a graph or
a real device model. **The competition is for the category label, not the capability** — and the
capability is where a pilot is won or lost once a firm actually loads a case.

**Available but shallow.** Audio and video transcription is now close to universal and must not be
sold as a differentiator. Constructive workspaces exist too — Storybuilder, DISCO Timelines,
Casefleet, CaseMap — but every one is a curation layer over a reductive document platform. The
difference is not that the feature is missing; **it is that the platform underneath is built to
subtract.**

**Closed.** Cited *document* Q&A, chronology generation from documents, and per-seat legal AI
assistants. Done, free or nearly free, and entering them means competing with Relativity's
distribution and Harvey's balance sheet.

**The gap nobody is defending.** Small and mid-sized investigative practices are structurally
underserved by every incumbent, and the reason is economic rather than technical:

| Platform | Entry economics | What the buyer gets |
|---|---|---|
| Harvey | ~$360,000/yr with seat minimums | AmLaw-priced legal AI, no evidence model |
| DataWalk | ~$560,000 | Graph + financial, enterprise procurement |
| Palantir | >$1M average per deal | Everything, unpurchasable |
| Relativity | Small firms via partner channel only | Review platform, no direct route |
| Casepoint | Federal agencies | FedRAMP High, no small-firm motion |
| i2 Analyst's Notebook | ~$7,160/yr | Manual charting, **no LLM in any tier** |
| Logikcull PAYG | low | Document hosting |
| **CROSStrax** | **$35/month** | PI case management, evidence modelling 6/60 |
| **Trackops** | **$99/month** | PI case management, evidence modelling 6/60 |

**The buyer already owns cheap case management and owns nothing that analyses evidence.** CROSStrax
and Trackops are built specifically for private investigators — the exact beachhead buyer — and
they are 46th and 47th of 47 in the study.

### The one to watch — a competitor's strategy, not ours

To be unambiguous: **giving Loupe away to public defenders is not the plan, and this section is
the reason we do not enter that market first.** The free tiers described here belong to rivals.
Everlaw for Good is free, covers CJA panel attorneys explicitly, and has passed **$6M in donated
technology across 235–300 organisations.** It is charity-funded, which caps how far it can scale —
but it means a federal defence attorney can already get a serious platform for nothing. **Any
pricing conversation in this segment happens in that shadow.**

---

## 5. Beachhead — where to land and what it costs to get in

### The buyer

**Defence-side private investigators and criminal-defence boutiques — firms of roughly five to
fifty people running federal or serious state matters.** Not public defenders, not police, not
corporate legal, not AmLaw.

The defining characteristic is not size or sector: **it is that this buyer receives evidence
rather than collecting it, receives it in formats built by the other side, and has no way to
analyse it properly.** A defence team is handed a UFDR extraction, a disclosure bundle, subpoena
returns and bank records, and the tools that could make sense of that combination are either sold
exclusively to law enforcement, priced for enterprises, or built to cull documents rather than
model a case.

*Lens confirmation:* in the criminal-defence profile Loupe ranks **first of 47 on fit at 87%**,
meets **12 of 12 core requirements**, and clears every gate. Only ten of 47 platforms clear every
defence gate, and the best of the rest on fit are Magnet (80%) and Exterro (76%), both device-only
examiner tools.

### Why this buyer and not the adjacent ones

| Segment | Why not first |
|---|---|
| **Public defenders** | Highest need, least money. Longeye intends to give its platform away; Everlaw for Good already covers CJA panel attorneys at no cost. Lens: accessibility gated at **8**, Loupe scores 7 — nothing that is not free clears it. Serve them later through grants or a donated tier. |
| **Police & prosecution** | Longest procurement, heaviest compliance burden, and the market every incumbent was built for. Cellebrite owns the extraction and now ships agentic AI over it. Lens: Loupe 15th on fit — the gap is forensic validation and disclosure mechanics, not paperwork. Fighting on their ground with none of their advantages. |
| **Corporate investigations** | **The right second market** — higher contract values, same product, no phone-data dependency. Wants SOC 2 and a reference customer; unlikely to close in year one. Lens: Loupe 15th at 73% fit, clearing every gate. |
| **Financial crime** | Quantexa, DataWalk and Siren entrenched and genuinely good; phone evidence barely features; the buyer is a bank. Lens: Loupe 17th at 72%. Wrong fight. |
| **Investigative journalism** | Excellent proof, terrible revenue. Linkurious and Everlaw both donate here. Lens: Loupe **3rd at 84% and fails no gate** — the best unpaid showcase available. Treat it as marketing, not a market. |

### How to reach them

This segment has no procurement department and does not read analyst reports, which cuts both
ways: **nobody can block you, and nobody is looking for you.** Three routes in order of proven
effectiveness:

1. **The defence bar, because it demonstrably works.** Matey went from a seed round to national
   presence by becoming a NACDL affinity partner and the exclusive AI eDiscovery partner of a
   state defence-lawyers' association. That is a published, repeatable playbook; the endorsement
   carries more weight with a fifteen-person practice than any marketing spend. **This should be
   the first commercial action taken.**
2. **Casework referral from the practice that already runs Loupe.** The platform was built inside
   a working private-investigations firm and has carried federal matters to trial. Every attorney
   on the other side of those cases has seen the output. A warm, credible list nobody else can
   assemble.
3. **The demo, as the whole sales motion.** Nothing in this market is won on a feature list. It is
   won by loading a real extraction and a real disclosure bundle in front of a sceptical
   investigator and asking a question that spans both. **Every competitive claim in this document
   is demonstrable in ten minutes; none of it is provable in a deck.**

### What has to be fixed first

**SOC 2 Type II.** Matey — the closest direct competitor, same buyer — holds SOC 2 Type II and ISO
27001 today. Longeye holds SOC 2 Type II and runs single-tenant on GovCloud. In a segment handling
privileged material under protective orders this is a question a firm's counsel will ask, and it is
among the cheapest items on the list to close. It is a procurement step taken when a deal requires
it, not a barrier to fit: **the lens excludes certifications from gating and scoring entirely, for
every platform, and Loupe still clears every gate in thirteen of fifteen markets.** What actually
constrains reach is different in each case — commercial accessibility in public defence, evidence
acquisition in national security.

Second, the two capabilities this document leans on that are not yet shipped — **Loupes and the
disconfirmation agent** — need to demo clean once before they appear in any external material.
Build first, claim second; anything unshipped on submission day becomes the roadmap answer.

### The sequence, in one line

> Get SOC 2. Win the defence bar through NACDL and one state association. Convert the casework
> referrals already available. Price per matter against investigator hours. Then, with references
> and a certification in hand, move to corporate internal investigations — where the same product
> carries a larger contract and phone data stops being the point.

---

## 6. Pricing — the entry-price ladder and the band nobody occupies

**The distribution is barbelled.** Below $10,000 sit document tools and one legacy charting
product; above $300,000 sit the platforms that model evidence properly. **The middle — real
evidence capability at a price a fifteen-person practice can authorise without a procurement
process — is close to vacant.**

The thirty-axis data makes the barbell literal:

| Band | Platforms | Best evidence-modelling score (A /60) | Median total |
|---|---|---|---|
| < $10k | 8 | i2 18, Casefleet 19, Clearbrief 15 | 121 |
| **$10–50k** | **14** | **Loupe 55**, then TrialKit 33, Longeye 32, Exterro 31 | 130 |
| $50–300k | 18 | Magnet 38, Pathfinder 37, Guardian 35 | 139 |
| $300k+ | 7 | Palantir 40, Cognyte 33, DataWalk 33 | 150 |

**Loupe's group-A score of 55 is 17 points clear of the best-modelling platform at any price, and
22 points clear of anything else in its own band.**

### What this implies for the model

**Price per matter, not per seat** — and note that per-gigabyte pricing is not neutral. It charges
by evidence volume, which **pays the customer to keep evidence out of the platform.** Coherent for
a discipline whose goal is culling; incoherent for one whose goal is building a complete account.

Four arguments converge on per-matter:

1. The work is case-shaped. A seat licence misprices a practice running four large matters a year
   and a hundred small ones.
2. **The buyer already thinks this way.** The ex-FBI principal benchmarked against the cost of a
   junior investigator or overseas review staff — a per-matter labour substitution, not a software
   subscription.
3. It puts Loupe in a budget line that already exists and is already large.
4. It sidesteps a direct price fight with a free tier. **Everlaw for Good cannot be undercut, but
   it can be out-scoped.**

**The defensible band is roughly $6,000–24,000 per major matter**, positioned explicitly against
what the same review costs in junior-investigator hours. The pool that band is drawn from is the
services spend, not a software budget: US criminal-defence firm revenue exceeds $15B a year across
roughly 252,000 practitioners, and private investigation services run about $22B globally. Market
sizing for all fifteen buyer profiles is in §7a of the Market Fit Lens narrative. That lands above every document tool, far
below every evidence platform, and inside what a federal defence budget already absorbs for expert
work.

**The counter-anchor to be ready for:** JusticeText's Cumberland County contract at $17,300 for a
year, grant-funded. A public-defence buyer will arrive with that number and it is per year, not
per case. This is a further argument for entering private defence first.

---

## 6a. What each market is worth

### The conclusion

**The field splits into two halves that never meet, and the buyer sits in the gap between them.**

One half can model evidence. Cellebrite, Magnet and Palantir build real structure out of what they
ingest — and either they will not sell to a defence practice at all, or what they model is devices
and nothing else. Magnet unifies five kinds of hardware and no kinds of document. Pathfinder builds
a genuine graph and is marketed solely to law enforcement, government and intelligence.

The other half serves the buyer. Relativity, Everlaw, DISCO, Reveal, Harvey, CoCounsel — all
purchasable, all excellent at documents, and all of them treat a phone extraction as an attachment.
Relativity's own documentation says call logs emerge "only as call log data in Excel format, not as
individual records," and that multi-device extractions are unsupported outright.

Forty-seven platforms, and the intersection is empty. That is not an artifact of how the axes were
drawn — it is structural. Modelling evidence and serving this buyer are different engineering
problems sold to different customers, and the companies that solved one have no commercial reason to
solve the other. Four funded startups have entered the defence-AI category in eighteen months, which
settles the question of whether the buyer spends. **None of them has a graph.**

**The gap is not that nobody is good enough. It is that the capability and the customer live in
different companies.**
**One more thing this explains.** The team went looking for a platform to run live federal casework,
**tried a number of them, and none could work the case.** Building was the second choice, not the
first. That is the structural finding arriving as lived experience rather than as analysis — a buyer
in this position evaluates the market and finds that everything able to model the evidence will not
sell to them, and everything that will sell to them treats a phone extraction as an attachment.
Trying several and finding none fit is the predicted outcome, not bad luck.

---

**On cost, the finding is simpler and more useful: this budget is already being spent.**

A defence team does not choose between Loupe and a competitor. It chooses between Loupe and what it
does today — which is to pay a forensic vendor to extract each device, pay per gigabyte per month to
host the result somewhere it cannot be properly analysed, pay an examiner by the hour to look at
parts of it, and then pay its own people to stitch the pieces together by hand.

On a serious matter that runs to **$34,000–$131,000 and sixty to a hundred hours of evidence
handling before anyone has answered a question about it** — and the largest single line in it, hosting, is charged per
gigabyte per month, so it grows with exactly the material this platform exists to model. A 435GB
federal case costs $4,350 a month to keep hosted. The outcome that money buys is a spreadsheet.

**So the sale is not "find budget for this." It is "you are already paying for this, and here is what
you are getting for it."** That is a far easier conversation, and it is why the absence of an
analyst category for defence-side investigation software does not indicate an absent market. The
spend is real, recurring and per-matter. It simply flows to vendors rather than to software, which
is what a category looks like immediately before it forms.

The one line that does not move is extraction: devices still go out to a vendor at $3,650 a case.
Everything downstream of it does.

**The scale of it.** Somewhere between 48,000 and 125,000 evidence-heavy private criminal-defence
matters run in the United States each year, carrying **$1.0–7.5B** of displaceable spend, inside a
services market above $15B. Capturing a fifth of the displaceable value across one to five thousand
firms is a **$350M–$900M** business — before any of the adjacent markets, all of which this same
product already scores respectably in.

**The sentence for a room:**

> **A serious case burns $34,000–$131,000 on processing, hosting and examiner time before anyone has
> answered a single question about the evidence. Loupe replaces that layer for a fraction of it —
> and hands back thirty to fifty investigator hours per matter.**

Everything below is the working behind those four paragraphs.

---

### The evidence behind it — market by market

| Market | Sized category | 2026 size | Forecast | Loupe fit | **Loupe rank** | Reach |
|---|---|---|---|---|---|---|
| **Prosecution & law enforcement** | Law enforcement software | **$22.0–22.9B** | $39.2B by 2032 (9.8%) | 70% | 15th | clears |
| **Law firms & civil disputes** | eDiscovery incl. services (software only $8.6B) | **$20.7B** | $23.7–31.5B by 2030 | 68% | **20th — worst** | clears |
| **Intelligence & national security** | OSINT | **$8.7–23B** | $34.1B by 2035 (16.4%) | 74% | 8th | **fails acquisition** |
| **Insurance SIU / fraud** | Insurance fraud detection | **$8.5–11.3B** | $19.6B by 2030 (**23.2% — fastest**) | 77% | 7th | clears |
| **Corporate & internal investigations** | Investigation management software | **$8.1B** | $21.5B by 2033 (14.8%) | 73% | 15th | clears |
| **Corporate security & insider threat** | Insider threat protection | **$5.7–6.6B** | $20.2B by 2035 (13.1%) | 75% | 13th | clears |
| **Due diligence / KYC** | KYC software $2.5B · KYC broad $7.8B · DD services $2.5B | **$2.5–7.8B** | DD services $5.2B by 2034 | 74% | 12th | clears |
| **Financial-crime units** | AML software | **$2.8–4.0B** | $6.5–6.8B by 2032–34 | 72% | 17th | clears |
| **Ethics, compliance & whistleblower** | Whistleblowing software | **$0.28B** | $0.46B by 2033 (6.5%) | 74% | 18th | clears |
| **UK / EU policing** | Inside law enforcement software | *not separately sized* | — | 70% | 15th | clears |
| **Regulators & government enforcement** | Spans law enforcement + investigation mgmt | *not separately sized* | — | 73% | 8th | clears |
| **Public-sector fraud** | Spans law enforcement + fraud detection | *not separately sized* | — | 72% | 14th | clears |
| **Criminal defence & PI** | No software category — services substitution | **services pool** | — | **87%** | **1st — best** | clears |
| **Public defender offices** | Grant-funded; no commercial category | *effectively unpriced* | — | 86% | 3rd | **fails accessibility** |
| **Investigative journalism** | No market — donated and grant-funded | *unsized by design* | — | 84% | 3rd | clears |

Read the rank column down the page. The table is ordered by market size, and the ranks run 15th,
20th, 8th, 7th, 15th — with **1st** appearing only at the bottom, beside the one market that has no
size at all. **Loupe fits best exactly where the analysts have drawn no category.**

Insurance SIU is the exception worth watching: seventh of forty-seven, no gate for any platform, and
the fastest-growing category in the set. The only thing between Loupe and the top of that table is
OSINT, scored 0 — a build item, not a commercial barrier.

### What a case costs, line by line

Three lines exist in every phone-heavy defence matter, and only one survives.

**Retained — extraction.** Devices still go to a forensic vendor: $1,575–2,975 per phone, $3,650 flat
for a one-or-two-device case, +$600 per device beyond. Loupe analyses what was produced rather than
acquiring it. This line is untouched and is never claimed as a saving.

**Displaced — processing, hosting, examiner analysis.** Processing $3–10/GB; hosting **$5–15 per
gigabyte per month** for the life of the matter; examiner analysis $300–500/hour.

**Released — investigator and paralegal hours.** RAND's National Public Defense Workload Study puts
defence work at 35 hours for a low-severity felony, 57 mid, 99 high, 167 for sex offences, 248 for
murder, 286 capital. Investigator time bills $85–225/hour (average $132), paralegal $100–200.

| Per matter | Mid felony<br>57h · 1 phone · 30GB | Doc-heavy fraud<br>2 phones · 300k docs · 120GB | Serious multi-defendant<br>4 phones · 160GB | Large federal<br>10 phones · 200k docs · 435GB |
|---|---|---|---|---|
| **Retained** — extraction | $3,650 | $3,650 | $4,850 | $8,450 |
| Processing | $150 | $600 | $800 | $2,175 |
| **Hosting** | $1,800 | **$21,600** | **$28,800** | **$104,400** |
| Examiner analysis | $2,400 | $12,000 | $16,000 | $24,000 |
| **Displaced subtotal** | **$4,350** | **$34,200** | **$45,600** | **$130,575** |
| Evidence-handling hours → **hours saved** | 20h → **10h** | 58h → **29h** | 87h → **43h** | 100h → **50h** |
| **Displaceable value** | **$5,846** | **$38,584** | **$52,110** | **$138,082** |
| Captured at $12,000 | 205% | 31% | 23% | 9% |

**Hosting is the line that breaks**, and it is the whole commercial argument. Charged per gigabyte
per month for the life of the matter, it scales with precisely the evidence this platform models. A
435GB federal case is $4,350 a month — over $100,000 across two years, more than three quarters of
everything displaceable, spent to have phone data emerge as spreadsheets. At 800GB it is $8,000 a
month.

**A flat per-matter price is wrong at both ends.** Displaceable value moves 24× between the smallest
and largest matters. At $12,000 the platform captures 205% of a one-phone case and 9% of a ten-phone
federal one. Price has to scale with device count, data volume and duration — the same drivers as
the model it displaces. That is a decision to make before a number is quoted to a prospect.

**Two assumptions carry the labour row and should be tested rather than asserted:** that roughly 35%
of case hours are evidence handling, and that half of that is removed. The vendor rates are published
and the case hours are RAND's; only the labour conversion is modelled. Matey publishes "90% time
saved on discovery review and $40K+ saved per case" for the same buyer, which corroborates the
magnitude without validating the split.

**One limit, stated plainly.** This holds for firms that already pay a vendor to process and host. A
share of small practices receive a hard drive and host nothing — there is no invoice to displace, and
the value is capability rather than substituted spend. It splits the pitch: *cheaper than what you
pay now* for the hosting firms, *you can finally do this at all* for the rest.

### How many matters

US felony filings run **1.6–2.5M a year**. Around a fifth are privately retained — **320,000 to
500,000 matters**. The evidence-heavy share carrying phone extractions and real document volume is
conservatively 15–25%: **48,000–125,000 matters a year**. At $20,000–60,000 of displaceable spend
each, that is **$1.0–7.5B flowing through private US criminal-defence matters annually**, inside a
services market exceeding $15B.

**On that felony figure.** BJS no longer publishes a national felony filing total — its series ended
with collections closed in 2006, and the live collection reports processing characteristics rather
than volumes. The Court Statistics Project holds the number but publishes it only through an
interactive dashboard that is not machine-readable: **Explore court caseload data → Criminal →
Incoming → Felony** returns it in about two minutes for anyone with a browser, and that is the right
way to replace this range with a figure. The bound above is built from CSP's 70M total state court
filings (2024), the historical BJS series, and California's published 183,151 felony filings.

At a fifth of displaceable value across 1,000–5,000 target firms, the bottom-up market is
**$350M–$900M**, with a path above a billion at the top of that firm range.

### The growth path — four stages, and what each requires

Priced at a blended **$12,000 per matter**. A typical boutique runs about eight evidence-heavy
matters a year and is worth roughly **$96,000 annually**; an active practice at twenty matters is
worth $240,000. The figures below use the conservative rate throughout.

| | **1 · Proof**<br>Owl & Ireland | **2 · The engine**<br>United States | **3 · Second geography**<br>+ United Kingdom | **4 · Expansion**<br>+ Europe |
|---|---|---|---|---|
| **ARR** | **$0.5M** | **$5M** | **$10M** | **$25M** |
| Customers | 5 | 52 | 104 | 260 |
| Matters / year | 42 | 417 | 833 | 2,083 |
| Share of the US evidence-heavy pool | — | 0.3–0.9% | 0.7–1.7% | 1.7–4.3% |
| Addressable pool added | Irish criminal legal aid €123M (services) | 48,000–125,000 matters/yr carrying **$1.0–7.5B** displaceable | ~80,200 open Crown Court cases → 104,500 by 2029; UK is 21.76% of European forensics (~$525M) | European digital forensics **$2.41B → $3.89B**; legal tech **$6.81B → $15.45B** |
| Channel | Law Society and Criminal Legal Aid panel | The defence bar — the channel Matey has proven | Law Society and Criminal Law Solicitors' Association | Partner-led, per jurisdiction |
| What gates it | A validated price from real matters | The bar channel converting | The per-matter model rebuilt on UK vendor and Legal Aid Agency rates | Partners, because every jurisdiction has its own procedure and disclosure regime |

**The point of the staircase is the customer and matter counts, not the ARR.** Ten million in
recurring revenue requires 104 customers running 833 matters between them — **under two per cent of
the US evidence-heavy pool alone**, before the UK or Europe contribute anything. Twenty-five million
requires 260 firms. Against a target population of one to five thousand practices, none of these
stages asks for market dominance. They ask for a channel that works and a price that holds.

**Each stage is gated on one thing rather than many**, which is what makes the sequence testable.
Stage 1 exists to produce a validated price and nameable references — it is not a revenue stage and
should not be defended as one. Stage 2 is where the business is. Stage 3 adds a second geography with
the same buyer shape and a funded government backlog behind it. Stage 4 trades direct selling for
partners and rests on the deployment-control advantage.

Customer counts assume the conservative eight-matter firm. At the twenty-matter active practice the
same revenue needs two and a half times fewer customers — 42 firms for $10M rather than 104. The
real mix will sit between the two, and the first cohort is what establishes which.

### Ireland, the UK and Europe

The analysis above is US-shaped because the beachhead is. The same structure exists in Europe, and
for an Irish company it is the nearer market.

| | Scale | Notes |
|---|---|---|
| **Europe — digital forensics** | **$2.41B (2026) → $3.89B by 2031**, 10.06% CAGR | Software is 44.6% of it; services growing fastest at 11.0% as corporates outsource evidence collection |
| **UK — share of that** | **21.76% of the European market**, roughly **$525M** | The largest single European market for exactly this work |
| **Europe — legal technology** | **$6.81B (2026) → $15.45B by 2034**, 10.78% CAGR | Europe is **25% of the global legal-tech market**; the UK holds the largest European share |
| **England & Wales — serious criminal caseload** | **~80,200 open Crown Court cases** (Dec 2025), receipts near series highs | Projected to **99,000–114,000 by March 2029** — central estimate 104,500 |
| **England & Wales — criminal legal aid** | ~55% of all legal aid expenditure; **+£92M** announced July 2025, fee increases December 2025 | Spend is rising, not falling |
| **Ireland — criminal legal aid** | **€123M allocated for 2026**, up €27M | Full restoration of criminal legal aid fees |
| **Ireland — Courts Service** | **€215M** total spend, up 8%, plus 20 additional judges in 2026 | Capacity is being funded |

**Three things make Europe more than a second market.**

**The Crown Court backlog is a stated government problem with money behind it.** Eighty thousand
open serious cases, rising toward a projected 104,500, with new funding directed at clearing them.
A tool whose measurable effect is removing hours from evidence handling on serious matters is
aligned to a published policy objective rather than merely to a firm's margin. That is an unusually
favourable position for a procurement conversation.

**Data residency is worth more here.** Deployment control — single-tenant, in-jurisdiction,
sovereign — is scored at 9, joint highest in the study. Under GDPR and the CPIA disclosure regime
that is not a preference but frequently a requirement, and most of the American-owned competitors in
this field score 2–6 on it. In the UK/EU policing profile deployment is gated at 7 and only ten of
forty-seven platforms clear every gate.

**Ireland is small, and that is not the point of it.** €123M of criminal legal aid is not a market
to build a company on. It is a credible home reference, a jurisdiction where a Dublin-based company
can run a first public-sector pilot, and the entry point to a European digital-forensics market
growing at 10% a year in which the UK alone is a fifth.

**What is not yet sized.** Europe-wide criminal case volumes are not consolidated the way US state
court data is — each jurisdiction publishes separately, and any European equivalent of the per-matter
model above would have to be rebuilt per country on local vendor rates and local counsel rates. The
figures here are market-level, not bottom-up, and should be treated as the weaker half of the
evidence until that work is done.

### The regional plan

Three jurisdictions, three different jobs. They are sequenced by what each one is *for*, not by size.

#### Ireland — the reference, not the revenue

€123M of criminal legal aid and a €215M Courts Service is not a market to build a company on, and
should never be presented as one. Ireland's job is to produce the first nameable customer in the
company's own jurisdiction.

- **Buyer:** criminal defence solicitors' practices doing Circuit and Central Criminal Court work,
  and the firms on the Criminal Legal Aid panel.
- **Route:** the Law Society and the Criminal Legal Aid panel are the equivalent of the US defence
  bar channel that Matey proved works. Same playbook, smaller room, shorter path to the people who
  matter.
- **What it unlocks:** a European reference customer, a jurisdiction where a Dublin company can run
  a first public-sector conversation without an ocean in the way, and the Dogpatch and NDRC network
  as introduction surface.
- **Gates:** none that bite. EU data residency is trivially satisfied by single-tenant deployment,
  which is scored 9.
- **Fee restoration in 2026 (+€27M) means the segment's budget is rising**, not being cut.

#### United Kingdom — the first real European revenue

The UK is 21.76% of the European digital-forensics market, roughly **$525M**, and it has the
clearest funded pain of any jurisdiction in this study.

- **Buyer:** criminal defence solicitors running Crown Court work — the same shape as the US
  beachhead, receiving evidence they cannot analyse.
- **The tailwind is a government problem with money attached.** ~80,200 open Crown Court cases at
  December 2025, receipts near series highs, projected to 99,000–114,000 by March 2029. Criminal
  legal aid is ~55% of legal aid spend, with £92M added in July 2025 and fees raised that December.
  A product that removes hours from evidence handling on serious matters is aligned to a published
  policy objective, which is a materially different conversation from selling efficiency to a firm.
- **Route:** the Law Society and the Criminal Law Solicitors' Association mirror the NACDL channel.
  Legal Aid Agency rates set the economics, so the per-matter model has to be rebuilt on UK vendor
  and counsel rates before a price is quoted.
- **Sequence: defence first, policing much later.** In the UK/EU policing profile, disclosure and
  production mechanics are gated at 8 under CPIA and **Loupe scores 2** — the heaviest single gap
  anywhere in the study for that buyer. Defence-side work does not carry the disclosure duty in the
  same way, which is precisely why it is the entry point and prosecution is not.
- **BlueLight Commercial's role as a policing procurement gatekeeper is unconfirmed** and should be
  established before any public-sector effort is planned around it.

#### Europe — expansion, on a structural advantage

- **Size:** digital forensics $2.41B (2026) → $3.89B by 2031 at 10.06%; legal technology $6.81B →
  $15.45B by 2034 at 10.78%, with Europe holding 25% of the global legal-tech market.
- **The advantage is deployment.** Single-tenant, in-jurisdiction, sovereign deployment is scored 9,
  joint highest in the study, while most American-owned competitors score 2–6. Under GDPR that
  converts from a preference into a procurement requirement, and it is the one axis where being a
  European company with European hosting is worth more than being a larger American one.
- **The obstacle is fragmentation.** Every jurisdiction has its own procedure, its own disclosure
  regime, its own languages and its own vendor rate card. There is no European equivalent of the US
  state-court dataset, so both the market sizing and the per-matter model have to be rebuilt country
  by country. Treat Europe beyond Ireland and the UK as a partner-led motion rather than a direct
  one, and do not carry a single European TAM figure into an investor conversation as though it were
  addressable in one go.

#### What this means for the sequence

Ireland produces the reference. The UK produces the first European revenue and has the strongest
policy tailwind of any market here. The US remains the largest opportunity and the one the product
was built inside. Europe beyond those two is a later, partner-led motion whose value is the
deployment-control advantage rather than any single national market.

Sources: 2026 estimates published by Grand View Research, Fortune Business Insights, Mordor
Intelligence, MarketsandMarkets, Precedence Research, Verified Market Reports, Research and Markets,
ComplexDiscovery and IBISWorld, retrieved 29 July 2026. None is a primary source commissioned for
this study. The **$3.5B-by-2030 "global investigations market" figure in internal circulation matches
none of these categories and should not be used.**

---

## 7. Threat register — what could take this market

Ordered by structural danger rather than current noise. The top two are the ones to hold an
opinion about in an investor meeting.

**T1 · Cellebrite moves down-market and defence-side.** *Structural · capability already exists ·
GTM is the only barrier.* Guardian Investigate went GA worldwide in March 2026 — agentic AI over
evidence, cross-file link surfacing, timeline building, chain of custody preserved, and cloud,
on-prem and hybrid deployment. Cellebrite Genesis explicitly targets "individual investigators or
small units." **They own the extraction format outright.** Every capability needed to serve
defence teams is built; the only thing keeping them out is a go-to-market choice, and choices
reverse. *Lens: Guardian 175, third-highest of the platforms above Loupe, accessibility 1.*

**T2 · Exterro ARMOUR makes agentic forensics auditable — and shipped three weeks ago.**
*Immediate · shipped · strongest agentic execution in the set.* Launched 9 July 2026. The
investigator "starts with the question" and the agent plans and executes governed forensic work,
producing "an auditable evidence record designed to withstand legal and regulatory scrutiny."
Above the Law's assessment: fast, auditable, and about to bloody Daubert. **Openly sold to law
firms, unlike Pathfinder.** *Lens: the only platform in the study scoring above Loupe on any AI
axis — agentic execution 9 v 8 — in Loupe's own price band, clearing every defence gate.*

**T3 · Axon moves up from records into investigation.** *Structural · owns acquisition and the
install base.* Axon owns the body-camera and digital-evidence ecosystem outright; Draft One cuts
administrative time a reported 50–80%. The install base is locked in and the acquisition layer is
theirs. Law-enforcement-only today, **which is the only thing keeping it out of the comparison a
defence buyer runs.** *Lens: 158, certifications 9, proven scale 10, vendor viability 10.*

**T4 · MCP flattens the integration layer and the agent stops being the product.** *Structural ·
argues for being the grounded substrate, not the agent.* Claude for Legal launched May 2026 with a
litigation plugin and twenty-plus connectors including Relativity, Everlaw and Consilio; Everlaw
shipped its own Anthropic MCP integration the same month; Thomson Reuters rebuilt CoCounsel on the
Claude Agent SDK; DataWalk, Neo4j and Quantexa all ship MCP servers. **Competing at the agent
layer is competing with the labs.**

**T5 · The funded defence-native startups add a device model.** *Near-term · capability gap is
closable with capital.* TrialKit already claims phone extractions and has the LA County Public
Defender. Matey has $7.5M, both major certifications and two bar-association channels. Neither has
a graph today. **Building one is eighteen months of work they can afford — and they have the
customers to justify it before Loupe has the customers to defend against it.**

**T6 · Nuix completes the Linkurious integration.** *12–24 months · enterprise-priced, leaves small
practices open.* Nuix acquired Linkurious for €20M — signed 4 December 2025, closed that month on
French FDI approval — **the strongest strategic convergence with Loupe's architecture in the
entire set.** Nuix Neo processes 1,000+ file types including forensic images; Linkurious brings the
graph. No shipped integration as of July 2026. When it ships, an enterprise-priced version of
Loupe's architecture exists.

**T7 · Free tiers compress the price floor.** *Ongoing · argues for per-matter over per-seat.*
Everlaw for Good covers CJA panel attorneys at no cost; Longeye intends to give its platform to
public defenders; Relativity's Justice for Change donates RelativityOne for 24 months. None scales
commercially, but **each one anchors what a defence buyer expects to pay.**

**T8 · Open-source graph RAG closes the plumbing gap.** *Low · commoditises the plumbing, not the
evidence layer.* LightRAG indexes 500 pages for about $0.50 in three minutes at 70–90% of
Microsoft GraphRAG's quality; Neo4j's Aura Agent builds GraphRAG agents with no code. A competent
team reaches "cited Q&A over a document corpus with an entity graph" in months. **What none of it
supplies is forensic ingestion, provenance objects, or curation** — the production literature lists
provenance and audit as explicitly absent.

---

## 8. Where Loupe is weakest

Written to be uncomfortable, because diligence will find all of these and it is better to have an
answer ready than a surprise. Each is paired with its lens score so the size of the gap is visible.

| Weakness | Lens | The comparison that hurts |
|---|---|---|
| **No certifications yet** | 1/10 (47th) | Matey holds SOC 2 Type II **and** ISO 27001. Harvey, Hebbia, Clearbrief, Casefleet hold SOC 2 Type II. Everlaw and Relativity hold FedRAMP. Casepoint holds FedRAMP High with DOD IL5 and IL6. Loupe holds nothing. |
| **No published scale proof** | 3/10 (44th) | Everlaw tested Deep Dive across databases in the tens of millions of documents. Relativity processed 8.7 petabytes in a year. Loupe has federal matters that went to trial — better evidence of value, weaker evidence of scale, and diligence asks about both. |
| **No ecosystem integrations** | 0/10 (47th) | No iManage or NetDocuments, no Clio or MyCase, no Westlaw or Lexis. CoCounsel scores 10 here. For a law firm the DMS is where the work already lives. |
| **Dependent on what was produced** | acquisition 0/10 | Cellebrite, Magnet and Exterro own acquisition through analysis. Defence-side that is largely fine — evidence arrives via discovery — but **Loupe can never see what the extraction did not capture and cannot independently verify the acquisition.** |
| **No forensic validation history** | 2/10 (43rd) | No NIST CFTT test reports, no published error rates, no history of expert testimony. Magnet, Exterro and Pathfinder score 9. In prosecution and UK policing this is gated at 8. |
| **Two headline capabilities not shipped** | — | Loupes are in build and uncommitted; the disconfirmation agent is a design. Both appear in positioning material. Nothing enters a deck until it has demoed clean once. |
| **Funding asymmetry** | viability 3/10 (46th) | Harvey has raised over $1B at an $11B valuation. Matey $7.5M for the same buyer; TrialKit $4.25M; Longeye $5M from a16z. Loupe is pre-seed. **The compensating advantage is that the product was built inside live federal casework rather than from a market hypothesis** — real, and it needs saying early because the balance sheet cannot be. |
| **No case workflow** | 4/10 (39th) | Kaseware, Hubstream, Ontic, Resolver, Case IQ and HR Acuity all score 8–9. Alex Solórzano's category. It gates every corporate and government market on merit, not just on procurement. |

---

## 9. Method and confidence

Compiled from **seventeen research sweeps run 25–26 July 2026**, drawing on more than **350 sourced
URLs.** The first pass was an adversarial workflow: 107 agents across five angles extracted 118
claims from 25 fetched sources, of which 25 were put to three independent skeptics each — **17
confirmed, 3 refuted and killed, 5 left mid-vote** when the run hit its quota. Remaining sweeps
were per-vendor deep reads with a standing instruction to flag anything unverifiable.

**Three claims were refuted and excluded:** that Nuix discloses no provenance mechanism; that
Guardian Investigate leaves defence-side segments unaddressed as originally framed; and that
Guardian was still in design-partner testing — it went GA in March 2026.

**Two research premises were wrong and are corrected:** Litera does not own CaseMap (LexisNexis
does; Litera exited litigation fact management in 2024), and Casepoint has no platform called
"Aurora" — that is Consilio's, and it runs on Reveal.

**Matey's funding is now confirmed from primary announcements:** $7.5M seed led by Timespan
Ventures with Neo and Streamlined Ventures, announced late August 2025, Austin-based, product CrimD,
in use across public defenders, private firms and government agencies.

**Still unverified, flagged before external use:** BlueLight Commercial's role as UK policing
procurement gatekeeper is unconfirmed; proposed Federal Rule of Evidence 707 on machine-generated
evidence is from background knowledge and was never sourced; Cellebrite's formal policy on selling
analytics to defence firms is strongly indicated by marketing but not documented either way; most
seat-price figures for Harvey, Hebbia, CoCounsel and Everlaw are third-party estimates.

**A second verification pass on 26 July** re-checked multimedia handling, ingestion-time
configuration and the reductive-versus-constructive paradigm across twenty-one platforms. It
produced corrections now folded in: DISCO does transcribe with diarization at ingest; Relativity's
diarization labels are internal and unsearchable; Harvey handles audio but no documented video and
publishes no duration cap; Siren has no multimedia capability at all; and Cellebrite states in its
own materials that **Genesis maintains no persistent case model.**

**Two entries rest on founder knowledge rather than public sources.** Siren's Cellebrite
integration and Octostar's phone-analysis capability are recorded from founder first-hand knowledge,
overriding a vendor marketing page in the first case and an absence of public documentation in the
second. Where founder knowledge and a vendor page conflict, this document follows the founder
knowledge and says so — **but such claims are unciteable externally, so they inform strategy rather
than appearing in investor material.**

Where an entry says "no public evidence," the capability was searched for in product pages,
documentation, release notes and press coverage and not found. **For several vendors that is
absence of evidence rather than proven absence**, and the per-vendor dossiers say which.

### Dossier coverage

Six category dossiers cover the field: enterprise intelligence; digital forensics / DFIR;
eDiscovery AI; legal AI and case narrative; AI-native defence and evidence startups; and
commoditisation. The dossier corpus (`16-loupe-competitor-dossiers.md`, 356KB) predates the
expansion to 47 platforms — **Kaseware, Altia and Comtrac have no dossier entry at all** despite
being scored, and Comtrac is the closest shipped analogue to the Loupes thesis in the entire study.
That is a real coverage gap.

---

## 10. Kaseware and Altia — where their graphs actually come from

Whether Kaseware's and Altia's link analysis is auto-built from ingested evidence or charted by an
analyst decides whether the auto-built-graph claim can stand. Both are resolved from vendor
documentation.

**Kaseware builds its graph automatically from ingested evidence.** Its link-analysis page states
charts are "automatically generated from case and entity data without any manual effort" and
update in real time. Its AI services page documents entity extraction that "identif[ies] people,
organizations, locations, and events across documents and data feeds", extraction of "names,
dates, locations, and other key details from unstructured data", AI-enhanced OCR, speech-to-text
for "interviews, calls, and field recordings", 160+ language translation, and relationship mapping
that "connect[s] entities across data sources to detect links". **No evidence of UFED/Cellebrite
parsing or financial-statement parsing.**

**Altia has genuine provenance and no unified graph.** Its Financial Investigation Toolkit "allows
investigators to upload, scan, and extract data from bank statements in a structured, reliable
format" and "structures and indexes that information so every transaction, source, and disclosure
can be traced back to its origin", and it "automatically logs every data ingestion with timestamps
and source references". But FIT is financial-only, holds no communications data, sits in a
separate product from the Insight case-management module, and no automatic entity or relationship
extraction from the parsed financial data is documented.

**Effect on the claims.** The loose version — "nobody else auto-builds a graph" — is dead, and was
already qualified out of the document in July. **The precise version is confirmed and now
evidenced:** Kaseware auto-builds from documents and audio but parses no device or financial data;
Altia parses financial data with excellent provenance but scores 1 on device data and has no
unified model. *No platform holds device data, financial records and documents in one model.*

Score revisions this implies, held pending sign-off: Kaseware graph 5→7, multimodal 2→5,
provenance 2→3 (total 122→128); Altia provenance 2→6, financial 7→8 (total 140→145). Neither
changes any market outcome or any finding.

---

## 11. Open items

Four things this analysis does not yet cover:

1. **Dossiers for Kaseware, Altia and Comtrac.** All three are scored and appear in the matrix;
   none has a dossier entry, and Comtrac is the closest shipped analogue to the Loupes thesis in the
   whole study.
2. **The Kaseware and Altia score revisions in §10**, which are held pending sign-off.
3. **Note coverage.** The matrix carries researched notes on 420 of its 1,410 cells. Seventeen
   platforms have none, and sixteen axes — link analysis, timeline, geospatial, financial, OSINT, processing breadth, case
   workflow, review at scale, disclosure, TAR, collaboration, cited Q&A, agentic execution,
   parsing validation, AI defensibility, vendor viability — carry none for any platform. The scores
   are sound; the evidence behind them lives in the dossiers rather than in the cell.
4. **Primary market-size sources.** All fifteen markets are sized in §7a of the Market Fit Lens
   narrative from published analyst estimates, with ranges given where houses disagree by two to
   three times. None is a primary source commissioned for this study; anything load-bearing in an
   investor document should be checked against the underlying report rather than the press summary.
   The $3.5B-by-2030 "global investigations market" figure in internal circulation matches none of
   the sized categories and should not be used.

---

## 12. The three sentences that carry into the accelerator application

An accelerator panel discounts a self-serving matrix on sight — a high score across axes chosen to
describe your own product reads as marketing. Comparative claims that concede something do the work
instead.

> **The two platforms that outscore Loupe on review-heavy capability, Relativity and Everlaw,
> reach three and four of the fifteen markets between them. A high total earned in one group of
> axes buys one market; Loupe's is spread across thirteen.**

> **No platform of forty-seven can be sold into all fifteen markets, and only eight reach more
> than twelve. Loupe reaches thirteen — and the two it does not are blocked by economics and by
> evidence collection, not by anything on a roadmap.**

> **Loupe is second of fourteen platforms in its price band and leads that band on evidence
> modelling by twenty-two points — the capability sits at a price the buyer can authorise without
> a procurement process, which is a combination that exists nowhere else in the study.**

The first two are strengths disguised as concessions. The third is the commercial thesis. All
three survive a five-minute check, which the current headline does not.
