import React, { useState } from 'react';
import { Phone, MessageSquare, Mail, Smartphone, Users } from 'lucide-react';
import PhoneIdentityChip from '../PhoneIdentityChip';
import { formatTs } from '../../events/eventUtils';
import MergeIdentitiesDialog from '../../overview/MergeIdentitiesDialog';

/**
 * Rail body for a unified-by-number contact.
 *
 * The selection's payload IS the rollup row (no extra fetch needed):
 *   {
 *     canonical: "+12028052817",
 *     display_number: "+1 (202) 805-2817",
 *     aliases: [{name, key, report_keys[]}, ...],
 *     person_keys: [...], report_keys: [...],
 *     msg_count, call_count, email_count,
 *     first_seen, last_seen, interactions
 *   }
 *
 * Renders:
 *   - Number + alias chip-group + owner badge
 *   - Per-device breakdown: which alias was used on which phone
 *   - Activity counters (calls / messages / emails)
 *   - First / last seen timestamps
 *
 * The G3 follow-up will add a "recent comms" feed below this — for
 * now keeping the body small means the rail loads instantly (no
 * extra fetch on selection).
 */
export default function UnifiedContactAccordion({ selection }) {
  const row = selection?.payload || null;
  const [showMerge, setShowMerge] = useState(false);
  if (!row) return null;

  // Primary identity for a merge = the canonical phone-keyed node when present,
  // else the bucket's first person key. Investigator merges OTHER numbers
  // (e.g. a contact's second SIM) into this unified contact.
  const caseId = selection?.caseId;
  const canonicalDigits = (row.canonical || '').replace(/[^0-9]/g, '');
  const primaryKey =
    (row.person_keys || []).find((k) => canonicalDigits && k === `phone-${canonicalDigits}`) ||
    (row.person_keys || [])[0];
  const primaryName = row.display_number || row.aliases?.[0]?.name || primaryKey;

  // Build an alias-by-device index so the per-device list can show
  // "this device knew them as X". A single alias may appear on
  // multiple devices; a single device may have multiple aliases (rare
  // — e.g. a phone with two contact entries for the same number).
  const devicesIndex = {};
  for (const a of row.aliases || []) {
    for (const rk of a.report_keys || []) {
      if (!devicesIndex[rk]) devicesIndex[rk] = [];
      devicesIndex[rk].push(a.name);
    }
  }

  return (
    <div className="px-3 py-3 space-y-3 text-xs">
      {/* Header: canonical number + alias chip-group */}
      <div>
        <div className="font-mono text-sm text-owl-blue-900 mb-1.5">
          {row.display_number || (
            <span className="italic text-light-500">
              No canonical number — {row.aliases[0]?.name || 'unknown'}
            </span>
          )}
          {row.is_phone_owner && (
            <span className="ml-2 text-[9px] uppercase tracking-wide bg-emerald-100 text-emerald-700 px-1 py-px rounded">
              owner
            </span>
          )}
        </div>
        {row.aliases && row.aliases.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {row.aliases.map((a) => (
              <span
                key={a.key}
                className="inline-flex items-center bg-light-100 text-light-700 px-1.5 py-0.5 rounded text-[11px]"
                title={`Used on ${a.report_keys.length} device${a.report_keys.length === 1 ? '' : 's'}`}
              >
                {a.name}
                {a.report_keys.length > 1 && (
                  <span className="ml-1 text-[9px] text-light-500">×{a.report_keys.length}</span>
                )}
              </span>
            ))}
          </div>
        )}
        {primaryKey && caseId && (
          <button
            onClick={() => setShowMerge(true)}
            className="mt-2 inline-flex items-center gap-1 text-[11px] text-owl-blue-700 hover:text-owl-blue-900 border border-owl-blue-200 rounded px-1.5 py-0.5"
            title="Merge another number/handle into this contact (same person, different identity)"
          >
            <Users className="w-3 h-3" /> Merge identity…
          </button>
        )}
      </div>

      {showMerge && (
        <MergeIdentitiesDialog
          caseId={caseId}
          primaryKey={primaryKey}
          primaryName={primaryName}
          onClose={() => setShowMerge(false)}
          onMerged={() => { setShowMerge(false); window.location.reload(); }}
        />
      )}

      {/* Activity counters */}
      <div className="grid grid-cols-3 gap-2">
        <CounterTile icon={Phone} label="Calls" value={row.call_count} />
        <CounterTile icon={MessageSquare} label="Messages" value={row.msg_count} />
        <CounterTile icon={Mail} label="Emails" value={row.email_count} />
      </div>

      {/* First / last seen */}
      {(row.first_seen || row.last_seen) && (
        <div className="text-[11px] text-light-600 border-t border-light-100 pt-2">
          {row.first_seen && (
            <div>
              <span className="text-light-500">First seen:</span>{' '}
              <span className="tabular-nums">{formatTs(row.first_seen)}</span>
            </div>
          )}
          {row.last_seen && (
            <div>
              <span className="text-light-500">Last seen:</span>{' '}
              <span className="tabular-nums">{formatTs(row.last_seen)}</span>
            </div>
          )}
        </div>
      )}

      {/* Per-device breakdown */}
      {Object.keys(devicesIndex).length > 0 && (
        <div className="border-t border-light-100 pt-2">
          <div className="text-[10px] uppercase tracking-wide text-light-500 mb-1.5 flex items-center gap-1">
            <Smartphone className="w-3 h-3" />
            Per device
          </div>
          <ul className="space-y-1">
            {Object.entries(devicesIndex).map(([rk, aliases]) => (
              <li
                key={rk}
                className="flex items-center justify-between gap-2 text-[11px]"
              >
                <PhoneIdentityChip reportKey={rk} variant="dense" />
                <span className="text-light-700 truncate">
                  Known as {aliases.join(', ')}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function CounterTile({ icon: Icon, label, value }) {
  return (
    <div className="border border-light-100 rounded px-2 py-1.5 text-center">
      <Icon className="w-3 h-3 text-light-500 inline mr-1" />
      <span className="text-[10px] uppercase tracking-wide text-light-500">{label}</span>
      <div className="text-base font-semibold tabular-nums text-owl-blue-900">
        {(value || 0).toLocaleString()}
      </div>
    </div>
  );
}
