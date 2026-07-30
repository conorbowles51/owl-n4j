import type { ReactNode } from "react"
import { Reveal } from "../lib/Reveal"

/* ------------------------------------------------------------------ shared */

function SectionHead({
  eyebrow,
  heading,
  lede,
}: {
  eyebrow: string
  heading: ReactNode
  lede?: ReactNode
}) {
  return (
    <Reveal className="sec-head">
      <p className="eyebrow">{eyebrow}</p>
      <h2>{heading}</h2>
      {lede ? <p className="sec-lede">{lede}</p> : null}
    </Reveal>
  )
}

function Source({ children }: { children: ReactNode }) {
  return <p className="src">{children}</p>
}

/* ------------------------------------------------------------------ evidence */

const evidence = [
  {
    entity: "communication",
    title: "Device extractions",
    detail: "Up to ten phones in one matter — calls, messages, contacts, locations and app records.",
  },
  {
    entity: "document",
    title: "Documents",
    detail: "Two hundred thousand pages of statements, returns, filings, reports and disclosure.",
  },
  {
    entity: "financial",
    title: "Financial records",
    detail: "Tens of thousands of transactions across accounts, entities and institutions.",
  },
  {
    entity: "event",
    title: "Recorded media",
    detail: "Five hundred hours of calls and interviews, transcribed and attributed by speaker.",
  },
]

export function ProblemSection() {
  return (
    <section className="sec sec-paper" id="problem">
      <div className="container">
        <SectionHead
          eyebrow="The evidence"
          heading="A serious matter arrives as more evidence than a team can read."
          lede="Four hundred and thirty-five gigabytes, in four formats that nothing on the market holds together."
        />

        <div className="evidence-rows">
          {evidence.map((item, i) => (
            <Reveal as="article" key={item.title} delay={i * 0.04}>
              <span className="dot" data-entity={item.entity} aria-hidden="true" />
              <h3>{item.title}</h3>
              <p>{item.detail}</p>
            </Reveal>
          ))}
        </div>

        <Reveal className="split-note">
          <div>
            <h3>The tools built to hold it are viewers.</h3>
            <p>
              Platforms that take the document set discard most of the rest. Call logs arrive as
              spreadsheet rows rather than records. Conversations are cut into thousand-message
              blocks or twenty-four-hour slices. Multi-device extractions often go unsupported.
            </p>
          </div>
          <div>
            <p>
              It is not an engineering failure. A review platform exists to make a pile smaller, and
              an investigation is the opposite job: every artifact processed should make the account
              of what happened richer, not shorter.
            </p>
            <Source>Published vendor processing documentation, 2026</Source>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ case model */

const sources = [
  ["Device data", "Calls · messages · contacts · app records", "communication"],
  ["Documents", "Pages · passages · exhibits · disclosure", "document"],
  ["Financial", "Accounts · transfers · transactions", "financial"],
  ["Media", "Audio · video · photographs", "event"],
]

export function CaseModelStory() {
  return (
    <section className="sec sec-paper" id="platform">
      <div className="container">
        <SectionHead
          eyebrow="The case model"
          heading="One model, not a folder of files."
          lede="Loupe resolves people, organisations, accounts, locations, events and transactions as evidence enters the case. A call at 02:14, a transfer of $8,400 and a line in a subpoena return become the same kind of citable object."
        />

        <Reveal className="flow">
          <div className="flow-col">
            <p className="col-label">Evidence in</p>
            <ul>
              {sources.map(([title, detail, entity]) => (
                <li key={title}>
                  <span className="dot" data-entity={entity} aria-hidden="true" />
                  <strong>{title}</strong>
                  <small>{detail}</small>
                </li>
              ))}
            </ul>
          </div>

          <div className="flow-col flow-mid">
            <p className="col-label">Resolved at ingestion</p>
            <ul>
              <li>
                <strong>Entities and events extracted</strong>
                <small>Directed per matter by an ingestion profile</small>
              </li>
              <li>
                <strong>Identities resolved across sources</strong>
                <small>One person, however many places they appear</small>
              </li>
              <li>
                <strong>Provenance attached to every object</strong>
                <small>File → page → passage → claim</small>
              </li>
            </ul>
          </div>

          <div className="flow-col">
            <p className="col-label">Queried as one case</p>
            <ul>
              <li>
                <strong>Graph, timeline, map, table</strong>
                <small>Perspectives on one structure, not separate tools</small>
              </li>
              <li>
                <strong>Financial and communications analysis</strong>
                <small>Across every source in the matter</small>
              </li>
              <li>
                <strong>Agent with tools over the model</strong>
                <small>Produces work product, not prose</small>
              </li>
            </ul>
          </div>
        </Reveal>

        <Reveal className="claim">
          <p>
            No other platform holds device data, financial records and documents in a single model.
          </p>
          <Source>Assessment of 47 investigation, forensics and eDiscovery platforms, 2026</Source>
        </Reveal>

        <Reveal className="split-note">
          <div>
            <h3>Traversal, not retrieval.</h3>
            <p>
              A general assistant retrieves the passages that look relevant and reasons over them.
              It returns a well-written opinion about a sample, and cannot say what it left out.
            </p>
          </div>
          <div>
            <p>
              Loupe traverses the model. <em>Who was in contact with this person in the fortnight
              before that transfer</em> has a definite answer across everything ingested, and the
              answer is the complete matching set. The citation falls out of the structure, because
              every object already carries its source.
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ loupes */

export function LoupeWorkflowSection() {
  return (
    <section className="sec sec-paper" id="findings">
      <div className="container">
        <SectionHead
          eyebrow="Findings"
          heading="Conclusions that carry their evidence."
          lede="A Loupe is a bonded collection — the passages, entities, events and transactions that establish one thing, each keeping the quote, page and file behind it."
        />

        <div className="steps">
          <Reveal as="article" delay={0}>
            <p className="step-n">01</p>
            <h3>Mark what matters</h3>
            <p>
              A passage, event, transaction or relationship is marked significant without being
              detached from its source. The marking is visible everywhere that object appears.
            </p>
          </Reveal>
          <Reveal as="article" delay={0.05}>
            <p className="step-n">02</p>
            <h3>Bind it into a Loupe</h3>
            <p>
              Evidence from several source types becomes one reusable object in the case. A Loupe
              holds a call, a transfer and a location as members — not only documents.
            </p>
          </Reveal>
          <Reveal as="article" delay={0.1}>
            <p className="step-n">03</p>
            <h3>Build the case from them</h3>
            <p>
              Loupes move into the case and the case is built out of them: conclusion, justification
              and evidence assembled as the investigation runs, rather than written up at the end.
            </p>
          </Reveal>
        </div>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ capability */

const capability = [
  {
    group: "Phone and device evidence",
    items: [
      "Cellebrite UFDR and multi-device extraction parsing",
      "Calls, messages, contacts, locations and app records as structured objects",
      "Conversations kept whole, not split into blocks",
      "Cross-device identity resolution with per-device contact naming preserved",
    ],
  },
  {
    group: "Documents and media",
    items: [
      "Automatic text recognition for scanned documents",
      "Speaker-separated audio transcription with speaker labelling and merging",
      "Entity and event extraction directed per matter at ingestion",
      "Case-wide full-text search across every document",
    ],
  },
  {
    group: "Analysis",
    items: [
      "Network graph with pathfinding and neighbourhood inspection",
      "Timeline with timezone control and saved, shareable views",
      "Map with location confidence and provenance shown honestly",
      "Financial explorer across accounts, transfers and counterparties",
    ],
  },
  {
    group: "Judgment and output",
    items: [
      "Significance marking that persists across graph, timeline and table",
      "Loupes — bonded, evidenced collections",
      "Case notebook and investigator-authored entities and relationships",
      "Tables, charts and exports that stay attached to the case",
    ],
  },
  {
    group: "The agent",
    items: [
      "Tools across the case model, not a chat box over files",
      "Grouping, aggregation and visualisation from a plain-language instruction",
      "Asks for clarification instead of guessing; proposes while the investigator disposes",
      "Safe read-only database access for aggregate queries",
    ],
  },
  {
    group: "Deployment",
    items: [
      "Single-tenant — one isolated stack per customer",
      "In-jurisdiction hosting, including on-premises",
      "Per-case membership enforced on every API route",
      "Multiple model providers behind one routing policy",
    ],
  },
]

export function CapabilitySection() {
  return (
    <section className="sec sec-paper sec-tight" id="capability">
      <div className="container">
        <SectionHead
          eyebrow="Capability"
          heading="What the platform does."
          lede="Every item below is in the product and demonstrable on a live matter."
        />

        <div className="cap-grid">
          {capability.map((block, i) => (
            <Reveal as="article" key={block.group} delay={(i % 3) * 0.05}>
              <h3>{block.group}</h3>
              <ul>
                {block.items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ difference */

const differences = [
  [
    "Where the case lives",
    "A context window, gone when the session ends.",
    "A persistent case model that outlives every conversation, handover and review.",
  ],
  [
    "Scale",
    "Hundreds of pages at best.",
    "Ten phones, two hundred thousand documents, five hundred hours of audio — all of it modelled.",
  ],
  [
    "What the AI does",
    "Retrieves a sample of what fits and reasons over it. What it missed is unknowable.",
    "Traverses the model and returns the complete matching set, every claim carrying its source.",
  ],
  [
    "Human judgment",
    "Lives outside the tool and is lost between sessions.",
    "Significance, highlights and Loupes are durable objects inside the case.",
  ],
  [
    "Confidentiality",
    "Evidence enters a shared, multi-tenant service.",
    "Single-tenant. Evidence stays in the customer's own instance.",
  ],
  [
    "Model dependence",
    "The language model is the product.",
    "Models are interchangeable components. The evidence layer is the product.",
  ],
]

export function DifferenceSection() {
  return (
    <section className="sec sec-paper" id="why-loupe">
      <div className="container">
        <SectionHead
          eyebrow="Compared with a general assistant"
          heading="The difference is what the answer is built on."
          lede="Every serious platform can point at a document. The question that decides an investigation is whether the answer came from a model of the whole case, or from whatever a retriever surfaced."
        />

        <Reveal className="cmp">
          <div className="cmp-head" aria-hidden="true">
            <span />
            <span>A general AI assistant</span>
            <span className="is-loupe">Loupe</span>
          </div>
          {differences.map(([label, generic, loupe]) => (
            <div className="cmp-row" key={label}>
              <strong>{label}</strong>
              <p data-label="A general AI assistant">{generic}</p>
              <p data-label="Loupe" className="is-loupe">
                {loupe}
              </p>
            </div>
          ))}
        </Reveal>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ economics */

const costLines = [
  ["Forensic extraction, per device", "$1,575 – $2,975", "Unchanged"],
  ["Processing", "$3 – $10 per gigabyte", "Replaced"],
  ["Hosting", "$5 – $15 per gigabyte, per month", "Replaced"],
  ["Examiner analysis", "$300 – $500 per hour", "Replaced"],
  ["Investigator and paralegal hours", "58 – 100 hours", "About half returned"],
]

export function EconomicsSection() {
  return (
    <section className="sec sec-paper" id="economics">
      <div className="container">
        <SectionHead
          eyebrow="What it replaces"
          heading="The budget already exists."
          lede="The choice is not between Loupe and another platform. It is between Loupe and what a serious matter costs today: a vendor per device, a hosting bill per gigabyte per month, an examiner by the hour, and a team stitching the pieces together by hand."
        />

        <div className="econ">
          <Reveal className="econ-table">
            <div className="econ-head" aria-hidden="true">
              <span>Per serious matter</span>
              <span>Today</span>
              <span>With Loupe</span>
            </div>
            {costLines.map(([label, cost, fate]) => (
              <div className="econ-row" key={label}>
                <strong>{label}</strong>
                <span className="fig">{cost}</span>
                <span className="fate">{fate}</span>
              </div>
            ))}
            <Source>
              Published 2026 eDiscovery processing and hosting rates · forensic vendor rate cards ·
              RAND National Public Defense Workload Study
            </Source>
          </Reveal>

          <Reveal className="econ-side" delay={0.06}>
            <div className="figure">
              <b>$4,350</b>
              <p>
                a month to keep a 435-gigabyte matter hosted — more than $100,000 across two years.
                What that buys is a spreadsheet.
              </p>
            </div>
            <p>
              Sixty to a hundred hours go into handling evidence on a serious matter before anyone
              has answered a question about it. The largest line, hosting, is charged per gigabyte
              per month, so it grows with exactly the material that makes the case.
            </p>
            <p>
              Extraction is untouched — devices still go to a vendor. Everything downstream of it is
              what changes.
            </p>
          </Reveal>
        </div>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ audience */

export function AudienceSection() {
  return (
    <section className="sec sec-paper" id="audience">
      <div className="container">
        <SectionHead
          eyebrow="Who it's for"
          heading="Built for the practice that receives the evidence."
          lede="Not size or sector — the defining characteristic is that this buyer receives evidence rather than collecting it, receives it in formats built by the other side, and has had no way to analyse it properly."
        />

        <div className="aud">
          <Reveal as="article" className="aud-lead">
            <p className="eyebrow">Primary</p>
            <h3>Defence-side investigations and criminal defence</h3>
            <p>
              Boutique forensic and criminal-defence practices of ten to fifty people running
              federal and serious state matters — Big-Four-class casework without Big-Four tooling
              budgets, and no implementation resource to spare. Loupe is designed to be usable out
              of the box.
            </p>
          </Reveal>
          <Reveal as="article" delay={0.05}>
            <h3>Corporate investigations and compliance</h3>
            <p>
              The same product on larger matters, where document and financial evidence carries the
              case and device data is a smaller part of the mix.
            </p>
          </Reveal>
          <Reveal as="article" delay={0.1}>
            <h3>Insurance SIU and fraud</h3>
            <p>
              Financial and document analysis at volume, in the fastest-growing category in the
              field and one where no platform is shut out on procurement grounds.
            </p>
          </Reveal>
        </div>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ trust */

export function ProofSection() {
  return (
    <section className="sec sec-paper sec-last" id="trust">
      <div className="container">
        <SectionHead
          eyebrow="Deployment and integrity"
          heading="Single-tenant, source-linked, auditable."
          lede="Loupe has carried federal matters to completion inside a working private-investigations practice — multi-gigabyte extractions, tens of thousands of curated transactions and full document corpora."
        />

        <div className="deploy-grid">
          <Reveal as="article">
            <h3>One isolated stack per customer</h3>
            <p>
              Evidence never enters a shared service, and the instance can sit in the jurisdiction
              the matter requires, including on-premises.
            </p>
          </Reveal>
          <Reveal as="article" delay={0.05}>
            <h3>Provenance by construction</h3>
            <p>
              Every object in the case model carries the file, page and passage it came from, so a
              finding can always be walked back to the evidence under it.
            </p>
          </Reveal>
          <Reveal as="article" delay={0.1}>
            <h3>Access enforced per case</h3>
            <p>
              Every route verifies case membership, so no user reaches a matter they are not on.
              Investigator edits are recorded against the person who made them.
            </p>
          </Reveal>
          <Reveal as="article" delay={0.15}>
            <h3>Staged onboarding</h3>
            <p>
              External evidence enters behind a security-gated release process covering isolation,
              backup and legal review.
            </p>
          </Reveal>
        </div>
      </div>
    </section>
  )
}
