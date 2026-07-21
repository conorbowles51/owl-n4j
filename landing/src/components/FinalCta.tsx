import { Reveal } from "../lib/Reveal"

interface FinalCtaProps {
  onContact: () => void
}
export function FinalCta({ onContact }: FinalCtaProps) {
  return (
    <section className="final-cta" id="contact">
      <div className="final-grid" aria-hidden="true" />
      <div className="final-lens" aria-hidden="true"><i /><i /><span /></div>
      <div className="container final-cta-inner">
        <Reveal>
          <p className="section-index">The next perspective</p>
          <h2>Make complexity<br /><span>observable.</span></h2>
          <p>See how Loupe can turn disconnected material into a connected body of intelligence.</p>
          <button className="button button-primary button-large" type="button" onClick={onContact}>
            Request a private walkthrough <span aria-hidden="true">↗</span>
          </button>
        </Reveal>
      </div>
    </section>
  )
}
