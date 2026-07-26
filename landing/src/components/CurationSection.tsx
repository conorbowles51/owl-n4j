import { Reveal } from "../lib/Reveal"

const loupePrinciples = [
  {
    number: "01",
    title: "Highlight what matters",
    body: "Promote the exact passage, entity or event that deserves investigative attention. Its source comes with it.",
  },
  {
    number: "02",
    title: "Bind evidence into meaning",
    body: "A Loupe gives a collection its own identity and explanation: what this evidence shows and why it belongs together.",
  },
  {
    number: "03",
    title: "Change the view, keep the object",
    body: "Read the same Loupe as a timeline, graph or evidence set without rebuilding the work or losing provenance.",
  },
]

export function CurationSection() {
  return (
    <section className="loupe-section" id="curation">
      <div className="container">
        <Reveal className="curation-heading">
          <p className="section-index">04 / The namesake object</p>
          <h2>
            Gather the evidence.
            <br />
            <span>Examine it through a Loupe.</span>
          </h2>
          <p>
            Automated extraction is the floor, not the ceiling. Investigators decide what matters,
            then preserve that judgment as durable, source-linked structure the whole system
            understands.
          </p>
        </Reveal>

        <div className="loupe-definition-layout">
          <Reveal className="loupe-definition" delay={0.08}>
            <span>Loupe / noun</span>
            <blockquote>
              A bonded collection of evidence, assembled to explain
              <strong>an event, a sequence or a thing.</strong>
            </blockquote>
            <p>
              Bind highlighted passages, documents, entities and events into a fully evidenced
              narrative. Each element stays traceable to its source; the collection carries the
              meaning above its parts.
            </p>
          </Reveal>

          <Reveal className="loupe-capture" delay={0.14}>
            <div className="product-capture-bar">
              <span>
                <i aria-hidden="true" />
                Actual product view
              </span>
              <strong>Significant layer</strong>
              <small>Fictional demonstration case</small>
            </div>
            <div className="loupe-image">
              <img
                src="/product/loupe-graph-demo.png"
                alt="Loupe graph showing the current product's All data and Significant layer controls alongside a selected case entity."
                width="2558"
                height="1265"
                loading="lazy"
                decoding="async"
              />
            </div>
            <div className="product-caption">
              <span>Investigator judgment, made durable</span>
              <p>
                Project any case view down to the Significant layer, then build Loupes from the
                evidence that matters.
              </p>
              <a href="/product/loupe-graph-demo.png" target="_blank" rel="noreferrer">
                View full capture <i aria-hidden="true">↗</i>
              </a>
            </div>
          </Reveal>
        </div>

        <Reveal className="loupe-principles">
          {loupePrinciples.map((principle) => (
            <article key={principle.number}>
              <span>{principle.number}</span>
              <h3>{principle.title}</h3>
              <p>{principle.body}</p>
            </article>
          ))}
        </Reveal>

        <Reveal className="hypothesis-statement">
          <span>The investigation starts with a theory</span>
          <p>
            Loupe helps assemble what supports it, hunt what breaks it and expose what should exist
            in the case—but does not.
          </p>
        </Reveal>
      </div>
    </section>
  )
}
