import React from 'react';

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
}) {
  // Prefer the key-derived E.164 (canonical identity) — explicit numbers[]
  // can carry junk MSISDN text from the extraction; the key is normalised.
  const num = phoneFromKey(personKey) || number || (numbers && numbers[0]);
  // "name" is really just a number when it's phone-formatted (digits / + / -
  // / spaces / parens), regardless of whether it carries the country code —
  // so "3014420513" and "+1 (301) 442-0513" both count as unnamed.
  const nameIsNumber = name && /^[+(]?\d[\d\s().-]{5,}$/.test(String(name).trim());
  const label = (name && !nameIsNumber)
    ? name
    : (num ? '(unnamed)' : (name || personKey || '—'));
  return (
    <span className={className}>
      <span>{label}</span>
      {num && (
        <span className={`ml-1.5 font-mono text-[11px] text-light-500 ${numberClassName}`}>
          {num}
        </span>
      )}
    </span>
  );
}
