import { Reveal } from "../lib/Reveal"

const comparisonRows = [
  ["Where the case lives", "A temporary context window", "A permanent, queryable case model"],
  ["What fits", "The files and pages in the prompt", "The complete evidence corpus"],
  ["What answers contain", "Fluent prose", "Claims linked to the exact source"],
  ["Where judgment lives", "Outside the conversation", "Inside highlights, Significant and Loupes"],
  ["What survives", "A chat transcript", "Graphs, tables, timelines, maps and reports"],
]

const capacities = [
  ["35 GB", "single phone report"],
  ["50k", "transactions per case"],
  ["10k+", "entities per case"],
]

const principles = [
  ["Compile, do not prompt", "The case becomes durable structure held beyond any conversation."],
  ["Cite, do not hope", "Every fact carries its quote, source location, confidence and review state."],
  ["Keep, do not repeat", "Investigator judgment and AI outputs persist as work the team can revisit."],
]

export function CapabilityMatrix() {
  return (
    <section className="difference-section" id="capabilities">
      <div className="container">
        <Reveal className="evidence-layer-heading">
          <p className="section-index">02 / The architectural difference</p>
          <h2>
            The whole case.
            <br />
            <span>Not the part that fits in a prompt.</span>
          </h2>
          <p>
            A chatbot reads a selection and produces prose. Loupe compiles the complete case into a
            permanent, provenance-carrying structure, then lets AI operate on that structure under
            guardrails.
          </p>
        </Reveal>

        <div className="difference-layout">
          <Reveal className="difference-statement" delay={0.08}>
            <span>The honest answer</span>
            <blockquote>
              The model is a component.
              <strong>The evidence layer is the product.</strong>
            </blockquote>
            <p>
              Documents, phone extractions, financial records and media resolve into one model of
              the people, events, money, places and sources inside the case.
            </p>
          </Reveal>

          <Reveal className="difference-table" delay={0.14}>
            <div role="table" aria-label="Straight LLM and Loupe comparison">
              <div className="difference-row difference-head" role="row">
                <span role="columnheader">What changes</span>
                <span role="columnheader">A straight LLM</span>
                <span role="columnheader">Loupe</span>
              </div>
              {comparisonRows.map(([label, llm, loupe]) => (
                <div className="difference-row" role="row" key={label}>
                  <strong role="cell">{label}</strong>
                  <span role="cell">{llm}</span>
                  <span role="cell">
                    <i aria-hidden="true" />
                    {loupe}
                  </span>
                </div>
              ))}
            </div>
          </Reveal>
        </div>

        <Reveal className="difference-principles">
          {principles.map(([title, body], index) => (
            <article key={title}>
              <span>0{index + 1}</span>
              <h3>{title}</h3>
              <p>{body}</p>
            </article>
          ))}
        </Reveal>

        <Reveal className="case-scale" delay={0.08}>
          <div className="case-scale-intro">
            <span>Designed for case scale</span>
            <p>Built for the volume serious investigations actually produce.</p>
          </div>
          {capacities.map(([value, label]) => (
            <div className="case-scale-stat" key={label}>
              <strong>{value}</strong>
              <span>{label}</span>
            </div>
          ))}
        </Reveal>
      </div>
    </section>
  )
}
