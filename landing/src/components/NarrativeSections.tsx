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
