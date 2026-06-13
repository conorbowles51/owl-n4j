import type { ReactNode } from 'react';
import { Reveal } from '../lib/Reveal';

interface Capability {
  glyph: ReactNode;
  title: string;
  body: string;
}

const stroke = {
  stroke: 'currentColor',
  strokeWidth: 1.5,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  fill: 'none',
} as const;

const CAPABILITIES: Capability[] = [
  {
    title: 'Knowledge graph',
    body: 'The whole case as a living network. Follow any thread — people, companies, accounts — and see how everything connects.',
    glyph: (
      <svg viewBox="0 0 48 48" aria-hidden="true">
        <g {...stroke}>
          <path d="M12 34 L24 14 L37 30 M24 14 L36 10 M12 34 L8 22" />
        </g>
        <circle cx="12" cy="34" r="3" fill="currentColor" />
        <circle cx="24" cy="14" r="3.4" fill="currentColor" />
        <circle cx="37" cy="30" r="2.6" fill="currentColor" />
        <circle cx="36" cy="10" r="2" fill="currentColor" />
        <circle cx="8" cy="22" r="2" fill="currentColor" />
      </svg>
    ),
  },
  {
    title: 'Timeline',
    body: 'Every dated event, automatically in order. Communications, transactions, movements — filterable by person, place, or period.',
    glyph: (
      <svg viewBox="0 0 48 48" aria-hidden="true">
        <g {...stroke}>
          <path d="M8 24 H40" />
          <path d="M14 24 V16 M26 24 V30 M34 24 V14" />
        </g>
        <circle cx="14" cy="14" r="2.4" fill="currentColor" />
        <circle cx="26" cy="32" r="2.4" fill="currentColor" />
        <circle cx="34" cy="12" r="2.4" fill="currentColor" />
      </svg>
    ),
  },
  {
    title: 'Map',
    body: 'Geocoded locations, movement patterns, and hotspots. See where the case happened.',
    glyph: (
      <svg viewBox="0 0 48 48" aria-hidden="true">
        <g {...stroke}>
          <path d="M8 30 C14 22, 20 34, 28 26 S40 18, 41 14" opacity="0.5" />
          <path d="M24 10 c4.4 0 8 3.5 8 7.9 0 5.9 -8 14.1 -8 14.1 s-8 -8.2 -8 -14.1 c0 -4.4 3.6 -7.9 8 -7.9 Z" />
        </g>
        <circle cx="24" cy="18" r="2.6" fill="currentColor" />
        <circle cx="10" cy="36" r="1.6" fill="currentColor" />
        <circle cx="38" cy="34" r="1.6" fill="currentColor" />
      </svg>
    ),
  },
  {
    title: 'Financial analysis',
    body: 'Money-flow networks built from statements and wire records. Trace funds between entities without a spreadsheet marathon.',
    glyph: (
      <svg viewBox="0 0 48 48" aria-hidden="true">
        <g {...stroke}>
          <path d="M8 14 C20 14, 26 24, 40 24" />
          <path d="M8 24 C18 24, 26 34, 40 34" opacity="0.6" />
          <path d="M8 34 C16 34, 24 14, 40 14" opacity="0.35" />
          <path d="M36 21 L40 24 L36 27" />
        </g>
      </svg>
    ),
  },
  {
    title: 'Source-cited AI',
    body: 'An assistant that has read every page and shows its work. Answers link to the underlying evidence — nothing unverifiable.',
    glyph: (
      <svg viewBox="0 0 48 48" aria-hidden="true">
        <g {...stroke}>
          <path d="M10 12 H38 V30 H20 L13 36 V30 H10 Z" />
          <path d="M16 19 H32 M16 24 H27" opacity="0.6" />
        </g>
        <circle cx="35" cy="35" r="2.2" fill="currentColor" />
        <g {...stroke} opacity="0.7">
          <path d="M35 33 V24" />
        </g>
      </svg>
    ),
  },
  {
    title: 'Phone forensics',
    body: 'Cellebrite extractions become unified contact and communication networks across devices — threads, calls, and locations in one view.',
    glyph: (
      <svg viewBox="0 0 48 48" aria-hidden="true">
        <g {...stroke}>
          <rect x="17" y="9" width="14" height="26" rx="3" />
          <path d="M22 39 C12 36, 8 28, 9 20" opacity="0.5" />
          <path d="M26 39 C36 36, 40 28, 39 20" opacity="0.5" />
        </g>
        <circle cx="9" cy="17" r="2" fill="currentColor" />
        <circle cx="39" cy="17" r="2" fill="currentColor" />
        <circle cx="24" cy="31" r="1.6" fill="currentColor" />
      </svg>
    ),
  },
];

export function Capabilities() {
  return (
    <section className="section capabilities" id="capabilities">
      <div className="container">
        <Reveal>
          <p className="kicker">Capabilities</p>
        </Reveal>
        <Reveal delay={0.08}>
          <h2 className="section-title">One case. Every lens.</h2>
        </Reveal>
        <Reveal delay={0.14}>
          <p className="section-lede">
            The same connected graph of your evidence, viewed the way the question demands.
          </p>
        </Reveal>
        <ul className="cap-grid">
          {CAPABILITIES.map((cap, i) => (
            <Reveal as="li" key={cap.title} delay={0.08 + (i % 3) * 0.1} className="cap-card">
              <span className="cap-glyph">{cap.glyph}</span>
              <h3 className="cap-title">{cap.title}</h3>
              <p className="cap-body">{cap.body}</p>
            </Reveal>
          ))}
        </ul>
      </div>
    </section>
  );
}
