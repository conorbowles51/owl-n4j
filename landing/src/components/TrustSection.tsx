import { Reveal } from "../lib/Reveal"

const controls = [
  {
    number: "01",
    title: "One customer. One isolated stack.",
    body: "Each customer gets a dedicated instance with private operating boundaries. Evidence never trains anyone else's model.",
    meta: "Single tenant",
  },
  {
    number: "02",
    title: "Provenance survives the case",
    body: "Quotes, source locations, confidence and review state accumulate through merges and re-ingestion rather than being overwritten.",
    meta: "Evidence integrity",
  },
  {
    number: "03",
    title: "AI stays inside the boundary",
    body: "Read-only case tools, prompt-injection defenses, run caps and investigator-approved changes constrain what automation may do.",
    meta: "Governed AI",
  },
  {
    number: "04",
    title: "Every operation can be accounted for",
    body: "Audit history, user attribution and a per-operation AI cost ledger make activity explainable to operators and reviewers.",
    meta: "Operational control",
  },
]

export function TrustSection() {
  return (
    <section className="trust-section trust-section-clean" id="control">
      <div className="container">
        <Reveal className="trust-heading">
          <p className="section-index">06 / Evidence infrastructure</p>
          <h2>
            Built for the moment
            <br />
            <span>the answer is challenged.</span>
          </h2>
          <p>
            Investigation teams cannot send evidence to an opaque shared cloud and hope for the
            best. Loupe is designed around isolation, provenance and control from the first file to
            the final report.
          </p>
        </Reveal>

        <div className="trust-grid trust-grid-clean">
          {controls.map((control, index) => (
            <Reveal as="article" className="trust-control trust-control-clean" delay={index * 0.07} key={control.number}>
              <div className="trust-control-top">
                <span>{control.number}</span>
                <b>
                  <i /> {control.meta}
                </b>
              </div>
              <h3>{control.title}</h3>
              <p>{control.body}</p>
            </Reveal>
          ))}
        </div>

        <Reveal className="trust-manifesto trust-manifesto-clean">
          <span>The defensible chain</span>
          <p>
            Source to claim. Claim to finding. Finding to report. Every step stays visible, bounded
            and ready to be examined.
          </p>
        </Reveal>
      </div>
    </section>
  )
}
