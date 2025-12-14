import React, { useState, useCallback, useRef, useEffect } from 'react';
import { Search, X } from 'lucide-react';

/**
 * GraphSearchFilter Component
 * 
 * Filters graph nodes or timeline events based on search term
 */
export default function GraphSearchFilter({ 
  onFilterChange, 
  placeholder = "Filter by search term...",
  disabled = false
}) {
  const [query, setQuery] = useState('');
  const inputRef = useRef(null);

  // Debounced filter update
  useEffect(() => {
    const timer = setTimeout(() => {
      onFilterChange?.(query.trim());
    }, 300);

    return () => clearTimeout(timer);
  }, [query, onFilterChange]);

  const handleClear = useCallback(() => {
    setQuery('');
    inputRef.current?.focus();
  }, []);

  return (
    <div className="relative">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-light-600" />
      <input
        ref={inputRef}
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        title="Supports AND, OR, NOT operators. Example: 'term1 AND term2 OR term3 NOT term4'"
        className="w-64 bg-white border border-light-300 rounded-lg pl-9 pr-8 py-2 text-sm text-light-900 placeholder-light-500 focus:outline-none focus:border-owl-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
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
  );
}

