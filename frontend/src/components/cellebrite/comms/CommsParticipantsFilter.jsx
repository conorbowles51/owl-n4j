import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  X, Search, Smartphone, User, ChevronDown, ChevronRight,
  ArrowUp, ArrowDown, ArrowLeftRight, Filter,
} from 'lucide-react';

/**
 * Phase K1 (revised) — Participants combined filter.
 *
 * The previous version put the picker behind an "Add participant"
 * button → popover. User feedback: the popover indirection is
 * annoying; show the picker inline.
 *
 * New shape: when the strip is EXPANDED (default) the chips appear
 * at the top, and a search input + filtered entity list appear
 * directly beneath. Click an entity row to add it as an 'any' chip.
 * Click a chip's role icon (↕ / ↑ / ↓) to cycle role. The whole
 * strip collapses via the chevron — chips stay visible in compact
 * form so the user knows what's filtered.
 *
 * Selection model unchanged: array of `{ key, name, role }` where
 * role ∈ 'any' | 'from' | 'to'. Parent (CommsCenter) derives the
 * legacy fromKeys / toKeys sets from this.
 */
export default function CommsParticipantsFilter({
  entities = [],
  participants,
  onParticipantsChange,
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [search, setSearch] = useState('');
  const inputRef = useRef(null);

  // Cycle role any → from → to → any
  const cycleRole = (key) => {
    const order = ['any', 'from', 'to'];
    const cur = participants.find(p => p.key === key);
    if (!cur) return;
    const next = order[(order.indexOf(cur.role) + 1) % order.length];
    onParticipantsChange(participants.map(p =>
      p.key === key ? { ...p, role: next } : p,
    ));
  };
  const setRole = (key, nextRole) => {
    onParticipantsChange(participants.map(p =>
      p.key === key ? { ...p, role: nextRole } : p,
    ));
  };
  const removeChip = (key) => {
    onParticipantsChange(participants.filter(p => p.key !== key));
  };
  const clearAll = () => onParticipantsChange([]);
  const addEntity = (entity) => {
    if (participants.some(p => p.key === entity.key)) return;
    onParticipantsChange([
      ...participants,
      { key: entity.key, name: entity.name || entity.key, role: 'any' },
    ]);
    // Keep search query so multi-add of similar names is fast.
    inputRef.current?.focus();
  };

  // Filter the entity list by search needle. Cap displayed rows so
  // the inline list doesn't dominate the screen on big cases (13K+
  // entities); user is expected to narrow with search.
  const existingKeys = useMemo(
    () => new Set(participants.map(p => p.key)),
    [participants],
  );
  const filteredEntities = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return entities.slice(0, 50);
    return entities
      .filter(e => (e.name || e.key || '').toLowerCase().includes(needle))
      .slice(0, 50);
  }, [entities, search]);

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
          <span className="text-light-500">({participants.length})</span>
        </button>
        <div className="flex-1" />
        {participants.length > 0 && (
          <button
            type="button"
            onClick={clearAll}
            className="text-[11px] text-light-500 hover:text-red-700"
            title="Remove every participant from the filter"
          >
            Clear all
          </button>
        )}
      </div>

      {/* Chip strip — always visible (even when collapsed) so the
          user knows what's filtered. */}
      {participants.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 px-3 py-1.5">
          {participants.map(p => (
            <ParticipantChip
              key={p.key}
              participant={p}
              onCycleRole={() => cycleRole(p.key)}
              onSetRole={(role) => setRole(p.key, role)}
              onRemove={() => removeChip(p.key)}
            />
          ))}
        </div>
      )}

      {/* Inline picker — only when expanded. Search input + filtered
          entity list directly below the chips so adding is one click,
          no popover. */}
      {!collapsed && (
        <div className="px-3 pb-2">
          <div className="flex items-center gap-1 px-2 py-1 border border-light-300 rounded bg-white focus-within:border-owl-blue-400">
            <Search className="w-3 h-3 text-light-400" />
            <input
              ref={inputRef}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Add participant — search by name or number…"
              className="flex-1 text-xs bg-transparent focus:outline-none text-light-900"
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
          <div className="mt-1 border border-light-200 rounded bg-light-50 max-h-[180px] overflow-y-auto">
            {filteredEntities.length === 0 ? (
              <div className="px-2 py-3 text-[11px] text-light-500 italic text-center">
                {search ? 'No matching entities.' : 'No entities loaded yet.'}
              </div>
            ) : (
              filteredEntities.map(e => {
                const already = existingKeys.has(e.key);
                return (
                  <button
                    key={e.key}
                    type="button"
                    disabled={already}
                    onClick={() => addEntity(e)}
                    className={`flex items-center gap-1.5 w-full px-2 py-1 text-left text-xs ${
                      already
                        ? 'text-light-400 cursor-default'
                        : 'text-light-800 hover:bg-owl-blue-50'
                    }`}
                  >
                    {e.is_owner
                      ? <Smartphone className="w-3 h-3 text-emerald-600 flex-shrink-0" />
                      : <User className="w-3 h-3 text-light-400 flex-shrink-0" />}
                    <span className="truncate">{e.name || e.key}</span>
                    {already && (
                      <span className="ml-auto text-[10px] text-light-400">added</span>
                    )}
                  </button>
                );
              })
            )}
            {entities.length > filteredEntities.length && filteredEntities.length === 50 && (
              <div className="px-2 py-1 text-[10px] text-light-500 border-t border-light-200 bg-white">
                Showing first 50 — narrow with search.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/** Per-participant chip with a role-cycle button and an X. */
function ParticipantChip({ participant, onCycleRole, onSetRole, onRemove }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const wrapperRef = useRef(null);
  useEffect(() => {
    if (!menuOpen) return undefined;
    const onDoc = (ev) => {
      if (wrapperRef.current && !wrapperRef.current.contains(ev.target)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [menuOpen]);

  const role = participant.role || 'any';
  const styles = ROLE_STYLES[role];
  return (
    <span
      ref={wrapperRef}
      className={`relative inline-flex items-center gap-1 pl-1 pr-1 py-0.5 rounded-full border text-[11px] ${styles.chip}`}
    >
      <button
        type="button"
        onClick={onCycleRole}
        onContextMenu={(ev) => { ev.preventDefault(); setMenuOpen(true); }}
        className={`inline-flex items-center justify-center w-5 h-5 rounded-full ${styles.role}`}
        title={`Role: ${role}. Click to cycle, right-click to pick.`}
      >
        {role === 'from' ? <ArrowUp className="w-3 h-3" /> :
         role === 'to' ? <ArrowDown className="w-3 h-3" /> :
         <ArrowLeftRight className="w-3 h-3" />}
      </button>
      <span className={`truncate max-w-[140px] ${styles.text}`} title={participant.name}>
        {participant.name}
      </span>
      <button
        type="button"
        onClick={onRemove}
        className={`flex-shrink-0 ml-0.5 p-0.5 rounded hover:opacity-70 ${styles.text}`}
        title="Remove from filter"
      >
        <X className="w-3 h-3" />
      </button>

      {menuOpen && (
        <div className="absolute top-full left-0 mt-1 z-30 bg-white border border-light-200 shadow-lg rounded text-[11px] min-w-[120px]">
          {[
            { v: 'any', label: 'Either', icon: ArrowLeftRight },
            { v: 'from', label: 'Sender (from)', icon: ArrowUp },
            { v: 'to', label: 'Recipient (to)', icon: ArrowDown },
          ].map(opt => {
            const active = role === opt.v;
            const I = opt.icon;
            return (
              <button
                key={opt.v}
                type="button"
                onClick={() => { onSetRole(opt.v); setMenuOpen(false); }}
                className={`flex items-center gap-1.5 w-full px-2 py-1 hover:bg-light-100 ${
                  active ? 'bg-owl-blue-50 text-owl-blue-800 font-semibold' : 'text-light-700'
                }`}
              >
                <I className="w-3 h-3" />
                {opt.label}
                {active && <span className="ml-auto text-owl-blue-600">●</span>}
              </button>
            );
          })}
        </div>
      )}
    </span>
  );
}

const ROLE_STYLES = {
  any: {
    chip: 'bg-light-100 border-light-300',
    role: 'bg-light-300 text-light-700',
    text: 'text-light-800',
  },
  from: {
    chip: 'bg-owl-blue-50 border-owl-blue-300',
    role: 'bg-owl-blue-200 text-owl-blue-800',
    text: 'text-owl-blue-900',
  },
  to: {
    chip: 'bg-emerald-50 border-emerald-300',
    role: 'bg-emerald-200 text-emerald-800',
    text: 'text-emerald-900',
  },
};
