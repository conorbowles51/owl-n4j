import React, { useState, useCallback, useRef, useEffect } from 'react';
import { Search, X } from 'lucide-react';

/**
 * GraphSearchFilter Component
 * 
 * Filters graph nodes or timeline events based on search term.
 * Supports two modes: immediate filter (runs on keystrokes) and manual search (runs on button click).
 */
export default function GraphSearchFilter({ 
  onFilterChange,
  onQueryChange,
  onSearch,
  mode = 'filter',
  onModeChange,
  placeholder = "Filter by search term...",
  disabled = false
}) {
  const [query, setQuery] = useState('');
  const inputRef = useRef(null);

  // Debounced filter update (only in filter mode)
  useEffect(() => {
    if (mode !== 'filter') {
      return;
    }

    const timer = setTimeout(() => {
      onFilterChange?.(query.trim());
    }, 300);

    return () => clearTimeout(timer);
  }, [query, mode, onFilterChange]);

  // Notify parent of raw query string (used for pending search text)
  useEffect(() => {
    onQueryChange?.(query.trim());
  }, [query, onQueryChange]);

  const handleClear = useCallback(() => {
    setQuery('');
    inputRef.current?.focus();
  }, []);

  const handleModeChange = (event) => {
    onModeChange?.(event.target.value);
  };

  const executeSearch = () => {
    if (mode === 'search') {
      onSearch?.(query.trim());
    }
  };

  const handleKeyDown = (event) => {
    if (mode === 'search' && event.key === 'Enter') {
      event.preventDefault();
      executeSearch();
    }
  };

  return (
    <div className="flex items-center gap-2">
      <div className="relative flex-1">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-light-600" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          title="Supports boolean logic, wildcards (*, ?), and fuzzy (~) expressions"
          className="w-full bg-white border border-light-300 rounded-lg pl-9 pr-20 py-2 text-sm text-light-900 placeholder-light-500 focus:outline-none focus:border-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed"
        />
        {query && (
          <button
            onClick={handleClear}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-light-600 hover:text-light-800"
            disabled={disabled}
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>
      <select
        value={mode}
        onChange={handleModeChange}
        disabled={disabled}
        className="border border-light-300 bg-white text-sm rounded-lg px-3 py-2 focus:outline-none"
        title="Choose 'Filter' for live updates or 'Search' to run on demand"
      >
        <option value="filter">Filter</option>
        <option value="search">Search</option>
      </select>
      {mode === 'search' && (
        <button
          onClick={executeSearch}
          disabled={disabled}
          className="px-3 py-2 bg-light-100 rounded-lg text-sm text-light-800 hover:bg-light-200 active:bg-light-300 transition-colors"
        >
          Search
        </button>
      )}
    </div>
  );
}

