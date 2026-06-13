import { Reveal } from '../lib/Reveal';

const INDEX_ROWS = [
  { id: '04', label: 'WITNESS STATEMENTS', meta: '31 pp' },
  { id: '07', label: 'WIRE TRANSFER PACKETS', meta: '442 pp' },
  { id: '09', label: 'TEXT MESSAGE EXPORTS', meta: '12,118 msgs' },
  { id: '10', label: 'CELL SITE / ALPR REPORT', meta: '88 pp' },
  { id: '14', label: 'PHONE TOLL ANALYSIS', meta: '8,209 rows' },
  { id: '17', label: 'RECORDED CALLS', meta: '61 hrs' },
];

export function Problem() {
  return (
    <section className="section problem">
      <div className="container problem-grid">
        <div>
          <Reveal>
            <p className="kicker">The problem</p>
          </Reveal>
          <Reveal delay={0.08}>
            <h2 className="section-title">The decisive connection is buried on page 4,217.</h2>
          </Reveal>
          <Reveal delay={0.16}>
            <p className="section-lede">
              Modern casework hands you more than any team can read: bank statements, phone
              extractions, surveillance logs, depositions, hours of recorded calls. The
              relationships that decide the case — who paid whom, who called whom, who was where —
              are in there. Finding them by hand takes weeks you don’t have.
            </p>
          </Reveal>
        </div>
        <Reveal delay={0.2} className="problem-index" aria-hidden="true">
          <p className="micro problem-index-title">Discovery index — partial</p>
          <ul className="problem-index-list">
            {INDEX_ROWS.map((row) => (
              <li key={row.id}>
                <span className="problem-index-id">{row.id}</span>
                <span className="problem-index-label">{row.label}</span>
                <span className="problem-index-meta">{row.meta}</span>
              </li>
            ))}
          </ul>
          <p className="micro problem-index-total">9,880 pages · 61 hrs audio · one team</p>
        </Reveal>
      </div>
    </section>
  );
}
