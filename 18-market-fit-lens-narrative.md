# Loupe — Market Fit Lens: full narrative

**Source artifact:** https://claude.ai/code/artifact/52e0afe2-11ef-4bd7-93dc-f47ce252d538
**Basis:** 47 platforms × 30 axes = 300 points, 15 market profiles. Every figure below is computed
directly from the score arrays.
**Register:** candid internal. Unshipped capability is marked unshipped.

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


## 1. What this instrument measures

Thirty axes, grouped in five bands, applied identically to forty-seven platforms. Fifteen buyer
profiles sit on top of them: each names the axes that buyer genuinely needs, the level it needs
them at, the axes that are irrelevant to it, and the small number of hard gates that decide whether
the platform can be bought at all. The output is not a league table — it answers a narrower
question: *for this buyer, at this budget, what does the field look like and who actually fits?*

**Two design decisions shape every number below.**

*Gates are advisory, not eliminating.* A platform that fails one still appears in the ranking with a
fail badge, because hiding it destroys the information you need — how good the thing you cannot yet
buy actually is, and therefore whether closing that gap is worth the money.

*Certifications gate nothing, for any platform.* SOC 2, ISO 27001, CJIS and FedRAMP are procurement
timing rather than capability — they are obtained when a market requires them, so gating on them
measures how old a company is rather than how well its product fits. The axis stays scored and
visible; it contributes to no gate and no fit percentage. Counted instead as a weighted requirement,
fit percentages move by one to four points and one market ordering changes: criminal defence, where
Loupe would sit second rather than first.

### How scores are banded

- **8–10** — shipped and evidenced in product documentation, release notes or press.
- **3–7** — partial, gated, or claimed but unverified.
- **0–2** — no public evidence. Searched for in product pages, docs, release notes and press,
  and not found. That is absence of evidence, not proven absence, and the distinction is stated
  wherever it changes a conclusion.

Loupe's own row is scored on the same basis as every competitor, and against the **imminent
release** rather than today's build — bonded collections ("Loupes") and the disconfirmation agent
are both in that release. Competitors are scored symmetrically on shipped-and-announced
capability; several of theirs are announced-not-GA too, DISCO's scaled agentic AI among them.

### The five groups

| Group | Axes | Points | What it asks |
|---|---|---|---|
| **A — Evidence modelling** | 1–6 | 60 | Does the platform build a model of the case, or hold files? |
| **B — Investigative analysis** | 7–11 | 50 | Once modelled, what can you do with it — links, time, place, money, outside sources? |
| **C — Processing & casework** | 12–18 | 70 | Can it decode what arrives, and can a team actually run a case in it? |
| **D — AI layer** | 19–21 | 30 | Cited answers, agentic work, and hunting for what breaks the theory. |
| **E — Readiness & commercial** | 22–30 | 90 | Can this buyer procure it, trust it, deploy it, and will the vendor survive? |

Group E is the largest at 90 points, and deliberately so. For most of these fifteen buyers,
procurement decides the outcome before capability is ever assessed — which is why readiness carries
more weight here than any single capability band.

---

## 2. The headline result, computed

**Loupe scores 168 of 300 and ranks 10th of 47.** Nine platforms score above it: Palantir (201),
Magnet Axiom (190), Exterro FTK/ARMOUR (177), Relativity aiR (176), Cellebrite Guardian (175),
Everlaw (175), Cellebrite Pathfinder (169), Cognyte NEXYTE (169) and Nuix Neo (169).

The shape of that number is more useful than the number:

| Group | Loupe | Field median | Field leader |
|---|---|---|---|
| A — Evidence modelling /60 | **55** | 19 | Loupe |
| B — Investigative analysis /50 | 30 | 19 | Palantir / Altia (40 / 37) |
| C — Processing & casework /70 | **26** | 32 | Relativity (61) |
| D — AI layer /30 | **24** | 10 | Loupe |
| E — Readiness & commercial /90 | **33** | 48 | Magnet (73) |

Loupe is first in the study on evidence modelling by seventeen points over Palantir, first on the
AI layer, and **fourth from bottom on readiness** — only Octostar, Trackops and CROSStrax score
lower. That inversion is the entire strategic position: the product is a long way ahead of the
company.

## 3. Where Loupe leads, and by how much

Loupe is the outright or joint leader on eight of the thirty axes:

| Axis | Loupe | Nearest rival | Gap |
|---|---|---|---|
| 3 · Cross-source unification | **10** | Longeye 7 | +3, sole leader |
| 5 · Multimodal entities into the model | **9** | Cognyte / Axon 7 | +2, sole leader |
| 21 · Disconfirmation detection | **8** | JusticeText 6 | +2, sole leader |
| 1 · Auto-built case graph | 9 | Palantir 9 | joint |
| 4 · Whole-corpus relational query | 9 | Palantir, Siren 9 | joint |
| 8 · Timeline & chronology | 8 | six others at 8 | joint |
| 18 · Durable judgment objects | 9 | Everlaw, CaseMap+, Casefleet 9 | joint |
| 30 · Deployment control | 9 | Palantir, Exterro, Nuix 9 | joint |

Three of those eight are sole leads, and **cross-source unification at 10 is the only score of 10
Loupe holds anywhere.** That is the differentiator, stated in the instrument's own terms: not the
graph (Palantir ties), not traversal (Palantir and Siren tie), not durable work product (three
others tie) — but phone, documents and financial records resolving into *one* model where the
same person is the same object across all three. The median score on that axis across 47
platforms is **2**.

Two more axes are worth reading as near-leads: **per-claim provenance 9** (only Clearbrief's 10 is
higher, and Clearbrief does nothing else — 119 total, 37th) and **financial/transaction analysis
8**, second only to DataWalk's 9.

## 4. Where Loupe is beaten, and what it costs

Ten axes where Loupe scores 3 or below — every one of them in groups C and E:

| Axis | Loupe | Field median | Leader | What the gap means |
|---|---|---|---|---|
| 11 · OSINT & external enrichment | **0** | 3 | Babel Street, Neotas, Maltego 10 | No route to reach outside the case at all. Kills due diligence and corporate security. |
| 16 · Analytics / TAR | **0** | 3 | Relativity 10 | No active learning, threading or near-dupe. Kills civil litigation. |
| 24 · Ecosystem integrations | **0** | 6 | CoCounsel 10 | No iManage, NetDocuments, Clio, Westlaw. Every absence is a manual step a rival removed. |
| 25 · Evidence acquisition | **0** | 2 | Magnet, Cellebrite ×2 10 | Analysis-only. Hard gate in national security; irrelevant defence-side. |
| 22 · Certifications & compliance | **1** | 7 | Palantir, Casepoint 10 | Scored but excluded from fit and gating — procurement timing, not capability. See §2. |
| 14 · Review workflow at scale | **1** | 3 | Everlaw, Relativity 10 | No batching, coding panels, reviewer QC. |
| 15 · Disclosure & production | **2** | 3 | Relativity 10 | No redaction, privilege log, Bates, load files. |
| 26 · Acquisition & parsing validation | **2** | 4 | Magnet, Exterro, Pathfinder 9 | No NIST CFTT testing, no published error rates, no testimony history. |
| 23 · Proven scale | **3** | 7 | Palantir, Relativity, Pathfinder, Axon 10 | Federal matters tried is better evidence of value, weaker evidence of volume. |
| 28 · Vendor viability & support | **3** | 7 | Palantir, Cellebrite, Relativity +4 10 | Pre-seed against $1B-raised Harvey. Structural, not fixable this year. |

Three of these are **deliberate scope decisions rather than deficiencies** — OSINT, evidence
acquisition and review-at-scale are marked *not applicable* in the criminal-defence profile,
because a defence practice receives evidence and never collects it. The lens excludes N/A axes
from the fit denominator entirely, which is why Loupe's defence fit is 87% while its raw total is
56% of the maximum. The other seven are real gaps with real prices attached.

## 5. Price bands — who you actually meet at each budget

Entry price is the annual cost to get in the door. Four bands, and the distribution is the most
commercially useful fact in the study.

| Band | Platforms | Best total | Median total |
|---|---|---|---|
| **< $10k** | 8 | CoCounsel 140 | 121 |
| **$10–50k** | 14 | **Exterro FTK/ARMOUR 177**, then **Loupe 168** | 130 |
| **$50–300k** | 18 | Magnet 190 | 139 |
| **$300k+** | 7 | Palantir 201 | 150 |

Read down the columns and the barbell is obvious. Below $10,000 sit document tools and one legacy
charting product — CoCounsel, i2, Casefleet, Maltego, Clearbrief, Case Closed, and at the very
bottom CROSStrax ($35/month, 73 points) and Trackops ($99/month, 68 points), both built
specifically for private investigators and both last in the study on evidence modelling. Above
$300,000 sit the platforms that model evidence properly. The middle is thin.

**Loupe is second of fourteen in the $10–50k band, and the only platform in that band above 160
other than Exterro.** That is the commercial position in one line: real evidence capability at a
price a fifteen-person practice can authorise without a procurement process. Everything else
capable of doing this work costs four to twenty times more.

The band comparison that should be in the accelerator deck is Loupe against its own price cohort,
not against Palantir:

| Platform | Total | A /60 | E /90 | Note |
|---|---|---|---|---|
| Exterro FTK / ARMOUR | 177 | 31 | 70 | The genuine threat. Agentic forensics, shipped 9 Jul 2026, sells to law firms. |
| **Loupe** | **168** | **55** | **33** | Leads the band on evidence modelling by 24 points; last on readiness. |
| Reveal / Logikcull | 143 | 19 | 48 | Document culling, not evidence modelling. |
| Matey / CrimD | 140 | 30 | 48 | Same buyer, same pitch, both certifications. |
| CaseMap+ AI | 139 | 19 | 51 | LexisNexis distribution. |
| Longeye | 138 | 32 | 50 | a16z-backed, GovCloud, free to public defenders. |
| JusticeText | 132 | 23 | 47 | $4.0M ARR, 4,100+ attorneys. |
| TrialKit | 128 | 33 | 39 | 20+ defence firms, closest to the stated buyer. |

## 6. Reach — how many markets a platform can actually be sold into

With certifications excluded, the remaining gates measure something a vendor cannot simply buy:
commercial accessibility, deployment control, and the ability to acquire evidence. That produces
the most useful single number in the instrument — **reach**, the count of the fifteen buyer
profiles a platform clears every gate for.

**No platform of forty-seven reaches all fifteen. Only eight reach more than twelve.**

| Reach | Platform | Avg fit across 15 markets | Entry price | Total |
|---|---|---|---|---|
| 14 | Magnet Axiom / Magnet One | 83.5% | $50–300k | 190 |
| 14 | Exterro FTK / ARMOUR | 79.5% | $10–50k | 177 |
| 14 | Longeye | 66.1% | $10–50k | 138 |
| 14 | IBM i2 | 63.9% | <$10k | 133 |
| **13** | **Loupe** | **75.3%** | **$10–50k** | **168** |
| 13 | Kaseware | 60.9% | $50–300k | 122 |
| 13 | Linkurious | 55.3% | $10–50k | 106 |
| 13 | Case Closed Software | 49.1% | <$10k | 100 |

Read against the platforms that outscore Loupe overall, reach is where the field separates:

| Platform | Total | Reach | Avg fit |
|---|---|---|---|
| Palantir Gotham / AIP | 201 | 11/15 | **88.3%** — highest average fit in the study, top-3 in all fifteen |
| Magnet Axiom | 190 | **14/15** | 83.5% |
| Exterro FTK / ARMOUR | 177 | **14/15** | 79.5% |
| Relativity (aiR) | 176 | **3/15** | 71.3% |
| Cellebrite Guardian | 175 | 10/15 | 79.6% |
| Everlaw | 175 | **4/15** | 72.9% |
| Cellebrite Pathfinder | 169 | 10/15 | 74.5% |
| Cognyte NEXYTE | 169 | 12/15 | 82.9% |
| Nuix Neo | 169 | 12/15 | 77.0% |
| **Loupe** | **168** | **13/15** | **75.3%** |

**Relativity and Everlaw are the finding here.** They score 176 and 175 — above Loupe — and reach
three and four markets respectively. A high total earned in group C (review at scale, TAR,
disclosure) buys you civil litigation and almost nothing else. Loupe's 168 is spread differently
and reaches thirteen.

Palantir is the mirror: the best average fit anywhere, top-3 in every one of the fifteen, and it
can be sold into eleven because its commercial model excludes the rest.

## 7. The markets, ranked by where Loupe actually stands

| Market | Loupe fit | Rank | Gates failed | Platforms clearing all gates |
|---|---|---|---|---|
| Criminal defence & PI | **87%** | **1 of 47** | none | 10 |
| Public defender offices | 86% | 3 | commercial accessibility | 9 |
| Investigative journalism | 84% | 3 | none | 31 |
| Insurance SIU / fraud | 77% | **7** | none | 47 |
| Corporate security & insider threat | 75% | 13 | none | 27 |
| Ethics, compliance & whistleblower | 74% | 18 | none | 23 |
| Due diligence / KYC | 74% | 12 | none | 47 |
| Intelligence & national security | 74% | 8 | evidence acquisition | 4 |
| Corporate & internal investigations | 73% | 15 | none | 27 |
| Regulators & government enforcement | 73% | 8 | none | 23 |
| Financial-crime units | 72% | 17 | none | 27 |
| Public-sector fraud | 72% | 14 | none | 23 |
| Prosecution & law enforcement | 70% | 15 | none | 23 |
| UK / EU policing | 70% | 15 | none | 17 |
| Law firms & civil disputes | **68%** | **20** | none | 47 |

Loupe's fit sits in a narrow band — 68% to 87% — across every buyer in the study. That flatness is
itself the result: **this is a platform with one shape, which fits one buyer outstandingly and most
others adequately.** It is first in criminal defence and third in journalism and public defence;
seventh in insurance SIU; and its floor is civil litigation, where the requirement set is review at
scale 9, disclosure 9, TAR 8 and processing breadth 8 against Loupe's 1, 2, 0 and 5.

**Insurance SIU is the most under-considered market in the set.** No gate of any kind for any
platform, budgets that exist, financial analysis and OSINT dominant — Loupe scores 8 and 0. The
OSINT gap is the barrier, and unlike a certificate it is a build item that changes the fit number.

---

---

## 7a. What each market is worth

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

On a serious matter that runs to **$34,000–$131,000 and sixty to a hundred hours before anyone has
answered a question about the evidence** — and the largest single line in it, hosting, is charged per
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
> and hands back sixty to a hundred investigator hours per matter.**

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
| Hours released | 20h → $1,496 | 58h → $4,384 | 87h → $6,510 | 100h → $7,508 |
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

### Sources

Figures are 2026 estimates published by Grand View Research, Fortune Business Insights, Mordor
Intelligence, MarketsandMarkets, Precedence Research, Verified Market Reports, Research and Markets,
ComplexDiscovery and IBISWorld, retrieved 29 July 2026. Where houses disagree the range is given
rather than a midpoint. **None of these is a primary source commissioned for this study**, and any
figure used in an investor document should be re-checked against the underlying report rather than
the press summary.

**The $3.5B-by-2030 "global investigations market" figure circulating internally matches none of
these categories** and is most likely a narrow regional or sub-segment estimate. It should not be
used.

---

## 8. The field, platform by platform, against Loupe

Every entry gives the total, the entry price band, how many of the thirty axes it beats Loupe on
and loses to Loupe on, and what that trade actually means commercially. The pattern repeats so
consistently it is worth stating up front: **almost every platform in this study beats Loupe on
readiness and loses to it on evidence modelling.** The exceptions are the interesting ones.

### The nine that outscore Loupe

**Palantir Gotham / AIP — 201, $300k+. Beats Loupe on 15 axes, loses on 10.**
The only platform that matches Loupe on both auto-built graph (9) and whole-corpus traversal (9),
and it does so with certifications 10, proven scale 10, vendor viability 10 and deployment
control 9. It is what Loupe looks like with fifteen years and a defence budget behind it. The
trade is stark: Palantir scores **1 on commercial accessibility** — averaging over a million
dollars per deal — and **2 on disconfirmation** against Loupe's 8. It wins twelve of the fifteen
markets on fit and cannot be bought by any buyer in the beachhead. In investor terms Palantir is
the proof the architecture is right, not the competitor to fear.

**Magnet Axiom / Magnet One — 190, $50–300k. Beats on 15, loses on 12.**
The broadest reach in the study — it clears every gate in fourteen of the fifteen markets, more
than any platform except Exterro, Longeye and i2, and at a far higher average fit than those three.
Evidence acquisition 10, parsing validation 9, certifications 8, vendor viability 9. Loupe beats it on
financial analysis **8 v 1**, disconfirmation 8 v 1, cross-source unification 10 v 5 and
whole-corpus query 9 v 5. Magnet unifies five kinds of device and no kinds of document — that is
the entire gap, and it is the gap the product argument rests on.

**Exterro FTK / ARMOUR — 177, $10–50k. Beats on 15, loses on 13.**
The nearest competitive threat in the whole study, because it is in Loupe's own price band, sells
openly to law firms (accessibility 6, the highest of the nine), clears the defence gates, and on
9 July 2026 shipped ARMOUR — agentic forensics scoring **9 on agentic task execution, the only
score in the study above Loupe's 8 on any AI axis.** Loupe beats it on disconfirmation 8 v 1,
financial analysis 8 v 2, auto-built graph 9 v 3 and cross-source unification 10 v 5. If one
competitor closes the evidence-model gap in the next two years, it is this one.

**Relativity (aiR) — 176, $50–300k. Beats on 15, loses on 13.**
The mirror image of Loupe. Relativity scores **61 of 70** on processing and casework — TAR 10,
review at scale 10, disclosure 10 — and **20 of 60** on evidence modelling. Loupe beats it on
cross-source unification 10 v 2, multimodal 9 v 2, device data 9 v 2, graph 9 v 2 and traversal
9 v 3. Two products that barely overlap, sold into overlapping rooms. Relativity wins civil
litigation and cannot answer a relational question; Loupe answers relational questions and cannot
run a document review.

**Cellebrite Guardian Investigate — 175, $50–300k. Beats on 14, loses on 13.**
Device data 10, acquisition 10, vendor viability 10, certifications 8. Loupe beats it on
disconfirmation 8 v 0, per-claim provenance 9 v 3, financial analysis 8 v 2 and durable judgment
objects 9 v 3. Guardian is the T1 threat in the landscape doc for a reason: every capability
needed to serve defence teams is built, and the only barrier is a go-to-market choice.
Accessibility 1 is that choice, and choices reverse.

**Everlaw — 175, $50–300k. Beats on 14, loses on 12.**
Cited document Q&A 10 — the highest in the study, above Loupe's 8 — plus review at scale 10, TAR
9, provenance 9 and durable judgment objects 9 (tied with Loupe). Everlaw is the strongest
counter-example to a naive "nobody else builds work product" claim. It loses on cross-source
unification 10 v 2, multimodal 9 v 2, disconfirmation 8 v 1 and deployment control 9 v 2. Its
Storybuilder fact model is genuinely excellent and document-scoped; it cannot hold a call.

**Cellebrite Pathfinder — 169, $50–300k. Beats on 16, loses on 13.**
The platform that disproves "nobody builds a graph": auto-built graph 7, link analysis 9, device
data 10, geospatial 9, acquisition 10, proven scale 10. Loupe beats it on disconfirmation 8 v 0,
financial analysis 8 v 2, durable judgment 9 v 3, AI defensibility 8 v 2 and unification 10 v 4.
Pathfinder is sold solely to law enforcement, government and intelligence — accessibility 1 — and
a Florida State Attorney's office publishes instructions telling defence counsel to view
extractions through read-only Guardian links. The graph exists; the defence cannot buy it.

**Cognyte NEXYTE — 169, $300k+. Beats on 14, loses on 15.**
The only platform in the top nine that loses to Loupe on more axes than it wins. Strong across
group B — link analysis 8, geospatial 8, OSINT 7 — with multimodal 7, the second highest after
Loupe. Loses on disconfirmation 8 v 1, provenance 9 v 4, device data 9 v 4, AI defensibility 8 v 3.
A national-intelligence platform priced accordingly.

**Nuix Neo — 169, $300k+. Beats on 13, loses on 16.**
Processing breadth **10 — the study's benchmark**, 1,000+ file types including forensic images —
plus case workflow 9 and TAR 8. Loses to Loupe on sixteen axes including disconfirmation 8 v 0,
unification 10 v 4, traversal 9 v 4 and multimodal 9 v 4. Nuix acquired Linkurious for €20M
(signed 4 Dec 2025, closed that month) and when that integration ships, an enterprise-priced
version of Loupe's architecture exists. No shipped integration as of July 2026.

### The forensics and law-enforcement tier

**Axon (Records / Evidence) — 158, $50–300k.** Owns the body-camera ecosystem outright:
acquisition 9, certifications 9, vendor viability 10, proven scale 10, multimodal 7. Loses to
Loupe on **seventeen** axes including financial analysis 8 v 1 and traversal 9 v 3. Law-enforcement
only, which is the only thing keeping it out of a defence buyer's comparison.

**NICE Investigate — 153, $50–300k.** Digital evidence management with strong disclosure (8) and
workflow (8). Loses on seventeen axes. The pattern across this tier is identical — excellent at
custody, acquisition and disclosure; nearly absent on modelling and AI.

### The eDiscovery tier — the mirror-image cohort

**DISCO (Cecilia) 144**, **Reveal / Logikcull 143**, **Casepoint 141**. All three beat Loupe on
review at scale, TAR, disclosure, certifications and integrations; all three lose on 15–17 axes
concentrated in evidence modelling. Casepoint holds **certifications 10** — FedRAMP High with DOD
IL5/IL6 — and scores **1 on cross-source unification, 1 on graph, 1 on device data.** Reveal's
own documentation states Ask is "designed for precision, not recall." This tier is where the
reductive-versus-constructive argument in the landscape doc is most visible in the numbers:
group C strong, group A empty.

### The graph and intelligence tier

**DataWalk 145, $300k+** — financial analysis **9, the study leader**, graph 8, traversal 8, link
analysis 8. The closest analogue to Loupe's architecture at the top of the market, and it loses on
durable judgment 9 v 2, device data 9 v 3, provenance 9 v 4 and disconfirmation 8 v 0. Entry
around $560,000.

**Babel Street 150** and **Neotas 130** — OSINT 10 each, and device data 0. **Maltego 123** —
link analysis 9, OSINT 10, and **9 of 60** on evidence modelling; it is an analyst's canvas fed by
outbound queries, with no path for received discovery. **IBM i2 133** — link analysis **10, the
study leader**, and **0 on all three AI axes**; no LLM in any tier, and native UFED import was
removed at version 9.1.0. **Siren 125** — traversal 9 (tied with Loupe), graph 8, and case
workflow 2. **Linkurious 106** — graph 8, traversal 8, processing breadth 1: a front end that
requires an already-populated graph database. **Octostar 110** — traversal 8, and the lowest
readiness score in the study at 28 of 90.

The tier's collective lesson is the F9 finding in numeric form: the graph vendors have the model
and no pipeline; the legal vendors have the pipeline and no model. Nobody has both. That
intersection is 19 points of Loupe's 55-point lead in group A.

### The defence-native cohort — the real comparison set

These four are the companies Loupe is actually competing with for the same buyer, and they are
funded at $2.5M–$7.5M seed, not war chests.

| | Total | Band | Certs | Graph | Device | Unification | Disconf | Provenance |
|---|---|---|---|---|---|---|---|---|
| **Loupe** | **168** | $10–50k | **1** | **9** | **9** | **10** | **8** | **9** |
| Matey / CrimD | 140 | $10–50k | **9** | 2 | 5 | 5 | 0 | 8 |
| Longeye | 138 | $10–50k | 8 | 1 | 6 | 7 | 0 | 8 |
| JusticeText | 132 | $10–50k | 6 | 1 | 0 | 4 | **6** | 7 |
| TrialKit | 128 | $10–50k | 4 | 2 | 7 | 6 | 0 | 8 |

Loupe outscores all four by 28–40 points, and every one of them currently holds certifications Loupe does not.
**Matey holds SOC 2 Type II and ISO 27001 today and sells to the same buyer through NACDL and a
state defence bar.** Longeye runs single-tenant on AWS GovCloud (deployment 8) and intends to give
the platform to public defenders free. JusticeText is the only competitor with a real
disconfirmation capability — Miranda AI at 6 — and it is narrow: inconsistencies across A/V
discovery, not a claims ledger. TrialKit claims phone extractions as an input type, not a modelled
device.

None of the four has a graph. All four have the category label, the bar associations and the
certifications. That is the competitive position in one paragraph.

### The legal-AI tier

**CoCounsel 140, <$10k** — ecosystem integrations **10, the study leader**, vendor viability 10,
and device data 0, graph 2, geospatial 0. **Harvey 127, $300k+** — provenance 8, agentic 8, cited
Q&A 9, and **1 on link analysis, 0 on geospatial, 1 on cross-source unification**; over $1B raised
at an $11B valuation, priced for the AmLaw 100 with seat minimums near $360,000/year.
**Hebbia 122** — agentic 8, cited Q&A 8, timeline **0**. **Clearbrief 119, <$10k** — per-claim
provenance **10 and AI defensibility 10, both study leaders**, on a total of 119; it does one
thing better than anyone and almost nothing else. **CaseMap+ AI 139** — durable judgment 9 (tied
with Loupe), LexisNexis distribution at integrations 9.

### The case-management tier

**Hubstream 144**, **Ontic 127**, **Kaseware 122**, **Comtrac 122**, **Resolver 114**,
**Case IQ 111**, **Case Closed 100**, **HR Acuity 96**, **Omnigo 93**, **CROSStrax 73**,
**Trackops 68**. Case workflow scores of 8–9 throughout against **Loupe's 4** — the axis where
Loupe ranks 39th of 47. Comtrac is the most interesting of them: its "Elementising Evidence"
methodology maps exhibits to the elements of an offence and scores **durable judgment objects 8**,
the closest shipped analogue anywhere to the Loupes thesis, on a total of 122.

CROSStrax ($35/month) and Trackops ($99/month) are built specifically for private investigators —
the exact beachhead buyer — and score 73 and 68, last and second-last in the study. They are the
proof of the whitespace: **the beachhead buyer already owns cheap case management and owns nothing
that analyses evidence.**

### Nearest neighbours by score profile

Ranking every platform by total absolute difference across all thirty axes gives the platforms
that most resemble Loupe in *shape* rather than in score:

| Platform | L1 distance | Total | Why it resembles Loupe |
|---|---|---|---|
| Longeye | 94 | 138 | Same buyer, same evidence mix claimed, no graph |
| TrialKit | 94 | 128 | Same buyer, device data 7, no graph |
| DataWalk | 95 | 145 | Graph + financial + traversal, enterprise-priced |
| Octostar | 96 | 110 | Graph-native, traversal 8, no readiness |
| Siren | 97 | 125 | Traversal 9, graph 8, no case workflow |
| Palantir | 101 | 201 | Same architecture, opposite commercial position |

The farthest are Relativity (150), Casepoint (145) and HR Acuity (144) — the pure review and pure
workflow platforms. This is a useful diligence answer: *the products that look most like Loupe are
either priced out of the beachhead or have no evidence model; the products that share the buyer
have no graph.*

---

## 9. Kaseware and Altia — where their graphs actually come from

Whether Kaseware's and Altia's link analysis is auto-built from ingested evidence or charted by an
analyst decides whether the auto-built-graph claim can stand. Direct research on vendor
documentation answers it, and the answer changes two rows.

**Kaseware — the graph is genuinely auto-built.** Kaseware's link-analysis page states charts are
"automatically generated from case and entity data without any manual effort" and update in real
time as information enters the system. Its AI services page goes further: entity extraction that
"identif[ies] people, organizations, locations, and events across documents and data feeds,"
extraction of "names, dates, locations, and other key details from unstructured data,"
AI-enhanced OCR for scanned documents, speech-to-text for "interviews, calls, and field
recordings," translation across 160+ languages, and relationship mapping that "connect[s] entities
across data sources to detect links." No evidence of UFED/Cellebrite parsing or financial-statement
parsing was found.

*Proposed revision:* axis 1 (auto-built graph) **5 → 7**; axis 5 (multimodal entities) **2 → 5**;
axis 6 (per-claim provenance) **2 → 3** (drill-through to source document, not quote-and-page).
New total **122 → 128**.

**Altia — provenance is real, the graph is not.** Altia's Financial Investigation Toolkit "allows
investigators to upload, scan, and extract data from bank statements in a structured, reliable
format," and "structures and indexes that information so every transaction, source, and disclosure
can be traced back to its origin." It "automatically logs every data ingestion with timestamps and
source references." That is genuine per-claim provenance over financial evidence. But FIT is
financial-only, holds no phone or communications data, sits in a separate product from the Insight
case-management module, and no evidence was found of automatic entity or relationship extraction
from the parsed financial data.

*Proposed revision:* axis 6 (per-claim provenance) **2 → 6**; axis 10 (financial analysis)
**7 → 8**. New total **140 → 145**.

**What this does to the claims.** It kills the loose version of "nobody else auto-builds a graph"
— Kaseware does, from ingested documents and audio. It leaves the precise version untouched and
in fact strengthens it: *no platform holds device data, financial records and documents in one
model.* Kaseware has no device or financial parsing; Altia has financial parsing with excellent
provenance and no device data (score 1) and no unified model. The claim was already qualified to
"cross-evidence-type, never graph" in the landscape doc — this research confirms that wording was
the right call and supplies the evidence for it.

**Held pending sign-off**, listed here so the change is auditable rather than silent. Neither
revision alters a market outcome or a finding.

---

## 10. What is still unverified

- **Comtrac** has no full dossier — the closest analogue to the Loupes thesis is covered in a
  paragraph. It should have one.
- **Price bands are entry-point estimates.** Several vendors publish nothing; Harvey, Hebbia,
  CoCounsel and Everlaw seat prices are third-party estimates.
- **Loupe's own row scores the imminent release**, not today's build. Loupes and the
  disconfirmation agent are in that release and are not yet shipped. The lens footer states this;
  any external use must too.
- **Market sizes are analyst estimates, not primary research.** §7a sizes every market from
  published reports; the houses disagree by two to three times on several categories and none of
  those categories was drawn around this product. Re-check any figure against the underlying report
  before it goes in an investor document.

## 11. How to use this instrument

- **For a specific prospect:** pick their market, pick their budget, read the gate column first.
  Capability arguments are wasted on a buyer whose procurement gate you fail.
- **For the accelerator application:** the three sentences that carry are — *no platform of
  forty-seven can be sold into all fifteen markets, and only eight reach more than twelve; Loupe
  reaches thirteen*; *the two platforms scoring above Loupe on review-heavy capability, Relativity
  and Everlaw, reach three and four markets between them — a high total earned in one group buys
  one market*; and *Loupe is second of fourteen in its price band and leads that band on evidence
  modelling by twenty-two points.* All three are comparative rather than self-descriptive, which is
  the register a diligence panel trusts.
- **For roadmap argument:** the axes where movement changes the most outcomes are, in order —
  OSINT (0, and it caps insurance SIU, due diligence and corporate security), case workflow (4,
  and it caps every corporate and government market), review-at-scale and disclosure (1 and 2,
  which together decide civil litigation, the largest spend pool and Loupe's weakest market), and
  evidence acquisition (0, the only thing keeping Loupe out of national security). Certifications
  are deliberately absent from this list: they are bought when a deal needs them and they change
  no fit number.

---

# Data appendix

Everything below is generated directly from the published artifact's score arrays.

## A. The thirty axes

| # | Group | Axis | What it measures | Leader(s) | Median | Loupe |
|---|---|---|---|---|---|---|
| 1 | A | **Auto-built case graph** | Whether the platform builds a persistent model of people, organisations, accounts and events — and the relationships between them — automatically as… | Loupe, Palantir Gotham / AIP — 9 | 3 | **9** (#1) |
| 2 | A | **Device data as structured evidence** | Whether a phone or device extraction becomes first-class objects — individual calls, contacts, messages, locations — that can each be queried and… | Magnet Axiom / Magnet One, Cellebrite Guardian Investigate, Cellebrite Pathfinder — 10 | 1 | **9** (#4) |
| 3 | A | **Cross-source unification** | Whether phone data, documents and financial records resolve into one model, so the same person is the same object across all three. Most platforms… | Loupe — 10 | 2 | **10** (#1) |
| 4 | A | **Whole-corpus relational query** | Whether a question whose answer depends on relationships can be answered across everything ingested, with a definite result — rather than by… | Loupe, Palantir Gotham / AIP, Siren — 9 | 4 | **9** (#1) |
| 5 | A | **Multimodal entities into the model** | Whether names and places spoken in audio or shown in video and images become the same objects as those in documents — not merely a searchable… | Loupe — 9 | 2 | **9** (#1) |
| 6 | A | **Per-claim provenance** | Whether every extracted fact carries the exact quote, page and file it came from, stored with the fact itself — so any assertion can be traced back… | Clearbrief — 10 | 5 | **9** (#2) |
| 7 | B | **Link / network analysis** | How mature the tooling is for exploring connections visually: expanding a person's neighbourhood, finding paths between two entities, ranking by… | IBM i2 (i2 Group) — 10 | 4 | **7** (#11) |
| 8 | B | **Timeline & chronology** | Whether dated facts assemble into a filterable chronology that persists as a work product with its citations intact, rather than a one-off view… | Loupe, Palantir Gotham / AIP, Magnet Axiom / Magnet One +7 — 8 | 5 | **8** (#1) |
| 9 | B | **Geospatial analysis** | Mapping of located evidence — movement trails, proximity between events, heatmaps — and the ability to ask questions about where something… | Palantir Gotham / AIP, Magnet Axiom / Magnet One, Cellebrite Pathfinder — 9 | 3 | **7** (#6) |
| 10 | B | **Financial / transaction analysis** | Handling of ledgers and transactions: categorisation, resolving who the counterparty actually is, tracing flows between parties, and keeping the… | DataWalk — 9 | 2 | **8** (#2) |
| 11 | B | **OSINT & external enrichment** | Ability to reach outside the case for open-source material — corporate registries, social media, adverse media, sanctions lists, court records — and… | Babel Street, Neotas, Maltego — 10 | 3 | **0** (#47) |
| 12 | C | **Processing & format breadth** | How many file types and container formats the ingestion engine can decode, including forensic disk images, nested archives and email stores. Nuix's… | Nuix Neo — 10 | 5 | **5** (#18) |
| 13 | C | **Case & investigation workflow** | Managing the investigation itself: intake, assignment, tasks, status, supervisor oversight — and whether the case exists as an object with a… | Nuix Neo, Hubstream, Ontic +5 — 9 | 6 | **4** (#39) |
| 14 | C | **Review workflow at scale** | Machinery for teams reviewing large document sets: batching work out, coding panels, tracking reviewer progress and sampling for quality… | Everlaw, Relativity (aiR) — 10 | 3 | **1** (#42) |
| 15 | C | **Disclosure & production mechanics** | Producing evidence to another party to a required standard: redaction, privilege logs, Bates numbering, load files and the production formats a court… | Relativity (aiR) — 10 | 3 | **2** (#36) |
| 16 | C | **Analytics / TAR** | Technology-assisted review — active learning that predicts relevance, email threading, near-duplicate detection, conceptual clustering. This is what… | Relativity (aiR) — 10 | 3 | **0** (#47) |
| 17 | C | **Collaboration & permissions** | Multiple people working one case safely: granular access control, need-to-know segregation, shared work product, and an audit of who did… | Everlaw, Relativity (aiR) — 9 | 7 | **5** (#34) |
| 18 | C | **Durable judgment objects** | Whether an investigator's conclusions persist as first-class objects in the system — curated collections, approved facts, built narratives — rather… | Loupe, Everlaw, CaseMap+ AI (LexisNexis) +1 — 9 | 5 | **9** (#1) |
| 19 | D | **Cited document Q&A** | Quality of natural-language question answering over the evidence, with each answer linked back to the source documents it rests… | Everlaw — 10 | 5 | **8** (#5) |
| 20 | D | **Agentic task execution** | Whether the AI can carry out multi-step work using tools and produce outputs you keep — tables, charts, reports, collections — rather than only… | Exterro FTK / ARMOUR — 9 | 4 | **8** (#2) |
| 21 | D | **Disconfirmation detection** | Whether the platform actively hunts for what contradicts a theory: the inconsistent date, the document placing someone elsewhere, the material that… | Loupe — 8 | 0 | **8** (#1) |
| 22 | E | **Certifications & compliance** | Independently audited security and compliance credentials — SOC 2 Type II, ISO 27001, CJIS, FedRAMP. Usually the first question a client's counsel… | Palantir Gotham / AIP, Casepoint — 10 | 7 | **1** (#47) |
| 23 | E | **Proven scale** | Published, verifiable evidence of the volumes the platform actually handles in production — data processed, customers, corpus sizes — as distinct… | Palantir Gotham / AIP, Relativity (aiR), Cellebrite Pathfinder +1 — 10 | 7 | **3** (#44) |
| 24 | E | **Ecosystem integrations** | Connections into the systems the work already lives in: document management, case and practice management, legal research, and third-party data… | CoCounsel (Thomson Reuters) — 10 | 6 | **0** (#47) |
| 25 | E | **Evidence acquisition** | Whether the vendor can collect evidence at source — extract a device, image an endpoint, pull from cloud accounts — rather than only analysing what… | Magnet Axiom / Magnet One, Cellebrite Guardian Investigate, Cellebrite Pathfinder — 10 | 2 | **0** (#33) |
| 26 | E | **Acquisition & parsing validation** | Whether the tool's collection and decoding has been independently tested and has survived challenge in court: NIST CFTT test reports, published error… | Magnet Axiom / Magnet One, Exterro FTK / ARMOUR, Cellebrite Pathfinder — 9 | 4 | **2** (#43) |
| 27 | E | **Defensibility of AI output** | Whether AI-produced findings can be audited and challenged: recorded prompts and outputs, explicit human review status, AI content visibly… | Clearbrief — 10 | 5 | **8** (#5) |
| 28 | E | **Vendor viability & support** | Whether the company will still be there and able to support you — funding and revenue, headcount, support commitments, training and professional… | Palantir Gotham / AIP, Cellebrite Guardian Investigate, Relativity (aiR) +4 — 10 | 7 | **3** (#46) |
| 29 | E | **Commercial accessibility** | Whether the target buyer can realistically buy it at all: the entry price, minimum commitments, whether there is a self-serve route, and whether the… | CROSStrax, Trackops — 10 | 5 | **7** (#10) |
| 30 | E | **Deployment control** | Whether the customer can run it in isolation — single-tenant, on-premises, or in their own sovereign cloud — so evidence never sits in a shared… | Loupe, Palantir Gotham / AIP, Exterro FTK / ARMOUR +1 — 9 | 5 | **9** (#1) |

## B. All 47 platforms — totals and group subtotals

| Rank | Platform | Entry price | A /60 | B /50 | C /70 | D /30 | E /90 | **Total /300** |
|---|---|---|---|---|---|---|---|---|
| 1 | Palantir Gotham / AIP | $300k+ | 40 | 40 | 41 | 16 | 64 | **201** |
| 2 | Magnet Axiom / Magnet One | $50–300k | 38 | 27 | 40 | 12 | 73 | **190** |
| 3 | Exterro FTK / ARMOUR | $10–50k | 31 | 20 | 40 | 16 | 70 | **177** |
| 4 | Relativity (aiR) | $50–300k | 20 | 16 | 61 | 16 | 63 | **176** |
| 5 | Cellebrite Guardian Investigate | $50–300k | 35 | 29 | 37 | 11 | 63 | **175** |
| 6 | Everlaw | $50–300k | 24 | 16 | 60 | 17 | 58 | **175** |
| 7 | Cellebrite Pathfinder | $50–300k | 37 | 31 | 30 | 7 | 64 | **169** |
| 8 | Cognyte NEXYTE | $300k+ | 33 | 35 | 34 | 13 | 54 | **169** |
| 9 | Nuix Neo | $300k+ | 27 | 19 | 54 | 11 | 58 | **169** |
| 10 | **Loupe** | $10–50k | 55 | 30 | 26 | 24 | 33 | **168** |
| 11 | Axon (Records / Evidence) | $50–300k | 25 | 18 | 40 | 10 | 65 | **158** |
| 12 | NICE Investigate | $50–300k | 28 | 21 | 41 | 6 | 57 | **153** |
| 13 | Babel Street | $300k+ | 25 | 33 | 25 | 12 | 55 | **150** |
| 14 | DataWalk | $300k+ | 33 | 34 | 28 | 8 | 42 | **145** |
| 15 | Hubstream | $50–300k | 24 | 31 | 36 | 8 | 45 | **144** |
| 16 | DISCO (Cecilia) | $50–300k | 20 | 12 | 52 | 15 | 45 | **144** |
| 17 | Reveal / Logikcull | $10–50k | 19 | 13 | 52 | 11 | 48 | **143** |
| 18 | Casepoint | $300k+ | 16 | 9 | 49 | 12 | 55 | **141** |
| 19 | Altia | $50–300k | 17 | 37 | 30 | 6 | 50 | **140** |
| 20 | CoCounsel (Thomson Reuters) | <$10k | 18 | 12 | 35 | 16 | 59 | **140** |
| 21 | Matey / CrimD | $10–50k | 30 | 14 | 37 | 11 | 48 | **140** |
| 22 | CaseMap+ AI (LexisNexis) | $10–50k | 19 | 18 | 41 | 10 | 51 | **139** |
| 23 | Longeye | $10–50k | 32 | 15 | 30 | 11 | 50 | **138** |
| 24 | Blackdot Videris | $50–300k | 19 | 33 | 25 | 10 | 47 | **134** |
| 25 | IBM i2 (i2 Group) | <$10k | 18 | 35 | 28 | 0 | 52 | **133** |
| 26 | JusticeText | $10–50k | 23 | 11 | 35 | 16 | 47 | **132** |
| 27 | Casefleet | <$10k | 19 | 16 | 36 | 12 | 48 | **131** |
| 28 | Neotas | $50–300k | 16 | 28 | 25 | 10 | 51 | **130** |
| 29 | TrialKit | $10–50k | 33 | 12 | 33 | 11 | 39 | **128** |
| 30 | Ontic | $50–300k | 16 | 24 | 32 | 6 | 49 | **127** |
| 31 | Harvey | $300k+ | 17 | 10 | 35 | 17 | 48 | **127** |
| 32 | Siren | $50–300k | 29 | 30 | 19 | 9 | 38 | **125** |
| 33 | Maltego | <$10k | 9 | 31 | 20 | 5 | 58 | **123** |
| 34 | Kaseware | $50–300k | 15 | 26 | 30 | 4 | 47 | **122** |
| 35 | Comtrac | $10–50k | 16 | 13 | 40 | 10 | 43 | **122** |
| 36 | Hebbia | $10–50k | 20 | 7 | 35 | 16 | 44 | **122** |
| 37 | Clearbrief | <$10k | 15 | 10 | 26 | 16 | 52 | **119** |
| 38 | Resolver (Kroll) | $50–300k | 9 | 17 | 33 | 8 | 47 | **114** |
| 39 | Case IQ | $10–50k | 9 | 14 | 33 | 7 | 48 | **111** |
| 40 | Octostar | $50–300k | 28 | 25 | 21 | 8 | 28 | **110** |
| 41 | Linkurious | $10–50k | 19 | 25 | 18 | 5 | 39 | **106** |
| 42 | ShadowDragon | $50–300k | 14 | 27 | 13 | 4 | 45 | **103** |
| 43 | Case Closed Software | <$10k | 13 | 16 | 27 | 2 | 42 | **100** |
| 44 | HR Acuity | $10–50k | 9 | 9 | 30 | 5 | 43 | **96** |
| 45 | Omnigo | $10–50k | 8 | 14 | 27 | 3 | 41 | **93** |
| 46 | CROSStrax | <$10k | 6 | 14 | 20 | 2 | 31 | **73** |
| 47 | Trackops | <$10k | 6 | 11 | 19 | 2 | 30 | **68** |

## C. Full score matrix — 47 platforms × 30 axes

| Platform | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 | 21 | 22 | 23 | 24 | 25 | 26 | 27 | 28 | 29 | 30 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Palantir Gotham / AIP | 9 | 4 | 6 | 9 | 6 | 6 | 9 | 8 | 9 | 7 | 7 | 7 | 6 | 4 | 3 | 6 | 8 | 7 | 6 | 8 | 2 | 10 | 10 | 8 | 4 | 6 | 6 | 10 | 1 | 9 |
| Magnet Axiom / Magnet One | 5 | 10 | 5 | 5 | 6 | 7 | 7 | 8 | 9 | 1 | 2 | 7 | 7 | 5 | 6 | 3 | 7 | 5 | 6 | 5 | 1 | 8 | 9 | 7 | 10 | 9 | 8 | 9 | 5 | 8 |
| Exterro FTK / ARMOUR | 3 | 7 | 5 | 5 | 4 | 7 | 4 | 8 | 3 | 2 | 3 | 8 | 6 | 5 | 5 | 4 | 7 | 5 | 6 | 9 | 1 | 7 | 8 | 6 | 8 | 9 | 9 | 8 | 6 | 9 |
| Relativity (aiR) | 2 | 2 | 2 | 3 | 2 | 9 | 4 | 8 | 1 | 2 | 1 | 8 | 6 | 10 | 10 | 10 | 9 | 8 | 9 | 5 | 2 | 9 | 10 | 9 | 4 | 7 | 9 | 10 | 2 | 3 |
| Cellebrite Guardian Investigate | 6 | 10 | 6 | 5 | 5 | 3 | 7 | 8 | 7 | 2 | 5 | 6 | 7 | 4 | 6 | 3 | 8 | 3 | 5 | 6 | 0 | 8 | 9 | 8 | 10 | 8 | 3 | 10 | 1 | 6 |
| Everlaw | 2 | 3 | 2 | 6 | 2 | 9 | 4 | 8 | 1 | 2 | 1 | 8 | 6 | 10 | 9 | 9 | 9 | 9 | 10 | 6 | 1 | 9 | 9 | 7 | 3 | 6 | 8 | 9 | 5 | 2 |
| Cellebrite Pathfinder | 7 | 10 | 4 | 6 | 6 | 4 | 9 | 8 | 9 | 2 | 3 | 6 | 5 | 3 | 4 | 3 | 6 | 3 | 3 | 4 | 0 | 8 | 10 | 8 | 10 | 9 | 2 | 10 | 1 | 6 |
| Cognyte NEXYTE | 7 | 4 | 5 | 6 | 7 | 4 | 8 | 7 | 8 | 5 | 7 | 5 | 7 | 3 | 3 | 4 | 7 | 5 | 6 | 6 | 1 | 7 | 8 | 6 | 7 | 5 | 3 | 8 | 2 | 8 |
| Nuix Neo | 4 | 5 | 4 | 4 | 4 | 6 | 5 | 5 | 3 | 4 | 2 | 10 | 9 | 8 | 7 | 8 | 7 | 5 | 6 | 5 | 0 | 7 | 9 | 7 | 6 | 8 | 3 | 7 | 2 | 9 |
| **Loupe** | 9 | 9 | 10 | 9 | 9 | 9 | 7 | 8 | 7 | 8 | 0 | 5 | 4 | 1 | 2 | 0 | 5 | 9 | 8 | 8 | 8 | 1 | 3 | 0 | 0 | 2 | 8 | 3 | 7 | 9 |
| Axon (Records / Evidence) | 3 | 3 | 4 | 3 | 7 | 5 | 3 | 6 | 6 | 1 | 2 | 5 | 8 | 4 | 8 | 3 | 8 | 4 | 4 | 6 | 0 | 9 | 10 | 8 | 9 | 7 | 5 | 10 | 1 | 6 |
| NICE Investigate | 4 | 4 | 6 | 4 | 5 | 5 | 5 | 6 | 5 | 2 | 3 | 6 | 8 | 4 | 8 | 3 | 8 | 4 | 3 | 3 | 0 | 8 | 8 | 7 | 6 | 7 | 5 | 8 | 2 | 6 |
| Babel Street | 5 | 0 | 1 | 6 | 5 | 8 | 7 | 5 | 7 | 4 | 10 | 3 | 4 | 2 | 2 | 4 | 5 | 5 | 7 | 5 | 0 | 8 | 7 | 7 | 8 | 4 | 7 | 7 | 2 | 5 |
| DataWalk | 8 | 3 | 5 | 8 | 5 | 4 | 8 | 6 | 6 | 9 | 5 | 5 | 5 | 3 | 2 | 5 | 6 | 2 | 4 | 4 | 0 | 6 | 6 | 6 | 1 | 4 | 4 | 6 | 1 | 8 |
| Hubstream | 6 | 2 | 4 | 5 | 3 | 4 | 8 | 7 | 7 | 4 | 5 | 4 | 9 | 3 | 4 | 4 | 7 | 5 | 4 | 4 | 0 | 7 | 7 | 5 | 2 | 5 | 3 | 6 | 3 | 7 |
| DISCO (Cecilia) | 1 | 2 | 2 | 5 | 2 | 8 | 1 | 8 | 1 | 1 | 1 | 7 | 5 | 9 | 8 | 7 | 8 | 8 | 8 | 7 | 0 | 6 | 7 | 6 | 2 | 6 | 7 | 5 | 4 | 2 |
| Reveal / Logikcull | 3 | 2 | 2 | 3 | 2 | 7 | 5 | 5 | 1 | 1 | 1 | 8 | 5 | 9 | 8 | 9 | 8 | 5 | 7 | 4 | 0 | 7 | 7 | 6 | 2 | 6 | 5 | 6 | 6 | 3 |
| Casepoint | 1 | 1 | 1 | 4 | 2 | 7 | 2 | 4 | 1 | 1 | 1 | 7 | 5 | 9 | 9 | 7 | 8 | 4 | 7 | 5 | 0 | 10 | 8 | 5 | 2 | 7 | 6 | 7 | 2 | 8 |
| Altia | 5 | 1 | 3 | 4 | 2 | 2 | 7 | 6 | 8 | 7 | 9 | 4 | 8 | 2 | 3 | 2 | 7 | 4 | 3 | 3 | 0 | 6 | 8 | 6 | 3 | 5 | 3 | 8 | 4 | 7 |
| CoCounsel (Thomson Reuters) | 2 | 0 | 2 | 3 | 3 | 8 | 1 | 5 | 0 | 2 | 4 | 5 | 6 | 5 | 4 | 4 | 6 | 5 | 9 | 7 | 0 | 8 | 9 | 10 | 0 | 4 | 8 | 10 | 7 | 3 |
| Matey / CrimD | 2 | 5 | 5 | 4 | 6 | 8 | 2 | 6 | 2 | 2 | 2 | 6 | 6 | 5 | 5 | 3 | 6 | 6 | 7 | 4 | 0 | 9 | 5 | 5 | 0 | 3 | 8 | 6 | 9 | 3 |
| CaseMap+ AI (LexisNexis) | 5 | 0 | 3 | 4 | 2 | 5 | 3 | 7 | 1 | 2 | 5 | 6 | 6 | 5 | 5 | 4 | 6 | 9 | 6 | 4 | 0 | 8 | 8 | 9 | 0 | 5 | 5 | 9 | 4 | 3 |
| Longeye | 1 | 6 | 7 | 4 | 6 | 8 | 2 | 5 | 2 | 4 | 2 | 6 | 5 | 4 | 4 | 3 | 6 | 2 | 7 | 4 | 0 | 8 | 4 | 4 | 0 | 4 | 7 | 6 | 9 | 8 |
| Blackdot Videris | 5 | 0 | 2 | 5 | 2 | 5 | 8 | 4 | 4 | 8 | 9 | 3 | 5 | 2 | 2 | 4 | 5 | 4 | 5 | 5 | 0 | 6 | 6 | 6 | 7 | 3 | 4 | 6 | 4 | 5 |
| IBM i2 (i2 Group) | 6 | 1 | 2 | 5 | 2 | 2 | 10 | 7 | 7 | 6 | 5 | 3 | 6 | 2 | 3 | 3 | 5 | 6 | 0 | 0 | 0 | 7 | 8 | 6 | 2 | 6 | 0 | 7 | 8 | 8 |
| JusticeText | 1 | 0 | 4 | 3 | 8 | 7 | 1 | 7 | 1 | 1 | 1 | 5 | 6 | 4 | 4 | 3 | 7 | 6 | 6 | 4 | 6 | 6 | 7 | 5 | 0 | 4 | 6 | 7 | 9 | 3 |
| Casefleet | 4 | 0 | 2 | 3 | 2 | 8 | 3 | 8 | 2 | 2 | 1 | 4 | 6 | 4 | 4 | 3 | 6 | 9 | 6 | 4 | 2 | 8 | 5 | 6 | 0 | 4 | 9 | 6 | 8 | 2 |
| Neotas | 4 | 0 | 2 | 3 | 3 | 4 | 6 | 4 | 3 | 5 | 10 | 3 | 5 | 2 | 3 | 3 | 5 | 4 | 5 | 4 | 1 | 7 | 7 | 6 | 5 | 4 | 6 | 7 | 5 | 4 |
| TrialKit | 2 | 7 | 6 | 4 | 6 | 8 | 2 | 5 | 2 | 1 | 2 | 6 | 6 | 4 | 4 | 3 | 6 | 4 | 7 | 4 | 0 | 4 | 4 | 4 | 0 | 3 | 7 | 5 | 9 | 3 |
| Ontic | 4 | 0 | 3 | 3 | 2 | 4 | 5 | 5 | 5 | 2 | 7 | 3 | 9 | 2 | 3 | 2 | 8 | 5 | 3 | 3 | 0 | 9 | 8 | 6 | 3 | 3 | 4 | 8 | 4 | 4 |
| Harvey | 1 | 0 | 1 | 4 | 3 | 8 | 1 | 5 | 0 | 2 | 2 | 5 | 5 | 5 | 4 | 4 | 7 | 5 | 9 | 8 | 0 | 8 | 8 | 8 | 0 | 3 | 7 | 10 | 1 | 3 |
| Siren | 8 | 3 | 4 | 9 | 1 | 4 | 8 | 6 | 6 | 4 | 6 | 4 | 2 | 2 | 1 | 3 | 5 | 2 | 4 | 4 | 1 | 4 | 6 | 6 | 1 | 3 | 3 | 5 | 2 | 8 |
| Maltego | 4 | 0 | 1 | 1 | 1 | 2 | 9 | 4 | 5 | 3 | 10 | 2 | 4 | 1 | 2 | 2 | 5 | 4 | 2 | 3 | 0 | 6 | 7 | 9 | 7 | 5 | 4 | 7 | 7 | 6 |
| Kaseware | 5 | 1 | 2 | 3 | 2 | 2 | 7 | 7 | 7 | 2 | 3 | 3 | 9 | 2 | 2 | 1 | 8 | 5 | 2 | 2 | 0 | 6 | 7 | 6 | 1 | 4 | 3 | 7 | 6 | 7 |
| Comtrac | 3 | 1 | 2 | 2 | 2 | 6 | 3 | 5 | 2 | 2 | 1 | 3 | 9 | 4 | 7 | 2 | 7 | 8 | 5 | 4 | 1 | 5 | 6 | 4 | 1 | 5 | 5 | 6 | 5 | 6 |
| Hebbia | 2 | 0 | 1 | 5 | 4 | 8 | 1 | 0 | 0 | 4 | 2 | 6 | 4 | 6 | 3 | 4 | 6 | 6 | 8 | 8 | 0 | 8 | 7 | 6 | 0 | 3 | 7 | 8 | 2 | 3 |
| Clearbrief | 1 | 0 | 1 | 2 | 1 | 10 | 0 | 6 | 0 | 1 | 3 | 3 | 4 | 2 | 5 | 2 | 4 | 6 | 8 | 3 | 5 | 8 | 5 | 8 | 0 | 5 | 10 | 6 | 8 | 2 |
| Resolver (Kroll) | 2 | 0 | 1 | 2 | 1 | 3 | 4 | 4 | 3 | 3 | 3 | 3 | 9 | 3 | 3 | 2 | 8 | 5 | 4 | 4 | 0 | 8 | 9 | 7 | 0 | 3 | 3 | 9 | 4 | 4 |
| Case IQ | 2 | 0 | 1 | 2 | 1 | 3 | 3 | 4 | 2 | 3 | 2 | 3 | 9 | 3 | 3 | 2 | 8 | 5 | 4 | 3 | 0 | 9 | 8 | 7 | 0 | 3 | 3 | 8 | 6 | 4 |
| Octostar | 6 | 4 | 4 | 8 | 2 | 4 | 6 | 5 | 4 | 4 | 6 | 4 | 3 | 2 | 1 | 3 | 5 | 3 | 4 | 4 | 0 | 2 | 2 | 5 | 3 | 2 | 3 | 3 | 1 | 7 |
| Linkurious | 8 | 0 | 1 | 8 | 0 | 2 | 8 | 5 | 4 | 5 | 3 | 1 | 4 | 1 | 1 | 2 | 5 | 4 | 2 | 3 | 0 | 5 | 5 | 6 | 0 | 3 | 2 | 6 | 5 | 7 |
| ShadowDragon | 3 | 0 | 1 | 3 | 2 | 5 | 6 | 4 | 5 | 3 | 9 | 2 | 2 | 1 | 1 | 2 | 3 | 2 | 2 | 2 | 0 | 5 | 5 | 8 | 8 | 3 | 2 | 5 | 4 | 5 |
| Case Closed Software | 3 | 1 | 2 | 3 | 1 | 3 | 4 | 4 | 4 | 2 | 2 | 3 | 8 | 2 | 3 | 3 | 5 | 3 | 1 | 1 | 0 | 7 | 5 | 4 | 1 | 4 | 2 | 5 | 6 | 8 |
| HR Acuity | 2 | 0 | 1 | 2 | 1 | 3 | 2 | 4 | 1 | 1 | 1 | 2 | 9 | 2 | 3 | 3 | 7 | 4 | 3 | 2 | 0 | 8 | 8 | 6 | 0 | 2 | 3 | 8 | 5 | 3 |
| Omnigo | 2 | 0 | 1 | 2 | 1 | 2 | 3 | 4 | 5 | 1 | 1 | 3 | 8 | 2 | 3 | 1 | 7 | 3 | 2 | 1 | 0 | 6 | 6 | 5 | 1 | 4 | 2 | 6 | 6 | 5 |
| CROSStrax | 1 | 0 | 1 | 1 | 1 | 2 | 2 | 3 | 3 | 2 | 4 | 2 | 7 | 1 | 2 | 1 | 5 | 2 | 1 | 1 | 0 | 2 | 3 | 5 | 1 | 2 | 1 | 4 | 10 | 3 |
| Trackops | 1 | 0 | 1 | 1 | 1 | 2 | 1 | 3 | 3 | 2 | 2 | 2 | 7 | 1 | 2 | 1 | 4 | 2 | 1 | 1 | 0 | 2 | 3 | 4 | 1 | 2 | 1 | 4 | 10 | 3 |

## D. Market profiles — requirements, gates and results


### Criminal defence & PI

This buyer **receives** evidence and never collects it, so OSINT, evidence acquisition, review-at-scale and TAR are genuinely not applicable rather than weaknesses — they are excluded from the fit calculation entirely. What remains is narrow and deep: the phone extraction that arrives in nearly every case, held in one model alongside the documents and bank records, every claim traceable to a page, and a chronology that can go in front of a judge. **Disconfirmation is a core requirement here and nowhere else at this weight** — breaking the prosecution's theory is the job. Gated on certifications, purchasability and single-tenant deployment, because privileged material under a protective order fails all three tests otherwise.

- **Gates:** Commercial accessibility ≥ 5, Deployment control ≥ 6
- **Not applicable here:** OSINT & external enrichment, Review workflow at scale, Analytics / TAR, Certifications & compliance, Evidence acquisition
- **Core requirements (12):** Auto-built case graph ≥6, Device data as structured evidence ≥7, Cross-source unification ≥7, Whole-corpus relational query ≥6, Multimodal entities into the model ≥5, Per-claim provenance ≥8, Timeline & chronology ≥6, Financial / transaction analysis ≥5, Processing & format breadth ≥5, Durable judgment objects ≥5, Cited document Q&A ≥6, Disconfirmation detection ≥4
- **Loupe:** fit **87%**, core met 12/12, rank **1 of 47**, gates failed: **none**
- **Platforms clearing every gate:** 10 of 47

| Fit | Platform | Core met | Entry price | Gate status |
|---|---|---|---|---|
| 87% | **Loupe** | 12/12 | $10–50k | clears all gates |
| 86% | Palantir Gotham / AIP | 8/12 | $300k+ | **fails:** Commercial accessibility |
| 80% | Magnet Axiom / Magnet One | 6/12 | $50–300k | clears all gates |
| 79% | Cognyte NEXYTE | 8/12 | $300k+ | **fails:** Commercial accessibility |
| 76% | Exterro FTK / ARMOUR | 5/12 | $10–50k | clears all gates |
| 74% | Cellebrite Guardian Investigate | 5/12 | $50–300k | **fails:** Commercial accessibility |
| 71% | Cellebrite Pathfinder | 6/12 | $50–300k | **fails:** Commercial accessibility |
| 71% | Nuix Neo | 3/12 | $300k+ | **fails:** Commercial accessibility |
| 68% | DataWalk | 6/12 | $300k+ | **fails:** Commercial accessibility |
| 67% | Everlaw | 6/12 | $50–300k | **fails:** Deployment control |

### Corporate & internal investigations

A workflow market first. Case management, collaboration across legal, HR and security, and enterprise procurement discipline dominate; phone evidence is incidental. Certifications gate hard and deployment gates alongside them — the security team has to be able to approve it, and nothing leaves the tenant.

- **Gates:** Deployment control ≥ 5
- **Not applicable here:** Certifications & compliance, Evidence acquisition
- **Core requirements (16):** Auto-built case graph ≥6, Cross-source unification ≥6, Whole-corpus relational query ≥7, Per-claim provenance ≥7, Link / network analysis ≥5, Timeline & chronology ≥6, Financial / transaction analysis ≥6, OSINT & external enrichment ≥5, Processing & format breadth ≥6, Case & investigation workflow ≥7, Collaboration & permissions ≥6, Durable judgment objects ≥5, Cited document Q&A ≥6, Proven scale ≥6, Ecosystem integrations ≥5, Vendor viability & support ≥6
- **Loupe:** fit **73%**, core met 9/16, rank **15 of 47**, gates failed: **none**
- **Platforms clearing every gate:** 27 of 47

| Fit | Platform | Core met | Entry price | Gate status |
|---|---|---|---|---|
| 89% | Palantir Gotham / AIP | 14/16 | $300k+ | clears all gates |
| 84% | Cognyte NEXYTE | 11/16 | $300k+ | clears all gates |
| 82% | Magnet Axiom / Magnet One | 11/16 | $50–300k | clears all gates |
| 80% | Exterro FTK / ARMOUR | 9/16 | $10–50k | clears all gates |
| 80% | Cellebrite Guardian Investigate | 11/16 | $50–300k | clears all gates |
| 78% | Nuix Neo | 9/16 | $300k+ | clears all gates |
| 78% | DataWalk | 10/16 | $300k+ | clears all gates |
| 77% | Hubstream | 10/16 | $50–300k | clears all gates |
| 75% | Everlaw | 9/16 | $50–300k | **fails:** Deployment control |
| 75% | NICE Investigate | 9/16 | $50–300k | clears all gates |
| 73% | **Loupe** | 9/16 | $10–50k | clears all gates |

### Prosecution & law enforcement

This buyer **owns the extraction**, so device data and acquisition are core rather than optional, and disclosure to the defence is a legal duty rather than a convenience. Forensic validation gates the courtroom — a tool whose parsing has never been tested is a Daubert problem. Certifications sit at CJIS and FedRAMP class.

- **Gates:** Deployment control ≥ 6
- **Not applicable here:** Certifications & compliance
- **Core requirements (22):** Auto-built case graph ≥7, Device data as structured evidence ≥8, Cross-source unification ≥6, Whole-corpus relational query ≥6, Multimodal entities into the model ≥6, Per-claim provenance ≥7, Link / network analysis ≥7, Timeline & chronology ≥7, Geospatial analysis ≥7, OSINT & external enrichment ≥5, Processing & format breadth ≥6, Case & investigation workflow ≥8, Disclosure & production mechanics ≥7, Collaboration & permissions ≥6, Durable judgment objects ≥5, Cited document Q&A ≥5, Proven scale ≥7, Ecosystem integrations ≥6, Evidence acquisition ≥6, Acquisition & parsing validation ≥8, Defensibility of AI output ≥8, Vendor viability & support ≥6
- **Loupe:** fit **70%**, core met 12/22, rank **15 of 47**, gates failed: **none**
- **Platforms clearing every gate:** 23 of 47

| Fit | Platform | Core met | Entry price | Gate status |
|---|---|---|---|---|
| 88% | Magnet Axiom / Magnet One | 16/22 | $50–300k | clears all gates |
| 86% | Palantir Gotham / AIP | 15/22 | $300k+ | clears all gates |
| 84% | Cellebrite Guardian Investigate | 14/22 | $50–300k | clears all gates |
| 82% | Exterro FTK / ARMOUR | 12/22 | $10–50k | clears all gates |
| 82% | Cognyte NEXYTE | 14/22 | $300k+ | clears all gates |
| 79% | Cellebrite Pathfinder | 14/22 | $50–300k | clears all gates |
| 77% | Nuix Neo | 11/22 | $300k+ | clears all gates |
| 77% | NICE Investigate | 9/22 | $50–300k | clears all gates |
| 74% | Axon (Records / Evidence) | 8/22 | $50–300k | clears all gates |
| 73% | Babel Street | 11/22 | $300k+ | **fails:** Deployment control |
| 70% | **Loupe** | 12/22 | $10–50k | clears all gates |

### Insurance SIU / fraud

**The only market in the set with no hard gate.** SIU teams buy tools without a federal certification regime standing over them. Financial analysis and OSINT dominate, because the claim and the claimant's public footprint are the case.

- **Gates:** none — the only ungated market
- **Not applicable here:** Certifications & compliance, Evidence acquisition
- **Core requirements (17):** Auto-built case graph ≥6, Cross-source unification ≥6, Whole-corpus relational query ≥6, Per-claim provenance ≥6, Link / network analysis ≥6, Timeline & chronology ≥6, Geospatial analysis ≥6, Financial / transaction analysis ≥7, OSINT & external enrichment ≥7, Processing & format breadth ≥5, Case & investigation workflow ≥7, Collaboration & permissions ≥5, Cited document Q&A ≥5, Proven scale ≥5, Ecosystem integrations ≥5, Vendor viability & support ≥5, Commercial accessibility ≥6
- **Loupe:** fit **77%**, core met 12/17, rank **7 of 47**, gates failed: **none**
- **Platforms clearing every gate:** 47 of 47

| Fit | Platform | Core met | Entry price | Gate status |
|---|---|---|---|---|
| 87% | Palantir Gotham / AIP | 15/17 | $300k+ | clears all gates |
| 83% | Cognyte NEXYTE | 13/17 | $300k+ | clears all gates |
| 82% | Magnet Axiom / Magnet One | 11/17 | $50–300k | clears all gates |
| 79% | Cellebrite Guardian Investigate | 12/17 | $50–300k | clears all gates |
| 79% | DataWalk | 11/17 | $300k+ | clears all gates |
| 78% | Exterro FTK / ARMOUR | 9/17 | $10–50k | clears all gates |
| 77% | **Loupe** | 12/17 | $10–50k | clears all gates |
| 77% | Hubstream | 9/17 | $50–300k | clears all gates |
| 75% | Nuix Neo | 8/17 | $300k+ | clears all gates |
| 75% | Altia | 10/17 | $50–300k | clears all gates |

### Investigative journalism

Excellent proof, terrible revenue. Provenance sits at 8 and disconfirmation is core, because publication standards demand verification before print. Accessibility is gated at 4 — there is no budget here, and the platforms that serve this market donate their way in. Deployment matters for source protection.

- **Gates:** Commercial accessibility ≥ 4
- **Not applicable here:** Disclosure & production mechanics, Certifications & compliance, Evidence acquisition, Acquisition & parsing validation, Defensibility of AI output
- **Core requirements (16):** Auto-built case graph ≥6, Cross-source unification ≥6, Whole-corpus relational query ≥7, Multimodal entities into the model ≥5, Per-claim provenance ≥8, Link / network analysis ≥6, Timeline & chronology ≥6, Geospatial analysis ≥5, Financial / transaction analysis ≥5, OSINT & external enrichment ≥6, Processing & format breadth ≥6, Collaboration & permissions ≥5, Durable judgment objects ≥6, Cited document Q&A ≥6, Disconfirmation detection ≥5, Deployment control ≥6
- **Loupe:** fit **84%**, core met 14/16, rank **3 of 47**, gates failed: **none**
- **Platforms clearing every gate:** 31 of 47

| Fit | Platform | Core met | Entry price | Gate status |
|---|---|---|---|---|
| 91% | Palantir Gotham / AIP | 14/16 | $300k+ | **fails:** Commercial accessibility |
| 84% | Cognyte NEXYTE | 10/16 | $300k+ | **fails:** Commercial accessibility |
| 84% | **Loupe** | 14/16 | $10–50k | clears all gates |
| 79% | Magnet Axiom / Magnet One | 8/16 | $50–300k | clears all gates |
| 78% | Cellebrite Guardian Investigate | 9/16 | $50–300k | **fails:** Commercial accessibility |
| 76% | DataWalk | 9/16 | $300k+ | **fails:** Commercial accessibility |
| 74% | Babel Street | 7/16 | $300k+ | **fails:** Commercial accessibility |
| 73% | Exterro FTK / ARMOUR | 5/16 | $10–50k | clears all gates |
| 73% | Cellebrite Pathfinder | 8/16 | $50–300k | **fails:** Commercial accessibility |
| 73% | Nuix Neo | 4/16 | $300k+ | **fails:** Commercial accessibility |

### Financial-crime units

Whole-corpus relational query at 8 and financial analysis at 8; phone evidence is genuinely not applicable and excluded. Gated on certifications and on sovereign or on-premises deployment — a regulated institution cannot put transaction data in a shared tenant.

- **Gates:** Deployment control ≥ 5
- **Not applicable here:** Device data as structured evidence, Certifications & compliance, Evidence acquisition
- **Core requirements (17):** Auto-built case graph ≥7, Cross-source unification ≥6, Whole-corpus relational query ≥8, Per-claim provenance ≥6, Link / network analysis ≥7, Timeline & chronology ≥6, Financial / transaction analysis ≥8, OSINT & external enrichment ≥6, Processing & format breadth ≥5, Case & investigation workflow ≥6, Analytics / TAR ≥5, Collaboration & permissions ≥5, Cited document Q&A ≥5, Agentic task execution ≥5, Proven scale ≥7, Ecosystem integrations ≥6, Vendor viability & support ≥6
- **Loupe:** fit **72%**, core met 11/17, rank **17 of 47**, gates failed: **none**
- **Platforms clearing every gate:** 27 of 47

| Fit | Platform | Core met | Entry price | Gate status |
|---|---|---|---|---|
| 92% | Palantir Gotham / AIP | 16/17 | $300k+ | clears all gates |
| 85% | Cognyte NEXYTE | 12/17 | $300k+ | clears all gates |
| 83% | DataWalk | 10/17 | $300k+ | clears all gates |
| 80% | Magnet Axiom / Magnet One | 11/17 | $50–300k | clears all gates |
| 79% | Cellebrite Guardian Investigate | 11/17 | $50–300k | clears all gates |
| 78% | Exterro FTK / ARMOUR | 10/17 | $10–50k | clears all gates |
| 77% | Nuix Neo | 10/17 | $300k+ | clears all gates |
| 76% | Babel Street | 9/17 | $300k+ | clears all gates |
| 76% | Hubstream | 6/17 | $50–300k | clears all gates |
| 75% | Everlaw | 11/17 | $50–300k | **fails:** Deployment control |
| 72% | **Loupe** | 11/17 | $10–50k | clears all gates |

### UK / EU policing

Prosecution's shape with stricter obligations. **Disclosure sits at 8** because CPIA duties are harder than the US equivalent, and **deployment is gated at 7** — the data must stay in jurisdiction. Forensic validation at 8.

- **Gates:** Deployment control ≥ 7
- **Not applicable here:** Certifications & compliance
- **Core requirements (22):** Auto-built case graph ≥7, Device data as structured evidence ≥8, Cross-source unification ≥6, Whole-corpus relational query ≥6, Multimodal entities into the model ≥6, Per-claim provenance ≥7, Link / network analysis ≥7, Timeline & chronology ≥7, Geospatial analysis ≥7, OSINT & external enrichment ≥5, Processing & format breadth ≥6, Case & investigation workflow ≥8, Disclosure & production mechanics ≥8, Collaboration & permissions ≥6, Durable judgment objects ≥5, Cited document Q&A ≥5, Proven scale ≥6, Ecosystem integrations ≥6, Evidence acquisition ≥6, Acquisition & parsing validation ≥8, Defensibility of AI output ≥8, Vendor viability & support ≥6
- **Loupe:** fit **70%**, core met 12/22, rank **15 of 47**, gates failed: **none**
- **Platforms clearing every gate:** 17 of 47

| Fit | Platform | Core met | Entry price | Gate status |
|---|---|---|---|---|
| 88% | Magnet Axiom / Magnet One | 16/22 | $50–300k | clears all gates |
| 86% | Palantir Gotham / AIP | 15/22 | $300k+ | clears all gates |
| 84% | Cellebrite Guardian Investigate | 14/22 | $50–300k | **fails:** Deployment control |
| 82% | Cognyte NEXYTE | 14/22 | $300k+ | clears all gates |
| 81% | Exterro FTK / ARMOUR | 12/22 | $10–50k | clears all gates |
| 79% | Cellebrite Pathfinder | 14/22 | $50–300k | **fails:** Deployment control |
| 77% | Nuix Neo | 10/22 | $300k+ | clears all gates |
| 77% | NICE Investigate | 9/22 | $50–300k | **fails:** Deployment control |
| 74% | Axon (Records / Evidence) | 8/22 | $50–300k | **fails:** Deployment control |
| 73% | Babel Street | 11/22 | $300k+ | **fails:** Deployment control |
| 70% | **Loupe** | 12/22 | $10–50k | clears all gates |

### Public defender offices

The same evidence problem as private defence on completely different economics. **Multimodal sits at 8** because bodycam and jail-call volume is the defining burden — it is an entire company's business model. **Accessibility is gated at 8**: one competitor intends to give the platform away here and another already covers CJA panel attorneys at no cost, so anything that is not free or near-free loses on price before it is evaluated on merit.

- **Gates:** Commercial accessibility ≥ 8
- **Not applicable here:** OSINT & external enrichment, Review workflow at scale, Analytics / TAR, Certifications & compliance, Evidence acquisition
- **Core requirements (16):** Auto-built case graph ≥5, Device data as structured evidence ≥6, Cross-source unification ≥6, Whole-corpus relational query ≥5, Multimodal entities into the model ≥8, Per-claim provenance ≥8, Timeline & chronology ≥6, Processing & format breadth ≥5, Case & investigation workflow ≥6, Collaboration & permissions ≥6, Durable judgment objects ≥5, Cited document Q&A ≥6, Disconfirmation detection ≥4, Proven scale ≥6, Vendor viability & support ≥5, Deployment control ≥5
- **Loupe:** fit **86%**, core met 12/16, rank **3 of 47**, gates failed: Commercial accessibility (needs 8, has 7)
- **Platforms clearing every gate:** 9 of 47

| Fit | Platform | Core met | Entry price | Gate status |
|---|---|---|---|---|
| 89% | Palantir Gotham / AIP | 12/16 | $300k+ | **fails:** Commercial accessibility |
| 88% | Magnet Axiom / Magnet One | 12/16 | $50–300k | **fails:** Commercial accessibility |
| 86% | **Loupe** | 12/16 | $10–50k | **fails:** Commercial accessibility |
| 84% | Exterro FTK / ARMOUR | 11/16 | $10–50k | **fails:** Commercial accessibility |
| 84% | Cognyte NEXYTE | 11/16 | $300k+ | **fails:** Commercial accessibility |
| 80% | Cellebrite Guardian Investigate | 11/16 | $50–300k | **fails:** Commercial accessibility |
| 78% | Nuix Neo | 8/16 | $300k+ | **fails:** Commercial accessibility |
| 77% | Cellebrite Pathfinder | 9/16 | $50–300k | **fails:** Commercial accessibility |
| 76% | NICE Investigate | 8/16 | $50–300k | **fails:** Commercial accessibility |
| 75% | Matey / CrimD | 8/16 | $10–50k | clears all gates |

### Law firms & civil disputes

The eDiscovery majors' home turf, the largest spend pool in the study, and **the market Loupe is furthest from serving**. Review at scale 9, disclosure and production 9, TAR 8, processing breadth 8. None of the evidence-modelling advantage matters if you cannot batch, code, quality-check, redact, log privilege and produce to a court's format.

- **Gates:** none — the only ungated market
- **Not applicable here:** Geospatial analysis, Certifications & compliance, Evidence acquisition
- **Core requirements (19):** Auto-built case graph ≥5, Cross-source unification ≥5, Whole-corpus relational query ≥7, Per-claim provenance ≥7, Timeline & chronology ≥7, Financial / transaction analysis ≥5, Processing & format breadth ≥8, Case & investigation workflow ≥6, Review workflow at scale ≥9, Disclosure & production mechanics ≥9, Analytics / TAR ≥8, Collaboration & permissions ≥7, Durable judgment objects ≥6, Cited document Q&A ≥7, Agentic task execution ≥5, Proven scale ≥8, Ecosystem integrations ≥7, Vendor viability & support ≥7, Deployment control ≥4
- **Loupe:** fit **68%**, core met 10/19, rank **20 of 47**, gates failed: **none**
- **Platforms clearing every gate:** 47 of 47

| Fit | Platform | Core met | Entry price | Gate status |
|---|---|---|---|---|
| 85% | Palantir Gotham / AIP | 13/19 | $300k+ | clears all gates |
| 82% | Magnet Axiom / Magnet One | 11/19 | $50–300k | clears all gates |
| 82% | Nuix Neo | 9/19 | $300k+ | clears all gates |
| 81% | Everlaw | 14/19 | $50–300k | clears all gates |
| 80% | Exterro FTK / ARMOUR | 10/19 | $10–50k | clears all gates |
| 80% | Relativity (aiR) | 14/19 | $50–300k | clears all gates |
| 78% | Cognyte NEXYTE | 10/19 | $300k+ | clears all gates |
| 75% | Cellebrite Guardian Investigate | 10/19 | $50–300k | clears all gates |
| 74% | Reveal / Logikcull | 6/19 | $10–50k | clears all gates |
| 73% | CaseMap+ AI (LexisNexis) | 7/19 | $10–50k | clears all gates |
| 68% | **Loupe** | 10/19 | $10–50k | clears all gates |

### Regulators & government enforcement

Provenance at 8 and durable judgment objects at 7, because mapping evidence to **offence elements** is the work product rather than a by-product. Disclosure at 8 — the brief of evidence goes to prosecution and has to survive it.

- **Gates:** Deployment control ≥ 6
- **Not applicable here:** Certifications & compliance
- **Core requirements (22):** Auto-built case graph ≥6, Device data as structured evidence ≥6, Cross-source unification ≥7, Whole-corpus relational query ≥6, Multimodal entities into the model ≥5, Per-claim provenance ≥8, Link / network analysis ≥6, Timeline & chronology ≥7, Financial / transaction analysis ≥7, OSINT & external enrichment ≥5, Processing & format breadth ≥6, Case & investigation workflow ≥8, Disclosure & production mechanics ≥8, Collaboration & permissions ≥6, Durable judgment objects ≥7, Cited document Q&A ≥6, Disconfirmation detection ≥5, Proven scale ≥6, Ecosystem integrations ≥5, Acquisition & parsing validation ≥7, Defensibility of AI output ≥7, Vendor viability & support ≥6
- **Loupe:** fit **73%**, core met 13/22, rank **8 of 47**, gates failed: **none**
- **Platforms clearing every gate:** 23 of 47

| Fit | Platform | Core met | Entry price | Gate status |
|---|---|---|---|---|
| 86% | Palantir Gotham / AIP | 14/22 | $300k+ | clears all gates |
| 82% | Magnet Axiom / Magnet One | 12/22 | $50–300k | clears all gates |
| 78% | Exterro FTK / ARMOUR | 10/22 | $10–50k | clears all gates |
| 78% | Cellebrite Guardian Investigate | 12/22 | $50–300k | clears all gates |
| 78% | Cognyte NEXYTE | 11/22 | $300k+ | clears all gates |
| 75% | Nuix Neo | 8/22 | $300k+ | clears all gates |
| 73% | Everlaw | 12/22 | $50–300k | **fails:** Deployment control |
| 73% | **Loupe** | 13/22 | $10–50k | clears all gates |
| 73% | NICE Investigate | 9/22 | $50–300k | clears all gates |
| 72% | Relativity (aiR) | 12/22 | $50–300k | **fails:** Deployment control |

### Corporate security & insider threat

**OSINT at 8** — threat-actor research, social listening and public records are the daily work — and workflow at 8, because the incident-to-investigation lifecycle is the product. Geospatial matters here in a way it does not for document-led markets: facilities, travel, executive protection.

- **Gates:** Deployment control ≥ 5
- **Not applicable here:** Review workflow at scale, Certifications & compliance
- **Core requirements (18):** Auto-built case graph ≥6, Cross-source unification ≥5, Whole-corpus relational query ≥6, Multimodal entities into the model ≥5, Per-claim provenance ≥6, Link / network analysis ≥7, Timeline & chronology ≥6, Geospatial analysis ≥7, OSINT & external enrichment ≥8, Processing & format breadth ≥5, Case & investigation workflow ≥8, Collaboration & permissions ≥7, Durable judgment objects ≥5, Cited document Q&A ≥5, Agentic task execution ≥5, Proven scale ≥6, Ecosystem integrations ≥6, Vendor viability & support ≥6
- **Loupe:** fit **75%**, core met 12/18, rank **13 of 47**, gates failed: **none**
- **Platforms clearing every gate:** 27 of 47

| Fit | Platform | Core met | Entry price | Gate status |
|---|---|---|---|---|
| 90% | Palantir Gotham / AIP | 16/18 | $300k+ | clears all gates |
| 88% | Magnet Axiom / Magnet One | 14/18 | $50–300k | clears all gates |
| 88% | Cognyte NEXYTE | 15/18 | $300k+ | clears all gates |
| 85% | Cellebrite Guardian Investigate | 13/18 | $50–300k | clears all gates |
| 81% | Exterro FTK / ARMOUR | 11/18 | $10–50k | clears all gates |
| 80% | Babel Street | 12/18 | $300k+ | clears all gates |
| 79% | Cellebrite Pathfinder | 10/18 | $50–300k | clears all gates |
| 79% | Nuix Neo | 10/18 | $300k+ | clears all gates |
| 79% | DataWalk | 10/18 | $300k+ | clears all gates |
| 79% | Hubstream | 9/18 | $50–300k | clears all gates |
| 75% | **Loupe** | 12/18 | $10–50k | clears all gates |

### Ethics, compliance & whistleblower

**Workflow at 9 and collaboration at 8.** Intake, triage, investigation and resolution is the entire product, and anonymity plus need-to-know segregation is not negotiable. Certifications gate at 7 — the most privacy-sensitive market in the set, with works councils and data-protection regimes on top of the usual audit.

- **Gates:** Deployment control ≥ 6
- **Not applicable here:** Device data as structured evidence, Geospatial analysis, Certifications & compliance, Evidence acquisition
- **Core requirements (15):** Auto-built case graph ≥4, Cross-source unification ≥4, Whole-corpus relational query ≥5, Multimodal entities into the model ≥5, Per-claim provenance ≥7, Timeline & chronology ≥6, Financial / transaction analysis ≥5, Processing & format breadth ≥5, Case & investigation workflow ≥9, Collaboration & permissions ≥8, Durable judgment objects ≥5, Cited document Q&A ≥5, Proven scale ≥6, Ecosystem integrations ≥6, Vendor viability & support ≥6
- **Loupe:** fit **74%**, core met 10/15, rank **18 of 47**, gates failed: **none**
- **Platforms clearing every gate:** 23 of 47

| Fit | Platform | Core met | Entry price | Gate status |
|---|---|---|---|---|
| 89% | Palantir Gotham / AIP | 13/15 | $300k+ | clears all gates |
| 85% | Magnet Axiom / Magnet One | 12/15 | $50–300k | clears all gates |
| 85% | Cognyte NEXYTE | 12/15 | $300k+ | clears all gates |
| 85% | Nuix Neo | 9/15 | $300k+ | clears all gates |
| 84% | Exterro FTK / ARMOUR | 10/15 | $10–50k | clears all gates |
| 80% | Cellebrite Guardian Investigate | 11/15 | $50–300k | clears all gates |
| 80% | Hubstream | 8/15 | $50–300k | clears all gates |
| 79% | Everlaw | 10/15 | $50–300k | **fails:** Deployment control |
| 79% | NICE Investigate | 9/15 | $50–300k | clears all gates |
| 78% | DataWalk | 10/15 | $300k+ | clears all gates |
| 74% | **Loupe** | 10/15 | $10–50k | clears all gates |

### Due diligence / KYC / third-party risk

**OSINT at 9 and evidence acquisition at 8.** You have to go and collect — nothing is handed to you, there is no discovery bundle. Structurally the wrong shape for a platform built to model evidence it receives.

- **Gates:** none — the only ungated market
- **Not applicable here:** Device data as structured evidence, Certifications & compliance, Acquisition & parsing validation, Defensibility of AI output
- **Core requirements (19):** Auto-built case graph ≥6, Cross-source unification ≥5, Whole-corpus relational query ≥6, Per-claim provenance ≥7, Link / network analysis ≥7, Financial / transaction analysis ≥7, OSINT & external enrichment ≥9, Processing & format breadth ≥4, Case & investigation workflow ≥6, Collaboration & permissions ≥5, Durable judgment objects ≥5, Cited document Q&A ≥6, Agentic task execution ≥6, Proven scale ≥6, Ecosystem integrations ≥6, Evidence acquisition ≥8, Vendor viability & support ≥6, Commercial accessibility ≥6, Deployment control ≥5
- **Loupe:** fit **74%**, core met 13/19, rank **12 of 47**, gates failed: **none**
- **Platforms clearing every gate:** 47 of 47

| Fit | Platform | Core met | Entry price | Gate status |
|---|---|---|---|---|
| 87% | Palantir Gotham / AIP | 15/19 | $300k+ | clears all gates |
| 86% | Cognyte NEXYTE | 14/19 | $300k+ | clears all gates |
| 84% | Magnet Axiom / Magnet One | 13/19 | $50–300k | clears all gates |
| 82% | Exterro FTK / ARMOUR | 14/19 | $10–50k | clears all gates |
| 80% | Babel Street | 12/19 | $300k+ | clears all gates |
| 80% | Blackdot Videris | 8/19 | $50–300k | clears all gates |
| 79% | Cellebrite Guardian Investigate | 12/19 | $50–300k | clears all gates |
| 78% | Nuix Neo | 9/19 | $300k+ | clears all gates |
| 76% | Hubstream | 9/19 | $50–300k | clears all gates |
| 75% | Altia | 10/19 | $50–300k | clears all gates |
| 74% | **Loupe** | 13/19 | $10–50k | clears all gates |

### Intelligence & national security

The highest bar anywhere: certifications gated at 8, deployment gated at 8 for sovereign and air-gapped operation, and **acquisition gated at 6** — an analysis-only tool cannot serve this buyer at all, however good the analysis.

- **Gates:** Evidence acquisition ≥ 6, Deployment control ≥ 8
- **Not applicable here:** Certifications & compliance
- **Core requirements (20):** Auto-built case graph ≥8, Device data as structured evidence ≥7, Cross-source unification ≥7, Whole-corpus relational query ≥8, Multimodal entities into the model ≥7, Per-claim provenance ≥6, Link / network analysis ≥8, Timeline & chronology ≥7, Geospatial analysis ≥8, Financial / transaction analysis ≥6, OSINT & external enrichment ≥7, Processing & format breadth ≥7, Case & investigation workflow ≥6, Collaboration & permissions ≥7, Durable judgment objects ≥5, Cited document Q&A ≥5, Agentic task execution ≥6, Proven scale ≥8, Ecosystem integrations ≥6, Vendor viability & support ≥7
- **Loupe:** fit **74%**, core met 11/20, rank **8 of 47**, gates failed: Evidence acquisition (needs 6, has 0)
- **Platforms clearing every gate:** 4 of 47

| Fit | Platform | Core met | Entry price | Gate status |
|---|---|---|---|---|
| 91% | Palantir Gotham / AIP | 17/20 | $300k+ | **fails:** Evidence acquisition |
| 84% | Cognyte NEXYTE | 13/20 | $300k+ | clears all gates |
| 82% | Magnet Axiom / Magnet One | 12/20 | $50–300k | clears all gates |
| 79% | Cellebrite Guardian Investigate | 9/20 | $50–300k | **fails:** Deployment control |
| 77% | Exterro FTK / ARMOUR | 12/20 | $10–50k | clears all gates |
| 74% | Cellebrite Pathfinder | 7/20 | $50–300k | **fails:** Deployment control |
| 74% | Nuix Neo | 9/20 | $300k+ | clears all gates |
| 74% | **Loupe** | 11/20 | $10–50k | **fails:** Evidence acquisition |
| 73% | DataWalk | 5/20 | $300k+ | **fails:** Evidence acquisition |
| 71% | Hubstream | 5/20 | $50–300k | **fails:** Evidence acquisition, Deployment control |

### Public-sector fraud (benefits, tax, immigration)

Population scale. Whole-corpus query at 8, financial analysis at 8 and proven scale at 8 — the corpora are enormous and the cases are individually small, which inverts the economics of every tool built for one big matter.

- **Gates:** Deployment control ≥ 6
- **Not applicable here:** Certifications & compliance
- **Core requirements (23):** Auto-built case graph ≥6, Cross-source unification ≥6, Whole-corpus relational query ≥8, Per-claim provenance ≥7, Link / network analysis ≥7, Timeline & chronology ≥6, Geospatial analysis ≥5, Financial / transaction analysis ≥8, OSINT & external enrichment ≥6, Processing & format breadth ≥6, Case & investigation workflow ≥7, Disclosure & production mechanics ≥6, Analytics / TAR ≥6, Collaboration & permissions ≥6, Durable judgment objects ≥5, Cited document Q&A ≥5, Agentic task execution ≥6, Disconfirmation detection ≥5, Proven scale ≥8, Ecosystem integrations ≥6, Acquisition & parsing validation ≥6, Defensibility of AI output ≥6, Vendor viability & support ≥6
- **Loupe:** fit **72%**, core met 13/23, rank **14 of 47**, gates failed: **none**
- **Platforms clearing every gate:** 23 of 47

| Fit | Platform | Core met | Entry price | Gate status |
|---|---|---|---|---|
| 90% | Palantir Gotham / AIP | 18/23 | $300k+ | clears all gates |
| 83% | Magnet Axiom / Magnet One | 15/23 | $50–300k | clears all gates |
| 81% | Cognyte NEXYTE | 13/23 | $300k+ | clears all gates |
| 80% | Cellebrite Guardian Investigate | 15/23 | $50–300k | clears all gates |
| 79% | Exterro FTK / ARMOUR | 12/23 | $10–50k | clears all gates |
| 76% | Nuix Neo | 11/23 | $300k+ | clears all gates |
| 75% | Everlaw | 14/23 | $50–300k | **fails:** Deployment control |
| 74% | NICE Investigate | 11/23 | $50–300k | clears all gates |
| 74% | DataWalk | 9/23 | $300k+ | clears all gates |
| 74% | Hubstream | 8/23 | $50–300k | clears all gates |
| 72% | **Loupe** | 13/23 | $10–50k | clears all gates |