import { Reveal } from '../lib/Reveal';

const STEPS = [
  {
    num: '01',
    title: 'Ingest everything',
    body: 'Drop in the whole case file — PDFs, spreadsheets, images, email, audio, video, Cellebrite phone extractions. Arclight reads, transcribes, and OCRs all of it.',
  },
  {
    num: '02',
    title: 'The graph assembles',
    body: 'Every person, company, account, location, and event is extracted and resolved — “J. Smith” and “Jonathan Smith” become one node, connected across every document they appear in.',
  },
  {
    num: '03',
    title: 'Interrogate with confidence',
    body: 'Ask questions in plain English. Every answer carries citations to the exact document, page, and passage — evidence you can stand behind.',
  },
];

export function HowItWorks() {
  return (
    <section className="section how" id="how-it-works">
      <div className="container">
        <Reveal>
          <p className="kicker">How it works</p>
        </Reveal>
        <Reveal delay={0.08}>
          <h2 className="section-title">From evidence dump to connected intelligence.</h2>
        </Reveal>
        <ol className="how-steps">
          {STEPS.map((step, i) => (
            <Reveal as="li" key={step.num} delay={0.1 + i * 0.12} className="how-step">
              <span className="how-step-num">{step.num}</span>
              <h3 className="how-step-title">{step.title}</h3>
              <p className="how-step-body">{step.body}</p>
            </Reveal>
          ))}
        </ol>
      </div>
    </section>
  );
}
