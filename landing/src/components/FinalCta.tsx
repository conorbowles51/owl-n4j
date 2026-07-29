import { Reveal } from "../lib/Reveal"

interface FinalCtaProps {
  onContact: () => void
}

export function FinalCta({ onContact }: FinalCtaProps) {
  return (
    <section className="final-cta" id="contact">
      <div className="final-grid" aria-hidden="true" />
      <div className="final-lens" aria-hidden="true"><i /><i /></div>
      <div className="container final-cta-inner">
        <Reveal>
          <p className="section-index">See the whole case</p>
          <h2>Bring the evidence.<br /><span>Find the connections.</span></h2>
          <p>
            See how Loupe gives your team a connected, source-linked view of complex evidence—from
            first review to final finding.
          </p>
          <button className="button button-primary button-large" type="button" onClick={onContact}>
            Request a private walkthrough <span aria-hidden="true">↗</span>
          </button>
          <a className="final-cta-email" href="mailto:sales@loupe.ie">sales@loupe.ie</a>
        </Reveal>
      </div>
    </section>
  )
}
