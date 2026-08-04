import type { ReactNode } from "react"
import { scaleComparison } from "../data/claims"
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

/* ------------------------------------------------------------------ evidence */

type EvidenceEntity = "communication" | "document" | "financial" | "event"

function EvidenceIcon({ entity }: { entity: EvidenceEntity }) {
  let paths: ReactNode

  switch (entity) {
    case "communication":
      paths = (
        <>
          <rect x="7" y="3" width="10" height="18" rx="2.25" />
          <path d="M10 6h4M11 18h2" />
        </>
      )
      break
    case "document":
      paths = (
        <>
          <path d="M6.5 3.5h7l4 4v13h-11z" />
          <path d="M13.5 3.5v4h4M9.5 12h5M9.5 15.5h5" />
        </>
      )
      break
    case "financial":
      paths = (
        <>
          <rect x="3.5" y="5" width="17" height="14" rx="1.8" />
          <path d="M3.5 9h17M9 5v14M14.5 9v10M9 14h11" />
        </>
      )
      break
    case "event":
      paths = <path d="M4 13v-2M8 16V8M12 19V5M16 16V8M20 13v-2" />
      break
  }

  return (
    <span className="evidence-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none">
        {paths}
      </svg>
    </span>
  )
}

const evidence: Array<{
  entity: EvidenceEntity
  title: string
  detail: string
}> = [
  {
    entity: "communication",
    title: "Device evidence",
    detail:
      "Explore calls, messages, contacts, locations and app activity across every device in the matter.",
  },
  {
    entity: "document",
    title: "Documents",
    detail:
      "Search statements, reports, filings and disclosure at scale, with every result linked back to its source.",
  },
  {
    entity: "financial",
    title: "Financial records",
    detail:
      "Follow transactions across accounts, entities and institutions to uncover patterns and relationships.",
  },
  {
    entity: "event",
    title: "Recorded media",
    detail:
      "Turn calls and interviews into searchable, speaker-attributed transcripts connected to the wider case.",
  },
]

export function ProblemSection() {
  return (
    <section className="sec sec-paper" id="problem">
      <div className="container">
        <SectionHead
          eyebrow="The evidence"
          heading="Bring every source into one connected investigation."
          lede="Loupe brings device data, documents, financial records and recorded media together in a single, searchable case model."
        />

        <div className="evidence-rows">
          {evidence.map((item, i) => (
            <Reveal as="article" key={item.title} delay={i * 0.04}>
              <div className="evidence-title">
                <EvidenceIcon entity={item.entity} />
                <h3>{item.title}</h3>
              </div>
              <p>{item.detail}</p>
            </Reveal>
          ))}
        </div>

        <Reveal className="split-note">
          <div>
            <h3>Move beyond reviewing files.</h3>
            <p>
              Traditional review tools treat each source as a separate collection. Loupe preserves
              the structure of device data, documents, transactions and conversations, then connects
              them around the people, organisations, places and events that matter.
            </p>
          </div>
          <div>
            <p>
              Investigators can move from a person to their communications, transactions and
              supporting documents in one workflow. Every conclusion remains traceable to the
              original file, page, record or timestamp.
            </p>
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
  ["Scale", "Hundreds of pages at best.", scaleComparison],
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
          <Reveal as="article">
            <p className="aud-index">01</p>
            <h3>Defence-side investigations and criminal defence</h3>
            <p>
              Boutique forensic and criminal-defence practices of ten to fifty people running
              federal and serious state matters — Big-Four-class casework without Big-Four tooling
              budgets, and no implementation resource to spare. Loupe is designed to be usable out
              of the box.
            </p>
          </Reveal>
          <Reveal as="article" delay={0.05}>
            <p className="aud-index">02</p>
            <h3>Corporate investigations and compliance</h3>
            <p>
              The same product on larger matters, where document and financial evidence carries the
              case and device data is a smaller part of the mix.
            </p>
          </Reveal>
          <Reveal as="article" delay={0.1}>
            <p className="aud-index">03</p>
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
    <section className="sec sec-paper" id="trust">
      <div className="container">
        <Reveal className="trust-feature">
          <div className="trust-feature-copy">
            <p className="eyebrow">Deployment and data isolation</p>
            <h2>
              <span>Your evidence.</span>
              <span>Your environment.</span>
              <span>Fully isolated.</span>
            </h2>
            <p>
              Loupe runs as a dedicated, single-tenant instance for each customer. Your data is
              never mixed with another organisation&apos;s and can be hosted in the region — or
              on-premises environment — your matter requires.
            </p>
          </div>

          <div className="trust-summary" aria-hidden="true" />
        </Reveal>

        <div className="deploy-grid">
          <Reveal as="article">
            <p className="deploy-index">01</p>
            <h3>Complete tenant isolation</h3>
            <p>
              Each customer receives a dedicated Loupe instance. Your evidence and case data stay
              separate from every other organisation.
            </p>
          </Reveal>
          <Reveal as="article" delay={0.05}>
            <p className="deploy-index">02</p>
            <h3>Deploy where you need it</h3>
            <p>
              Host Loupe in the region your legal, regulatory and operational requirements demand,
              including on-premises.
            </p>
          </Reveal>
          <Reveal as="article" delay={0.1}>
            <p className="deploy-index">03</p>
            <h3>Access enforced per case</h3>
            <p>
              Membership is verified on every route, and investigator actions are recorded against
              the person who made them.
            </p>
          </Reveal>
          <Reveal as="article" delay={0.15}>
            <p className="deploy-index">04</p>
            <h3>Source-linked and auditable</h3>
            <p>
              Every object carries the file, page, record or timestamp it came from, so findings can
              always be traced back to the evidence.
            </p>
          </Reveal>
        </div>
      </div>
    </section>
  )
}
