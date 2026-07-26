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
          <p className="section-index">Find the signal in everything</p>
          <h2>Bring the case.<br /><span>Keep the receipt.</span></h2>
          <p>
            See how Loupe turns complex evidence into connected, source-linked intelligence your
            team can explore, explain and defend.
          </p>
          <div className="final-audiences" aria-label="Teams Loupe supports">
            <span>Fraud teams</span>
            <span>Law enforcement</span>
            <span>Legal disputes</span>
            <span>Corporate investigations</span>
          </div>
          <button className="button button-primary button-large" type="button" onClick={onContact}>
            Request a private walkthrough <span aria-hidden="true">↗</span>
          </button>
        </Reveal>
      </div>
    </section>
  )
}
