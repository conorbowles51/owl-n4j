import React from 'react';

/**
 * Render the per-device "saved as" alias names for one identity as a wrapped
 * chip group — the same treatment the Contacts (unified) tab uses, factored
 * out so every surface (Communications tab, comms participant/entity filters)
 * shows aliases consistently.
 *
 * aliases: [{ name, report_keys?: [...] }, ...] (most-used first, as returned
 * by neo4j_service.person_aliases / get_unified_contacts).
 *
 * Props:
 *   omit   — a name already shown elsewhere on the row (e.g. the primary
 *            display name) so it isn't repeated as a chip.
 *   max    — cap the visible chips; the remainder collapses to a "+N" pill.
 *   empty  — what to render when there are no aliases to show (default: null).
 */
export default function AliasChips({
  aliases,
  omit = null,
  max = 8,
  className = '',
  empty = null,
}) {
  const omitLc = omit ? String(omit).trim().toLowerCase() : null;
  const list = (aliases || []).filter(
    (a) => a && a.name && (!omitLc || String(a.name).trim().toLowerCase() !== omitLc),
  );
  if (!list.length) return empty;
  const shown = list.slice(0, max);
  const extra = list.length - shown.length;
  return (
    <span className={`inline-flex flex-wrap items-center gap-1 ${className}`}>
      {shown.map((a, i) => {
        const n = (a.report_keys || []).length;
        return (
          <span
            key={`${a.name}::${i}`}
            className="inline-flex items-center text-[10px] bg-light-100 text-light-600 px-1.5 py-0.5 rounded"
            title={n ? `Saved as "${a.name}" on ${n} device${n === 1 ? '' : 's'}` : a.name}
          >
            {a.name}
            {n > 1 && <span className="ml-1 text-[8px] text-light-400">×{n}</span>}
          </span>
        );
      })}
      {extra > 0 && (
        <span className="text-[10px] text-light-400" title={list.slice(max).map((a) => a.name).join(', ')}>
          +{extra}
        </span>
      )}
    </span>
  );
}
