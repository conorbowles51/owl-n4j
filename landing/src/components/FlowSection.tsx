import { Reveal } from "../lib/Reveal"

const steps = [
  ["01", "Ingest", "Documents, devices, ledgers and media enter one controlled workspace."],
  ["02", "Ground", "Facts retain the verbatim quote, source location, confidence and review state."],
  ["03", "Connect", "People, events, money and places resolve without losing what they came from."],
  ["04", "Explore", "Graph, timeline, map, table and ledger stay on the same underlying case."],
  ["05", "Prove", "Open the evidence behind a finding at the right page, passage or record."],
]

export function FlowSection() {
  return (
    <section className="provenance-section" id="approach">
      <div className="container">
        <Reveal className="grounding-heading">
          <p className="section-index">03 / Provenance, end to end</p>
          <h2>
            Every claim
            <br />
            <span>carries its receipt.</span>
          </h2>
          <p>
            Provenance is not a citation added after the answer. It is part of the case model:
            attached to facts, preserved through entity resolution and visible wherever the
            investigation moves.
          </p>
        </Reveal>

        <div className="provenance-layout">
          <Reveal className="provenance-capture" delay={0.12}>
            <div className="product-capture-bar">
              <span>
                <i aria-hidden="true" />
                Actual product view
              </span>
              <strong>Timeline details</strong>
              <small>Fictional demonstration case</small>
            </div>
            <div className="provenance-image">
              <img
                src="/product/loupe-timeline-demo.png"
                alt="Loupe timeline with a selected communication, source-backed verified fact and exact source page visible in the details panel."
                width="2558"
                height="1265"
                loading="lazy"
                decoding="async"
              />
            </div>
            <div className="product-caption">
              <span>Source-linked by design</span>
              <p>
                Select an event, inspect the verified fact and move directly to the source document
                and page that supports it.
              </p>
              <a href="/product/loupe-timeline-demo.png" target="_blank" rel="noreferrer">
                View full capture <i aria-hidden="true">↗</i>
              </a>
            </div>
          </Reveal>

          <ol className="provenance-steps">
            {steps.map(([number, title, body], index) => (
              <Reveal as="li" delay={0.08 + index * 0.055} key={number}>
                <span>{number}</span>
                <div>
                  <h3>{title}</h3>
                  <p>{body}</p>
                </div>
              </Reveal>
            ))}
          </ol>
        </div>
      </div>
    </section>
  )
}
