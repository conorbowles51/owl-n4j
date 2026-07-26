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
            Evidence infrastructure for complex investigations
          </div>
          <h1 className="hero-title hero-enter hero-enter-2">
            <span className="hero-title-line">Bring</span>
            <span className="hero-title-line">structure to</span>
            <span className="hero-title-line hero-title-accent">complex</span>
            <span className="hero-title-line hero-title-accent">investigations.</span>
          </h1>
          <p className="hero-lede hero-enter hero-enter-3">
            Loupe compiles documents, phone extractions, financial records and media into one
            permanent case model—where every fact links back to the page, quote and file it came
            from.
          </p>
          <div className="hero-actions hero-enter hero-enter-4">
            <a className="button button-primary" href="#platform">
              See the platform
              <span className="button-arrow" aria-hidden="true">↓</span>
            </a>
            <button className="button button-ghost" type="button" onClick={onContact}>
              Request a walkthrough
              <span aria-hidden="true">↗</span>
            </button>
          </div>
          <div className="hero-proof hero-enter hero-enter-5" aria-label="Platform principles">
            <span>Whole-case, not prompt-sized</span>
            <span>Every answer source-linked</span>
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
        <span>Explore the workspace</span>
        <i aria-hidden="true" />
      </a>
    </section>
  )
}
