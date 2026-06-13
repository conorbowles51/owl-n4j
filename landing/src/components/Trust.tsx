import { Reveal } from '../lib/Reveal';

const PILLARS = [
  {
    num: '01',
    title: 'Single-tenant by design',
    body: 'Every customer runs a fully isolated instance — separate databases, separate storage, no shared infrastructure.',
  },
  {
    num: '02',
    title: 'Citations, not confidence',
    body: 'AI output links to the document and page it came from. If it can’t be sourced, it isn’t an answer.',
  },
  {
    num: '03',
    title: 'No training on your data',
    body: 'Your evidence is processed under strict no-training terms. Your cases never improve anyone else’s model.',
  },
  {
    num: '04',
    title: 'Your data stays yours',
    body: 'Export everything at any time. When you leave, your instance — and every byte in it — goes with you.',
  },
];

export function Trust() {
  return (
    <section className="section trust" id="security">
      <div className="container">
        <Reveal>
          <p className="kicker">Security &amp; trust</p>
        </Reveal>
        <Reveal delay={0.08}>
          <h2 className="section-title">Built for evidence you can’t afford to mishandle.</h2>
        </Reveal>
        <Reveal delay={0.14}>
          <p className="section-lede">
            Investigation data is among the most sensitive there is. Arclight’s architecture
            starts from that assumption.
          </p>
        </Reveal>
        <ul className="trust-grid">
          {PILLARS.map((pillar, i) => (
            <Reveal as="li" key={pillar.num} delay={0.08 + i * 0.08} className="trust-card">
              <span className="micro trust-num">{pillar.num}</span>
              <h3 className="trust-title">{pillar.title}</h3>
              <p className="trust-body">{pillar.body}</p>
            </Reveal>
          ))}
        </ul>
      </div>
    </section>
  );
}
