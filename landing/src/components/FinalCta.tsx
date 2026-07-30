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
          <p className="section-index">Bring a matter</p>
          <h2>
            The fastest way to understand Loupe
            <br />
            <span>is to watch it work a case.</span>
          </h2>
          <p>
            Load a real extraction and a real disclosure bundle, then ask a question that spans both.
            That takes about ten minutes — and it is not a demo anyone else can run.
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
