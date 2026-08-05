import type { ReactNode } from "react"
import { scaleComparison } from "../data/claims"
import { Reveal } from "./primitives/Reveal"

/**
 * Act III — the argument. Four sections: why not a chatbot, what the platform
 * does, where it runs, who it is for. Everything here is claim-level; the
 * evidence for these claims is Act II, so nothing below restates it.
 */

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
    <Reveal>
      <div className="sec-head">
        <p className="eyebrow">{eyebrow}</p>
        <h2>{heading}</h2>
        {lede ? <p className="sec-lede">{lede}</p> : null}
      </div>
    </Reveal>
  )
}

/* ------------------------------------------------------------------ difference */

interface DifferenceRow {
  label: string
  generic: string
  loupe: string
  /** Optional red receipt under the Loupe cell — the symbol the page has taught. */
  receipt?: string
}

// Six rows in v1, four now. Human judgment lives in the capability grid,
// confidentiality in the deployment section, and model dependence was cut:
// the table led with its weakest arguments and buried bounded claims.
const differences: DifferenceRow[] = [
  {
    label: "What it will claim",
    generic:
      "Whatever reads well. Gaps are filled fluently, and a wrong answer looks identical to a right one.",
    loupe:
      "Only what the sources support. Claims the model cannot ground are quarantined, and the agent asks a clarifying question rather than guess.",
  },
  {
    label: "Where the case lives",
    generic: "A context window, gone when the session ends.",
    loupe: "A persistent case model that outlives every conversation, handover and review.",
  },
  {
    label: "What an answer is built on",
    generic: "A retrieved sample of whatever fits. What it missed is unknowable.",
    loupe:
      "A traversal of the whole model — the complete matching set, every claim carrying its source.",
    receipt: "03_bank_statement_nexus.pdf, p.1",
  },
  {
    label: "Scale",
    generic: "Hundreds of pages at best.",
    loupe: scaleComparison,
  },
]

export function DifferenceSection() {
  return (
    <section className="sec" id="why-loupe">
      <div className="container">
        <SectionHead
          eyebrow="Compared with a general assistant"
          heading="It will not claim what it cannot cite."
          lede="Any capable model can produce a confident paragraph about a case. Loupe is built to stay inside the evidence: claims it cannot ground are quarantined, the agent asks before guessing, and no answer exceeds its sources. The rest of the difference follows from that."
        />

        <Reveal delay={80}>
          <div className="cmp">
            <div className="cmp-head" aria-hidden="true">
              <span />
              <span>A general AI assistant</span>
              <span className="is-loupe">Loupe</span>
            </div>
            {differences.map((row) => (
              <div className="cmp-row" key={row.label}>
                <strong>{row.label}</strong>
                <p data-label="A general AI assistant">{row.generic}</p>
                <p data-label="Loupe" className="is-loupe">
                  {row.loupe}
                  {row.receipt ? (
                    <>
                      <br />
                      <span className="receipt">{row.receipt}</span>
                    </>
                  ) : null}
                </p>
              </div>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ capability */

// Six groups of four in v1. Deployment folded into the section that follows,
// device and document intake merged into one column — the grid answers
// "what else does it do" in a single screen instead of re-arguing Act II.
const capability = [
  {
    group: "Evidence in",
    items: [
      "Cellebrite UFDR and multi-device extraction parsing",
      "Automatic text recognition for scanned documents, page by page",
      "Speaker-separated, timestamped and searchable transcription",
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
      "Investigator-authored entities, relationships and case notes",
      "Tables, charts and exports that stay attached to the case",
    ],
  },
  {
    group: "The agent",
    items: [
      "Tools across the case model, not a chat box over files",
      "Grouping, aggregation and visualisation from a plain-language instruction",
      "Clarifying questions instead of guesses; the investigator disposes",
      "Safe read-only database access for aggregate queries",
    ],
  },
]

export function CapabilitySection() {
  return (
    <section className="sec sec-tight" id="capability">
      <div className="container">
        <SectionHead
          eyebrow="Capability"
          heading="What the platform does."
          lede="Every item below is in the product and demonstrable on a live matter."
        />

        <Reveal delay={80}>
          <div className="cap-grid">
            {capability.map((block) => (
              <article key={block.group}>
                <h3>{block.group}</h3>
                <ul>
                  {block.items.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ deployment */

const deployment = [
  {
    title: "Complete tenant isolation",
    body: "A dedicated instance per customer. Case data never shares a database, a queue or a network with another organisation's.",
  },
  {
    title: "Deploy where you need it",
    body: "Hosted in the region your legal, regulatory and operational requirements demand — including on-premises.",
  },
  {
    title: "Access enforced per case",
    body: "Membership is verified on every route, and investigator actions are recorded against the person who made them.",
  },
  {
    title: "Source-linked and auditable",
    body: "Every object carries the file, page, record or timestamp it came from, so findings trace back to the evidence.",
  },
]

export function ProofSection() {
  // id="deployment" is a nav target — keep it if this section is ever renamed.
  return (
    <section className="sec sec-tight" id="deployment">
      <div className="container">
        <SectionHead
          eyebrow="Deployment"
          heading="Your evidence. Your environment. Fully isolated."
          lede="Loupe runs as a dedicated, single-tenant instance for each customer, hosted in the region — or on-premises environment — your matter requires. Evidence is never mixed with another organisation's."
        />

        <Reveal delay={80}>
          <div className="deploy-grid">
            {deployment.map((item, i) => (
              <article key={item.title}>
                <p className="deploy-index">{String(i + 1).padStart(2, "0")}</p>
                <h3>{item.title}</h3>
                <p>{item.body}</p>
              </article>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ audience */

const audiences = [
  {
    title: "Defence-side investigations and criminal defence",
    body: "Boutique practices running federal and serious state matters — Big-Four-class casework without Big-Four tooling budgets, and no implementation resource to spare. Loupe is designed to be usable out of the box.",
  },
  {
    title: "Corporate investigations and compliance",
    body: "The same product on larger matters, where document and financial evidence carries the case and device data is a smaller part of the mix.",
  },
  {
    title: "Insurance SIU and fraud",
    body: "Financial and document analysis at volume, in the fastest-growing category in the field.",
  },
]

export function AudienceSection() {
  return (
    <section className="sec" id="audience">
      <div className="container">
        <SectionHead
          eyebrow="Who it's for"
          heading="Built for the practice that receives the evidence."
          lede="Not size or sector — the defining characteristic is that this buyer receives evidence rather than collecting it, in formats built by the other side, with no proper way to analyse it."
        />

        <Reveal delay={80}>
          <div className="aud">
            {audiences.map((audience, i) => (
              <article key={audience.title}>
                <p className="aud-index">{String(i + 1).padStart(2, "0")}</p>
                <h3>{audience.title}</h3>
                <p>{audience.body}</p>
              </article>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  )
}
