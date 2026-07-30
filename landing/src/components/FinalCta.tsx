import { Reveal } from "../lib/Reveal"

interface FinalCtaProps {
  onContact: () => void
}

export function FinalCta({ onContact }: FinalCtaProps) {
  return (
    <section className="final-cta" id="contact">
      <div className="container final-cta-inner">
        <Reveal>
          <p className="eyebrow">Bring a matter</p>
          <h2>See it work a real case.</h2>
          <p>
            Load an extraction and a disclosure bundle, then ask a question that spans both. It
            takes about ten minutes.
          </p>
          <button className="button button-primary button-large" type="button" onClick={onContact}>
            Request a walkthrough
          </button>
          <a className="final-cta-email" href="mailto:sales@loupe.ie">
            sales@loupe.ie
          </a>
        </Reveal>
      </div>
    </section>
  )
}
