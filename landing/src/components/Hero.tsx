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
          <p className="eyebrow hero-enter hero-enter-1">
            Investigation platform for complex investigations
          </p>
          <h1 className="hero-enter hero-enter-2">Query the whole case.</h1>
          <p className="hero-lede hero-enter hero-enter-3">
            Loupe resolves phone extractions, documents, financial records and audio into one
            connected model of the case — so a question reaches all of it at once, and every answer
            carries the file, page and passage behind it.
          </p>
          <div className="hero-actions hero-enter hero-enter-4">
            <button className="button button-primary" type="button" onClick={onContact}>
              Request a walkthrough
            </button>
            <a className="button button-ghost" href="#platform">
              See the platform
            </a>
          </div>
          <p className="hero-proof hero-enter hero-enter-5">
            Every source, connected. Every finding, traceable.
          </p>
        </div>

        <div className="hero-identity hero-enter hero-enter-3" aria-hidden="true">
          <span className="hero-lens-halo" />
          <span className="identity-orbit identity-orbit-outer" />
          <span className="identity-orbit identity-orbit-inner" />
          <HeroScene />
        </div>
      </div>
    </section>
  )
}
