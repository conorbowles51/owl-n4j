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
            Built for complex, evidence-heavy investigations
          </div>
          <h1 className="hero-title hero-enter hero-enter-2">
            <span className="hero-title-line">Query the case.</span>
            <span className="hero-title-line hero-title-accent">Not just the</span>
            <span className="hero-title-line hero-title-accent">documents.</span>
          </h1>
          <p className="hero-lede hero-enter hero-enter-3">
            Loupe turns phone extractions, documents, financial records, audio, video, and images
            into one connected case model—so investigators can work the whole matter at once and
            trace every claim back to its source.
          </p>
          <div className="hero-actions hero-enter hero-enter-4">
            <a className="button button-primary" href="#platform">
              Explore the case model
              <span className="button-arrow" aria-hidden="true">↓</span>
            </a>
            <button className="button button-ghost" type="button" onClick={onContact}>
              Request a private walkthrough
              <span aria-hidden="true">↗</span>
            </button>
          </div>
          <div className="hero-proof hero-enter hero-enter-5" aria-label="Platform principles">
            <span>Whole-case, not prompt-sized</span>
            <span>Every claim source-linked</span>
            <span>Single-tenant by design</span>
          </div>
        </div>

        <div className="hero-identity hero-enter hero-enter-3" aria-hidden="true">
          <div className="identity-orbit identity-orbit-outer" />
          <div className="identity-orbit identity-orbit-inner" />
          <HeroScene />
        </div>
      </div>

      <div className="hero-transition" aria-hidden="true" />

      <a className="scroll-cue" href="#platform" aria-label="Scroll to platform overview">
        <span>Follow the evidence</span>
        <i aria-hidden="true" />
      </a>
    </section>
  )
}
