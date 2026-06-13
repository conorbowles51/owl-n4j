import { Reveal } from '../lib/Reveal';

interface FinalCtaProps {
  onBookDemo: () => void;
}

export function FinalCta({ onBookDemo }: FinalCtaProps) {
  return (
    <section className="section final-cta">
      <div className="container final-cta-inner">
        <Reveal>
          <p className="kicker">Get started</p>
        </Reveal>
        <Reveal delay={0.08}>
          <h2 className="section-title final-cta-title">Bring Arclight to your next case.</h2>
        </Reveal>
        <Reveal delay={0.16}>
          <p className="section-lede final-cta-lede">
            We onboard a limited number of firms at a time. Book a demo and see your kind of
            casework, illuminated.
          </p>
        </Reveal>
        <Reveal delay={0.24}>
          <button type="button" className="btn btn-primary final-cta-btn" onClick={onBookDemo}>
            Book a demo
          </button>
        </Reveal>
      </div>
    </section>
  );
}
