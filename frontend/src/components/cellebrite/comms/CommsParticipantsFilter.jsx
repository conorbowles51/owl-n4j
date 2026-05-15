import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Plus, X, Search, Smartphone, User, ChevronDown, ChevronRight,
  ArrowUp, ArrowDown, ArrowLeftRight, Filter,
} from 'lucide-react';

/**
 * Phase K1 — Participants combined filter for the Comms Center.
 *
 * Replaces the side-by-side From / To EntityFilter (which presented
 * direction as a layout choice — left column = senders, right column
 * = recipients) with a single chip-based participants picker.
 *
 * Selection model: an array of `{ key, name, role }` where role is
 * one of:
 *   - 'any'  — comm involving this person in either direction (default)
 *   - 'from' — comm where this person is the sender
 *   - 'to'   — comm where this person is the recipient
 *
 * Click the role icon on a chip to cycle any → from → to → any.
 * Click the X to remove. Click "+ Add participant" to open a search
 * popover that lists all entities (windowed render for big cases).
 *
 * The whole panel collapses (chevron button) so users can give the
 * conversation feed even more space — selected chips stay visible
 * in compact form so the user knows what's filtered.
 *
 * The PARENT (CommsCenter) is responsible for converting the
 * participants array into the existing `fromKeys` / `toKeys` server
 * params:
 *   - 'from'/'to' chips → strict from_keys/to_keys (existing semantics)
 *   - 'any' chips      → unioned into BOTH from_keys + to_keys so the
 *                        server returns comms with the participant in
 *                        either role
 * That keeps the backend untouched.
 */
export default function CommsParticipantsFilter({
  entities = [],
  participants,
  onParticipantsChange,
  // Optional: pair-overlap matrix the EntityFilter used to use to
  // cross-filter the From/To panels. We keep accepting it (parents
  // pass it today) but don't currently need it for the picker — the
  // search list shows every entity. Reintroduce if we need to narrow
  // by "only people who actually communicate with the selection".
  // eslint-disable-next-line no-unused-vars
  pairMatrix = null,
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);

  // Chip-level mutators
  const setRole = (key, nextRole) => {
    onParticipantsChange(participants.map(p =>
      p.key === key ? { ...p, role: nextRole } : p,
    ));
  };
  const cycleRole = (key) => {
    const order = ['any', 'from', 'to'];
    const cur = participants.find(p => p.key === key);
    if (!cur) return;
    const next = order[(order.indexOf(cur.role) + 1) % order.length];
    setRole(key, next);
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
  };

  return (
    <div className="border-b border-light-200 bg-white flex-shrink-0">
      {/* Header strip — always visible. Shows chip count + collapse
          toggle + clear-all when applicable. */}
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
            ({participants.length})
          </span>
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

      {/* Body — chip strip + add button. Always shows the chips
          themselves (even when collapsed) so the user knows what
          they've filtered to. The ADD button is the only thing
          that hides on collapse. */}
      <div className="flex flex-wrap items-center gap-1.5 px-3 py-1.5">
        {participants.length === 0 && (
          <span className="text-[11px] text-light-500 italic mr-2">
            No participants — Comms feed shows everything.
          </span>
        )}
        {participants.map(p => (
          <ParticipantChip
            key={p.key}
            participant={p}
            onCycleRole={() => cycleRole(p.key)}
            onSetRole={(role) => setRole(p.key, role)}
            onRemove={() => removeChip(p.key)}
          />
        ))}
        {!collapsed && (
          <button
            type="button"
            onClick={() => setPickerOpen(true)}
            className="inline-flex items-center gap-1 text-[11px] px-2 py-1 border border-dashed border-light-300 rounded text-light-700 hover:bg-light-50 hover:border-owl-blue-400 hover:text-owl-blue-700"
          >
            <Plus className="w-3 h-3" />
            Add participant
          </button>
        )}
      </div>

      {pickerOpen && (
        <ParticipantPicker
          entities={entities}
          existingKeys={new Set(participants.map(p => p.key))}
          onPick={(e) => { addEntity(e); /* keep open for multi-add */ }}
          onClose={() => setPickerOpen(false)}
        />
      )}
    </div>
  );
}

/** Per-participant chip with a role-cycle button and an X. */
function ParticipantChip({ participant, onCycleRole, onSetRole, onRemove }) {
  // Right-click opens a tiny menu so users who don't want to click
  // through any → from → to can jump straight. Left-click cycles.
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

/**
 * Floating popover for adding new participants. Shows a search input
 * + a windowed list of every entity (handles 13K-entity cases).
 * Clicking adds the entity as an 'any' chip and keeps the popover
 * open so the user can multi-add without re-clicking the trigger.
 */
function ParticipantPicker({ entities, existingKeys, onPick, onClose }) {
  const [search, setSearch] = useState('');
  const inputRef = useRef(null);
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Esc closes
  useEffect(() => {
    const onKey = (ev) => { if (ev.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return entities.slice(0, 200);
    return entities
      .filter(e => (e.name || e.key || '').toLowerCase().includes(needle))
      .slice(0, 200);
  }, [entities, search]);

  return (
    <>
      {/* Light backdrop — click outside dismisses. Translucent so
          the user sees the chip strip update underneath as they
          add participants. */}
      <div
        className="fixed inset-0 z-30"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        className="absolute mt-1 ml-3 z-40 w-[320px] bg-white border border-light-300 rounded shadow-xl flex flex-col max-h-[60vh]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-1 px-2 py-1.5 border-b border-light-200 bg-light-50">
          <Search className="w-3 h-3 text-light-500" />
          <input
            ref={inputRef}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name or number…"
            className="flex-1 text-xs bg-transparent focus:outline-none text-light-900"
          />
          <button
            type="button"
            onClick={onClose}
            className="text-light-400 hover:text-light-700 p-0.5"
            title="Close (Esc)"
          >
            <X className="w-3 h-3" />
          </button>
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto py-1">
          {filtered.length === 0 ? (
            <div className="px-3 py-6 text-xs text-light-500 italic text-center">
              No matching entities.
            </div>
          ) : (
            filtered.map(e => {
              const already = existingKeys.has(e.key);
              return (
                <button
                  key={e.key}
                  type="button"
                  disabled={already}
                  onClick={() => onPick(e)}
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
        </div>
        {entities.length > filtered.length && filtered.length === 200 && (
          <div className="px-2 py-1 text-[10px] text-light-500 border-t border-light-200 bg-light-50">
            Showing first 200 — narrow with search.
          </div>
        )}
      </div>
    </>
  );
}
