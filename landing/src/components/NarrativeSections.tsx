import type { ReactNode } from "react"
import { Reveal } from "../lib/Reveal"

/* ------------------------------------------------------------------ shared */

interface SectionHeadProps {
  index: string
  eyebrow: string
  heading: ReactNode
  lede?: ReactNode
}

function SectionHead({ index, eyebrow, heading, lede }: SectionHeadProps) {
  return (
    <Reveal className={`story-heading ${lede ? "story-heading-split" : ""}`}>
      <div>
        <p className="section-index">
          <b>{index}</b>
          {eyebrow}
        </p>
        <h2>{heading}</h2>
      </div>
      {lede ? <p>{lede}</p> : null}
    </Reveal>
  )
}

function SourceNote({ children }: { children: ReactNode }) {
  return (
    <p className="source-note">
      <i aria-hidden="true" />
      {children}
    </p>
  )
}

/* ------------------------------------------------------------------ 01 origin */

export function OriginSection() {
  return (
    <section className="story-section origin-story" id="origin">
      <div className="container">
        <SectionHead
          index="01"
          eyebrow="Why Loupe exists"
          heading={
            <>
              We went looking for this.
              <br />
              We couldn’t buy it.
            </>
          }
        />

        <div className="origin-layout">
          <Reveal className="origin-prose">
            <p>
              Loupe did not begin as a market hypothesis. It began with a live federal matter and a
              plain problem: the evidence was connected, and there was nothing available that would
              hold it that way.
            </p>
            <p>
              We assessed a number of platforms against that case. Each was good at part of it. None
              could work the case the way an investigation actually runs — a call at 02:14, a
              transfer of $8,400 and a line in a subpoena return had to be the same kind of object,
              and nowhere were they.
            </p>
            <p className="origin-turn">Building it was the second choice, not the first.</p>
          </Reveal>

          <Reveal className="origin-aside" delay={0.08}>
            <blockquote>
              Every feature in Loupe was requested by a working investigator, on a live case.
            </blockquote>
            <div className="origin-facts">
              <div>
                <b>Built inside</b>
                <span>A working private-investigations practice</span>
              </div>
              <div>
                <b>Proven on</b>
                <span>Federal matters carried to completion</span>
              </div>
              <div>
                <b>Directed by</b>
                <span>The investigator running those matters</span>
              </div>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ 02 problem */

const evidenceLoads = [
  {
    number: "01",
    entity: "communication",
    title: "Phone extractions",
    detail:
      "Ten devices in a single matter. Hundreds of thousands of calls, messages, locations, contacts and app records.",
  },
  {
    number: "02",
    entity: "document",
    title: "Documents",
    detail:
      "Two hundred thousand pages of statements, returns, filings, reports, disclosure and correspondence.",
  },
  {
    number: "03",
    entity: "financial",
    title: "Financial records",
    detail:
      "Tens of thousands of transactions across accounts, entities and institutions, in every format a bank produces.",
  },
  {
    number: "04",
    entity: "event",
    title: "Recorded media",
    detail:
      "Five hundred hours of calls and interviews — every name spoken is a person who has to be matched to the rest of the case.",
  },
]

export function ProblemSection() {
  return (
    <section className="story-section problem-story" id="problem">
      <div className="story-grid" aria-hidden="true" />
      <div className="container">
        <SectionHead
          index="02"
          eyebrow="What a case arrives as"
          heading={
            <>
              A data problem wearing
              <br />a legal costume.
            </>
          }
          lede={
            <>
              A single serious fraud or criminal matter now arrives as more evidence than a team can
              read, in more formats than any one tool holds. The largest matter Loupe has carried
              ran to <strong>435 gigabytes</strong>.
            </>
          }
        />

        <div className="problem-layout">
          <Reveal as="article" className="problem-thesis">
            <p className="problem-quote">
              One phone. One PDF. One spreadsheet.
              <strong>Every connection left in someone’s head.</strong>
            </p>
            <p>
              The same person in a witness statement, a messaging thread and a beneficiary field.
              The meeting two streets from the cash withdrawal. Those connections are the case, and
              today they live in investigators’ heads and on whiteboards.
            </p>
            <div className="problem-origin">
              <span>The cost</span>
              <p>
                They do not scale, they do not survive staff turnover, and they cannot be handed to
                a court.
              </p>
            </div>
          </Reveal>

          <div className="evidence-load" aria-label="Evidence a single serious matter can contain">
            {evidenceLoads.map((item, index) => (
              <Reveal as="article" key={item.number} delay={index * 0.05}>
                <span data-entity={item.entity}>{item.number}</span>
                <div>
                  <h3>{item.title}</h3>
                  <p>{item.detail}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>

        <Reveal className="problem-structural">
          <div>
            <h3>The tools built to hold it are viewers.</h3>
            <p>
              The platforms that can take the document set discard most of the rest. Call logs
              arrive as spreadsheet rows rather than records. Conversations are cut into
              thousand-message blocks or twenty-four-hour slices. Multi-device extractions are
              frequently unsupported outright.
            </p>
            <p>
              This is not an engineering failure. It is what happens when a platform is built to
              make a pile smaller, and an investigation is the opposite job — every artifact
              processed should make the account of what happened richer, not shorter.
            </p>
          </div>
          <SourceNote>Published vendor processing documentation, 2026</SourceNote>
        </Reveal>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ 03 the field */

const fieldColumns = [
  {
    title: "They model the evidence — and won’t sell it to you",
    body: "Forensic and intelligence platforms build real structure from what they ingest. They are sold to law enforcement, government and intelligence. What a private practice can buy is examiner tooling: several kinds of device, no kinds of document.",
  },
  {
    title: "They’ll sell to you — and treat a phone as an attachment",
    body: "The document platforms are excellent, purchasable and everywhere. The phone data does not survive the door. Call logs flatten into spreadsheets, conversations are split into blocks, and multi-device extractions go unsupported.",
  },
  {
    title: "Same buyer as us — and no case model",
    body: "Four funded companies now sell AI to criminal defence, with the bar associations and the certifications. All four answer by retrieval, which returns what looked relevant and cannot tell you what it missed. On a defence matter, the thing you never saw is the thing that loses the case.",
    emphasis: true,
  },
]

export function FieldSection() {
  return (
    <section className="story-section field-story" id="field">
      <div className="container">
        <SectionHead
          index="03"
          eyebrow="Why this is still open"
          heading={
            <>
              Forty-seven platforms.
              <br />
              The intersection is empty.
            </>
          }
          lede={
            <>
              We assessed the category across forty-seven platforms and thirty capability axes. It
              splits into two halves that never meet — and this buyer sits in the gap between them.
            </>
          }
        />

        <div className="field-columns">
          {fieldColumns.map((column, index) => (
            <Reveal
              as="article"
              key={column.title}
              delay={index * 0.06}
              className={column.emphasis ? "is-emphasis" : ""}
            >
              <span>{`0${index + 1}`}</span>
              <h3>{column.title}</h3>
              <p>{column.body}</p>
            </Reveal>
          ))}
        </div>

        <Reveal className="statement">
          <p>
            Not one of the forty-seven holds device data, financial records and documents in a
            single model.
          </p>
          <p className="statement-sub">
            That is structural rather than an accident of scoring. Modelling evidence and serving
            this buyer are different problems, sold to different customers — so the companies that
            solved one have never had a commercial reason to solve the other.
          </p>
          <SourceNote>Assessment of 47 platforms across 30 capability axes · July 2026</SourceNote>
        </Reveal>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ 04 case model */

const sourceTypes = [
  ["Device data", "Calls · messages · contacts · app records", "communication"],
  ["Documents", "Pages · passages · exhibits · disclosure", "document"],
  ["Financial", "Accounts · transfers · transactions", "financial"],
  ["Media", "Audio · video · photographs", "event"],
]

const caseViews = ["Graph", "Timeline", "Map", "Evidence", "Financial", "Agent"]

export function CaseModelStory() {
  return (
    <section className="story-section model-story" id="platform">
      <div className="container">
        <SectionHead
          index="04"
          eyebrow="The layer beneath the answer"
          heading={
            <>
              Evidence in.
              <br />
              One connected model out.
            </>
          }
          lede={
            <>
              Loupe resolves people, organisations, accounts, locations, events and transactions as
              evidence enters the case. A call, a transfer and a line in a subpoena return become
              the same kind of citable object.
            </>
          }
        />

        <Reveal className="model-system" delay={0.08}>
          <div className="model-system-top">
            <span>Case model / live structure</span>
            <span>
              <i />
              Resolved at ingestion
            </span>
          </div>
          <div className="model-system-body">
            <div className="model-sources">
              <p>Mixed evidence</p>
              {sourceTypes.map(([title, detail, entity], index) => (
                <div key={title} data-entity={entity}>
                  <span>0{index + 1}</span>
                  <p>
                    <strong>{title}</strong>
                    <small>{detail}</small>
                  </p>
                  <i aria-hidden="true" />
                </div>
              ))}
            </div>

            <div className="model-core" aria-label="Persistent Loupe case model">
              <svg viewBox="0 0 340 340" aria-hidden="true">
                <circle cx="170" cy="170" r="128" />
                <circle cx="170" cy="170" r="92" />
                <path d="M48 118 120 92 167 152 236 83 290 137" />
                <path d="M55 238 125 211 167 152 222 225 284 191" />
                <path d="m120 92 5 119 97 14 14-142" />
              </svg>
              <span className="model-node node-1" />
              <span className="model-node node-2" />
              <span className="model-node node-3" />
              <span className="model-node node-4" />
              <span className="model-node node-5" />
              <div>
                <small>Persistent</small>
                <strong>Case model</strong>
                <span>Entities · events · sources</span>
              </div>
            </div>

            <div className="model-views">
              <p>Investigation views</p>
              {caseViews.map((view, index) => (
                <span key={view} className={index === 0 ? "is-active" : ""}>
                  <i>0{index + 1}</i>
                  {view}
                </span>
              ))}
            </div>
          </div>
          <div className="model-system-foot">
            <p>
              <span>One identity</span>
              <strong>The same person across every source</strong>
            </p>
            <p>
              <span>One provenance path</span>
              <strong>File → page → passage → claim</strong>
            </p>
            <p>
              <span>One question</span>
              <strong>Put to the whole case, not a sample</strong>
            </p>
          </div>
        </Reveal>

        <Reveal className="traversal-note" delay={0.06}>
          <div>
            <p className="section-index">
              <b>—</b>
              Traversal, not retrieval
            </p>
            <h3>The difference is what the answer is made of.</h3>
          </div>
          <div>
            <p>
              A general assistant retrieves the passages that look relevant and reasons over them.
              It produces a well-written opinion about a sample, and it cannot tell you what it
              left out.
            </p>
            <p>
              Loupe traverses the model instead. <em>Who was in contact with this person in the
              fortnight before that transfer</em> has a definite answer across everything ingested,
              and the answer is the complete matching set. The citation falls out of the structure,
              because every object already knows where it came from.
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ 06 loupes */

export function LoupeWorkflowSection() {
  return (
    <section className="story-section loupe-workflow" id="workflow">
      <div className="container">
        <SectionHead
          index="06"
          eyebrow="Human judgment, made durable"
          heading={
            <>
              Find what matters.
              <br />
              Bind it. Keep the reasoning.
            </>
          }
          lede={
            <>
              A Loupe is a bonded collection — the passages, entities, events and transactions that
              establish one thing, each carrying the quote, page and file it came from.
            </>
          }
        />

        <div className="loupe-assembly" aria-label="How investigators build durable findings">
          <Reveal as="article" className="assembly-step assembly-source">
            <div className="assembly-index">
              <span>01</span>
              <p>Mark the signal</p>
            </div>
            <div className="assembly-card evidence-fragment">
              <div>
                <span>Source passage</span>
                <b>Significant</b>
              </div>
              <blockquote>
                “The transfer was approved after the call and before the account changed.”
              </blockquote>
              <p>
                Interview transcript <strong>p. 18</strong>
              </p>
            </div>
            <p>
              An investigator marks a passage, event, transaction or relationship as significant
              without detaching it from its source.
            </p>
          </Reveal>

          <Reveal as="article" className="assembly-step assembly-loupe" delay={0.06}>
            <div className="assembly-index">
              <span>02</span>
              <p>Build the Loupe</p>
            </div>
            <div className="assembly-card loupe-object">
              <div className="loupe-object-ring" aria-hidden="true">
                <i />
                <i />
                <i />
              </div>
              <span>Focused enquiry</span>
              <h3>Approval and movement of funds</h3>
              <div>
                <p>
                  <strong>14</strong>
                  facts
                </p>
                <p>
                  <strong>6</strong>
                  sources
                </p>
                <p>
                  <strong>4</strong>
                  people
                </p>
              </div>
            </div>
            <p>
              Evidence from several source types becomes one reusable object in the case. A Loupe
              can hold a call, a transfer and a location as members — not only documents.
            </p>
          </Reveal>

          <Reveal as="article" className="assembly-step assembly-output" delay={0.12}>
            <div className="assembly-index">
              <span>03</span>
              <p>Build the case out of them</p>
            </div>
            <div className="assembly-card finding-object">
              <div>
                <span>Finding 03</span>
                <b>Ready for review</b>
              </div>
              <h3>The sequence is supported across communications and financial records.</h3>
              <ul>
                <li>Conclusion written</li>
                <li>Evidence path retained</li>
                <li>Timeline and table attached</li>
              </ul>
            </div>
            <p>
              Loupes move into the case, and the case is built out of them — conclusion,
              justification and evidence assembled as the investigation runs, rather than written up
              at the end.
            </p>
          </Reveal>
        </div>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ 07 difference */

const differences = [
  {
    label: "Where the case lives",
    generic: "A context window, forgotten when the session ends.",
    loupe: "A persistent case model that outlives every conversation, handover and review.",
  },
  {
    label: "Scale",
    generic: "Hundreds of pages at best.",
    loupe:
      "Ten phones, two hundred thousand documents, five hundred hours of audio — 435GB, all of it modelled.",
  },
  {
    label: "What the AI does",
    generic: "Retrieves a sample of what fits and reasons over it. You cannot know what it missed.",
    loupe:
      "Traverses a model of the whole case and returns the complete matching set, every claim carrying its source.",
  },
  {
    label: "Human judgment",
    generic: "Lives outside the tool and is lost between sessions.",
    loupe: "Significance, highlights and Loupes are durable objects inside the case model.",
  },
  {
    label: "Confidentiality",
    generic: "Evidence enters a shared, multi-tenant service.",
    loupe: "Single-tenant. Evidence never leaves the customer’s own instance.",
  },
  {
    label: "Model dependence",
    generic: "The language model is the product.",
    loupe: "Models are interchangeable components. The evidence layer is the product.",
  },
]

export function DifferenceSection() {
  return (
    <section className="story-section difference-story" id="why-loupe">
      <div className="story-grid" aria-hidden="true" />
      <div className="container">
        <SectionHead
          index="07"
          eyebrow="Why this isn’t a chat window"
          heading={
            <>
              The difference isn’t the citation.
              <br />
              It’s what the AI is standing on.
            </>
          }
          lede={
            <>
              Every serious platform can point at a document now, and most give it away. The
              question that decides an investigation is a different one: was the answer built from a
              model of the whole case, or from whatever a retriever happened to surface?
            </>
          }
        />

        <Reveal className="difference-matrix" delay={0.08}>
          <div className="difference-matrix-head" aria-hidden="true">
            <span>What changes</span>
            <span>A general AI assistant</span>
            <span>Loupe</span>
          </div>
          {differences.map((row) => (
            <div className="difference-matrix-row" key={row.label}>
              <strong>{row.label}</strong>
              <p data-label="A general AI assistant">{row.generic}</p>
              <p data-label="Loupe">
                <i aria-hidden="true" />
                {row.loupe}
              </p>
            </div>
          ))}
        </Reveal>

        <Reveal className="difference-close-block">
          <p>
            The specialist platforms publish their own ceilings: indexes capped in the hundreds of
            thousands of documents, comparison runs that degrade past a couple of hundred files,
            search tuned for precision rather than completeness. Those are honest limits of reading
            documents one at a time.
          </p>
          <p className="difference-close">The language model can change. The case does not.</p>
        </Reveal>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ 08 economics */

const costLines = [
  ["Forensic extraction, per device", "$1,575 – 2,975", "Retained — devices still go to a vendor"],
  ["Processing", "$3 – 10 per gigabyte", "Displaced"],
  ["Hosting", "$5 – 15 per gigabyte, per month", "Displaced — for the life of the matter"],
  ["Examiner analysis", "$300 – 500 per hour", "Displaced"],
  ["Investigator and paralegal hours", "58 – 100 hours", "Roughly half returned"],
]

export function EconomicsSection() {
  return (
    <section className="story-section economics-story" id="economics">
      <div className="container">
        <SectionHead
          index="08"
          eyebrow="What this replaces"
          heading={
            <>
              This budget is
              <br />
              already being spent.
            </>
          }
          lede={
            <>
              A practice does not choose between Loupe and a competitor. It chooses between Loupe
              and what it does today — a vendor per device, a hosting bill per gigabyte per month,
              an examiner by the hour, and its own people stitching the pieces together by hand.
            </>
          }
        />

        <div className="economics-layout">
          <Reveal className="cost-table">
            <div className="cost-table-head" aria-hidden="true">
              <span>Per serious matter</span>
              <span>Today</span>
              <span>Under Loupe</span>
            </div>
            {costLines.map(([label, cost, fate]) => (
              <div className="cost-row" key={label}>
                <strong>{label}</strong>
                <span className="cost-figure">{cost}</span>
                <span className="cost-fate">{fate}</span>
              </div>
            ))}
            <SourceNote>
              Published 2026 eDiscovery processing and hosting rates · forensic vendor rate cards ·
              RAND National Public Defense Workload Study
            </SourceNote>
          </Reveal>

          <Reveal className="economics-argument" delay={0.08}>
            <div className="economics-callout">
              <b>$4,350</b>
              <p>
                a month to keep a 435-gigabyte matter hosted — over $100,000 across two years. What
                that money buys is a spreadsheet.
              </p>
            </div>
            <p>
              Sixty to a hundred hours go into handling the evidence on a serious matter before
              anyone has answered a question about it. The largest line in the bill, hosting, is
              charged per gigabyte per month — so it grows with exactly the material that makes the
              case.
            </p>
            <p>
              Loupe does not displace the extraction. Devices still go to a vendor, and that line is
              unchanged; saying so is what makes the rest credible. Everything downstream of it is
              what changes.
            </p>
            <p className="economics-turn">
              Priced per matter, against the investigator hours it returns — never per gigabyte,
              which pays a practice to keep evidence out of the platform.
            </p>
          </Reveal>
        </div>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ 09 audience */

export function AudienceSection() {
  return (
    <section className="story-section audience-story" id="audience">
      <div className="story-grid" aria-hidden="true" />
      <div className="container">
        <SectionHead
          index="09"
          eyebrow="Who this is for"
          heading={
            <>
              Built for the practice
              <br />
              that receives the evidence.
            </>
          }
          lede={
            <>
              The defining characteristic is not size or sector. It is that this buyer receives
              evidence rather than collecting it, receives it in formats built by the other side,
              and has had no way to analyse it properly.
            </>
          }
        />

        <div className="audience-layout">
          <Reveal className="audience-primary">
            <span>Built for, first</span>
            <h3>Defence-side investigations and criminal defence.</h3>
            <p>
              Boutique forensic and criminal-defence practices of roughly ten to fifty people,
              running federal and serious state matters. Big-Four-class casework without Big-Four
              tooling budgets, and no implementation resource to spare — so Loupe is designed to be
              usable out of the box.
            </p>
          </Reveal>

          <div className="audience-secondary">
            <Reveal as="article" delay={0.05}>
              <span>02</span>
              <div>
                <strong>Corporate investigations &amp; compliance</strong>
                <p>
                  The same product on larger matters, where the document and financial evidence
                  carries the case and device data is a smaller part of the mix.
                </p>
              </div>
            </Reveal>
            <Reveal as="article" delay={0.1}>
              <span>03</span>
              <div>
                <strong>Insurance SIU &amp; fraud</strong>
                <p>
                  Financial and document analysis at volume, in the fastest-growing category in the
                  field and one where no platform is locked out on procurement grounds.
                </p>
              </div>
            </Reveal>
          </div>
        </div>

        <Reveal className="audience-later">
          <div>
            <span>Later, and deliberately</span>
            <p>
              Law enforcement, prosecutors and financial-crime units are served by platforms built
              specifically for them, and served well. Civil litigation belongs to the review
              platforms, whose whole apparatus exists to cull a corpus down. Loupe reaches those
              rooms once it is proven where it is strongest — not by claiming to be the best answer
              everywhere.
            </p>
          </div>
        </Reveal>

        <Reveal className="statement">
          <p>
            This buyer receives the evidence, cannot collect it, and cannot buy the analytics the
            other side runs on. <em>That is the whole opportunity.</em>
          </p>
        </Reveal>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ 10 proof */

export function ProofSection() {
  return (
    <section className="story-section proof-story" id="proof">
      <div className="container">
        <SectionHead
          index="10"
          eyebrow="How it’s built"
          heading={
            <>
              Built inside live casework,
              <br />
              not around a demo.
            </>
          }
          lede={
            <>
              Loupe has carried federal matters to completion inside a working
              private-investigations practice — multi-gigabyte extractions, tens of thousands of
              curated transactions and full document corpora.
            </>
          }
        />

        <div className="proof-layout">
          <Reveal className="proof-statement">
            <span>From first review to final finding</span>
            <p>
              Investigators, lawyers and reviewers work from one source-linked model of the
              evidence.
            </p>
            <div className="proof-status">
              <i />
              In production use
            </div>
          </Reveal>

          <div className="proof-ledger">
            <Reveal as="article">
              <span>01</span>
              <div>
                <strong>Single-tenant deployment</strong>
                <p>
                  One isolated stack per customer. Evidence never enters a shared service, and the
                  instance can sit in the jurisdiction the matter requires.
                </p>
              </div>
            </Reveal>
            <Reveal as="article" delay={0.05}>
              <span>02</span>
              <div>
                <strong>Provider-independent AI</strong>
                <p>
                  Multiple model providers sit behind one routing policy. The model is a swappable
                  component; the evidence layer is what persists.
                </p>
              </div>
            </Reveal>
            <Reveal as="article" delay={0.1}>
              <span>03</span>
              <div>
                <strong>Source-linked by construction</strong>
                <p>
                  Every object in the case model carries the file, page and passage it came from, so
                  a finding can always be walked back to the evidence under it.
                </p>
              </div>
            </Reveal>
            <Reveal as="article" delay={0.15}>
              <span>04</span>
              <div>
                <strong>Staged release discipline</strong>
                <p>
                  Onboarding an external practice’s evidence runs behind a security-gated release
                  plan. No external case data enters the platform until the security, isolation,
                  backup and legal stages pass.
                </p>
              </div>
            </Reveal>
          </div>
        </div>

        <Reveal className="architecture-rail">
          <span>Architecture</span>
          <p>
            React console · FastAPI case service · asynchronous evidence engine · Neo4j case graph ·
            Postgres for cases, identity and audit · vector retrieval · isolated stack per customer
          </p>
        </Reveal>
      </div>
    </section>
  )
}

