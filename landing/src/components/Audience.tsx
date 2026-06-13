import { Reveal } from '../lib/Reveal';

const AUDIENCES = [
  {
    title: 'Private investigation firms',
    body: 'Take on bigger, messier cases without bigger headcount.',
  },
  {
    title: 'Criminal defense teams',
    body: 'Master the discovery dump before anyone expects you to.',
  },
  {
    title: 'Litigation support',
    body: 'Deliver connected intelligence, not just processed documents.',
  },
  {
    title: 'Forensic accountants',
    body: 'Follow the money across thousands of transactions at once.',
  },
];

export function Audience() {
  return (
    <section className="section audience" id="who-its-for">
      <div className="container">
        <Reveal>
          <p className="kicker">Who it’s for</p>
        </Reveal>
        <Reveal delay={0.08}>
          <h2 className="section-title">Made for the teams who do the finding.</h2>
        </Reveal>
        <ul className="audience-grid">
          {AUDIENCES.map((audience, i) => (
            <Reveal as="li" key={audience.title} delay={0.08 + i * 0.08} className="audience-card">
              <h3 className="audience-title">{audience.title}</h3>
              <p className="audience-body">{audience.body}</p>
            </Reveal>
          ))}
        </ul>
      </div>
    </section>
  );
}
