import React from 'react';
import HighlightedText from './HighlightedText';

/**
 * Derive the E.164-ish phone number from a person key. Cellebrite person
 * keys are `phone-<digits>` (country code included), so a contact's number
 * is always recoverable even when the caller didn't pass it explicitly.
 */
export function phoneFromKey(key) {
  if (!key) return null;
  const m = /^phone-(\d{7,15})$/.exec(String(key));
  return m ? `+${m[1]}` : null;
}

const _digits = (s) => String(s || '').replace(/\D/g, '');

/**
 * A "name" that's really just a bare phone number (digits / + / - / spaces /
 * parens), regardless of whether it carries the country code — so both
 * "3014420513" and "+1 (301) 442-0513" count. Used to decide when to show
 * "(unnamed)" instead of printing the number twice.
 */
const _nameIsNumber = (name) =>
  !!name && /^[+(]?\d[\d\s().-]{5,}$/.test(String(name).trim());

/**
 * Render a contact/person name with its phone number ALWAYS shown alongside
 * (investigator requirement: a name is never shown without its number).
 *
 *  - number comes from an explicit `numbers[]`/`number`, else derived from
 *    the `phone-<digits>` key.
 *  - when the "name" is really just the bare number (no human label saved),
 *    show "(unnamed)" so the row reads "(unnamed) +1…" rather than the number
 *    twice. Covers device owners whose own number was never saved as a contact.
 *  - non-phone identities (email/app keys) with no number just show the name.
 */
export default function PersonName({
  name,
  personKey,
  number,
  numbers,
  className = '',
  numberClassName = '',
  // When provided (array of lowercase needles), the name label is rendered
  // through HighlightedText so search-driven surfaces (comms cards, event
  // tables) keep their match highlighting while still gaining the number.
  highlights = null,
  // For two-column layouts that already show the number in a dedicated
  // adjacent column (e.g. the Contacts table): suppress the inline number
  // but KEEP the "(unnamed)" cleanup so a bare-number/empty name never
  // renders as the ugly raw `phone-…` key.
  hideNumber = false,
}) {
  // Prefer the key-derived E.164 (canonical identity) — explicit numbers[]
  // can carry junk MSISDN text from the extraction; the key is normalised.
  const num = phoneFromKey(personKey) || number || (numbers && numbers[0]);
  const label = (name && !_nameIsNumber(name))
    ? name
    : (num ? '(unnamed)' : (name || personKey || '—'));
  const hasHl = Array.isArray(highlights) && highlights.length > 0;
  return (
    <span className={className}>
      {hasHl ? <HighlightedText text={label} highlights={highlights} /> : <span>{label}</span>}
      {num && !hideNumber && (
        <span className={`ml-1.5 font-mono text-[11px] text-light-500 ${numberClassName}`}>
          {num}
        </span>
      )}
    </span>
  );
}
