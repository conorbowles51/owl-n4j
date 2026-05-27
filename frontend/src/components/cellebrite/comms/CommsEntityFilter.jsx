import React, { useMemo, useState, useEffect, useRef } from 'react';
import { Search, X, Phone, MessageSquare, Mail, ArrowLeftRight, Smartphone, User } from 'lucide-react';
import PersonName from '../shared/PersonName';

/**
 * Bidirectional From/To participant filter for the Comms Center.
 * Inspired by EntityFlowTables in the Financial view — selecting entities on
 * one side cross-filters the other, and selected items are always retained in
 * their list even if they no longer match.
 *
 * Props:
 *  - entities: array of entity objects (from cellebriteCommsAPI.getEntities)
 *  - fromKeys: Set<string>
 *  - toKeys: Set<string>
 *  - onFromChange: (Set<string>) => void
 *  - onToChange: (Set<string>) => void
 *  - threadsByPair: Map<string, Set<string>> of pair keys "A|B" → { ... } used for cross-filtering
 *                  (optional — if not provided, all entities visible in both panels regardless of cross-filter)
 */
export default function CommsEntityFilter({
  entities = [],
  fromKeys,
  toKeys,
  onFromChange,
  onToChange,
  pairMatrix = null,  // Set<string> of "A|B" pair keys representing any communication between A and B
}) {
  const [fromSearch, setFromSearch] = useState('');
  const [toSearch, setToSearch] = useState('');
  // Default to alphabetical because the parent now fetches entities
  // without per-entity comms counts (counts default to 0 in lean mode).
  // Activity/comms sort still works if a caller threads down a list
  // that was fetched with `withCounts: true`.
  const [sortKey, setSortKey] = useState('name'); // 'name' | 'activity' | 'comms'
  const nameCacheRef = useRef(new Map());

  // Build name cache for persistent chip labels
  useEffect(() => {
    entities.forEach(e => nameCacheRef.current.set(e.key, e.name));
  }, [entities]);

  const getName = (key) => nameCacheRef.current.get(key) || key;

  const sortFn = (a, b) => {
    if (sortKey === 'name') return (a.name || '').localeCompare(b.name || '');
    if (sortKey === 'comms') {
      const ca = (a.call_count || 0) + (a.message_count || 0) + (a.email_count || 0);
      const cb = (b.call_count || 0) + (b.message_count || 0) + (b.email_count || 0);
      return cb - ca;
    }
    // activity — approximation: comm total. Real last_activity would require backend.
    const ca = (a.call_count || 0) + (a.message_count || 0) + (a.email_count || 0);
    const cb = (b.call_count || 0) + (b.message_count || 0) + (b.email_count || 0);
    return cb - ca;
  };

  const matchesPair = (a, b) => {
    if (!pairMatrix) return true;
    if (a === b) return false;
    const keyA = `${a}|${b}`;
    const keyB = `${b}|${a}`;
    return pairMatrix.has(keyA) || pairMatrix.has(keyB);
  };

  // "From" list: filtered by search + optional pair cross-filter vs selected To
  const fromList = useMemo(() => {
    const search = fromSearch.trim().toLowerCase();
    const base = entities.filter(e => {
      if (search && !(e.name || '').toLowerCase().includes(search)) return false;
      if (toKeys.size > 0 && pairMatrix) {
        // Entity must have communicated with at least one selected To entity
        const matched = [...toKeys].some(tk => matchesPair(e.key, tk));
        if (!matched && !fromKeys.has(e.key)) return false; // keep if selected
      }
      return true;
    });
    base.sort(sortFn);
    // Ensure selected From entities are always present
    const present = new Set(base.map(e => e.key));
    fromKeys.forEach(k => {
      if (!present.has(k)) {
        base.push({
          key: k, name: getName(k),
          call_count: 0, message_count: 0, email_count: 0,
          device_count: 0, device_keys: [], phone_numbers: [],
          is_owner: false,
        });
      }
    });
    return base;
  }, [entities, fromSearch, toKeys, fromKeys, sortKey, pairMatrix]);

  const toList = useMemo(() => {
    const search = toSearch.trim().toLowerCase();
    const base = entities.filter(e => {
      if (search && !(e.name || '').toLowerCase().includes(search)) return false;
      if (fromKeys.size > 0 && pairMatrix) {
        const matched = [...fromKeys].some(fk => matchesPair(fk, e.key));
        if (!matched && !toKeys.has(e.key)) return false;
      }
      return true;
    });
    base.sort(sortFn);
    const present = new Set(base.map(e => e.key));
    toKeys.forEach(k => {
      if (!present.has(k)) {
        base.push({
          key: k, name: getName(k),
          call_count: 0, message_count: 0, email_count: 0,
          device_count: 0, device_keys: [], phone_numbers: [],
          is_owner: false,
        });
      }
    });
    return base;
  }, [entities, toSearch, fromKeys, toKeys, sortKey, pairMatrix]);

  const toggleFrom = (key) => {
    const next = new Set(fromKeys);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    onFromChange(next);
  };

  const toggleTo = (key) => {
    const next = new Set(toKeys);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    onToChange(next);
  };

  const clearAll = () => {
    onFromChange(new Set());
    onToChange(new Set());
  };

  const hasSelection = fromKeys.size > 0 || toKeys.size > 0;

  return (
    <div className="flex flex-col border-b border-light-200 bg-white h-full min-h-0">
      {/* Selection bar */}
      {hasSelection && (
        <div className="flex items-center gap-2 px-4 py-1.5 bg-owl-blue-50 border-b border-owl-blue-100 text-xs">
          <ArrowLeftRight className="w-3.5 h-3.5 text-owl-blue-700" />
          <span className="text-owl-blue-800 font-medium">
            {fromKeys.size} sender{fromKeys.size !== 1 ? 's' : ''} · {toKeys.size} recipient{toKeys.size !== 1 ? 's' : ''}
          </span>
          <div className="flex-1 flex items-center gap-1 overflow-x-auto">
            {[...fromKeys].map(k => (
              <Chip key={`f-${k}`} color="blue" onRemove={() => toggleFrom(k)}>
                <span className="mr-0.5">→</span>
                <PersonName name={getName(k)} personKey={k} numberClassName="text-[10px] opacity-70" />
              </Chip>
            ))}
            {[...toKeys].map(k => (
              <Chip key={`t-${k}`} color="green" onRemove={() => toggleTo(k)}>
                <span className="mr-0.5">←</span>
                <PersonName name={getName(k)} personKey={k} numberClassName="text-[10px] opacity-70" />
              </Chip>
            ))}
          </div>
          <button
            onClick={clearAll}
            className="text-xs text-owl-blue-700 hover:text-owl-blue-900 underline flex-shrink-0"
          >
            Clear all
          </button>
        </div>
      )}

      {/* Two panels side by side */}
      <div className="grid grid-cols-2 divide-x divide-light-200 flex-1 min-h-0">
        <EntityPanel
          title="From (senders)"
          accent="blue"
          entities={fromList}
          selectedKeys={fromKeys}
          search={fromSearch}
          onSearchChange={setFromSearch}
          onToggle={toggleFrom}
          sortKey={sortKey}
          onSortChange={setSortKey}
        />
        <EntityPanel
          title="To (recipients)"
          accent="green"
          entities={toList}
          selectedKeys={toKeys}
          search={toSearch}
          onSearchChange={setToSearch}
          onToggle={toggleTo}
          sortKey={sortKey}
          onSortChange={setSortKey}
        />
      </div>
    </div>
  );
}

function Chip({ children, color, onRemove }) {
  const base = color === 'green'
    ? 'bg-emerald-100 border-emerald-300 text-emerald-900'
    : 'bg-owl-blue-100 border-owl-blue-300 text-owl-blue-900';
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border ${base} text-xs max-w-[160px]`}>
      <span className="truncate">{children}</span>
      <button onClick={onRemove} className="flex-shrink-0 hover:opacity-70">
        <X className="w-3 h-3" />
      </button>
    </span>
  );
}

// Fixed row height — keeps the windowed scroll math trivial and
// matches the per-row padding/border of the button below. If the
// row template ever grows (e.g. multi-line layout), bump this.
const ENTITY_ROW_PX = 28;
// Render this many rows above + below the viewport so a smooth
// scroll never reaches the edge before more rows are mounted.
const ENTITY_OVERSCAN = 12;

function EntityPanel({ title, accent, entities, selectedKeys, search, onSearchChange, onToggle, sortKey, onSortChange }) {
  const headerColor = accent === 'green' ? 'text-emerald-700' : 'text-owl-blue-700';
  const rowSelectedBg = accent === 'green' ? 'bg-emerald-50' : 'bg-owl-blue-50';

  // Windowed render — without this, a 13K-entity case (OPDMD28) would
  // mount 13K buttons per panel × 2 panels = 26K DOM nodes on first
  // paint, freezing the main thread for ~30s. We keep the entire
  // entities array in memory but only mount the slice currently
  // visible in the scroller (+ overscan).
  const scrollRef = React.useRef(null);
  const [scrollTop, setScrollTop] = React.useState(0);
  const [viewportH, setViewportH] = React.useState(180);
  React.useEffect(() => {
    const el = scrollRef.current;
    if (!el) return undefined;
    setViewportH(el.clientHeight || 180);
    const onScroll = () => setScrollTop(el.scrollTop);
    el.addEventListener('scroll', onScroll, { passive: true });
    // ResizeObserver in case the panel's max-height changes (e.g. user
    // resizes the window). Falls back to one-shot measure if RO isn't
    // available.
    let ro;
    if (typeof ResizeObserver !== 'undefined') {
      ro = new ResizeObserver(() => setViewportH(el.clientHeight || 180));
      ro.observe(el);
    }
    return () => {
      el.removeEventListener('scroll', onScroll);
      if (ro) ro.disconnect();
    };
  }, []);
  // Reset scroll to top when the entity list itself changes (search
  // narrows the list, sort changes order, etc.) — otherwise scrollTop
  // can point past the end of a now-shorter list.
  React.useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
    setScrollTop(0);
  }, [entities]);

  const startIdx = Math.max(0, Math.floor(scrollTop / ENTITY_ROW_PX) - ENTITY_OVERSCAN);
  const endIdx = Math.min(
    entities.length,
    Math.ceil((scrollTop + viewportH) / ENTITY_ROW_PX) + ENTITY_OVERSCAN,
  );
  const topPad = startIdx * ENTITY_ROW_PX;
  const bottomPad = Math.max(0, (entities.length - endIdx) * ENTITY_ROW_PX);
  const visible = entities.slice(startIdx, endIdx);

  return (
    <div className="flex flex-col min-h-0">
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-light-200">
        <span className={`text-xs font-semibold ${headerColor}`}>{title}</span>
        <span className="text-xs text-light-400">({entities.length})</span>
        <div className="flex-1" />
        <select
          value={sortKey}
          onChange={(e) => onSortChange(e.target.value)}
          className="text-xs bg-transparent text-light-600 border border-light-200 rounded px-1 py-0.5"
        >
          <option value="activity">Sort: activity</option>
          <option value="comms">Sort: comms</option>
          <option value="name">Sort: name</option>
        </select>
      </div>

      <div className="px-3 py-1.5 border-b border-light-200">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-light-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search participants..."
            className="w-full pl-7 pr-2 py-1 text-xs border border-light-200 rounded focus:outline-none focus:border-owl-blue-400"
          />
        </div>
      </div>

      <div ref={scrollRef} className="overflow-y-auto flex-1 min-h-0">
        {entities.length === 0 ? (
          <div className="p-4 text-center text-xs text-light-400 italic">No participants</div>
        ) : (
          <>
            {topPad > 0 && <div style={{ height: topPad }} />}
            {visible.map(e => {
            const isSelected = selectedKeys.has(e.key);
            const total = (e.call_count || 0) + (e.message_count || 0) + (e.email_count || 0);
            return (
              <button
                key={e.key}
                onClick={() => onToggle(e.key)}
                className={`w-full flex items-center gap-2 px-3 py-1.5 text-xs text-left border-b border-light-100 hover:bg-light-50 transition-colors ${
                  isSelected ? rowSelectedBg : ''
                }`}
              >
                {e.is_owner ? (
                  <Smartphone className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0" />
                ) : (
                  <User className="w-3.5 h-3.5 text-light-400 flex-shrink-0" />
                )}
                <PersonName
                  name={e.name}
                  personKey={e.key}
                  numbers={e.phone_numbers}
                  className="flex-1 truncate text-light-900 font-medium"
                  numberClassName="text-[10px] font-normal"
                />
                {e.device_count > 1 && (
                  <span
                    className="flex items-center gap-0.5 px-1 py-0.5 rounded bg-amber-100 text-amber-800 text-[10px] flex-shrink-0"
                    title={`On ${e.device_count} devices`}
                  >
                    <Smartphone className="w-2.5 h-2.5" />
                    {e.device_count}
                  </span>
                )}
                <span className="flex items-center gap-1.5 flex-shrink-0 text-[10px] text-light-500">
                  {e.call_count > 0 && (
                    <span className="flex items-center gap-0.5">
                      <Phone className="w-2.5 h-2.5" />
                      {e.call_count}
                    </span>
                  )}
                  {e.message_count > 0 && (
                    <span className="flex items-center gap-0.5">
                      <MessageSquare className="w-2.5 h-2.5" />
                      {e.message_count}
                    </span>
                  )}
                  {e.email_count > 0 && (
                    <span className="flex items-center gap-0.5">
                      <Mail className="w-2.5 h-2.5" />
                      {e.email_count}
                    </span>
                  )}
                </span>
              </button>
            );
          })}
            {bottomPad > 0 && <div style={{ height: bottomPad }} />}
          </>
        )}
      </div>
    </div>
  );
}
