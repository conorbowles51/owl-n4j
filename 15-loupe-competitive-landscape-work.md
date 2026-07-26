# Loupe — Competitive landscape & beachhead research (WORKFILE)

**Status:** research recovery + fan-out in progress, 2026-07-26 morning.
**Deliverable:** competitive landscape + capability-gap matrix + whitespace + barrier-to-entry + ranked beachhead recommendation (the full spec is in the workflow `args` below).

## ▶ NEXT
1. Wait for the 5 remaining research agents (graph platforms, enterprise intel, eDiscovery AI, legal AI assistants, forensics/DFIR). Paste each result into §4 as it lands.
2. Re-verify the 5 quota-killed claims (§2c): Matey/CrimD funding + traction + provenance positioning; BlueLight Commercial UK procurement gatekeeping.
3. Synthesize the final report per the original spec (§0): (a) capability-gap matrix, (b) whitespace, (c) barrier-to-entry per segment, (d) ranked beachhead + pricing model. Write as `16-loupe-competitive-landscape-2026-07.md`. Respect Neil's voice rules for any copy-ready lines (finished-product tense, no status markers, one product).

## §0 Original research spec (from last night's workflow)
Full spec preserved in: `/root/.claude/projects/-home-conorbowles51-app-v2/2c9b0b73-ff8e-49ff-81f4-0c06630e989c/workflows/wf_471a1665-569.json` (args field) and extracted result at `/tmp/claude-0/-home-conorbowles51-app-v2/c24975f6-f0e9-43eb-861b-3ee7c9ddb61a/scratchpad/wf-result.json`.
Categories: link-analysis platforms; DFIR review; eDiscovery+litigation AI; chronology/case-narrative tools; fincrime; police DEMS; OSS document intelligence; AI-native startups 2023–26. Synthesis: capability-gap matrix, whitespace, barrier-to-entry (CJIS/SOC 2/FedRAMP/ISO 27001/UK police assured; procurement; deal sizes), ranked beachhead + pricing. Candidate segments: US PI/defense-side federal discovery review, criminal defense firms, small/mid prosecutors, corporate investigations, insurance SIU, UK/EU police, fincrime units, investigative journalism.

## §1 What happened last night (2026-07-25/26)
- Session `2c9b0b73` ran deep-research workflow `wf_471a1665-569` at 02:26–02:49 UTC: 107 agents, 2.36M tokens, 5 angles, 25 sources fetched, 118 claims extracted, top 25 adversarially verified (3 skeptics each).
- Quota hit mid-verification ("resets 5:10am UTC"): 5 claims left unverified, synthesis step never ran, session died with no report.
- Result object survived intact (17 confirmed / 3 refuted / 5 unverified + 25 sources) — recovered 2026-07-26 morning.

## §2 Recovered verified claims

### §2a CONFIRMED (adversarial votes shown; source + verbatim quote in wf-result.json)
1. **Quantexa** launched "Quantexa AI" 2025-11-04 — Decision Intelligence Platform now "fully agentic ready" (3-0). quantexa.com/press/quantexa-makes-its-decision-intelligence-platform-agent-ready/
2. **Quantexa Agent Gateway**: multi-provider orchestration (OpenAI/Claude/Mistral/Gemini) via MCP server, governance + lineage tracking (2-1). Same source.
3. **Quantexa Q Assist Workspace**: agentic copilot claiming grounded/explainable/auditable outputs — same axis as Loupe's grounded claims, but over enterprise data, not case evidence files (3-0).
4. **i2 Analyst's Notebook Core plan**: single-user manual/visual link analysis, drag-and-drop import — no automated ingestion, no knowledge-graph pipeline (3-0). i2group.com/solutions/i2-analysts-notebook/plans
5. **i2 plans page shows no LLM/AI in any tier** — no cited AI Q&A, no grounded claims, no hypothesis agent (3-0). Same source.
6. **Nuix Neo Investigations**: 1,000+ file types/sources in one platform — emails, chat, call logs, documents, media (3-0). nuix.com/solutions/fraud-investigations
7. **Nuix Neo** does deep-link analysis + relationship mapping across cases — overlaps Loupe's cross-source graph (3-0). Same source.
8. **Cellebrite Guardian Investigate GA worldwide March 2026**: cloud-based agentic-AI investigative "nerve center" — cross-file Q&A, link surfacing, timeline building (3-0). investors.cellebrite.com (guardian-investigate launch release)
9. **Guardian Investigate ingests beyond phone data**: documents, images, mobile, CDRs — but release does not claim audio/video transcription, financial records, or email (3-0). Same source.
10. **Cellebrite Guardian is cloud-only (AWS)**, Ireland ops for EU data residency, third-party file ingestion now accepted (3-0). cellebrite.com autumn-release-2025.
11. **Longeye** raised $5M seed led by a16z American Dynamism, Sept 2025 — AI police investigations platform built with Redmond PD (3-0). businesswire 20250930738278.
12. **Longeye capability overlap**: multi-format evidence (audio/video/images/docs/social), real-time transcription/translation, verifiable citations linking summaries to originals (3-0). Same source.
13. **Longeye deployment**: self-hosted AWS GovCloud, no third-party AI APIs, no training on case data — stronger US-LE/CJIS posture than Loupe currently has (3-0). Same source.
14. **Longeye targets** LE, detectives, prosecutors AND public defenders; plans to give it to public defenders **free** — undercuts a defense-side pricing wedge (3-0). Same source.
15. **TrialKit**: AI-native criminal-defense discovery, out of stealth April 2025, $4.25M seed (UpWest; 97212, Kaedan, NYU Law EVCP) (3-0). trialkit.ai library post.
16. **TrialKit capability overlap**: ingests documents, video, bodycam, phone extractions, audio, handwritten notes into one searchable workspace; cited answers, full source provenance (3-0). Same source.
17. **TrialKit traction**: 20+ criminal defense firms at launch; current site names LA County Public Defender's Office and Reed Smith (3-0). Same source.

### §2b REFUTED (0-3 — do NOT use these claims)
- "Nuix discloses no LLM provenance/hallucination controls" — refuted; Nuix does disclose more than the claim said.
- "Guardian Investigate leaves PI/defense segments unaddressed" — refuted as stated (buyer framing was wrong; see agent report §4a for the accurate version).
- "Guardian Investigate not yet GA (design-partner only)" — refuted; it went GA March 2026 (autumn-2025 page was stale).

### §2c UNVERIFIED (quota-killed mid-vote — re-verify before use)
- **Matey** (Austin TX, CEO Jared White) $7.5M seed led by Timespan Ventures + Neo + Streamlined, announced 2025-08-27 (1 valid confirm vote). theglobeandmail.com ACCESS Newswire 34429365.
- **Matey CrimD** deployed with public defenders, law firms, gov agencies for criminal discovery (ingest, media transcription, evidence analysis, trial prep) — if true, defense-discovery is NOT whitespace.
- **Matey positions on anti-hallucination/provenance** ("audit trails, full explainability") — provenance alone may not differentiate.
- **BlueLight Commercial** took over UK national policing IT procurement from Police Digital Service April 2024 — centralized gatekeeper.
- **UK forces steered to pre-vetted frameworks** — structural barrier for new vendors.

### §2d Source list (25, with quality ratings) — in wf-result.json `sources`

## §3 Commoditization-threat report (agent completed 2026-07-26 ~08:05) — VERBATIM

*The investor question: "what stops general-purpose AI from commoditising this in eighteen months?"*

### 3.1 Open-source graph-RAG: mature retrieval layer, absent evidence layer
- **Microsoft GraphRAG**: expensive/heavy — ~$50–200 and ~45 min to index 500 pages; entity extraction ~58% of indexing tokens; graph maintenance requires re-extraction on document change (paperclipped.de/en/blog/graph-rag-production/; github.com/microsoft/graphrag).
- **LazyGraphRAG still not open-sourced** as of July 2026 — announced Nov 2024, shipped inside Microsoft Discovery/Azure Local June 2025, but the promised OSS integration never landed; community skepticism the OSS project is active (github.com/microsoft/graphrag/discussions/1490; articsledge.com post).
- **LightRAG**: ~$0.50 / 3 min for the same 500 pages, "70–90% of GraphRAG's quality at 1/100th the cost", better incremental updates (paperclipped).
- **LlamaIndex** Property Graph Index + GraphRAG cookbooks; in-memory modeling vs Neo4j native storage (docs.llamaindex.ai; suhasbhairav.com comparison). **Graphiti (Zep)**: agent memory, not document evidence.
- Frameworks give: entity/relation extraction, community summaries, hybrid retrieval, multi-hop QA. They do NOT give: entity-resolution QC, ontology maintenance ("weeks in ontology design"), **no native provenance/audit trails**, weak retrieval monitoring (paperclipped). [Assessment] Nothing resembling per-claim citation UX pinned to source bytes, chain of custody, forensic-format ingestion (UFED XML, bank statements), curation objects, reviewer workflow, defensible export. Retrieval libraries, not evidence systems.

### 3.2 Frontier labs
- **ChatGPT Projects**: 40 files/project cap (Pro/Business/Enterprise), 512MB/file — two orders of magnitude below discovery corpora. Enterprise: no-training default; **ZDR is negotiable for eligible API endpoints, not a product default**; no customer-premises single-tenant (onefileapp.com; help.openai.com retention; teleskope.ai ZDR).
- **Claude for Legal launched 2026-05-12 — the biggest single encroachment event**: 12 practice-area plugins incl. **Litigation**, 20+ MCP connectors incl. **Relativity, Everlaw, Consilio**, iManage, NetDocuments, Westlaw/CoCounsel; Word/Outlook; playbook "setup interviews"; 4 plugins as Managed Agents via API (lawnext.com 2026/05; claude.com/blog/claude-for-the-legal-industry; abajournal.com; artificiallawyer.com 2026/05/12; fortune.com 2026/05/12 — Freshfields, Quinn Emanuel, Holland & Knight on live matters).
- Claude corpus limits: 200K standard context (500K newer models); Projects switch to RAG mode above ~150K tokens, "up to 10x" capacity ≈ ~1.5M tokens — far short of full-case discovery; generic citation UX (support.claude.com RAG article).
- Claude confidentiality: Enterprise DPA/SSO/SCIM/audit/custom retention; **optional ZDR add-on** (privacy.claude.com; code.claude.com ZDR docs). Still cloud multi-tenant infra; no on-prem model hosting.
- **Google**: Agentspace → **Gemini Enterprise** (Oct 2025): governed agent platform, RBAC/IAM, connectors (atlan.com; cloud release notes; virtualizationreview.com Cloud Next '26).
- **NotebookLM Enterprise** = most credible confidentiality story of the three: runs in customer's own GCP project, region-lockable US/EU, VPC-SC, IAM, HIPAA (Mar 2025), SOC 2/ISO 27001, no training (medium google-cloud community; devoteam.com; Google data-residency docs). Customer-project ≠ customer-premises, but it narrows the "your data never leaves your environment" pitch for cloud-tolerant buyers.

### 3.3 NotebookLM consumer tiers
- Post-I/O May 2026: 50 sources free → 100 Plus → 300 Pro → 500–600 Ultra ($99.99–$200/mo); each source capped 500K words / 200MB, no plan lifts it; chat caps 50–5,000/day (elephas.app; posttosource.com; notebooklm-guide.com).
- Citations inline + clickable — genuinely good grounding UX. [Assessment] But no forensic ingestion (a UFED extraction is not "a source"), no cross-source entity model, no durable curation objects, no defensible per-claim audit trail. It educates the market to expect cited answers — which helps Loupe — while being architecturally unable to handle mixed phone+document evidence.

### 3.4 Neo4j's own AI positioning (Loupe's substrate)
- **Aura Agent**: no/low-code GraphRAG agents over AuraDB — vector search, Text2Cypher, query-template tools, MCP endpoint (neo4j.com/docs/aura/aura-agent; neo4j blog; infoworld.com 4139414). **LLM Knowledge Graph Builder** + official **Neo4j MCP server**.
- Vertical: Neo4j markets the **POLE model** for policing (go.neo4j.com POLE; github neo4j-graph-examples/pole); partners **Siren**, Kineviz in investigative viz. [Assessment] Horizontal platforms + LE/intel link-analysis; none combines forensic phone ingestion + defense-discovery documents + provenance-cited answers + defense-side workflow. Aura Agent lowers the plumbing cost of a clone but supplies no domain layer — and is Aura-cloud-only, conflicting with single-tenant defense confidentiality.

### 3.5 Dated encroachment events (2025–2026)
- **Relativity aiR for Case Strategy GA Jan 2026**: generative fact extraction into chronologies/timelines, witness summaries, depo outlines, facts linked to source text; 5,000 docs/job limit; gov version H1 2026; aiR for Review/Privilege folded into RelativityOne at no charge from early 2026 (lawnext.com 2026/01; ediscoverytoday.com 2026/01/12; ilsteam.com).
- **Everlaw Storybuilder**: Chronology + Fact Timelines + AI Deep Dive with citation-backed answers; single-use AI features made free (everlaw.com/storybuilder; support KB; ilsteam.com).
- **Cellebrite Guardian Investigate GA 2026-03-18** — closest single competitor announcement: agentic "nerve center", questions-over-evidence, links, timelines, **chain of custody preserved; cloud, on-prem, and hybrid** (investors.cellebrite.com; cellebrite agentic-AI blog). Guardian GenAI (audio/thread summarization) GA Feb 2025. Targets LE/defense-intel/sheriffs/ICAC — prosecution side.
  - NOTE conflict with §2a#10 (cloud-only claim, autumn-2025 page) — the newer GA release says cloud/on-prem/hybrid; treat the GA release as current, re-verify at synthesis.
- **Magnet Copilot** in Axiom: Q&A over chats/web history, artifact surfacing, synthetic-media detection, **offline AI** in Axiom 8.6 (magnetforensics.com blogs).
- **Harvey**: $200M at $11B (Mar 2026), $190M ARR, 25,000+ custom agents; litigation agents; Vault bulk review (gc.ai review; aivortex.io). Briefs-and-drafting shaped, AmLaw-priced, no forensic extractions.
- **[UNVERIFIED — source before investor use]**: proposed FRE 707 (machine-generated evidence under Daubert-style scrutiny) in public-comment pipeline from mid-2025 — would reward defensible provenance.

### 3.6 Honest counter-case
**Concede as commoditised:** graph construction + retrieval (months, not 18, for a 2–4 person team); document chronology extraction with citations (Relativity proved it); cited-answer UX expectations (NotebookLM, free); model quality itself.
**The 18-month clone still lacks:**
1. **Forensic ingestion that survives real data** — UFED version drift, dropped artifact classes, empty owner MSISDN, UTC/display traps, one-edge call models, dense-node corruption at 100k+ artifacts. Accumulated correction-knowledge, not downloadable code.
2. **Mixed-evidence unification** — phone + bank statements + subpoena returns + scanned OCR in one provenance-bearing graph; nobody productized the join for defense practices.
3. **Provenance as first-class object** — per-claim links to exact artifact/row plus ingestion lineage (parser version, what was dropped and disclosed). OSS literature lists provenance/audit as absent.
4. **Durable curation objects** — Loupes/chronologies as persistent, exportable work product across model versions.
5. **Single-tenant/on-prem confidentiality** — labs offer ZDR contracts, Google offers customer-project; none offers customer-controlled infra with local models. Cellebrite offers on-prem — to the prosecution side.
6. **Admissibility posture** — visible truncation, honest counts, reproducible answers an expert can defend (hallucinations already appearing in filings — Fortune).
7. **Segment economics** — Harvey→AmLaw, Relativity/Everlaw→per-GB corporate, Cellebrite→agencies. Small/mid defense-investigative practices structurally underserved.
**Two real risks to state honestly:** (1) **Cellebrite moving defense-side/down-market** — Guardian Investigate is functionally closest; GTM is a strategy choice, not a capability gap. #1 structural threat. (2) **MCP flattening the integration layer** — Claude-for-Legal's connector model is the endgame; Loupe's defense is to BE the repository worth connecting to (system of record for evidence, provenance, curation), not to compete with the agent layer. Investor answer: "the AI is the commodity; the evidence substrate is what an 18-month generalist effort reliably fails to replicate — see Microsoft failing to ship LazyGraphRAG OSS in 18 months of promising it."


## §5 CORRECTIONS FROM NEIL (2026-07-26, post-artifact-v1) — these override the research

**C1 — The claim is grounding, not citations.** We are NOT claiming nobody else can give citations
(everyone can; most give it away free — see §3.5). The claim is that graphing huge evidence sets means
we are not relying on a black-box LLM answering questions a document at a time. The graph is concrete
grounding that lets us query the WHOLE case corpus at once, reliably. Citation is a consequence of the
structure (every node knows its source), not the headline feature. Artifact v2 rebuilt around this:
new H1 ("Everyone can cite a document. Nobody can query a case."), new executive finding
("The differentiator was never the citation. It is the grounding."), new matrix axis #8
**Whole-corpus relational query**, and new finding F2 ("Every competitor answers by retrieval; none
answers by traversal"). Supporting evidence found in vendors' own docs: Reveal Ask is "designed for
precision, not recall" and cannot find all instances; Relativity caps 300k docs/index, 1.5M/workspace,
5,000 docs per fact-extraction job; CoCounsel ~200 docs/comparison run degrading with volume, 2,000
pages/doc; Harvey runs a prompt per document across the vault and aggregates.

**C2 — Siren's Cellebrite integration is NOT real (first-hand, Neil worked there 7 years).** It is a
poor Python script that does not represent the data well in-platform. Vendor marketing (siren.io
"Cellebrite Connectors since Siren 12", UFED XML + Pathfinder, per-device dedup) OVERSTATES it. The
original research took the marketing at face value — that was wrong. Siren's query layer IS genuinely
corpus-wide (Federate joins/semi-joins), so Siren sits on OUR side of the grounding line; its weakness
is what gets INTO the index, not the query. Matrix downgraded: phone-data ● → ◐, unified ● → ◐,
whole-corpus-query ●. Dossier entry rewritten. NOTE: this correction is unciteable externally —
it informs strategy, it does not go in investor material.

### C3 — Octostar DOES do Cellebrite phone analysis (first-hand, Neil). 2026-07-26
Research found zero Cellebrite/UFDR/UFED mentions across Octostar's site bundle, 11 repos, 6 npm
packages — but Octostar publishes NO technical documentation at all (no docs portal), so web silence is
near-meaningless there. Scores raised (phone 0→5, unified 2→4). Second founder-knowledge override after
the Siren one; also unciteable externally.

### C4 — Second verification pass (multimedia / ingestion-config / paradigm), 2026-07-26
Corrections folded into artifact v4:
- **DISCO DOES transcribe** at ingest WITH diarization (up to 10 speakers), 4hr/file cap. My earlier "no
  A/V" was WRONG. Score 1→3.
- **Relativity**: Azure STT + diarization, but speaker labels stored internally, NOT searchable/visible;
  4GB/file, 4hr cap when diarization on; NO native translation (needs Veritone). Score 1→3.
- **Harvey**: audio ONLY, no video documented anywhere; the "2-hour cap" I asserted is UNVERIFIED (help
  centre behind Auth0) — removed from the doc. Do not cite it.
- **Siren**: NO multimedia capability at all (NLP plugin is text-field enrichment). Score 4→1.
- **Everlaw**: synced transcription English+Spanish only; native A/V redaction (best-integrated).
- **Cellebrite**: NO diarization documented anywhere across Pathfinder/Guardian/Genesis — surprising given
  jail calls. Translation 60+ langs, 3-6mo→~1.5 days. **Genesis explicitly "does not build a persistent
  cross-case knowledge graph… analyzes uploaded evidence per session"** — best quote in the study.
- **Palantir Foundry**: diarization w/ speaker_id, but "media reference lists are not supported as a
  property type on an object" — hands you parts, not a case model.
- **JusticeText**: does NOT explicitly document diarization despite being A/V-native — real soft spot.
- **Ingestion-time AI extraction**: only Siren (Elasticsearch pipeline JSON) and Palantir (assembled
  components) do it — both ENGINEER-level. Forensic "processing profiles" (Nuix/Magnet CAG/Cellebrite
  Python parsers) are deterministic schema-mapping, NOT AI/ontology. Best-supported differentiator.
- **Paradigm**: Relativity blog literally titled "Reduce, Reduce, Reduce" + 77%/70% case studies; Nuix
  "cut review volumes 40-60%"; **DISCO admits in its own docs that "Timeline creation doesn't happen in
  DISCO Ediscovery"** (separate Case Builder product).
- **Longeye is the most serious competitor**: only platform naming BOTH Cellebrite extraction data AND
  bank records AND documents; SOC 2 Type II; single-tenant dedicated US infra; $50k PD grant programme.
  Scores raised (phone 0→5, unified 4→7, multimodal 5→7, workspace 1→4).

### C5 — Artifact v4 additions
- **Market lens** on the matrix: 8 lenses re-weighting the same 12 scores per buyer, WITH GATING —
  markets that structurally cannot buy a platform show n/a rather than a rank (12 platforms gate out of
  criminal defence). Answers "who actually competes for this buyer."
- **Row selection → generated comparison prose** below the table (2+ platforms).
- **New section 02 "Fit and route to market"** (buyer, why-not-adjacent table, 3 channels incl. the
  NACDL/state-bar playbook Matey proved, per-matter pricing, what to lead with, SOC 2 as gate).
- Numeric 0-10 scores + totals replaced the ●◐○ glyphs; heat shading + column-leader outlines.

### C6 — "We win everything" was a real credibility problem. FIXED in v5 (2026-07-26)
Neil: *"it looks slightly suspect when we're number 1 for everything."* Correct — and the cause was
**axis-selection bias**, not weighting. All twelve original axes were chosen to describe the problem
Loupe solves, so Loupe swept them. Weighting could never fix that; only adding axes where Loupe loses
could.

**Added 4 READINESS axes** (scored for all 30 rows): certifications & compliance, proven scale,
ecosystem integrations, evidence acquisition. Matrix now 12 capability + 4 readiness, with **two
separate subtotals deliberately not summed by default** (teal = capability /120, orange = readiness /40).

**The resulting honest picture — use this, it is far more persuasive than a sweep:**
- Loupe capability **99/120 (rank 1)**, readiness **5/40 (near last)**.
- Loupe and **Palantir tie at 104** overall, from opposite directions (Palantir 71 cap / 33 rdy).
- Relativity is the mirror image: 46 cap / 34 rdy.
- Framing line now in the doc: **"the product is ahead of the company."** Everything Loupe lacks is
  purchasable with time and money — none of it quickly.

**Also fixed:** axis 7 renamed "Defence-side purchasable" → **"Purchasable by this buyer"** (it is a
product↔buyer relationship, not a capability — the tell was weight 0 in 5 of 7 market lenses).
Market weights extended to 16 axes. Comparison generator + lens both handle 16.

**Still open (my recommendation, not yet built):** treat some axes as *thresholds* rather than linear
weights in specific markets (court work needs provenance ≥8; a 5 is unusable, not half-useful), and
consider a scale-fit axis — Casefleet scores 9 on judgment objects but its Starter tier caps at 20
documents and cannot absorb a 35GB extraction.

## §4 Cluster-agent reports (paste as they land)
- [x] Commoditization threat → §3
- [ ] Graph investigation platforms (Siren, Linkurious, Octostar, Maltego, DataWalk)
- [ ] Enterprise intel (Palantir Gotham/AIP, i2, adjacent LE platforms)
- [ ] eDiscovery AI (Relativity aiR, Everlaw, DISCO Cecilia, Reveal, Casepoint, Logikcull)
- [ ] Legal AI assistants (Harvey, CoCounsel, Clearbrief, Hebbia, defense-AI startups)
- [ ] Forensics/DFIR (Cellebrite, Magnet, Nuix, Exterro — incl. defense-side access-policy verification)
