
import { Filter, ChevronDown, ChevronRight } from "lucide-react";

const TYPE_COLORS = {
  Transaction: '#06b6d4',  // cyan
  Transfer: '#14b8a6',     // teal
  Payment: '#84cc16',      // lime
  Communication: '#f97316', // orange
  Email: '#f97316',        // orange
  PhoneCall: '#a855f7',    // purple
  Meeting: '#eab308',      // yellow
  Other: '#6b7280',        // gray
};

/**
 * Filter Panel
 */
export function FilterPanel({
  eventTypes,
  selectedTypes,
  onToggleType,
  onSelectAll,
  onClearAll,
  isExpanded = true,
  onToggleExpand
}) {
  const selectedCount = selectedTypes.size;
  const totalCount = eventTypes.length;

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
          <span>Filter by type</span>
          {!isExpanded && (
            <span className="text-xs text-light-500">
              ({selectedCount}/{totalCount} selected)
            </span>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={onSelectAll}
            className="text-xs text-light-600 hover:text-light-800"
          >
            All
          </button>
          <span className="text-light-400">|</span>
          <button
            onClick={onClearAll}
            className="text-xs text-light-600 hover:text-light-800"
          >
            None
          </button>
        </div>
      </div>
      {isExpanded && (
        <div className="flex flex-wrap gap-2 mt-2">
          {eventTypes.map(type => {
            const isSelected = selectedTypes.has(type);
            const color = TYPE_COLORS[type] || TYPE_COLORS.Other;
            return (
              <button
                key={type}
                onClick={() => onToggleType(type)}
                className={`text-xs px-2 py-1 rounded transition-all ${
                  isSelected
                    ? 'opacity-100'
                    : 'opacity-40'
                }`}
                style={{
                  backgroundColor: `${color}20`,
                  color,
                  border: `1px solid ${isSelected ? color : 'transparent'}`
                }}
              >
                {type}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}