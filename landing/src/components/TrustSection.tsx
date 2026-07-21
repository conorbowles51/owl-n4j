import { Reveal } from "../lib/Reveal"

const controls = [
  ["Deployment boundary", "Designed to operate inside controlled environments."],
  ["Role-aware access", "Keep sensitive work visible to the right people."],
  ["Source provenance", "Preserve the path from insight back to origin."],
  ["Portable outputs", "Move findings into the formats your work requires."],
]

export function TrustSection() {
  return (
    <section className="trust-section" id="control">
      <div className="container trust-layout">
        <Reveal className="trust-copy">
          <p className="section-index">04 / Control</p>
          <h2>Clarity without<br />losing control.</h2>
          <p>
            Powerful analysis means little without clear boundaries, accountable access and a
            visible connection to the underlying material.
          </p>
          <ul>
            {controls.map(([title, body], index) => (
              <li key={title}>
                <span>0{index + 1}</span>
                <div><strong>{title}</strong><p>{body}</p></div>
              </li>
            ))}
          </ul>
        </Reveal>
        <Reveal className="control-console" delay={0.15}>
          <div className="console-header">
            <span>Loupe / Control plane</span>
            <b><i /> Operational</b>
          </div>
          <div className="console-radar" aria-hidden="true">
            <div className="radar-grid" />
            <div className="radar-sweep" />
            <i className="radar-point radar-point-a" />
            <i className="radar-point radar-point-b" />
            <i className="radar-point radar-point-c" />
            <span className="radar-core" />
          </div>
          <div className="console-readouts">
            <div><span>Access model</span><strong>Role aware</strong></div>
            <div><span>Provenance</span><strong>Source linked</strong></div>
            <div><span>Workspace</span><strong>Controlled</strong></div>
          </div>
          <div className="console-log">
            <span>12:42:08</span><p>Source connection verified</p><b>OK</b>
            <span>12:42:11</span><p>Workspace boundary checked</p><b>OK</b>
            <span>12:42:14</span><p>Provenance path available</p><b>OK</b>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
