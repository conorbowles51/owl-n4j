import { HeroScene } from './hero-scene/HeroScene';

interface HeroProps {
  onBookDemo: () => void;
}

export function Hero({ onBookDemo }: HeroProps) {
  return (
    <section className="hero" id="top">
      <div className="hero-scene-wrap">
        <HeroScene />
      </div>
      <div className="container hero-content">
        <p className="kicker hero-kicker">Investigation intelligence platform</p>
        <h1 className="hero-title">
          Every case hides
          <br />
          a structure.
          <span className="hero-title-accent"> Arclight reveals it.</span>
        </h1>
        <p className="hero-sub">
          Turn documents, phone extractions, financial records, and hours of audio into one
          connected, searchable graph of your case — every answer cited back to its source.
        </p>
        <div className="hero-actions">
          <button type="button" className="btn btn-primary" onClick={onBookDemo}>
            Book a demo
          </button>
          <a href="#how-it-works" className="btn btn-ghost">
            See how it works
          </a>
        </div>
      </div>
      <p className="micro hero-fig" aria-hidden="true">
        Fig. 01 — Evidence field, illuminated
      </p>
      <div className="hero-fade" aria-hidden="true" />
    </section>
  );
}
