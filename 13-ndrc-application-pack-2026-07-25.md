# NDRC Application Pack — Loupe

Prepared 25 July 2026. Companion to `09-gtm-research-pack`, `10-ceo-operating-plan`,
`11-platform-capability-audit`, and the 25 July accelerator brief.

**Programme:** NDRC Rolling Investment — €100k uncapped SAFE, Dogpatch Labs Dublin,
12 months free desk space, 40+ mentors, EIR access, global demo day. Rolling
applications, no deadline.

**Critical structural fact:** the application form has no essay questions. It collects
name, email, phone, LinkedIn, county, gender identity, co-founder details, fundraising
status, a website URL and **a PDF pitch deck**. The deck carries 100% of the
application. Nothing in this repo is read unless it is in the deck.

**Verified against the live form at `accelerator.ndrc.ie/apply` on 29 July 2026.** The
only stated deck requirement is *"Please upload pitch deck. Format: PDF."* — **no slide
count, no page limit, no required sections.** Deck length is therefore an editorial
decision, not a constraint; make it as long as it needs to be and no longer. Terms
confirmed: **€100,000 through a founder-friendly, uncapped SAFE**, for "early-stage,
globally scalable tech startups", with investment available "as early as formation".
Rolling — no deadline visible on the form.

---

## Part 1 — Form answers (the trivial part)

| Field | Answer |
|---|---|
| First / Last name | Neil Byrne |
| Startup name | Loupe |
| Email / Telephone | *(fill)* |
| Pitch deck | Part 2 of this doc, exported to PDF |
| Website | *(live Loupe site URL)* |
| Has the startup raised investment? | **No** |
| LinkedIn | *(fill)* |
| County | Dublin *(confirm which — affects LEO too)* |
| Co-founders? | **Yes — 2** |
| Co-founder 1 | Conor Bowles — CTO — email, LinkedIn, county |
| Co-founder 2 | Alexandra Solórzano — CPO — email, LinkedIn — **"Not based on Island of Ireland"** |
| Gender identity | Woman · Man · Non-binary · Prefer not to say · Other — *asked of the applicant; decide and move on* |

Note on the last row: selecting the non-Ireland option for Alex is correct and honest.
Pre-empt it on the team slide rather than letting it surface as a surprise — the
company is Irish, the IP is Irish-owned, the engineering is Dublin-based, and the
US-based founder is the domain expert and design partner. That is a strength, not a
flag, provided you say it first.

---

## Part 2 — The deck, slide by slide

**Ten slides.** Every product claim below traces to code on
`integration/evidence-main-reunion` unless marked **[ROADMAP]**. Claims-safety notes
are drawn from the "Claims to avoid" list — honour them.

**Slide 7 is the growth path**, added 29 July and built into `build_deck.py` as
`slide6b()`. It sits between Market and Team because a market slide that states a
pool without stating what share of it the plan needs invites the question rather
than answering it.

---

### Slide 1 — Title

> **Loupe**
> Find the signal in everything.
>
> An investigation platform for fraud and criminal casework.
> Dublin, Ireland.

Speaker note: one line only. Do not open with the product.

---

### Slide 2 — The problem

> **Modern casework is a data problem wearing a legal costume.**
>
> A single serious-fraud or criminal case now arrives as:
> - thousands of documents
> - multi-gigabyte phone extractions, hundreds of thousands of events
> - bank records spanning tens of thousands of transactions
> - hours of recorded audio
>
> The tools investigators have are **viewers**. One phone at a time. One PDF at a
> time. One spreadsheet at a time.
>
> The connections — the same person in a witness statement, a WhatsApp thread and a
> beneficiary field; the meeting two streets from the cash withdrawal — live in
> investigators' heads and on whiteboards.
>
> **They don't scale, they don't survive staff turnover, and they can't be handed to
> a court.**
>
> ---
>
> **We didn't start with a product idea. We started with a case we couldn't work.**
>
> Between us we have seen this problem from both sides: seven years building
> investigative-intelligence software for enterprise buyers, and a decade running
> federal casework as an investigator using it.
>
> When our CPO needed a platform for live federal casework, we went looking for one.
> We evaluated an existing investigative intelligence platform against a real case. It
> could not work the case the way a real investigation needs.
>
> **We tried to buy this. Building it was the second choice, not the first.**

Speaker note: **this is your origin story and it is a strong one.** "We tried to buy
it, it failed on a live case, so we built it" is behavioural evidence of a market gap.
It outranks any number of stated-preference interviews, and investors know it.

What makes it work is that you have seen the category from both sides — vendor and
user. That is what turns "a platform didn't fit" from an anecdote into a judgement
about how this market is built.

**Deliberately not said here:** anything about what you personally built for a former
employer's customers, or any suggestion that Loupe derives from it. Your CV stands on
its own on slide 7. Linking the product back to work done under someone else's
employment creates a question you do not want asked, and it buys you nothing the
"we tried to buy it and it failed" beat doesn't already deliver. Keep that separation
everywhere.

Judgement calls, and the third one is the important one:

- **Name Octostar or not.** Naming is more credible and specific; vagueness gets
  discounted. But only name it if you are ready for the follow-up. A sharp partner
  *will* ask what specifically failed. "It just didn't work" would damage you. If you
  can say "it couldn't hold multi-device phone extractions and document evidence in one
  model, so she couldn't see X" — name it. If not, use "a leading investigative
  intelligence platform" and give the specifics verbally.
- **Have the specific failure mode ready either way.** This is the single most
  likely follow-up question in the whole meeting. Write the answer down before you
  present.
- **Never let Siren be the platform that failed.** The failed evaluation on slide 2 is
  a *different* platform, and that distinction matters — keep it unambiguous, in the
  deck and out loud. Siren is Irish, Enterprise Ireland-backed, and Dublin is small;
  there is a live chance someone in the NDRC room knows the founders. When Siren comes
  up, it is a credential and a compliment: it is very good at what it is built for —
  enterprise law-enforcement and intelligence buyers, who arrive with budget for
  configuration and support. That is the right model for that market. It simply
  doesn't reach a 15-person PI firm. **You are not competing with Siren and you are
  not criticising it. You are serving a tier its model was never aimed at.** Warmth
  about a former employer reads as confidence; anything else reads as a risk.

---

### Slide 3 — Why now

> **Three curves crossed.**
>
> 1. **Digital evidence volume exploded.** A phone extraction now appears in nearly
>    every case.
> 2. **LLMs became good enough** to read evidence at scale.
> 3. **Bare LLMs remain unusable in evidence work** — no provenance, no audit, no
>    confidentiality.
>
> The gap between (2) and (3) is exactly where Loupe sits: **the trust layer that
> makes AI admissible in investigative work.**
>
> Supporting signal: only ~25% of anti-fraud programmes use AI/ML today — and only
> **~6% of fraud examiners are confident explaining how their AI reaches its
> conclusions.** *(ACFE 2026 anti-fraud technology benchmarking)*

Speaker note: the 6% stat is the strongest number in your material. The entire product
is an answer to it. Say it, pause, then move to slide 4 and show the answer.

---

### Slide 4 — Product

Two screenshots only. Resist the feature list.

> **Left:** a Loupe — five highlighted passages from three documents, bound into one
> evidenced narrative timeline.
>
> **Right:** an AI answer with a citation, mid-click, opening the source document at
> the cited page.
>
> **Caption:** Evidence in. One connected model out. Every fact carries the verbatim
> quote, source location and confidence it rests on.
>
> Ingest → Ground → Connect → Explore → Prove

Speaker note: the right-hand screenshot is the whole pitch. An investor who
understands that one click understands the company. Rehearse it as a live demo if
you get a meeting.

**Capture the right-hand shot with the result graph visible.** The 25 July brief notes
that AI chat now returns *"a result graph and result set alongside the text"* — so the
citation click and the structured result appear in one frame. That is a materially
better screenshot than prose-plus-citation, because it shows the answer being **grounded
and structured at the same time**, which is the whole differentiation argument in a
single image. It also keeps the graph in the deck where it belongs: as a *result*, not
as a landing page.

**Do not lead with the case graph.** This changed, and the reason is the same reason
the product's default view is changing: a case that opens on ten thousand nodes is
overwhelming to an investigator, and it is illegible on a projected slide. Three
specific problems with a graph as the hero image:

- **It is the category's most clichéd picture.** Palantir, i2, Siren, Linkurious all
  lead with it. It says "we are in this category" at exactly the moment slides 5 and 6
  are arguing you are serving a tier the category does not reach. In a Dublin room
  where someone may have seen a Siren deck, it invites the comparison you spend two
  slides declining.
- **Nobody parses it.** A reader registers "graph product" and moves on. That is the
  entire return on the most valuable image in the deck.
- **It shows connection a machine inferred, not judgment a person applied** — which is
  the weaker half of your argument.

**A Loupe does the same job better.** It is legible in three seconds because a timeline
reads left to right. It shows evidence from multiple sources bound deliberately, which
is the **Human judgment** row on slide 5 and your actual defensibility argument. And no
competitor's deck has this picture. It also makes the slide internally coherent — the
caption already names Loupes; showing a graph underneath it is a mismatch.

**Screenshot whatever the product actually opens on.** If a partner gets a live demo
and the app opens somewhere other than what slide 4 showed, that is a small, free
credibility scratch. Let the default-view decision drive the screenshot, not the
reverse. ✅ **Settled by the 25 July brief**, which now says the workspace *"meets
investigators where casework actually starts — in the evidence and the day's work — with
the analytical lenses one click away. Depth is there when you reach for it, never dumped
on you when you open the door."* That is the right decision and it is also a good line;
it belongs in the verbal answer, not on the slide.

**Keep the graph — move it to the demo and to the answer.** It is what says "real
infrastructure, not a chat wrapper," and you will want it when a technical partner asks
what is underneath. It should not be the first thing a reader sees.

**And the default-view decision is itself pitch material.** *"We moved the default off
the graph because opening a case on ten thousand nodes is what every tool in this
category does, and it is useless to a working investigator."* That is small, concrete
evidence for slide 6's claim that every feature came from a real investigator on a live
case — a claim currently asserted rather than shown. Keep it in your pocket for the
meeting.

**One line to add under the caption:**

> Investigators highlight what matters and bind it into **Loupes** — evidenced
> collections that carry the narrative, not just the extraction.

Worth the space. It pre-empts "isn't this just an extraction pipeline?" before slide 5
has to argue it, and it sets up the **Human judgment** row that follows.

**Name the Loupe, and name it here.** The product is named after its core curation
object — a bonded collection of documents, highlighted passages, entities and events
with its own identity and description, bound together to explain an event, a sequence
or a thing. That is not a feature detail; it is the reason the company is called what
it is, and it is the thing a competitor cannot copy by improving their extraction. A
deck that never explains its own name leaves the strongest structural idea on the
table.

Keep it to one line on the slide. The full highlights-and-Loupes story is a demo, and
it is a good one: highlight five sentences across three documents, bind them into a
Loupe, and you have a fully evidenced narrative viewable as a timeline or a graph. If
you get to demo anything beyond the citation click, demo this.

---

### Slide 5 — Why this isn't ChatGPT with files

Cut your comparison table to five rows. These five:

| | A straight LLM | Loupe |
|---|---|---|
| **Where the case lives** | A context window, forgotten after | A persistent case knowledge graph — outlives every conversation |
| **Scale** | Hundreds of pages at best | Entire corpora: thousands of documents, multi-gigabyte phone reports |
| **What the AI does** | Answers in prose, one conversation at a time | **Cites every claim** to the exact page — and **runs tools on the case model:** builds Loupes, groupings and outputs from plain instruction |
| **Confidentiality** | Multi-tenant cloud | Single-tenant: evidence never leaves the customer's instance |
| **Human judgment** | Lives outside the tool — lost between sessions | Highlights, significance and **Loupes** — bonded collections of evidence, like custom narrative timelines — are **durable objects in the case model.** The investigator's thinking is stored, not retyped |
| **Model dependence** | The model *is* the product | Models are interchangeable components. **The moat is the evidence layer.** |

The **Human judgment** row is new, from the 25 July brief, and it earns its place —
take six rows rather than cut it. It is the only row that answers the question a
technical investor will actually be holding: *what stops Microsoft GraphRAG
commoditising this in eighteen months?* Extraction pipelines will commoditise.
**A durable, evidenced record of what an investigator decided mattered, and why, does
not** — it accrues per customer, per case, and it is worthless to a competitor. That
is your defensibility argument, and it was missing from every earlier version of this
material.

**The Agent was badly under-represented, and the "What the AI does" row is where it
gets fixed.** Before this revision the pack mentioned the AI layer's agency exactly
once, in a Part 3 block, and what it said was *"read-only, case-scoped, cost-metered"*
— a sentence that argues the AI is **safe**, not that it is **capable.** Every other
reference framed Loupe's AI as question-answering over evidence. That framing sells a
search product.

**An agent that runs tools is a different category of thing, and the difference maps
directly onto how your buyer already thinks.** The ex-FBI prospect was explicit that
she was not buying a tool for herself — she was asking whether it makes her **junior
investigators** effective, and benchmarking price against **the cost of a junior
investigator or overseas staff.** That is a labour-substitution purchase. A question-
answering box does not substitute for labour; something that builds the query, the
grouping, the visualisation and the draft output does. The agent is the part of the
product that matches the sale you are actually making, and it was invisible. Same for
the **pre-engagement triage** wedge on slide 6 — *"here are 400 pages from a prospect,
tell me whether to take this matter"* is an agent task producing an artifact, not a
chat turn.

**The strongest version of this claim is not "it runs tools" — it is that the unit of
work stops being a query and becomes a hypothesis.** The agent builds *Loupes* from
plain instruction. That matters more than any single tool in the list, for two reasons.
First, it **closes a loop the deck already opens**: slide 4 introduces the Loupe as the
namesake object and the durable container for human judgment; slide 5 can now say that
object is producible by instruction. The moat argument and the agent argument stop being
two separate claims and become one. Second, it changes what the investigator is doing.
They do not arrive at a search box with a question. They arrive at a blank page and
start building the scenarios they need to test — *did this company receive money before
the contract was signed; who was in contact in the fortnight before the transfer* — and
the agent assembles the evidence for each one, **or shows them it isn't there.** That is
how investigators actually think, and no competitor describes their product that way.

> An investigator doesn't have questions, they have theories. Loupe is the first tool
> where the unit of work is a hypothesis rather than a query: you describe the scenario
> you want to test, and the agent builds the Loupe that proves or breaks it.

**Two things to be careful with here.** *"Show me all companies"* is a saved view, not a
hypothesis — it is the weakest available example and it makes the capability sound like
faceted search. Lead with a scenario that has a theory inside it. And the hypothesis
framing carries a specific risk in a legal market: an investigator who states a theory
and has a machine populate it is doing **confirmation bias at speed**, and opposing
counsel will say exactly that. The defence against it is not a disclaimer — it is that
the same agent can be pointed at *disconfirmation*. See the tool note below.

**Three cautions, and the third one decides how you say any of it.**

- **"Tools can do anything we can imagine" is true in engineering and fatal in a
  pitch.** Unbounded capability reads as unfocused, and investors discount it to zero.
  Name two or three concrete outputs a forensic investigator would recognise — a
  transaction grouping, a generated timeline, a drafted exhibit summary — and stop.
  Specific beats expansive every time.
- **It collides with your own Model dependence row unless you frame it carefully.** If
  the deck leans on agent capability, a sharp reader asks: isn't the agent just the
  model, and therefore the thing that commoditises? **The answer is that the tools are
  the moat, not the agent.** A generic agent pointed at a folder of PDFs produces
  confident garbage. The same agent pointed at a grounded claims ledger, a provenance-
  carrying case graph and a set of Loupes produces work you can check. The agent is
  interchangeable; **what it can reach is not.** Say it in those words — it strengthens
  the moat argument rather than undercutting it.
- **The courtroom question is the one that matters, and you should answer it before it
  is asked.** Your market is criminal defence and forensic accounting. The instant you
  say "agent that does the work," a domain-aware listener thinks: *what happens when it
  is wrong, and who signs their name to it?* That is the same question the ~6% ACFE
  stat on slide 3 is about. So do not pitch autonomy — **pitch bounded agency:**

> The agent can run tools across the case, but it cannot invent a fact. Everything it
> produces is built from grounded claims that carry their source, and nothing leaves
> the system without a human verifying it. It does the work a junior would do, and it
> shows you exactly where every piece of it came from.

That is a stronger position than either "read-only Q&A" or "autonomous agent," because
it is the only one that survives the question your buyer is actually holding.

---

### ⚠️ The hypothesis-workbench claims — read this before pasting anything

The 25 July brief's **"The hypothesis workbench"** now describes four capabilities in the
present tense: *assemble the scenario* (agent builds a Loupe from plain language), *hunt
what breaks it* (disconfirmation), *find what isn't there* (gap enumeration), and
*hypotheses that stay open* (standing re-evaluation as new disclosure lands).

**Three of those four originated as my roadmap suggestions in this pack, one revision
ago, written as "worth building first."** Neil has confirmed they are **scheduled to be
built before the application goes in**, so the question is no longer *are these true* —
it is **are they true by the date you need them to be.** That distinction matters more
than it sounds, because these are the **highest-exposure sentences in the application**,
for reasons that have nothing to do with whether they are true today:

- **They are the most vivid, specific and memorable claims in the document.** *"Two of
  your five supporting passages are now contradicted by the latest disclosure bundle"*
  is exactly the line a partner repeats back to you, and exactly the line they ask to
  see. Vague claims get skimmed. That one gets tested.
- **They are the differentiators.** Every other capability in the brief has a plausible
  competitor analogue. These four do not — which is precisely why they draw scrutiny,
  and why being unable to demo one costs more than never having claimed it.
- **They are unverifiable from outside and trivially verifiable in a demo.** The worst
  possible combination. Nobody can check them in diligence, and everybody can check
  them in ten minutes on a screen share.

**The test, per capability, is one question: has this run on a real case?** Not "is the
architecture there," not "could the agent do this if prompted well" — has an
investigator used it and got a usable result. Sort the four into:

| | Meaning | What you may do with it |
|---|---|---|
| **Shipped** | Has run on real casework, would survive a live demo | Say it in present tense, demo it, lead with it |
| **Works, unrehearsed** | Exists, has not been used in anger | Say it, keep it out of the live demo, never volunteer it as the example |
| **Building** | Committed and dated, not finished | Fine to build toward — but it does not go in the deck until it demos |

**The rule now is a date, not a cut.** Since these are being built ahead of the
application, the discipline is simply: **nothing enters the deck or a paste block until
it has demoed clean once.** Build first, claim second — never the reverse. Anything still
in the third row on the day you submit gets pulled from the material that day, without
argument, and becomes the roadmap answer instead: *"that's where the tool model takes us
next."* That is blocker 5g.

**The good news, and it is substantial:** the brief's agent section now names a *real,
checkable toolbox* — case overview, graph entity search and schema inspection, entity
details and neighbourhoods, pathfinding, full-text document search, timeline events,
financial records, map locations, and safe read-only Cypher for grouping and
aggregation. That list is specific, plainly built, and it does the job the vague version
could not. **If the hypothesis-workbench claims have to be pulled back, the toolbox
survives and the pitch still works** — because the argument was never "the agent is
magic," it was "the agent can reach things a chatbot cannot."

**Also adopted from the brief, and worth keeping:** *"The ceiling is the toolbox — and
the toolbox grows. Every new platform surface becomes something the agent can wield. The
agent compounds with the product."* That is a better answer to the commoditisation
question than the one this pack had — it says the agent's value is a function of the
platform's surface area, which is the thing competitors cannot copy quickly.

**Beyond the four**, the obvious next tools are entity resolution across alias variants
(partly there already), flow-of-funds tracing and structuring detection over the ledger,
communications-pattern analysis on Cellebrite data (first contact, burst, silence), and
corroboration scoring across independent sources. Useful, mostly table stakes, and safe
to describe as roadmap.

> **One sentence:** A straight LLM gives you a well-written opinion about the fraction
> of the evidence that fits in its context window. Loupe gives you a complete,
> permanent, cross-referenced model of all of it — where every claim carries its
> receipt.

Speaker note — **the objection you will actually get in the market is not from
investors, it's from buyers, and it is: "can't I just do this with a $20 Claude
subscription?"** You have heard it directly. Have the answer rehearsed, because the
honest version is also the strong version:

> A $20 subscription reads what fits in one conversation and forgets it. It cannot
> hold a 35GB phone extraction, it has no persistent case model, it gives you prose
> instead of citations, and it puts privileged evidence on a multi-tenant service.
> The reason a case costs real money to process is the same reason the answer is
> trustworthy: we read **everything**, not a sample.

That last line converts your cost structure from a weakness into the proof of the
claim. Use it. (See the pricing note on slide 9 — the AI-processing cost model is a
live open item, not a solved one.)

---

### Slide 6 — Market and lead customer

> **Every feature in Loupe was requested by a working investigator on a live case.**
>
> Our CPO is our design partner. Development has been customer-led from the first
> commit — not a roadmap we invented and then validated, but a backlog generated by
> real federal casework. Cases have been worked to completion in the platform, and
> **three attorneys on those cases have been given access to it.**
>
> **Why this tier is empty — and stays empty.**
>
> Enterprise investigative-intelligence platforms are sold with configuration and
> support attached. That is the right model for their buyers: agencies and large
> institutions arrive with budget, procurement and implementation resource.
>
> The tier below has the same casework complexity and the same evidence volumes — and
> none of that budget. **Loupe is built for it directly: usable out of the box, by a
> practice with no implementation resource at all.**
>
> **Beachhead:** boutique forensic and criminal-defence practices — 10–50 people,
> Big-Four-class casework without Big-Four tooling budgets.
>
> **Expansion:** financial-crime & fraud units · law enforcement & prosecutors · law
> firms & disputes teams · corporate investigations & compliance.
>
> **Channel — this buyer is organised and reachable.** ACFE has ~95k members and ~60k
> CFEs worldwide, with chapters, conferences and directories, including an Ireland
> chapter since 2016. The defence bar is the same shape: a competitor reached national
> presence through a national association and one state bar.
>
> **Why we know the gap is real.** We tried a number of platforms on live federal
> casework before we built anything. None of them could work the case.

Add to this slide, as the closing line:

> **We did not set out to build a platform. We went looking for one, tried several,
> and none could work the case.**

**Two deliberate changes, made 29 July.** *Reachable* became **Channel**, because ACFE
membership is a distribution fact rather than a market-size one and it answers a
question the growth slide does not — how these buyers are reached. And the **Harvey
adjacent-validation line was removed**: market weight is now carried by slide 7's own
numbers, and naming Harvey on a slide invites two bad reactions in a room — *"so why
aren't you Harvey?"* and *"Harvey will crush you."* Neither is true. Harvey scores 127
in the study, is priced for the AmLaw 100 with seat minimums near $360k a year, and has
no evidence model at all. **That is an excellent answer in the meeting if asked, and a
liability volunteered on a slide.**

**On the origin story — say "a number of platforms", never name one.** The evaluation
was plural, which is both more accurate and safer: naming a single vendor turns a
systematic evaluation into what sounds like a grievance, and that is a scored negative
(see blocker 5d). The plural version is also the stronger claim, because it is exactly
what the structural finding predicts — the field splits into platforms that model
evidence but will not sell to a defence practice, and platforms that serve this buyer
but treat a phone extraction as an attachment. Trying several and finding none fit is
the expected outcome, not bad luck.

**A second use case surfaced in discovery — and it may be the better wedge.**

A PI-firm CEO (ex-FBI, Tampa Bay, clients across Miami, New York, California and the
Midwest) described her sharpest pain as something upstream of casework entirely:
**pre-engagement triage.** She gives free 15-minute consultations, receives large
document sets from prospective clients, and has to decide whether to take the matter
and produce a proposal — without burning senior hours reading it all. She also
described being handed 15 audio recordings and needing a summary.

Strategically this is worth noticing, because the triage use case:

- sits on **prospect intake material, not privileged case evidence** — so it can be
  sold *before* the 12-stage security gate closes, not after
- has an obvious ROI denominator: the senior hours it replaces
- is a natural front door into the same firm's casework once trust is established

It also reframes the buyer. She was explicit that she was not buying a tool for
herself — she was asking whether it makes her **junior investigators** effective, and
benchmarking the price directly against **the cost of a junior investigator or
overseas staff.** That is a labour-substitution sale, not a software-features sale.

**What genuinely remains open.**

Between seven years at Siren (hundreds of analysts, bespoke solutions per customer)
and a founding investigator running federal cases, *what to build* and *how this
market behaves* are answered. Siren's buyers, though, were **enterprise
law-enforcement and intelligence** — big-ticket, procurement-led, long cycle. The
boutique tier buys completely differently, and discovery has now confirmed the shape
of that difference without yet producing a number:

> **What does a 10–50 person forensic or defence practice actually pay, and through
> what mechanism — per-matter passed through to the client, or a per-seat licence?**

The honest state of that question: the ex-FBI prospect **declined to name a price
before using the product** — *"I would have to use it before I could answer that
appropriately"* — which is a normal and reasonable position, and it means the answer
comes from a pilot, not from an interview. She is aware of the ~$25k/licence reference
point in the market and is open to a mutual MSA at low cost and low risk. Other
anchors to test: Valid8 ~$42k/yr, CaseWare IDEA licences.

Downstream of that answer sits the lead-edition choice (P1 forensic accounting, which
prices best, vs P2 criminal defence, which is most complete in code).

**Implication for the plan: the pricing question is closed by running a paid pilot,
not by booking more calls.** That is a better answer than the one this document
carried a week ago, and it lines up exactly with the €100k ask on slide 9.

Market sizing below is desk research, not primary — label it as such on the slide.
Global forensic accounting ~$18–20B, US ~$10.5B, highly fragmented.

---

### Slide 7 — Growth path

> **Ten million in ARR is 104 firms and under 2% of one market.**
>
> Priced at a blended **$12,000 per matter**. A boutique running eight evidence-heavy
> matters a year is worth $96,000 annually; an active practice at twenty is worth
> $240,000. These figures use the conservative rate throughout.
>
> | | **1 · Proof**<br>Owl & Ireland | **2 · Engine**<br>United States | **3 · Second geography**<br>+ UK | **4 · Expansion**<br>+ Europe |
> |---|---|---|---|---|
> | **ARR** | **$0.5M** | **$5M** | **$10M** | **$25M** |
> | Customers | 5 | 52 | 104 | 260 |
> | Matters / yr | 42 | 417 | 833 | 2,083 |
> | Share of US pool | — | 0.3–0.9% | 0.7–1.7% | 1.7–4.3% |
>
> Stage 1 produces references and a validated price. Stage 2 is the business —
> 48,000–125,000 evidence-heavy matters a year carrying $1.0–7.5B of displaceable
> spend, reached through the defence bar. Stage 3 adds the UK: ~80,200 open Crown
> Court cases rising toward 104,500 by 2029, same buyer shape, same channel, with a
> funded government backlog behind it. Stage 4 is partner-led across Europe on a
> deployment-control advantage that is a procurement requirement under GDPR.

**Speaker note.** The point is the middle two rows, not the ARR. None of these stages
asks for market dominance against a target population of one to five thousand
practices — they ask for a channel that works and a price that holds. Each is gated on
exactly one thing: stage 1 a validated price from real matters, stage 2 the bar channel
converting, stage 3 the per-matter model rebuilt on UK vendor and Legal Aid Agency
rates, stage 4 partners.

**If asked why stage 1 is so small:** because it is not a revenue stage and should not
be defended as one. Its output is a nameable reference and a price that survived contact
with real matters — which is what stage 2 needs to exist.

**If asked about the firm mix:** customer counts assume the conservative eight-matter
firm. At a twenty-matter active practice, $10M needs 42 firms rather than 104. The real
mix sits between the two and the first cohort establishes which — which is another
reason the pilot in slide 10 is the thing being funded.

---

### Slide 8 — Team

> **Neil Byrne — CEO.** **Seven years at Siren**, the Irish investigative-intelligence
> platform — the same category, selling to law enforcement, intelligence and
> financial-crime teams. **Solutions engineer: I managed customer accounts and built
> the customisations each client needed to make the platform fit their process.**
> Spoke with **hundreds of analysts** across conference talks and deployments. 10+
> years across data engineering, AI systems and full-stack development.
> **Full-time on close.**
>
> **Conor Bowles — CTO.** Data infrastructure, security and scalable systems. Core
> engineering, database architecture, deployment operations. **Full-time on close.**
>
> **Alexandra Solórzano — CPO.** 10+ years as a licensed private investigator on
> federal criminal defence and financial fraud casework. US-based. **The domain
> authority — and the customer the product was built for.**
>
> **Why this team:** we didn't research this market, we worked in it — **from both
> sides.** Seven years building investigative intelligence software for enterprise
> buyers, and a decade running federal casework as the kind of investigator who has to
> live with the result. Our CPO has run federal cases to completion inside this
> platform.

**The line to say out loud, and the strongest thing on this slide:** *I was the
solutions engineer. When an enterprise buys an investigative platform, it buys
configuration and support attached — and I was the person who built the customisations
that made it fit. A fifteen-person practice cannot buy me. That is why Loupe has to
work out of the box.* Slide 6 argues that the tier below has the same casework
complexity and none of the implementation budget; this is that argument in the first
person, from the person who used to be the implementation budget. It also answers the
Siren question (blocker 5d) as a compliment rather than a comparison.

**Holding item — the Udemy line.** Neil is currently a sales solutions engineer at
Udemy across large-enterprise and strategic accounts, which extends the same discipline
to a larger commercial scale and is worth one clause:

> **Currently a sales solutions engineer at Udemy across large-enterprise and strategic
> accounts** — the same discipline at enterprise scale: technical discovery, and
> building what a large customer actually needs.

**Do not add it until blocker #1 (current-employer IP review) is closed.** Naming the
current employer on the team slide walks a reader straight to "was this built on their
time?", and ~55% of commits were made while employed there. Once the waiver is in hand
it is a non-issue and the clause should go in — LinkedIn is a required form field, so
they will see Udemy regardless, and it is better framed by you than discovered by them.
Put it immediately before "Full-time on close" so the fact and its resolution land
together.

Speaker note: **lead with Siren.** It is the strongest founder-market-fit signal you
have and it was missing from every earlier version of this material. NDRC will know
Siren — Irish, Enterprise Ireland-backed, same category. It converts you from "engineer
who built a thing" to "category-native founder who has seen this market's buying
behaviour for seven years." It also pre-answers the sales-cycle and procurement
questions before they're asked.

"Full-time on close" appears twice on purpose. Say it out loud as well as printing it.

Do not hide Alex being US-based. Address it in one line: the company is Irish, the IP
is Irish-owned, engineering is in Dublin, and the market is US-first — which is why
the domain founder is where the customers are.

---

### Slide 9 — Status and traction

**Lead with the fact, not the caveat. Loupe is a working platform that has done the
job.** Everything else on this slide is context for that sentence.

> **Loupe is in production use on real federal casework.**
>
> Built inside **Owl Consultancy**, a working US private-investigations practice, and
> used there to carry federal cases **to completion** — multi-gigabyte phone
> extractions, tens of thousands of curated financial transactions, full document
> corpora. **Three attorneys on those cases have been given access to it.** Attorneys
> have retained the practice specifically because of the platform — unprompted, before
> any marketing existed.
>
> This is not a prototype seeking a first user. It is **an application that works,
> in the hands of the investigators it was built for, on cases with real stakes.**
>
> **First external pilot in motion.** A US private-investigations firm led by a
> **former FBI undercover agent** — clients across Miami, New York, California and the
> Midwest — has agreed to send its **next large-document matter** through Loupe as a
> paid trial at cost, and to put a mutual MSA in front of us. Sourced through
> casework, not marketing.
>
> **What that means:** this is a **design-partner-validated spinout** — a product
> built feature-by-feature against live federal casework, proven in the practice it
> was built in, now being taken to firms beyond it.
>
> **Built so far, verifiable:**
> - ~180,000 lines across a React console, a FastAPI case API and a separate
>   asynchronous evidence engine
> - 913 commits since December 2025 — 7.5 months, two primary engineers
> - Neo4j (case graph) · Postgres (cases, auth, audit) · ChromaDB (retrieval) ·
>   Redis (job orchestration)
> - Three AI providers behind one routing policy — the model is a swappable component
> - Single-tenant deployment: one isolated stack per customer
>
> **Release discipline:** onboarding an external customer's evidence runs behind a
> **12-stage security-gated release plan.** **No external case data enters the
> platform until the security, isolation, backup and legal stages pass.**
>
> **Roadmap:** a 13-epic, 265-ticket board takes Loupe from a platform that works for
> the practice it was built in to one that scales across many. Depth, not existence.

Speaker note — **two beats, in this order, and do not invert them.**

**First: it works.** Cases closed, attorneys using it, a practice winning business
because of it. That is a further-along position than most of what NDRC will see this
year, and it should be the first thing out of your mouth on this slide.

**Second: the security gate.** No external customer's evidence enters until the
isolation, backup and legal stages pass. Most pre-seed teams cannot demonstrate
release discipline at all — give it its own beat, and frame it as *why the external
pilot hasn't started yet*, which turns a delay into evidence of seriousness.

**On the roadmap: mention it, don't dwell on it.** It is a statement of ambition —
what it takes to go from *works for one practice* to *works for many*. It is not a
list of things Loupe cannot do. If the deck spends more pixels on the roadmap than on
the working product, a reader will conclude the product is the roadmap. Two lines,
maximum, and always after the traction.

**Claims safety — a short list, and it is short deliberately.**

You know the state of your own codebase better than any external read of it does, so
these are the few where the risk isn't *whether it works* but *whether you can produce
the artifact when someone says "show me."*

- ❌ The ex-FBI PI firm as a **signed** customer, an LOI, or a pipeline value. Nothing
  is signed. What is true and sufficient: an agreed next case, an at-cost trial, and an
  MSA to be exchanged. Say exactly that. If it converts before you submit, upgrade the
  line — until then, under-claim it. **This is the only hard prohibition on the slide.**
- ⚠️ **"WCAG 2.1 AA compliant" and "verified against a 571k-node corpus."** Both fine
  if evidenced — have the audit result and the load-test output to hand. They are the
  two most likely to draw a *show me*, because they are the two a technical partner can
  ask about without knowing your domain.
- ✅ **Scale figures — largely closed by the 25 July brief,** which now labels the
  10k-entity / 50k-transaction / 35GB-phone-report numbers as *"platform design
  capacities, validated against production-scale test corpora."* That is exactly the
  right disclosure. Carry the label with the numbers wherever they go. The corollary:
  **they are targets, not case results** — so never let them stand next to the real
  casework figures without the distinction. The real ones (multi-gigabyte extractions,
  10k+ curated transactions) are the stronger claim anyway, because they happened.
- ⚠️ **"Human-verified facts."** Prefer "verification workflow." A slightly narrower
  claim, and it avoids implying an external verifier.
- ⚠️ **CI.** `.github/workflows` is absent from the branch I inspected. If CI runs
  elsewhere, ignore this. If it doesn't, don't claim "hard-gating CI on every pull
  request" — and consider standing it up, because it's hours of work and the deck leans
  on release discipline. This is the one gap worth closing rather than wording around.

> **The framing rule for the whole deck:** Loupe is one product, and it works. Do not
> write a sentence that invites a reader to wonder whether the thing that ran federal
> cases is the same thing you are pitching. It is. Earlier drafts of this pack split it
> into "v1" and "v2" as a caution against overclaiming, and that framing was wrong: it
> converted a shipped, case-proven platform into something that sounded like an alpha.
> If a distinction genuinely matters in the room — an older deployment versus the
> current hardened one — draw it verbally, once, in answer to a direct question. Never
> in the deck.

---

### Slide 10 — The ask

> **€100k. What it buys: the first paying customer outside the practice that built it.**
>
> The platform works and has closed real federal cases. What stands between it and
> external revenue is the **security gate** — the isolation, backup and legal stages
> that let another firm's privileged evidence enter the system — and the pilot itself.
>
> **Use of funds:** two founders full-time, clearing those gates, and running the
> agreed pilot to a signed contract. **The pilot candidate is already secured.**
>
> **What we want from NDRC beyond capital:** Dublin base at Dogpatch, EIR time on
> pricing and enterprise sales motion, and introductions into Irish and UK
> professional-services buyers — ACFE Ireland, Chartered Accountants Ireland forensic
> group, Law Society criminal law committee.

Speaker note — **do not put an hours figure on this slide, and do not pre-empt an
arithmetic problem you don't have.**

An earlier draft of this pack led with "~4,200 estimated hours" and then spent a
paragraph explaining why €100k doesn't cover it. That was a mistake twice over: the
estimate is inflated, and volunteering a number that makes your ask look inadequate
invites a problem nobody in the room had. Cut it.

**The correct framing of the ask, and it is a much stronger one:**

> The product works. It has closed federal cases. What we don't yet have is a customer
> outside the practice it was built in — and the reason is the security gate, not the
> software. €100k puts two founders full-time on clearing that gate and running the
> first external pilot to a signed contract.

That is a **commercialisation** raise, not a build raise. It is the easier of the two
to underwrite, and it happens to be true. You are not asking anyone to fund the
invention of a product; you are asking them to fund the distance between *works* and
*sold*.

**If the roadmap comes up — and it should, briefly:** it is the path from serving one
practice to serving many, and it is deliberately ambitious because the category
rewards depth. Present it as where the company goes, never as what the product still
lacks. If someone asks what €100k funds against a 265-ticket board, the answer is the
gate and the pilot, and the rest is sequenced behind revenue from customers you will
have by then.

**Second speaker note — the gross-margin question, and be ready for it.**

Loupe has a real variable cost per case: AI processing. Current observed order of
magnitude is roughly **$70 to ingest a 1,600-page document**. A buyer has already
asked the exact right question — *does the licence fee cover AI processing, or are
tokens billed separately?* — and it is not yet answered.

Do not hide this and do not pretend it is solved. The credible position:

> Every case carries a measurable AI processing cost. We meter it today. Whether it
> sits inside the licence or is passed through is a pricing decision we are taking
> from pilot data rather than guessing — and it is one of the questions this round
> exists to answer.

Two things make this a strength rather than a hole: (1) you **measure** it, which
most applicants at this stage cannot; (2) the cost is the direct evidence of the
product claim — the price is high because the system reads everything, which is
precisely what a $20 chat subscription does not do.

Have a rough per-case unit economic ready — cost to process a representative matter
versus the senior/junior hours it displaces. You do not need a final price. You need
to show you know the shape of the P&L.

---

## Part 3 — Ready-to-paste blocks

**One-liner**
> Loupe turns raw case evidence — documents, phone extractions, financial records,
> audio — into one connected, source-linked intelligence layer that investigators can
> explore, question and take to court.

**~50 words**
> Loupe is an investigation platform for fraud and criminal casework. It ingests every
> kind of case evidence and compiles it into a connected knowledge graph — explorable
> as a network, timeline, map and financial ledger — where AI answers questions with
> citations and every fact links back to its source page.

**~100 words** — ⚠️ **use this version, not the brief's.** The 25 July brief's ~100-word
block still ends the AI sentence with *"operates under hard guardrails — read-only,
case-scoped, cost-metered."* That was accurate before the agent existed; it now
contradicts the brief's own section 05, which describes an agent that builds durable
artifacts. A reader who meets both will conclude one of them is marketing. The version
below keeps the guardrails without the word that breaks them.
> Investigation teams drown in digital evidence: thousands of documents, multi-gigabyte
> phone extractions, tens of thousands of transactions per case. Their tools are
> viewers; the connections live in their heads. Loupe ingests everything through a
> forensic-grade pipeline and builds one case knowledge graph where every extracted
> fact carries its verbatim quote, source location and confidence. Investigators
> explore it as a graph, timeline, map, table and ledger; an agent answers with
> citations and runs tools across the case — grouping transactions, generating
> visualisations, and assembling whole evidence collections from a plain instruction —
> under hard guardrails: case-scoped, cost-metered, and unable to assert anything that
> isn't grounded in a cited source. Deployed single-tenant, so
> evidence never leaves the customer's instance. It's the layer that makes AI usable —
> and defensible — in real casework.

**Differentiation, one breath** *(from the 25 July brief — use it)*
> ChatGPT reads what fits in a prompt and gives you unsourced prose. Loupe compiles the
> entire case into permanent structure, cites every answer down to the page, bounds
> what the AI may touch, meters what it spends, and runs inside the customer's own
> instance. The model is a component; the evidence layer is the product.

**The agent, one breath** *(from the 25 July brief — better than the version this pack
carried, use the brief's)*
> An investigator doesn't have questions — they have theories. Loupe is the first tool
> where the unit of work is a hypothesis rather than a query: describe the scenario you
> want to test and the agent works the case — searching the graph and the raw document
> text, running safe read-only queries for complex grouping and aggregation — and
> assembles the Loupe that proves or breaks it, alongside durable outputs: tables,
> charts, timelines, maps, full reports. Reasoning trail visible, access read-only and
> case-scoped, cost metered per run. Question-answering AI tells you about your
> evidence; an agent with tools produces the work product.

That last sentence is the best single line in the brief. It converts the agent from a
feature into a **category distinction**, and it does it in eleven words. Use it verbally
even where the paragraph doesn't fit.

**Two more from the brief worth having ready.** *"An agent that does, not a chatbot that
answers"* — a better section title than anything in this pack. And on commoditisation:
*"The ceiling is the toolbox — and the toolbox grows. Every new platform surface becomes
something the agent can wield. The agent compounds with the product."*

**And two agent behaviours in the brief that are worth saying out loud, because they are
exactly what a defence-market buyer is listening for:** the agent **asks for
clarification with concrete options rather than guessing** when a request is ambiguous,
and **it proposes while the investigator disposes** — merges and case changes stay under
human control. Those two sentences do more to answer the courtroom question than any
amount of assurance about accuracy, because they describe a *mechanism* rather than an
intention.

**One caution on the paragraph above:** it contains the hypothesis-workbench claim
(*"assembles the Loupe that proves or breaks it"*). Do not paste it anywhere until that
claim clears the check in the slide 5 tool note and blocker 5g. If the disconfirmation
half isn't shipped, cut *"or breaks"* and the paragraph still stands.

**Say this if anyone suggests the agent is the commoditising part:** the tools are the
moat, not the agent. A generic agent pointed at a folder of PDFs produces confident
garbage. The same agent pointed at a grounded claims ledger, a provenance-carrying case
graph and a set of Loupes produces work that can be checked. The agent is
interchangeable; what it can reach is not.

**The namesake feature** *(from the 25 July brief — use it, and use it early)*
> Loupe is named for what investigators do inside it: gather evidence and examine it
> closely. A "Loupe" is the product's core curation object — a bonded collection of
> documents, highlighted passages, entities or events, with its own identity and
> description, bound together to explain an event, a sequence, or a thing. Bind five
> highlighted sentences from three documents into a Loupe and you have a fully
> evidenced narrative — viewable as a timeline, a graph, or whichever lens the question
> calls for. **And the agent assembles them from plain language: describe the scenario,
> get the bonded collection that tests it.**

This is the best material in the 25 July brief. It does three jobs at once: it explains
the company name, it makes the defensibility argument concrete, and it is the part of
the product that is hardest to describe and easiest to demo. Use it in any form long
enough to carry it.

The closing sentence is new and it is the one that ties the deck together — it makes the
namesake object and the agent **one argument instead of two.** Subject to the same check
as everything else in the workbench section: paste it only once you have confirmed the
agent can do it on a real case.

**Status** — rewritten. **Do not paste the brief's version.** ⚠️ **This is the third
revision of the brief to carry it.** The brief still describes Loupe as "the second
generation" whose first generation "ran real casework," with Loupe "rebuilding that
proven capability" — the exact framing that makes a shipped, case-proven platform read
as unfinished. It also survives in the financial section: *"10k+ hand-curated,
categorised, audited transactions from real casework on the platform's first
generation."* **Fix it at source in the brief, not just here** — every revision that
carries it is one more chance it reaches an investor by copy-paste. This pack has said
"do not paste the brief's version" for three revisions running, which protects the deck
and does nothing to the source; that is precisely why it keeps coming back.
**`14-brief-cleanup-instructions.md` is the fix** — hand it to whatever has file access
to the brief and it strips v1/v2, the read-only contradiction and the pipeline sentence
at source. Meanwhile, use this instead:
> Loupe is a working investigation platform in production use on real casework —
> multi-gigabyte phone extractions, tens of thousands of curated financial
> transactions, full document corpora — built inside a US private-investigations
> practice and used there to carry federal cases to completion. It runs single-tenant
> and hardened, behind a security-gated process for onboarding external customers'
> evidence.

**Cut before use, two things, both from the brief's own Status block:**

- *"Development runs on an in-house autonomous AI engineering pipeline that takes
  features from specification to reviewed pull request, letting a small team ship at
  multi-team pace."* See item 10 in Part 4 — this needs a decision before it goes
  anywhere near an investor.
- Any "first generation / second generation" phrasing. It also survives elsewhere in
  the brief: the financial capability list says *"10k+ hand-curated, categorised,
  audited transactions from real casework on the platform's first generation."* Say
  **"on real casework"** and stop. The transactions are real, the casework is real,
  and the generation number adds nothing except doubt.

---

## Part 4 — Blockers before submitting

Ordered by risk, not effort. Rolling applications mean there is no cost to waiting and
a high cost to applying at half strength.

| # | Blocker | Owner | Why it's blocking |
|---|---|---|---|
| 1 | **Current-employer IP review** | Neil | ~55% of commits are Neil's while employed elsewhere. If the employer has a colourable IP claim, the company cannot cleanly own its core asset and the Week-5 assignment deeds fail. Resolve at zero company value — a waiver is obtainable now and near-impossible post-funding. Irish employment solicitor. |
| 1b | **Former-employer restrictive-covenant review** | Neil | Precautionary, and cheap. The deck no longer makes any claim linking Loupe to work done at a former employer — that was the right edit and it removes most of the surface. But the underlying facts are unchanged, so bring the old contract to the same solicitor session as #1 and get a clean read on three things: **non-compete scope and duration** (same category), **customer non-solicit** (a former customer of that employer is now a co-founder), and **confidential information / know-how**. Most likely nothing — Irish non-competes are frequently unenforceable when overbroad, and time may well have run. The point is to know the answer before an investor's lawyer asks, not after. |
| 2 | **"Loupe" trademark clearance** | Neil | Incorporating and building a deck around the name. CRO CORE check **plus IPOI/EUIPO search in Class 9 and 42** — "Loupe" is a common optical term with marks in adjacent hardware/photography spaces. Cheap now, expensive after launch. |
| 3 | **Incorporate the Irish LTD** | Neil + Conor | NDRC needs an entity. Neil + Conor as directors (PPSN holders, no VIF delay); Alex's third issued shortly after while value is nominal; start her BEN2/VIF in parallel. |
| 4 | **IP assignment deeds — all three founders** | All | Company must own the IP before any investor diligence. Sign the week the cert lands; do not wait for the full SHA. |
| 5 | ~~**A per-case unit economic**~~ **— CLOSED 29 Jul, see Part 6** | Neil + Conor | *Replaces the old "2–3 pricing conversations" item — see note below.* The arithmetic now exists from published vendor rates: displaced spend of $34k–$131k per matter, hours released on top, extraction retained. You do not need a price to submit, but you must be able to answer "what does a case cost you to run, and what does it displace?" Take the ~$70/1,600-page datapoint, extrapolate to a representative matter, and set it against the junior-investigator hours it replaces. One slide's worth of arithmetic. |
| 5c | **Write down the Octostar failure mode** | Neil + Alex | The origin story is the deck's strongest beat, and "what specifically couldn't it do?" is the most likely follow-up question in the meeting. One paragraph, specific, rehearsed. Without it, naming a competitor is a liability rather than an asset. |
| 5d | **Rehearse the Siren answer in one non-defensive sentence** | Neil | You will be asked how Loupe relates to Siren, and possibly by someone who knows them. The answer is a compliment, not a comparison: *Siren is built for enterprise LE and intelligence buyers who come with solutions engineering attached, and it is good at that. A 15-person PI firm cannot buy the engineer — that tier is what we serve.* Anything that sounds like a grievance, or like you left with something, is a scored negative. |
| 5e | **Re-estimate the roadmap, and decide what to publish** | Neil + Conor | The ~4,200-hour figure is inflated and it was doing real damage — it made a working product look like a year of unbuilt work. Two decisions: (a) get an honest number for **the security-gate work that unblocks the first external customer**, which is the only estimate slide 9 needs; (b) decide whether the full-roadmap hours appear anywhere at all. Recommendation: they don't. Show the 13 epics as ambition and scope, without an hours total. Nobody asks for one, and volunteering it only ever creates arithmetic that works against you. |
| 5f | **Separate built from planned in the capability brief** | Neil + Conor | The 25 July brief's "full capability surface" reads as one continuous list of what Loupe does — but it visibly blends shipped capability with the 12-stage release plan. "Hard-gating CI on every pull request" sits in it, and `.github/workflows` was absent from the branch inspected. So do "rehearsed six-service incident runbooks," "Terraform per-customer provisioning," "two-person deletion," "counsel review" of the legal package. On a marketing site that is survivable. In an investor application it is the single most likely way to get caught, because the items easiest to verify are the ones written in the future tense everywhere else in your own documents. **Mark each line built / in progress / planned before any of it is pasted anywhere.** This is an hour with the epic board open, and it protects every other claim in the pack. **Neil has confirmed the outstanding codebase items land before submission** — which is the right answer and removes most of this. It does not remove the marking exercise: the brief is the source every future deck is generated from, so the status markers need to exist in it, and be cleared as each item lands. See `14-brief-cleanup-instructions.md` §4 for the convention. |
| 5g | **Land the four hypothesis-workbench capabilities before submission — and hold the claims until each one demos** | Neil + Conor | The 25 July brief's **"hypothesis workbench"** states four things in the present tense: the agent **assembles a Loupe from a plain-language scenario**; it **hunts the evidence that breaks the theory**; it **enumerates what is missing** from the production; and **standing hypotheses re-evaluate as new disclosure lands.** Three of those four entered this material one revision ago as *roadmap suggestions*. **Neil has confirmed these are being built before the application goes in**, which converts this from a claims risk into a delivery item — but the discipline stays the same, because these are the most specific, quotable and differentiating claims in the whole application, and therefore the ones a partner asks to see. **One rule: nothing goes into the deck or a paste block until it has demoed clean once.** Build first, claim second. Do a final pass the day you submit and pull anything that hasn't demoed — it becomes the roadmap answer instead, at no cost, because the fallback is strong: the brief's *actual* toolbox — case overview, graph entity search, schema inspection, entity details and neighbourhoods, pathfinding, full-text document search, timeline events, financial records, map locations, safe read-only Cypher — is specific, plainly built, and carries the pitch on its own. |
| 6 | **Build and export the deck** | Neil | Part 2 above. **Done** — `Loupe-NDRC-deck.pptx` and `Loupe-NDRC-deck.pdf`, nine slides with speaker notes, generated by `build_deck.py`. Slide 4 still carries two empty screenshot placeholders; those are the remaining work — and the left one is now specified as **a Loupe, not the case graph.** |

**Closed since the last revision:**

- ~~**5b — Quantify the attorney-access claim.**~~ Answered: **three attorneys.** Now stated
  as a specific number on slides 6 and 8. Good enough; do not inflate it.
- ~~**5 (original) — 2–3 boutique-tier pricing conversations.**~~ Superseded rather
  than completed. The ex-FBI PI-firm conversation established the buying frame
  (labour substitution against junior/overseas staff cost), the reference point
  (~$25k/licence awareness), and the contracting appetite (mutual MSA, low cost, low
  risk) — but the buyer declined to name a number before using the product. **More
  interviews will not produce that number; a pilot will.** Booking further calls to
  chase it would be motion, not progress. The right move is to run the agreed case
  and price from the result — which is exactly what slide 9 asks NDRC to fund.

**New, and not blocking submission — but do not let it drift:**

| # | Item | Owner | Why it matters |
|---|---|---|---|
| 7 | **Decide the AI-cost model: bundled vs passed through** | Neil + Conor | A buyer has already asked directly. It is the difference between a clean software gross margin and a cost-plus services margin, and it changes the entire pricing narrative. Decide it from pilot data, but decide it — an unanswered "we'll figure it out" in a partner meeting reads as not having thought about the business. |
| 8 | **A ready answer to "why not a $20 Claude subscription?"** | Neil | This is the real market objection and you have heard it in the wild. Slide 5's speaker note has the answer; rehearse it until it is automatic. It will decide more deals than any feature. |
| 9 | **Convert the pilot before submitting, if it lands in time** | Alex | Nothing is signed. If the case runs and the MSA is exchanged before you submit, slide 8 upgrades from "agreed next case" to "first pilot running" — a materially different application. Rolling deadline means it is worth waiting a short window for. |
| 10 | **Decide whether to disclose the autonomous AI engineering pipeline** | Neil + Conor | The 25 July brief's Status block claims an in-house pipeline taking features "from specification to reviewed pull request." Genuinely double-edged and needs a deliberate call, not a default. **For:** it is the only credible explanation for ~180k LOC and 913 commits from two engineers, and pre-empts "how did you build all this?" **Against:** it invites "how much of your codebase did a human read?" — and the honest answers today are ~15–20% test coverage and no CI, which is a bad place to be standing when that question lands. **Recommendation:** hold it back from the deck, be ready to volunteer it if asked about velocity, and land CI first so the answer is "AI writes, gates verify." Do not lead with it while the gates are absent. |

**Non-blocking but do it:** rotate the OpenAI keys sitting in plaintext in the local
`.env`. They were never committed and `.gitignore` is correct — this is hygiene, not
remediation.

---

## Part 5 — Fit assessment, recorded

**Where Loupe is unusually strong for NDRC pre-seed:**

- **Founder-market fit few applicants can match.** Seven years at Siren in the same
  category, bespoke solutions built for every customer, hundreds of analyst
  conversations — plus a co-founder who is a practising federal investigator and the
  product's design partner.
- **A behavioural origin story.** They went looking for a platform for live federal
  casework, evaluated one, and it couldn't work the case. Building was the second
  choice, not the first. Stronger evidence of a market gap than any interview
  programme.
- **A structural explanation for why the beachhead is empty.** Not "incumbents are
  bad" — incumbents are sold with configuration and support attached, which is correct
  for institutional buyers and unreachable for a 15-person practice. Seven years inside
  the category is what makes that read credible rather than convenient.
- **Both sides of the category represented in the founding team** — someone who built
  the software and someone who had to work cases with it. Rare, and hard for a
  competitor to assemble.
- **A working product in production use — this is the headline and everything else is
  supporting material.** Not a prototype, not an alpha: an application that has
  carried federal cases to completion inside Owl Consultancy, with three attorneys
  given access and attorneys retaining the practice because of it. ~180k LOC, 913
  commits, two primary engineers. The median pre-seed applicant has a demo and a
  hypothesis; this has closed cases.
- **The raise is commercialisation, not construction.** The gap between Loupe today
  and Loupe with external revenue is a security gate and a pilot, not a year of
  engineering. That is a materially easier thing for an investor to underwrite, and it
  is the honest description.
- **Customer-led development from the first commit** — every feature requested by a
  working investigator on a live matter.
- **A pilot in motion, sourced through casework rather than marketing** — an ex-FBI
  PI-firm principal who has agreed to send her next large-document matter and exchange
  an MSA. Warm, inbound-adjacent, and a credible first logo.
- **Release discipline** most seed-stage companies cannot demonstrate — a 12-stage
  security gate with a hard no-real-evidence-until-passed rule.
- **A moat in the evidence and provenance layer**, not in a model — and, more
  specifically, in **Loupes.** Extraction pipelines will commoditise; a durable,
  evidenced record of what an investigator decided mattered and how they bound it into
  a narrative does not. It accrues per customer, per case, and it is worthless to a
  competitor. The product being named after that object is a good sign the team knows
  where the value sits.
- **An agent whose value comes from what it can reach, not from the model behind it.**
  Loupe's AI runs tools against the case model — grouping transactions, generating
  visualisations, drafting outputs, and assembling Loupes from a plain instruction —
  rather than answering questions about a context window. The unit of work is a
  **hypothesis, not a query:** the investigator describes a scenario to test and the
  agent builds the evidence collection that proves or breaks it. That is the
  difference between a search product and a labour-substitution product, and
  labour substitution is precisely the frame the lead prospect used when she
  benchmarked price against a junior investigator's cost. It is also the right answer
  to the commoditisation question: the agent is interchangeable, the grounded claims
  ledger it operates over is not. And because capability is delivered as tools, **the
  agent compounds with the product** — every new platform surface becomes something it
  can wield. That is a moat that widens on its own.

**Where it is genuinely weak:**

- **No revenue and nothing signed.** The pilot is agreed, not contracted.
- **No price.** The buying frame is now understood — labour substitution, benchmarked
  against junior-investigator and overseas-staff cost, with ~$25k/licence in the
  buyer's frame of reference — but no one has quoted or accepted a number. This is
  resolved by a pilot, not by more discovery.
- **An unresolved cost-of-goods question.** ~$70 to ingest a 1,600-page document is a
  real variable cost and it is not yet decided whether it is bundled or passed
  through. Until that lands, gross margin is a hypothesis.
- **A live positioning objection** — "can't I do this with a $20 Claude subscription?"
  — which is wrong but widely believed, and will need answering in every sales
  conversation.
- **All the validation is inside one practice.** Cases closed, attorneys using it — but
  the practice is the co-founder's own. That is a legitimate strength *and* the obvious
  question: does it work for a firm with no founder embedded in it? Only the external
  pilot answers that, which is exactly why it is the thing being funded. Name this
  before someone else does; it costs nothing to acknowledge and looks evasive if
  discovered.
- **A claims-drift risk that has now appeared twice, running in opposite directions.**
  This pack once under-claimed a shipped platform into sounding like an alpha. The 25
  July brief now over-reaches in the other direction: three capabilities that entered
  this material as *roadmap suggestions* one revision ago appear in it as present-tense
  product. Both errors have the same root — material moving between documents without
  anyone re-checking what is actually true. **The fix is a single owner for the
  built/in-progress/planned status of every capability line**, and it is blockers 5f and
  5g. Worth recording as a pattern, because it will recur every time the brief is
  revised.
- **A self-inflicted narrative risk this pack was actively causing.** Earlier drafts
  described the product as a v1/v2 split with the current generation "in structured
  alpha" — which made a shipped, case-proven platform sound unbuilt, and put a roadmap
  hours figure in front of the traction. Corrected throughout, but worth recording,
  because under-claiming cost more here than overclaiming would have. Whoever briefs a
  designer or writes the next revision needs to know why the framing changed.
- **Structural:** a US-based co-founder and US-first market against Irish
  state-adjacent capital.
- **An unreviewed former-employer contract.** Reduced but not eliminated: the deck no
  longer links the product to prior employment, which was the main exposure. What
  remains is ordinary and probably benign — same-category build, a former customer of
  that employer now a co-founder — but nobody has read the covenants. One hour of legal
  time. See blocker 1b.

**Net:** a strong fit, and arguably ahead of the stage NDRC is aimed at rather than
behind it. This is not a technical team looking for a market — it is a domain-native
team that hit the gap from inside the category, tried to buy their way out, and built
because nothing worked. **The product is not the risk. It exists and it has done the
job on real cases.** What is unproven is commercial: no external customer, no price,
no signed contract. That is the right thing to be raising for and it should be said
plainly.

The critical judgement to hold onto: **the remaining commercial unknowns are now
pilot-shaped, not interview-shaped.** Every one of them — price, mechanism, edition
choice, AI-cost model, gross margin — is answered by running one real case for one
real firm. That is the correct thing to be raising for, and it is worth saying to
NDRC in exactly those words.

---

## Part 6 — What the competitive research supplies, slide by slide

Added 29 July 2026. Sources: `18-market-fit-lens-narrative.md` and
`19-competitive-landscape-narrative.md` (both internal candid register — **translate, never paste**),
sitting behind the Competitive Landscape and Market Fit Lens artifacts.

**Blocker #5 is now closed.** *"A per-case unit economic — what does a case cost you to run, and
what does it displace?"* The arithmetic exists, built from published vendor rates rather than
estimates. It is the strongest single addition to this deck.

### Slide 2 — The problem

The blind spot is now documented from the incumbents' own materials, which is far stronger than
asserting it:

- Relativity's processing documentation: calls, contacts, calendar, locations, web history and
  installed apps flatten into Excel in an "Other Data" folder; call logs emerge **"only as call log
  data in Excel format, not as individual records"**; voicemail unsupported; **multi-device
  extractions unsupported outright**.
- Everlaw splits conversations every thousand messages. Reveal slices them into 24-hour blocks,
  each block becoming "a document."
- i2 removed native UFED import at 9.1.0 and now tells customers to export CSV.

Pair it with what that costs: **a 435GB federal matter is $4,350 a month to keep hosted** — over
$100,000 across a two-year case — to have the phone data come out as spreadsheets. Problem and
price on one slide.

### Slide 3 — Why now

The citation layer commoditised inside four months, and it is dateable: Relativity folded aiR into
the base rate November 2025; Everlaw bundled three AI features into core pricing the same month;
DISCO announced agentic AI at no additional cost February 2026; Reveal gave its review engine away
through 2025. **Everyone can cite a document; the pricing power left that layer.** Combined with
evidence volume — ten-phone cases and six-figure document sets as routine — that is the "why now"
without needing a market-growth chart.

### Slide 5 — Why this isn't ChatGPT with files

The competitor-published limits are the most quotable material in the entire study, because each
one is the vendor's own documentation conceding the ceiling:

- Relativity: **300,000 documents per index**, 1.5M per workspace, fact extraction **5,000 documents
  per job**.
- CoCounsel: **~200 documents per comparison run**, quality explicitly degrading at volume.
- Reveal: Ask is **"designed for precision, not recall"** and cannot find all instances of anything.
- Harvey: **one prompt per document** across a vault, aggregated.

That is retrieval-versus-traversal argued with their numbers instead of our adjectives. It also
answers blocker #8 — *"why not a $20 Claude subscription?"* — in the same breath.

### Slide 6 — Market and lead customer  ← **the biggest upgrade**

This slide currently leans on ACFE membership (~95k) and Harvey's ARR as proxies. Both are
reachability and adjacency signals, not market size. Replace with the per-matter economics:

| Per matter | Doc-heavy fraud | Serious multi-defendant | Large federal |
|---|---|---|---|
| Displaced (processing, hosting, examiner analysis) | $34,200 | $45,600 | $130,575 |
| Hours released | $4,384 | $6,510 | $7,508 |
| **Displaceable value** | **$38,584** | **$52,110** | **$138,082** |

Then the pool: **US criminal-defence firm revenue exceeds $15B a year** across ~252,000
practitioners; a practice on a realistic case mix carries **$0.89M–$1.94M of displaceable value
annually**; bottom-up at a fifth of that across 1,000–5,000 target firms is **$350M–$900M**.

**Say the extraction line is retained.** Devices still go to a forensic vendor — $3,650 for a
one-or-two-device case. Conceding it makes every other number credible, and a panel that finds an
unconceded overclaim discounts the whole slide.

**"Why this tier is empty — and stays empty"** now has evidence rather than assertion: GrayKey is
restricted to law enforcement and public safety, with Magnet stating plainly it is not available to
the private sector; Cellebrite Pathfinder is marketed solely to law enforcement, government and
intelligence; and **a Florida State Attorney's office publishes instructions telling defence counsel
to view extractions through read-only share links in the prosecution's own tool.** That last one is
the single most vivid fact in the corpus and belongs in the meeting even if it does not fit the
slide.

### Slide 6 — the Irish and European case, which NDRC will care about most

NDRC is an Irish programme. A US-only market slide invites the obvious question, so answer it before
it is asked. The regional plan is in §7a / §6a of the narratives; the short form:

- **Ireland is the reference, not the revenue.** €123M of criminal legal aid for 2026 (up €27M) and
  a €215M Courts Service is not a market to build a company on and should not be presented as one.
  Its job is the first nameable customer in the company's own jurisdiction, reached through the Law
  Society and the Criminal Legal Aid panel — the same bar-association channel Matey proved in the US.
- **The UK is the first real European revenue, and it has the strongest tailwind in the study.**
  21.76% of the European digital-forensics market (~$525M), and a funded government problem:
  **~80,200 open Crown Court cases** at December 2025, projected to **99,000–114,000 by March 2029**,
  with £92M added to criminal legal aid in July 2025. A product that removes hours from evidence
  handling on serious matters is aligned to a published policy objective, not just a firm's margin.
- **Europe is a structural advantage, not just a bigger number.** Single-tenant, in-jurisdiction
  deployment scores 9 — joint highest of forty-seven platforms — while most American-owned
  competitors score 2–6. Under GDPR that is a procurement requirement rather than a preference, and
  it is the one axis where being a European company beats being a larger American one. Europe is 25%
  of the global legal-tech market ($6.81B in 2026 → $15.45B by 2034).

**Two things to be disciplined about.** Do not carry a single European TAM into the room as though
it were addressable in one go — every jurisdiction has its own procedure, disclosure regime and
vendor rates, so Europe beyond Ireland and the UK is a partner-led motion. And **sequence defence
before policing in the UK**: CPIA disclosure obligations are gated at 8 in the policing profile and
Loupe scores 2, the heaviest single gap in the study for that buyer.

### Slide 10 — The ask, and pricing

**Displaceable value moves 24× between the smallest and largest matters.** A flat $6–24k per-matter
band captures 205% of a one-phone case and 9% of a ten-phone federal one. The pilot NDRC is being
asked to fund is exactly what settles it — price should scale with device count, data volume and
duration, which are the same drivers as the model it displaces. Framing the ask as *"fund the pilot
that sets the scaling"* is sharper than *"fund the pilot that sets the price."*

### For the meeting, not the deck

- **Competition.** Four funded companies already sell AI to criminal defence — TrialKit $4.25M,
  Matey $7.5M (verified: Timespan Ventures, Neo, Streamlined, Aug 2025), JusticeText $4.0M ARR
  across 4,100 attorneys, Longeye $5M from a16z. **None has a graph.** Knowing this cold, and
  naming them first, reads as command of the category. Pretending the category is empty does not
  survive one search.
- **Matey is the closest comparable** — same buyer, sells through NACDL and a state defence bar,
  and holds SOC 2 Type II and ISO 27001 today.
- **The honest ranking.** Nine of forty-seven platforms outscore Loupe overall; seven of those
  cannot be sold to a defence practice at all. Volunteering that is a strength — it shows the matrix
  was not built to flatter.
- **Siren** — blocker 5d's one-sentence answer, unchanged.

### Do not use

The narratives are candid internal register. Specifically keep out of the deck: Loupe's own axis
scores and rank; the weaknesses table; anything describing civil litigation as the market Loupe is
furthest from serving; the founder-knowledge entries on Siren and Octostar, which are unciteable;
and the two unshipped capabilities unless they have demoed clean, per blocker 5g.
