import React, { useMemo, useState } from 'react';
import {
  BarChart3, ChevronDown, ChevronRight, ArrowDownLeft, ArrowUpRight,
  MessageSquare, Phone, Mail, Loader2, Smartphone, User, Trophy,
} from 'lucide-react';
import PersonName from '../shared/PersonName';

/**
 * DKT-43 — Comms Center tally + "most contacted" ranking.
 *
 * A live count of messages / calls / emails, split inbound vs outbound and
 * broken down by platform, that updates as filters are applied (the parent
 * refetches /comms/tally under the same filter contract as the feed).
 *
 * Two parts:
 *   • Totals strip — case-level in/out per type + a platform breakdown, so the
 *     analyst sees the shape of the currently-filtered universe at a glance.
 *   • Most-contacted ranking — the top counterparties by interaction volume.
 *     Clicking a row filters the whole Comms Center to that contact (Any-mode
 *     involvement), so the ranking doubles as a fast pivot. The device owner
 *     is kept out of the ranking (never their own top contact).
 *
 * Names/numbers are resolved against the entity list (same source the filter
 * panels use) so a ranked contact reads the way it does everywhere else, with
 * its number always shown alongside the name.
 */
const DEFAULT_VISIBLE = 8;

export default function CommsTallyPanel({
  tally,
  loading = false,
  approximate = false,     // true when `tally` is the thread-derived fallback
  entities = [],
  selectedKeys,            // Set of currently-filtered participant keys
  onSelectContact,         // (key, name) => void — toggle contact filter
  collapsed = false,
  onToggleCollapsed,
}) {
  const [showAll, setShowAll] = useState(false);

  const entityByKey = useMemo(() => {
    const m = new Map();
    for (const e of entities) m.set(e.key, e);
    return m;
  }, [entities]);

  const totals = tally?.totals || null;
  const contacts = tally?.contacts || [];
  const truncated = tally?.truncated || 0;

  const grandTotal = totals
    ? totals.message_in + totals.message_out
      + totals.call_in + totals.call_out
      + totals.email_in + totals.email_out
    : 0;

  // Platform breakdown, most-used first.
  const platforms = useMemo(() => {
    const byPlat = totals?.by_platform || {};
    return Object.entries(byPlat)
      .sort((a, b) => b[1] - a[1]);
  }, [totals]);

  const visible = showAll ? contacts : contacts.slice(0, DEFAULT_VISIBLE);
  const maxTotal = contacts.length ? (contacts[0].total || 1) : 1;

  return (
    <div
      data-testid="comms-tally-panel"
      className="border-b border-light-200 bg-white flex-shrink-0"
    >
      {/* Header strip — always visible, mirrors the participants filter chrome */}
      <div className="flex items-center gap-2 px-3 py-1 bg-light-50">
        <button
          type="button"
          onClick={onToggleCollapsed}
          className="flex items-center gap-1 text-[11px] text-light-700 hover:text-owl-blue-700"
          title={collapsed ? 'Expand comms tally' : 'Collapse comms tally'}
        >
          {collapsed
            ? <ChevronRight className="w-3 h-3" />
            : <ChevronDown className="w-3 h-3" />}
          <BarChart3 className="w-3 h-3" />
          <span className="font-semibold">Tally</span>
        </button>

        {/* Inline totals summary — visible even when collapsed. */}
        {totals && (
          <div className="flex items-center gap-2 text-[11px] text-light-600">
            <TypeStat icon={MessageSquare} inN={totals.message_in} outN={totals.message_out} label="messages" approximate={approximate} />
            <TypeStat icon={Phone} inN={totals.call_in} outN={totals.call_out} label="calls" approximate={approximate} />
            <TypeStat icon={Mail} inN={totals.email_in} outN={totals.email_out} label="emails" approximate={approximate} />
          </div>
        )}

        {/* No totals yet AND not loading → say so inline, so the bar always
            reads as present-and-working rather than a lone "Tally" button that
            looks like the panel failed to render. */}
        {!totals && !loading && (
          <span className="text-[11px] text-light-500 italic">
            No interactions under the current filters
          </span>
        )}

        <div className="flex-1" />
        {loading && <Loader2 className="w-3 h-3 text-light-400 animate-spin" />}
        {!loading && totals && (
          <span className="flex items-center gap-1.5 text-[11px] text-light-500 tabular-nums">
            <span>
              {grandTotal.toLocaleString()} interactions · {(tally?.contact_count || 0).toLocaleString()} contacts
            </span>
            {approximate && (
              <span
                className="inline-flex items-center gap-0.5 text-light-400"
                title="Counted from the loaded conversations — combined volume, without the inbound/outbound split. The exact split is filled in automatically when the precise tally finishes."
              >
                <BarChart3 className="w-3 h-3" />
                approx
              </span>
            )}
          </span>
        )}
      </div>

      {!collapsed && (
        <div className="px-3 py-2">
          {/* Platform breakdown chips */}
          {platforms.length > 0 && (
            <div className="flex flex-wrap items-center gap-1 mb-2">
              <span className="text-[10px] uppercase tracking-wide text-light-400 mr-0.5">By platform</span>
              {platforms.map(([app, n]) => (
                <span
                  key={app}
                  className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full border border-light-200 bg-light-50 text-[11px] text-light-700"
                  title={`${n.toLocaleString()} ${app} interactions`}
                >
                  <span className="font-medium">{app}</span>
                  <span className="tabular-nums text-light-500">{n.toLocaleString()}</span>
                </span>
              ))}
            </div>
          )}

          {/* Most-contacted ranking */}
          <div className="flex items-center gap-1 mb-1">
            <Trophy className="w-3 h-3 text-amber-500" />
            <span className="text-[11px] font-semibold text-owl-blue-900">Most contacted</span>
            <span className="text-[10px] text-light-500">— click to filter</span>
          </div>

          {loading && contacts.length === 0 ? (
            <div className="py-3 text-[11px] text-light-500 italic text-center">
              Computing tally…
            </div>
          ) : contacts.length === 0 ? (
            <div className="py-3 text-[11px] text-light-500 italic text-center">
              No interactions under the current filters.
            </div>
          ) : (
            <div className="flex flex-col gap-0.5">
              {visible.map((c, i) => (
                <RankRow
                  key={c.key}
                  rank={i + 1}
                  contact={c}
                  entity={entityByKey.get(c.key)}
                  maxTotal={maxTotal}
                  approximate={approximate}
                  active={selectedKeys?.has(c.key)}
                  onClick={() => onSelectContact?.(c.key, c.name)}
                />
              ))}

              {(contacts.length > DEFAULT_VISIBLE || truncated > 0) && (
                <div className="flex items-center gap-2 mt-1 text-[11px]">
                  {contacts.length > DEFAULT_VISIBLE && (
                    <button
                      type="button"
                      onClick={() => setShowAll(v => !v)}
                      className="text-owl-blue-700 hover:text-owl-blue-900 font-medium"
                    >
                      {showAll
                        ? 'Show top 8'
                        : `Show all ${contacts.length}`}
                    </button>
                  )}
                  {truncated > 0 && (
                    <span className="text-light-500">
                      +{truncated.toLocaleString()} more — refine filters to rank them
                    </span>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Compact "↓in ↑out" pair for one comm type in the header summary. Hidden
 * entirely when the type has no traffic under the active filters.
 */
function TypeStat({ icon: Icon, inN, outN, label, approximate = false }) {
  if (!inN && !outN) return null;
  // The thread-derived fallback has no direction — show a single combined
  // count rather than a misleading "N in / 0 out".
  if (approximate) {
    const total = inN + outN;
    return (
      <span className="inline-flex items-center gap-0.5" title={`${total} ${label}`}>
        <Icon className="w-3 h-3 text-light-400" />
        <span className="tabular-nums text-light-600">{total.toLocaleString()}</span>
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-0.5" title={`${label}: ${inN} in / ${outN} out`}>
      <Icon className="w-3 h-3 text-light-400" />
      <span className="inline-flex items-center text-emerald-700 tabular-nums">
        <ArrowDownLeft className="w-2.5 h-2.5" />{inN.toLocaleString()}
      </span>
      <span className="inline-flex items-center text-owl-blue-700 tabular-nums">
        <ArrowUpRight className="w-2.5 h-2.5" />{outN.toLocaleString()}
      </span>
    </span>
  );
}

/**
 * One row of the most-contacted ranking. A subtle volume bar behind the row
 * gives an at-a-glance sense of relative weight; the per-type in/out counts
 * spell out the breakdown.
 */
function RankRow({ rank, contact, entity, maxTotal, active, onClick, approximate = false }) {
  const msg = contact.message_in + contact.message_out;
  const call = contact.call_in + contact.call_out;
  const email = contact.email_in + contact.email_out;
  const pct = Math.max(3, Math.round((contact.total / (maxTotal || 1)) * 100));

  return (
    <button
      type="button"
      onClick={onClick}
      className={`relative flex items-center gap-2 w-full px-2 py-1 rounded text-left text-xs overflow-hidden transition-colors ${
        active
          ? 'bg-owl-blue-50 ring-1 ring-owl-blue-200'
          : 'hover:bg-light-100'
      }`}
      title={active ? 'Remove this contact from the filter' : 'Filter the Comms Center to this contact'}
    >
      {/* Volume bar */}
      <span
        className="absolute inset-y-0 left-0 bg-owl-blue-50/70 pointer-events-none"
        style={{ width: `${pct}%` }}
        aria-hidden="true"
      />

      <span className="relative z-10 w-5 flex-shrink-0 text-[10px] tabular-nums text-light-400 text-right">
        {rank}
      </span>

      {contact.is_owner
        ? <Smartphone className="relative z-10 w-3 h-3 text-emerald-600 flex-shrink-0" />
        : <User className="relative z-10 w-3 h-3 text-light-400 flex-shrink-0" />}

      <span className="relative z-10 flex-1 min-w-0">
        <PersonName
          name={entity?.name || contact.name}
          personKey={contact.key}
          numbers={entity?.phone_numbers}
          className="truncate block text-light-900"
          numberClassName="text-[10px]"
        />
      </span>

      {/* Per-type breakdown — only the types with traffic show. */}
      <span className="relative z-10 flex items-center gap-1.5 flex-shrink-0 text-[10px] text-light-500">
        {msg > 0 && (
          <TypeMini icon={MessageSquare} inN={contact.message_in} outN={contact.message_out} label="messages" approximate={approximate} />
        )}
        {call > 0 && (
          <TypeMini icon={Phone} inN={contact.call_in} outN={contact.call_out} label="calls" approximate={approximate} />
        )}
        {email > 0 && (
          <TypeMini icon={Mail} inN={contact.email_in} outN={contact.email_out} label="emails" approximate={approximate} />
        )}
      </span>

      <span className="relative z-10 w-12 flex-shrink-0 text-right text-[11px] font-semibold tabular-nums text-owl-blue-900">
        {contact.total.toLocaleString()}
      </span>
    </button>
  );
}

function TypeMini({ icon: Icon, inN, outN, label = '', approximate = false }) {
  const total = inN + outN;
  return (
    <span
      className="inline-flex items-center gap-0.5"
      title={approximate ? `${total} ${label}`.trim() : `${inN} in / ${outN} out`}
    >
      <Icon className="w-2.5 h-2.5" />
      <span className="tabular-nums">{total.toLocaleString()}</span>
    </span>
  );
}
