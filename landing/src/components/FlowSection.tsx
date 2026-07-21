import { Reveal } from "../lib/Reveal"

const steps = [
  ["01", "Ingest", "Bring every relevant source into one controlled workspace."],
  ["02", "Structure", "Resolve entities, events and relationships across the material."],
  ["03", "Explore", "Change perspective without breaking the chain of context."],
  ["04", "Explain", "Turn discoveries into a traceable, shareable understanding."],
]

export function FlowSection() {
  return (
    <section className="flow-section" id="approach">
      <div className="flow-orbit" aria-hidden="true">
        <i /><i /><i /><span />
      </div>
      <div className="container flow-content">
        <Reveal className="flow-statement">
          <p className="section-index">03 / Approach</p>
          <h2>Complexity in.<br /><span>Clarity out.</span></h2>
          <p>
            The path from source material to understanding should be continuous, visible and
            reversible. Loupe keeps it that way.
          </p>
        </Reveal>
        <ol className="flow-steps">
          {steps.map(([number, title, body], index) => (
            <Reveal as="li" delay={0.08 + index * 0.07} key={number}>
              <span>{number}</span>
              <div><h3>{title}</h3><p>{body}</p></div>
            </Reveal>
          ))}
        </ol>
      </div>
    </section>
  )
}
