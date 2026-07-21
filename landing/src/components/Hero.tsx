import { lazy, Suspense } from "react"

const HeroScene = lazy(() =>
  import("./HeroScene").then(({ HeroScene: Scene }) => ({ default: Scene })),
)

interface HeroProps {
  onContact: () => void
}

const signals = ["Documents", "Communications", "Entities", "Events", "Transactions", "Locations"]

export function Hero({ onContact }: HeroProps) {
  return (
    <section className="hero" id="top">
      <div className="hero-atmosphere" aria-hidden="true" />
      <div className="hero-scene">
        <Suspense fallback={<div className="hero-scene-fallback" aria-hidden="true" />}>
          <HeroScene />
        </Suspense>
      </div>
      <div className="container hero-layout">
        <div className="hero-copy">
          <div className="hero-eyebrow hero-enter hero-enter-1">
            <span className="status-dot" />
            Connected intelligence, made visible
          </div>
          <h1 className="hero-title hero-enter hero-enter-2">
            Find the signal
            <span>in everything.</span>
          </h1>
          <p className="hero-lede hero-enter hero-enter-3">
            Loupe turns complex information into one connected, explorable intelligence layer—so
            relationships emerge, chronology becomes clear, and every insight leads back to its source.
          </p>
          <div className="hero-actions hero-enter hero-enter-4">
            <a className="button button-primary" href="#platform">
              Explore the platform
              <span className="button-arrow" aria-hidden="true">↓</span>
            </a>
            <button className="button button-ghost" type="button" onClick={onContact}>
              Request a walkthrough
              <span aria-hidden="true">↗</span>
            </button>
          </div>
          <div className="hero-proof hero-enter hero-enter-5" aria-label="Platform principles">
            <span>One connected model</span>
            <span>Every insight traceable</span>
          </div>
        </div>
      </div>
      <div className="signal-ribbon" aria-label="Information Loupe can connect">
        <div className="signal-track">
          {[...signals, ...signals].map((signal, index) => (
            <span key={`${signal}-${index}`}>
              {signal}
              <i aria-hidden="true" />
            </span>
          ))}
        </div>
      </div>
      <a className="scroll-cue" href="#platform" aria-label="Scroll to platform overview">
        <span>Scroll to observe</span>
        <i aria-hidden="true" />
      </a>
    </section>
  )
}
