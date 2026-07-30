import { HeroScene } from "./HeroScene"

interface HeroProps {
  onContact: () => void
}

export function Hero({ onContact }: HeroProps) {
  return (
    <section className="hero" id="top">
      <div className="hero-grid" aria-hidden="true" />
      <div className="container hero-layout">
        <div className="hero-copy">
          <div className="hero-eyebrow hero-enter hero-enter-1">
            <span className="status-dot" />
            Find the signal in everything
          </div>
          <h1 className="hero-title hero-enter hero-enter-2">
            <span className="hero-title-line">Everyone can cite</span>
            <span className="hero-title-line">a document.</span>
            <span className="hero-title-line hero-title-accent">Nobody can query</span>
            <span className="hero-title-line hero-title-accent">a case.</span>
          </h1>
          <p className="hero-lede hero-enter hero-enter-3">
            Loupe resolves phone extractions, documents, financial records and recorded media into
            one connected model of the case — so a question can be put to all of it at once, and
            every answer carries the file, page and passage it came from.
          </p>
          <div className="hero-actions hero-enter hero-enter-4">
            <button className="button button-primary" type="button" onClick={onContact}>
              Request a private walkthrough
              <span aria-hidden="true">↗</span>
            </button>
            <a className="button button-ghost" href="#origin">
              Why we built it
              <span className="button-arrow" aria-hidden="true">
                ↓
              </span>
            </a>
          </div>
          <div className="hero-proof hero-enter hero-enter-5" aria-label="Where Loupe stands today">
            <span>Built inside a working investigations practice</span>
            <span>Federal matters carried to completion</span>
            <span>Single-tenant — evidence stays in your instance</span>
          </div>
        </div>

        <div className="hero-identity hero-enter hero-enter-3" aria-hidden="true">
          <HeroScene />
        </div>
      </div>

      <div className="hero-transition" aria-hidden="true" />

      <a className="scroll-cue" href="#origin" aria-label="Scroll to why Loupe was built">
        <span>Follow the evidence</span>
        <i aria-hidden="true" />
      </a>
    </section>
  )
}
