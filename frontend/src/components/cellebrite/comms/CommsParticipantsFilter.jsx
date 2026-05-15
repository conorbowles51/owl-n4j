import React, { useEffect, useMemo, useState } from 'react';
import {
  X, Search, Smartphone, User, ChevronDown, ChevronRight, Filter,
  ChevronLeft, ChevronRight as ChevronRightSm,
  Split, GitMerge,
} from 'lucide-react';

/**
 * Phase K1 — Participants filter with a Mode toggle.
 *
 * Two layouts share the same chrome (collapsible header, count, clear-all,
 * persistent selected-chips strip):
 *
 *   • Split  (default) — two side-by-side panels: From and To. Direction
 *     matters; investigators see direction as geography. Each selected
 *     person carries role 'from', 'to', or 'any' (in both buckets).
 *
 *   • Any    — single list, every selected person becomes role 'any'.
 *     Backend semantics flip: parent serialises selections via
 *     `participant_keys` (OR/involvement) instead of `from_keys`/`to_keys`,
 *     so "filter by this contact" returns every comm involving them
 *     regardless of direction. This is what Filter Comms from a contact
 *     row was always intended to do — Split mode required sender to equal
 *     recipient and silently returned nothing.
 *
 * The Mode pill is the cure for the "filtered but nothing showed up" bug
 * the user reported; Filter Comms intents force mode → Any so the default
 * surface from contacts/calls/emails just works.
 *
 * Backend contract is unchanged for Split mode. Mode is owned by the
 * parent (per-case localStorage) and passed in.
 */
export default function CommsParticipantsFilter({
  entities = [],
  // Parent passes a `participants` array { key, name, role } and a setter.
  participants = [],
  onParticipantsChange,
  // 'split' (default) or 'any'. Owned by parent so the serialiser
  // (CommsCenter) and the picker stay in lockstep.
  mode = 'split',
  onModeChange,
}) {
  const [collapsed, setCollapsed] = useState(false);

  // From/To Sets derived from participants for the Split-mode panels.
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
  // The Any-mode panel just shows everyone selected (any role) as a
  // single set. Toggling adds/removes with role 'any'.
  const anyKeys = useMemo(() => {
    const s = new Set();
    for (const p of participants) s.add(p.key);
    return s;
  }, [participants]);

  // Toggle inclusion of `key` in either the From or To bucket.
  const toggleSplit = (bucket, key, name) => {
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

  // Any-mode: a single bucket. Toggle off removes; toggle on adds with
  // role 'any'. If a participant was in role 'from' or 'to' before the
  // user flipped to Any, we leave the row untouched until the user
  // actively toggles it (so flipping modes is non-destructive).
  const toggleAny = (key, name) => {
    if (anyKeys.has(key)) {
      onParticipantsChange(participants.filter(p => p.key !== key));
    } else {
      onParticipantsChange([
        ...participants,
        { key, name: name || key, role: 'any' },
      ]);
    }
  };

  const clearAll = () => onParticipantsChange([]);

  const totalSelected = participants.length;
  const isAny = mode === 'any';

  return (
    <div className="border-b border-light-200 bg-white flex-shrink-0">
      {/* Header strip — always visible */}
      <div className="flex items-center gap-2 px-3 py-1 bg-light-50">
        <button
          type="button"
          onClick={() => setCollapsed(v => !v)}
          className="flex items-center gap-1 text-[11px] text-light-700 hover:text-owl-blue-700"
          title={collapsed ? 'Expand participants filter' : 'Collapse participants filter'}
        >
          {collapsed
            ? <ChevronRight className="w-3 h-3" />
            : <ChevronDown className="w-3 h-3" />}
          <Filter className="w-3 h-3" />
          <span className="font-semibold">Participants</span>
          <span className="text-light-500">
            {isAny
              ? `(Any · ${anyKeys.size})`
              : `(From ${fromKeys.size} · To ${toKeys.size})`}
          </span>
        </button>

        {/* Mode pill — Split / Any. Tiny, sits next to the title so the
            user always sees the active mode without expanding. */}
        <ModePill mode={mode} onChange={onModeChange} />

        <div className="flex-1" />
        {totalSelected > 0 && (
          <button
            type="button"
            onClick={clearAll}
            className="text-[11px] text-light-500 hover:text-red-700"
            title="Clear all selections"
          >
            Clear all
          </button>
        )}
      </div>

      {/* Body — Split mode: two panels. Any mode: one wider panel. */}
      {!collapsed && (
        isAny ? (
          <div>
            <SidePanel
              title="Anyone involved (sender or recipient)"
              entities={entities}
              selected={anyKeys}
              onToggle={(e) => toggleAny(e.key, e.name)}
              wide
            />
          </div>
        ) : (
          <div className="grid grid-cols-2 divide-x divide-light-200">
            <SidePanel
              title="From"
              entities={entities}
              selected={fromKeys}
              onToggle={(e) => toggleSplit('from', e.key, e.name)}
            />
            <SidePanel
              title="To"
              entities={entities}
              selected={toKeys}
              onToggle={(e) => toggleSplit('to', e.key, e.name)}
            />
          </div>
        )
      )}

      {/* Selected chips — same in both modes. */}
      {totalSelected > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 px-3 py-1 border-t border-light-100 bg-light-50">
          {participants.map(p => (
            <SelectedChip
              key={`${p.role}:${p.key}`}
              participant={p}
              modeIsAny={isAny}
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
 * Mode toggle pill — Split / Any. Render-only; state lives in the parent.
 */
function ModePill({ mode, onChange }) {
  const isAny = mode === 'any';
  return (
    <div className="inline-flex border border-light-300 rounded overflow-hidden text-[10px] ml-1">
      <button
        type="button"
        onClick={() => onChange?.('split')}
        className={`flex items-center gap-1 px-1.5 py-0.5 transition-colors ${
          !isAny
            ? 'bg-owl-blue-100 text-owl-blue-800'
            : 'bg-white text-light-600 hover:bg-light-100'
        }`}
        title="Split mode — separate From and To"
      >
        <Split className="w-2.5 h-2.5" />
        From / To
      </button>
      <button
        type="button"
        onClick={() => onChange?.('any')}
        className={`flex items-center gap-1 px-1.5 py-0.5 border-l border-light-300 transition-colors ${
          isAny
            ? 'bg-emerald-100 text-emerald-800'
            : 'bg-white text-light-600 hover:bg-light-100'
        }`}
        title="Any mode — direction-agnostic involvement"
      >
        <GitMerge className="w-2.5 h-2.5" />
        Any
      </button>
    </div>
  );
}

/**
 * One side of the From / To split, or the single Any-mode panel.
 * Search + paginated list. Selected items always appear in the list
 * (pinned to the top of page 1) even when they don't match the current
 * search, so the user can always deselect them.
 */
function SidePanel({ title, entities, selected, onToggle, wide = false }) {
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);

  // Reset to page 0 whenever the search changes.
  useEffect(() => { setPage(0); }, [search]);

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

  // Wide panels (Any mode) get more vertical room because they're the
  // only panel — the From/To split has TWO panels eating the same space
  // so each is shorter.
  const listMax = wide ? 'max-h-[260px]' : 'max-h-[180px]';

  return (
    <div className="flex flex-col">
      <div className="flex items-center gap-1 px-2 py-1 border-b border-light-200 bg-light-50">
        <span className="text-[11px] font-semibold text-owl-blue-900">{title}</span>
        <span className="text-[10px] text-light-500">
          ({selected.size} selected · {display.length} shown)
        </span>
      </div>

      <div className="flex items-center gap-1 px-2 py-1 border-b border-light-100">
        <Search className="w-3 h-3 text-light-400" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search…"
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

      <div className={`overflow-y-auto ${listMax} min-h-[100px]`}>
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

/**
 * Always-visible chip in the selected-chips strip. In Any mode the
 * label is just "Any" regardless of the participant's stored role —
 * the Split-mode role data is preserved on the participant so flipping
 * back to Split picks up where the user left off.
 */
function SelectedChip({ participant, modeIsAny, onRemove }) {
  const role = participant.role || 'any';
  const label = modeIsAny
    ? 'Any'
    : (role === 'from' ? 'From' : role === 'to' ? 'To' : 'Any');
  const styles = modeIsAny
    ? 'bg-emerald-50 border-emerald-300 text-emerald-900'
    : (role === 'from'
        ? 'bg-owl-blue-50 border-owl-blue-300 text-owl-blue-900'
        : role === 'to'
          ? 'bg-emerald-50 border-emerald-300 text-emerald-900'
          : 'bg-light-100 border-light-300 text-light-800');
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
