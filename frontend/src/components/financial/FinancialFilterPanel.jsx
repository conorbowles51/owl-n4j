import { useState, useRef, useEffect } from 'react';
import { Filter, ChevronDown, ChevronRight, X, Search, User, Plus } from 'lucide-react';
import { CATEGORY_COLORS } from './constants';

const TYPE_COLORS = {
  Transaction: '#06b6d4',
  Transfer: '#14b8a6',
  Payment: '#84cc16',
  Invoice: '#f97316',
  Deposit: '#3b82f6',
  Withdrawal: '#ef4444',
  Other: '#6b7280',
};

function EntityFilterDropdown({ allEntities, entityFilter, onEntityFilterChange }) {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState('');
  const dropdownRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(e) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isOpen]);

  const filtered = search
    ? allEntities.filter(e => e.name?.toLowerCase().includes(search.toLowerCase()))
    : allEntities;

  return (
    <div className="relative inline-block" ref={dropdownRef}>
      {entityFilter ? (
        <span className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded bg-owl-blue-50 text-owl-blue-700 border border-owl-blue-200">
          <User className="w-3 h-3" />
          <span className="max-w-[120px] truncate">{entityFilter.name}</span>
          <button
            onClick={() => onEntityFilterChange(null)}
            className="p-0.5 hover:bg-owl-blue-100 rounded"
          >
            <X className="w-3 h-3" />
          </button>
        </span>
      ) : (
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded border border-light-200 text-light-600 hover:text-light-800 hover:border-light-300"
        >
          <User className="w-3 h-3" />
          <span>Filter by entity...</span>
          <ChevronDown className="w-3 h-3" />
        </button>
      )}

      {isOpen && (
        <div className="absolute z-50 mt-1 w-56 bg-white rounded-lg shadow-lg border border-light-200 py-1 left-0">
          <div className="px-2 pb-1">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-light-400" />
              <input
                type="text"
                placeholder="Search entities..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full text-xs pl-7 pr-2 py-1.5 border border-light-200 rounded focus:outline-none focus:border-owl-blue-400"
                autoFocus
              />
            </div>
          </div>
          <div className="max-h-48 overflow-y-auto">
            {filtered.length === 0 ? (
              <div className="px-3 py-2 text-xs text-light-500">No entities found</div>
            ) : (
              filtered.map((entity) => (
                <button
                  key={entity.key || entity.name}
                  onClick={() => {
                    onEntityFilterChange(entity);
                    setIsOpen(false);
                    setSearch('');
                  }}
                  className="w-full text-left px-3 py-1.5 text-xs hover:bg-light-50 truncate"
                >
                  {entity.name}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function FinancialFilterPanel({
  transactionTypes = [],
  selectedTypes,
  onToggleType,
  onSelectAllTypes,
  onClearAllTypes,
  categories = [],
  selectedCategories,
  onToggleCategory,
  onSelectAllCategories,
  onClearAllCategories,
  startDate,
  endDate,
  onStartDateChange,
  onEndDateChange,
  entityFilter,
  onEntityFilterChange,
  allEntities = [],
  isExpanded = true,
  onToggleExpand,
  categoryColorMap = {},
  onAddCategory,
}) {
  const selectedTypeCount = selectedTypes.size;
  const totalTypeCount = transactionTypes.length;
  const selectedCatCount = selectedCategories.size;
  const totalCatCount = categories.length;

  return (
    <div className="bg-light-50 rounded-lg p-3 border border-light-200">
      <div className="flex items-center justify-between">
        <div
          className="flex items-center gap-2 text-sm text-light-700 cursor-pointer hover:text-light-900 select-none"
          onClick={onToggleExpand}
        >
          {isExpanded ? (
            <ChevronDown className="w-4 h-4" />
          ) : (
            <ChevronRight className="w-4 h-4" />
          )}
          <Filter className="w-4 h-4" />
          <span>Filters</span>
          {!isExpanded && (
            <span className="text-xs text-light-500">
              ({selectedTypeCount}/{totalTypeCount} types, {selectedCatCount}/{totalCatCount} categories{entityFilter ? `, entity: ${entityFilter.name}` : ''})
            </span>
          )}
        </div>
      </div>

      {isExpanded && (
        <div className="space-y-3 mt-3">
          {/* Transaction Type chips */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs text-light-600 font-medium">Transaction Type</span>
              <div className="flex gap-2">
                <button onClick={onSelectAllTypes} className="text-xs text-light-600 hover:text-light-800">All</button>
                <span className="text-light-400">|</span>
                <button onClick={onClearAllTypes} className="text-xs text-light-600 hover:text-light-800">None</button>
              </div>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {transactionTypes.map(type => {
                const isSelected = selectedTypes.has(type);
                const color = TYPE_COLORS[type] || TYPE_COLORS.Other;
                return (
                  <button
                    key={type}
                    onClick={() => onToggleType(type)}
                    className={`text-xs px-2 py-0.5 rounded transition-all ${isSelected ? 'opacity-100' : 'opacity-40'}`}
                    style={{
                      backgroundColor: `${color}20`,
                      color,
                      border: `1px solid ${isSelected ? color : 'transparent'}`,
                    }}
                  >
                    {type}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Category chips */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-light-600 font-medium">Category</span>
                {onAddCategory && (
                  <button
                    onClick={onAddCategory}
                    className="p-0.5 text-light-400 hover:text-owl-blue-600 rounded hover:bg-light-100"
                    title="Add custom category"
                  >
                    <Plus className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
              <div className="flex gap-2">
                <button onClick={onSelectAllCategories} className="text-xs text-light-600 hover:text-light-800">All</button>
                <span className="text-light-400">|</span>
                <button onClick={onClearAllCategories} className="text-xs text-light-600 hover:text-light-800">None</button>
              </div>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {categories.map(cat => {
                const isSelected = selectedCategories.has(cat);
                const color = categoryColorMap[cat] || CATEGORY_COLORS[cat] || '#6b7280';
                return (
                  <button
                    key={cat}
                    onClick={() => onToggleCategory(cat)}
                    className={`text-xs px-2 py-0.5 rounded transition-all ${isSelected ? 'opacity-100' : 'opacity-40'}`}
                    style={{
                      backgroundColor: `${color}20`,
                      color,
                      border: `1px solid ${isSelected ? color : 'transparent'}`,
                    }}
                  >
                    {cat}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Date range + Entity filter */}
          <div className="flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-3">
              <span className="text-xs text-light-600 font-medium">Date range:</span>
              <input
                type="date"
                value={startDate || ''}
                onChange={(e) => onStartDateChange(e.target.value || null)}
                className="text-xs px-2 py-1 border border-light-200 rounded focus:outline-none focus:border-owl-blue-400"
              />
              <span className="text-xs text-light-500">to</span>
              <input
                type="date"
                value={endDate || ''}
                onChange={(e) => onEndDateChange(e.target.value || null)}
                className="text-xs px-2 py-1 border border-light-200 rounded focus:outline-none focus:border-owl-blue-400"
              />
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-light-600 font-medium">Entity:</span>
              <EntityFilterDropdown
                allEntities={allEntities}
                entityFilter={entityFilter}
                onEntityFilterChange={onEntityFilterChange}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
