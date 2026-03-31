import { useState, useMemo } from 'react';
import { Search, X, ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react';

function formatCompactAmount(amount) {
  if (amount >= 1_000_000) return `$${(amount / 1_000_000).toFixed(1)}M`;
  if (amount >= 1_000) return `$${(amount / 1_000).toFixed(1)}K`;
  return `$${amount.toFixed(2)}`;
}

function EntityTable({ title, entities, selectedEntities, onSelectionChange, accentColor }) {
  const [search, setSearch] = useState('');
  const [sortField, setSortField] = useState('totalAmount');
  const [sortDir, setSortDir] = useState('desc');

  const filtered = useMemo(() => {
    let list = entities;
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(e => e.name.toLowerCase().includes(q));
    }
    return [...list].sort((a, b) => {
      const mul = sortDir === 'asc' ? 1 : -1;
      if (sortField === 'name') return mul * a.name.localeCompare(b.name);
      if (sortField === 'count') return mul * (a.count - b.count);
      return mul * (a.totalAmount - b.totalAmount);
    });
  }, [entities, search, sortField, sortDir]);

  // Build a lookup for selected entities that may have been cross-filtered out of the current list
  const selectedEntityNames = useMemo(() => {
    const nameMap = new Map();
    entities.forEach(e => nameMap.set(e.key, e.name));
    return nameMap;
  }, [entities]);

  const toggleSort = (field) => {
    if (sortField === field) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  };

  const toggleEntity = (key) => {
    const next = new Set(selectedEntities);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    onSelectionChange(next);
  };

  const removeEntity = (key) => {
    const next = new Set(selectedEntities);
    next.delete(key);
    onSelectionChange(next);
  };

  const SortIcon = ({ field }) => {
    if (sortField !== field) return <ArrowUpDown className="w-3 h-3 text-light-300" />;
    return sortDir === 'asc'
      ? <ArrowUp className="w-3 h-3 text-light-600" />
      : <ArrowDown className="w-3 h-3 text-light-600" />;
  };

  return (
    <div className="flex-1 min-w-0 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-2.5 py-1.5 border-b border-light-100">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-semibold" style={{ color: accentColor }}>{title}</span>
          <span className="text-[10px] text-light-400 bg-light-50 px-1.5 py-0.5 rounded-full">{entities.length}</span>
        </div>
        {selectedEntities.size > 0 && (
          <button
            onClick={() => onSelectionChange(new Set())}
            className="flex items-center gap-1 text-[10px] text-red-500 hover:text-red-700 px-1.5 py-0.5 rounded hover:bg-red-50 transition-colors"
          >
            <X className="w-3 h-3" />
            Clear all ({selectedEntities.size})
          </button>
        )}
      </div>

      {/* Selected entity chips */}
      {selectedEntities.size > 0 && (
        <div className="px-2 py-1.5 border-b border-light-100 bg-owl-blue-50/50">
          <div className="flex flex-wrap gap-1">
            {[...selectedEntities].map(key => {
              const name = selectedEntityNames.get(key) || key;
              return (
                <span
                  key={key}
                  className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded-full bg-owl-blue-100 text-owl-blue-700 max-w-[140px]"
                >
                  <span className="truncate">{name}</span>
                  <button
                    onClick={(e) => { e.stopPropagation(); removeEntity(key); }}
                    className="flex-shrink-0 p-0.5 rounded-full hover:bg-owl-blue-200 transition-colors"
                    title={`Remove ${name}`}
                  >
                    <X className="w-2.5 h-2.5" />
                  </button>
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* Search */}
      <div className="px-2 py-1.5 border-b border-light-50">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-light-400" />
          <input
            type="text"
            placeholder={`Search ${title.toLowerCase()}...`}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full text-[11px] pl-6 pr-6 py-1 border border-light-200 rounded focus:outline-none focus:border-owl-blue-400"
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              className="absolute right-1.5 top-1/2 -translate-y-1/2 p-0.5 text-light-400 hover:text-light-600"
            >
              <X className="w-2.5 h-2.5" />
            </button>
          )}
        </div>
      </div>

      {/* Column headers */}
      <div className="flex items-center text-[10px] text-light-500 font-medium border-b border-light-100 bg-light-25">
        <button
          onClick={() => toggleSort('name')}
          className="flex-1 min-w-0 flex items-center gap-1 px-2.5 py-1.5 hover:text-light-700 text-left"
        >
          Entity <SortIcon field="name" />
        </button>
        <button
          onClick={() => toggleSort('count')}
          className="w-14 flex items-center justify-end gap-1 px-2 py-1.5 hover:text-light-700"
        >
          Txns <SortIcon field="count" />
        </button>
        <button
          onClick={() => toggleSort('totalAmount')}
          className="w-20 flex items-center justify-end gap-1 px-2.5 py-1.5 hover:text-light-700"
        >
          Amount <SortIcon field="totalAmount" />
        </button>
      </div>

      {/* Rows */}
      <div className="max-h-[240px] overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="px-3 py-4 text-[11px] text-light-400 text-center">
            {search ? 'No matches' : 'No entities'}
          </div>
        ) : (
          filtered.map((entity) => {
            const isSelected = selectedEntities.has(entity.key);
            return (
              <div
                key={entity.key}
                onClick={() => toggleEntity(entity.key)}
                className={`flex items-center cursor-pointer transition-colors border-b border-light-50 last:border-b-0
                  ${isSelected ? 'bg-owl-blue-50 hover:bg-owl-blue-100' : 'hover:bg-light-50'}`}
              >
                <div className="flex-1 min-w-0 px-2.5 py-1.5">
                  <span
                    className={`text-[11px] truncate block ${isSelected ? 'text-owl-blue-700 font-medium' : 'text-light-700'}`}
                    title={entity.name}
                  >
                    {entity.name}
                  </span>
                </div>
                <div className={`w-14 text-right px-2 py-1.5 text-[11px] ${isSelected ? 'text-owl-blue-600' : 'text-light-500'}`}>
                  {entity.count}
                </div>
                <div className={`w-20 text-right px-2.5 py-1.5 text-[11px] font-medium ${isSelected ? 'text-owl-blue-700' : 'text-light-700'}`}>
                  {formatCompactAmount(entity.totalAmount)}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

/**
 * EntityFlowTables
 *
 * Side-by-side From (Senders) / To (Recipients) tables with multi-select
 * and cross-filtering. Selecting entities in one table constrains the other
 * to only show related entities (those appearing on the same transactions).
 */
export default function EntityFlowTables({
  fromEntities,
  toEntities,
  selectedFromEntities,
  selectedToEntities,
  onFromSelectionChange,
  onToSelectionChange,
}) {
  const hasAnySelection = selectedFromEntities.size > 0 || selectedToEntities.size > 0;

  return (
    <div className="border border-light-200 rounded-lg bg-white overflow-hidden">
      {/* Global clear bar — visible when any entity is selected */}
      {hasAnySelection && (
        <div className="flex items-center justify-between px-3 py-1.5 bg-owl-blue-50 border-b border-owl-blue-100">
          <span className="text-[11px] text-owl-blue-700">
            {[
              selectedFromEntities.size > 0 ? `${selectedFromEntities.size} sender(s)` : '',
              selectedToEntities.size > 0 ? `${selectedToEntities.size} recipient(s)` : '',
            ].filter(Boolean).join(' and ')}{' '}
            selected — transactions filtered
          </span>
          <button
            onClick={() => { onFromSelectionChange(new Set()); onToSelectionChange(new Set()); }}
            className="flex items-center gap-1 text-[11px] text-red-600 hover:text-red-800 px-2 py-0.5 rounded hover:bg-red-50 font-medium transition-colors"
          >
            <X className="w-3.5 h-3.5" />
            Clear all filters
          </button>
        </div>
      )}
      <div className="flex">
        <EntityTable
          title="Senders (From)"
          entities={fromEntities}
          selectedEntities={selectedFromEntities}
          onSelectionChange={onFromSelectionChange}
          accentColor="#ef4444"
        />
        <div className="w-px bg-light-200" />
        <EntityTable
          title="Recipients (To)"
          entities={toEntities}
          selectedEntities={selectedToEntities}
          onSelectionChange={onToSelectionChange}
          accentColor="#22c55e"
        />
      </div>
    </div>
  );
}
