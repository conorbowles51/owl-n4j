import React, { useEffect, useMemo, useState } from 'react';
import {
  X, Search, Smartphone, User, ChevronDown, ChevronRight, Filter,
  ChevronLeft, ChevronRight as ChevronRightSm,
} from 'lucide-react';

/**
 * Phase K1 (revised again) — Bidirectional From / To filter.
 *
 * The previous K1 revision combined From + To into a single
 * Participants picker with per-chip role toggles. User feedback:
 * the original split layout (From column on the left, To on the
 * right) was clearer; investigators liked seeing direction as
 * geography. Bring it back, but keep the K1 wins:
 *
 *   - Collapsible header chrome (chevron + count + clear-all)
 *   - Inline search per panel — no popovers
 *   - Per-panel pagination (50 rows / page) so big cases don't
 *     blow out vertically
 *   - Selected items persist across pages even if no longer
 *     matching the current search
 *
 * Backend contract unchanged: parent (CommsCenter) derives
 * fromKeys / toKeys sets from this and feeds them to the existing
 * /comms/threads + /comms/envelope params.
 *
 * The participants list is two distinct selections — From and To.
 * Cross-tab Filter Comms intents seed entities into BOTH (role
 * 'any') for the panoramic "every comm involving this person" feel.
 */
export default function CommsParticipantsFilter({
  entities = [],
  // Parent passes a `participants` array { key, name, role } and a
  // setter; we adapt that to From/To Sets internally for the panels.
  participants = [],
  onParticipantsChange,
}) {
  const [collapsed, setCollapsed] = useState(false);

  // Derive the current from/to selections from the participants
  // array. role='from' → in fromKeys only; role='to' → toKeys only;
  // role='any' → both (the panoramic case from Filter Comms intents).
  const fromKeys = useMemo(() => {
    const s = new Set();
    for (const p of participants) {
      if (p.role === 'from' || p.role === 'any') s.add(p.key);
    }
    return s;
  }, [participants]);
  const toKeys = useMemo(() => {
    const s = new Set();
    for (const p of participants) {
      if (p.role === 'to' || p.role === 'any') s.add(p.key);
    }
    return s;
  }, [participants]);

  // Toggle inclusion of `key` in either the From or To bucket.
  // Roles update so a person in BOTH buckets carries role='any'
  // (round-trippable through Filter Comms intents).
  const toggleIn = (bucket, key, name) => {
    const inFrom = fromKeys.has(key);
    const inTo = toKeys.has(key);
    let nextInFrom = inFrom;
    let nextInTo = inTo;
    if (bucket === 'from') nextInFrom = !inFrom;
    if (bucket === 'to') nextInTo = !inTo;

    const next = participants.filter(p => p.key !== key);
    if (nextInFrom && nextInTo) {
      next.push({ key, name: name || key, role: 'any' });
    } else if (nextInFrom) {
      next.push({ key, name: name || key, role: 'from' });
    } else if (nextInTo) {
      next.push({ key, name: name || key, role: 'to' });
    }
    onParticipantsChange(next);
  };

  const clearAll = () => onParticipantsChange([]);

  const totalSelected = participants.length;

  return (
    <div className="border-b border-light-200 bg-white flex-shrink-0">
      {/* Header strip — always visible */}
      <div className="flex items-center gap-2 px-3 py-1 bg-light-50">
        <button
          type="button"
          onClick={() => setCollapsed(v => !v)}
          className="flex items-center gap-1 text-[11px] text-light-700 hover:text-owl-blue-700"
          title={collapsed ? 'Expand From / To filter' : 'Collapse From / To filter'}
        >
          {collapsed
            ? <ChevronRight className="w-3 h-3" />
            : <ChevronDown className="w-3 h-3" />}
          <Filter className="w-3 h-3" />
          <span className="font-semibold">Participants</span>
          <span className="text-light-500">
            (From {fromKeys.size} · To {toKeys.size})
          </span>
        </button>
        <div className="flex-1" />
        {totalSelected > 0 && (
          <button
            type="button"
            onClick={clearAll}
            className="text-[11px] text-light-500 hover:text-red-700"
            title="Clear From and To selections"
          >
            Clear all
          </button>
        )}
      </div>

      {/* Body — two panels side by side, each with its own search +
          paginated list. Hidden when collapsed; the selected-chips
          row stays visible (rendered below) so the user always
          knows what's filtered. */}
      {!collapsed && (
        <div className="grid grid-cols-2 divide-x divide-light-200">
          <SidePanel
            title="From"
            entities={entities}
            selected={fromKeys}
            onToggle={(e) => toggleIn('from', e.key, e.name)}
          />
          <SidePanel
            title="To"
            entities={entities}
            selected={toKeys}
            onToggle={(e) => toggleIn('to', e.key, e.name)}
          />
        </div>
      )}

      {/* Compact selected-chips strip — visible regardless of
          collapse state so the user can always see (and remove)
          selections without expanding the panels. */}
      {totalSelected > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 px-3 py-1 border-t border-light-100 bg-light-50">
          {participants.map(p => (
            <SelectedChip
              key={`${p.role}:${p.key}`}
              participant={p}
              onRemove={() => {
                onParticipantsChange(participants.filter(x => x.key !== p.key));
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}

const PAGE_SIZE = 50;

/**
 * One side of the From / To split. Search + paginated list.
 * Selected items always appear in the list (pinned to the top of
 * page 1) even when they don't match the current search, so the
 * user can always deselect them.
 */
function SidePanel({ title, entities, selected, onToggle }) {
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);

  // Reset to page 0 whenever the search changes.
  useEffect(() => { setPage(0); }, [search]);

  // Build the displayed list:
  //   1. Stub rows for selected keys not yet present in entities
  //      (e.g. seeded by Filter Comms intent before entities loaded)
  //   2. Pinned selected entries (in entities-array order — stable)
  //   3. Search-filtered remainder
  const display = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const isMatch = (e) =>
      !needle || (e.name || e.key || '').toLowerCase().includes(needle);

    const pinned = entities.filter(e => selected.has(e.key));
    const rest = entities.filter(e => !selected.has(e.key) && isMatch(e));
    const presentKeys = new Set(pinned.map(e => e.key));
    const stubs = [...selected]
      .filter(k => !presentKeys.has(k))
      .map(k => ({ key: k, name: k, _stub: true }));

    return [...stubs, ...pinned, ...rest];
  }, [entities, selected, search]);

  const pageCount = Math.max(1, Math.ceil(display.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const sliceStart = safePage * PAGE_SIZE;
  const sliceEnd = sliceStart + PAGE_SIZE;
  const visible = display.slice(sliceStart, sliceEnd);

  return (
    <div className="flex flex-col">
      {/* Panel header — title + count */}
      <div className="flex items-center gap-1 px-2 py-1 border-b border-light-200 bg-light-50">
        <span className="text-[11px] font-semibold text-owl-blue-900">{title}</span>
        <span className="text-[10px] text-light-500">
          ({selected.size} selected · {display.length} shown)
        </span>
      </div>

      {/* Search */}
      <div className="flex items-center gap-1 px-2 py-1 border-b border-light-100">
        <Search className="w-3 h-3 text-light-400" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={`Search ${title.toLowerCase()}…`}
          className="flex-1 text-xs bg-transparent focus:outline-none text-light-900 min-w-0"
        />
        {search && (
          <button
            type="button"
            onClick={() => setSearch('')}
            className="text-light-400 hover:text-light-700 p-0.5"
            title="Clear search"
          >
            <X className="w-3 h-3" />
          </button>
        )}
      </div>

      {/* Paginated list — fixed height bounds the panel so nothing
          blows out vertically. Both panels match in height. */}
      <div className="overflow-y-auto max-h-[180px] min-h-[100px]">
        {visible.length === 0 ? (
          <div className="px-2 py-3 text-[11px] text-light-500 italic text-center">
            {search ? 'No matches.' : 'No entities.'}
          </div>
        ) : (
          visible.map(e => {
            const isSelected = selected.has(e.key);
            return (
              <button
                key={e.key}
                type="button"
                onClick={() => onToggle(e)}
                className={`flex items-center gap-1.5 w-full px-2 py-1 text-left text-xs ${
                  isSelected
                    ? 'bg-owl-blue-50 text-owl-blue-900'
                    : 'text-light-800 hover:bg-light-100'
                }`}
              >
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={() => {}}
                  className="flex-shrink-0 w-3 h-3 accent-owl-blue-600 pointer-events-none"
                />
                {e.is_owner
                  ? <Smartphone className="w-3 h-3 text-emerald-600 flex-shrink-0" />
                  : <User className="w-3 h-3 text-light-400 flex-shrink-0" />}
                <span className="truncate" title={e.name || e.key}>
                  {e.name || e.key}
                </span>
                {e._stub && (
                  <span className="ml-auto text-[9px] text-light-400 uppercase tracking-wide">
                    pending
                  </span>
                )}
              </button>
            );
          })
        )}
      </div>

      {/* Pager — only shown when there's more than one page */}
      {pageCount > 1 && (
        <div className="flex items-center gap-1 px-2 py-0.5 border-t border-light-100 bg-light-50 text-[10px] text-light-600">
          <button
            type="button"
            disabled={safePage === 0}
            onClick={() => setPage(p => Math.max(0, p - 1))}
            className="p-0.5 hover:text-owl-blue-700 disabled:text-light-300"
            title="Previous page"
          >
            <ChevronLeft className="w-3 h-3" />
          </button>
          <span className="tabular-nums">
            {safePage + 1} / {pageCount}
          </span>
          <button
            type="button"
            disabled={safePage >= pageCount - 1}
            onClick={() => setPage(p => Math.min(pageCount - 1, p + 1))}
            className="p-0.5 hover:text-owl-blue-700 disabled:text-light-300"
            title="Next page"
          >
            <ChevronRightSm className="w-3 h-3" />
          </button>
          <span className="ml-auto text-light-500">
            {sliceStart + 1}–{Math.min(sliceEnd, display.length)} of {display.length}
          </span>
        </div>
      )}
    </div>
  );
}

/** Always-visible chip in the selected-chips strip. */
function SelectedChip({ participant, onRemove }) {
  const role = participant.role || 'any';
  const label =
    role === 'from' ? 'From' :
    role === 'to' ? 'To' :
    'Any';
  const styles =
    role === 'from'
      ? 'bg-owl-blue-50 border-owl-blue-300 text-owl-blue-900'
      : role === 'to'
        ? 'bg-emerald-50 border-emerald-300 text-emerald-900'
        : 'bg-light-100 border-light-300 text-light-800';
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full border text-[11px] ${styles}`}>
      <span className="text-[9px] uppercase tracking-wide opacity-70">
        {label}
      </span>
      <span className="truncate max-w-[140px]" title={participant.name}>
        {participant.name}
      </span>
      <button
        type="button"
        onClick={onRemove}
        className="flex-shrink-0 ml-0.5 p-0.5 rounded hover:opacity-70"
        title="Remove from filter"
      >
        <X className="w-3 h-3" />
      </button>
    </span>
  );
}
