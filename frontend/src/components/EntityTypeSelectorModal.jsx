import React, { useState, useMemo, useCallback } from 'react';
import { X, Search, Loader2 } from 'lucide-react';

/**
 * Color palette for entity types (matches GraphView.jsx)
 */
const TYPE_COLORS = {
  Person: '#ef4444',       // red
  Company: '#3b82f6',      // blue
  Account: '#22c55e',      // green
  Bank: '#f59e0b',         // amber
  Organisation: '#8b5cf6', // violet
  Transaction: '#06b6d4',  // cyan
  Location: '#ec4899',     // pink
  Document: '#64748b',     // slate
  Transfer: '#14b8a6',     // teal
  Payment: '#84cc16',      // lime
  Email: '#f97316',        // orange
  PhoneCall: '#a855f7',    // purple
  Meeting: '#eab308',      // yellow
  Other: '#6b7280',        // gray
};

/**
 * Generate a deterministic color for an entity type based on its name
 */
function generateColorForType(type) {
  if (!type) return TYPE_COLORS.Other;

  let hash = 0;
  for (let i = 0; i < type.length; i++) {
    hash = type.charCodeAt(i) + ((hash << 5) - hash);
  }

  const colors = [
    '#ef4444', '#3b82f6', '#22c55e', '#f59e0b', '#8b5cf6',
    '#06b6d4', '#ec4899', '#64748b', '#14b8a6', '#84cc16',
    '#f97316', '#a855f7', '#eab308', '#10b981', '#6366f1',
    '#ec4899', '#14b8a6', '#f43f5e', '#0ea5e9', '#22c55e',
  ];

  return colors[Math.abs(hash) % colors.length];
}

/**
 * Get color for entity type
 */
function getTypeColor(type) {
  if (!type) return TYPE_COLORS.Other;
  if (TYPE_COLORS[type]) return TYPE_COLORS[type];
  return generateColorForType(type);
}

/**
 * Entity Type Selector Modal
 *
 * Allows users to select which entity types to include in similar entities scan.
 */
export default function EntityTypeSelectorModal({
  isOpen,
  onClose,
  onStartScan,
  entityTypes = [],
  isLoading = false,
}) {
  const [selectedTypes, setSelectedTypes] = useState(new Set());
  const [searchQuery, setSearchQuery] = useState('');

  // Sort types by count (descending) and filter by search
  const sortedAndFilteredTypes = useMemo(() => {
    let types = [...entityTypes].sort((a, b) => b.count - a.count);

    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      types = types.filter(t => t.type.toLowerCase().includes(query));
    }

    return types;
  }, [entityTypes, searchQuery]);

  // Initialize selection when types load
  React.useEffect(() => {
    if (entityTypes.length > 0 && selectedTypes.size === 0) {
      // Select all types by default
      setSelectedTypes(new Set(entityTypes.map(t => t.type)));
    }
  }, [entityTypes]);

  // Reset state when modal closes
  React.useEffect(() => {
    if (!isOpen) {
      setSearchQuery('');
      setSelectedTypes(new Set());
    }
  }, [isOpen]);

  const handleToggleType = useCallback((type) => {
    setSelectedTypes(prev => {
      const next = new Set(prev);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  }, []);

  const handleSelectAll = useCallback(() => {
    setSelectedTypes(new Set(entityTypes.map(t => t.type)));
  }, [entityTypes]);

  const handleSelectNone = useCallback(() => {
    setSelectedTypes(new Set());
  }, []);

  const handleStartScan = useCallback(() => {
    if (selectedTypes.size > 0) {
      onStartScan(Array.from(selectedTypes));
    }
  }, [selectedTypes, onStartScan]);

  // Calculate estimated entity count
  const selectedEntityCount = useMemo(() => {
    return entityTypes
      .filter(t => selectedTypes.has(t.type))
      .reduce((sum, t) => sum + t.count, 0);
  }, [entityTypes, selectedTypes]);

  const showSearch = entityTypes.length > 10;

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg mx-4 max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-light-200">
          <h2 className="text-lg font-semibold text-light-900">Select Entity Types to Scan</h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-light-100 rounded transition-colors"
          >
            <X className="w-5 h-5 text-light-500" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden flex flex-col p-4">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
              <span className="ml-2 text-light-600">Loading entity types...</span>
            </div>
          ) : entityTypes.length === 0 ? (
            <div className="text-center py-12 text-light-500">
              No entity types found in this case.
            </div>
          ) : (
            <>
              {/* Search (only show when > 10 types) */}
              {showSearch && (
                <div className="relative mb-3">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-light-400" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search types..."
                    className="w-full pl-9 pr-3 py-2 text-sm border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                </div>
              )}

              {/* Quick Actions */}
              <div className="flex items-center gap-3 mb-3">
                <span className="text-sm text-light-600">Quick Actions:</span>
                <button
                  onClick={handleSelectAll}
                  className="text-sm text-blue-600 hover:text-blue-700 hover:underline"
                >
                  Select All
                </button>
                <button
                  onClick={handleSelectNone}
                  className="text-sm text-blue-600 hover:text-blue-700 hover:underline"
                >
                  Select None
                </button>
              </div>

              <div className="border-t border-light-200 my-2" />

              {/* Type Grid */}
              <div className="flex-1 overflow-y-auto">
                <div className="grid grid-cols-2 gap-2">
                  {sortedAndFilteredTypes.map(({ type, count }) => {
                    const isSelected = selectedTypes.has(type);
                    const color = getTypeColor(type);
                    return (
                      <button
                        key={type}
                        onClick={() => handleToggleType(type)}
                        className={`flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-all text-left ${
                          isSelected
                            ? 'opacity-100'
                            : 'opacity-40'
                        }`}
                        style={{
                          backgroundColor: `${color}15`,
                          color: color,
                          border: `1px solid ${isSelected ? color : 'transparent'}`
                        }}
                      >
                        <span className="truncate font-medium">{type}</span>
                        <span className="ml-2 text-xs opacity-75">
                          ({count.toLocaleString()})
                        </span>
                      </button>
                    );
                  })}
                </div>

                {sortedAndFilteredTypes.length === 0 && searchQuery && (
                  <div className="text-center py-8 text-light-500">
                    No types match "{searchQuery}"
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-light-200 px-4 py-3 flex items-center justify-between">
          <div className="text-sm text-light-600">
            {selectedTypes.size} of {entityTypes.length} types selected
            {selectedEntityCount > 0 && (
              <span className="ml-1">
                (~{selectedEntityCount.toLocaleString()} entities)
              </span>
            )}
          </div>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm text-light-600 hover:text-light-800 hover:bg-light-100 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleStartScan}
              disabled={selectedTypes.size === 0}
              className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                selectedTypes.size > 0
                  ? 'bg-blue-600 text-white hover:bg-blue-700'
                  : 'bg-light-200 text-light-400 cursor-not-allowed'
              }`}
            >
              Start Scan →
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
