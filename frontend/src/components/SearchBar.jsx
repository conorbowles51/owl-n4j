import React, { useState, useEffect, useRef } from 'react';
import { Search, X, Loader2 } from 'lucide-react';
import { graphAPI } from '../services/api';

/**
 * SearchBar Component
 * 
 * Search for nodes in the graph
 */
export default function SearchBar({ onSelectNode }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const inputRef = useRef(null);
  const containerRef = useRef(null);

  // Debounced search
  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }

    const timer = setTimeout(async () => {
      setIsLoading(true);
      try {
        const data = await graphAPI.search(query);
        setResults(data);
        setIsOpen(true);
      } catch (err) {
        console.error('Search error:', err);
        setResults([]);
      } finally {
        setIsLoading(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [query]);

  // Close on click outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelect = (node) => {
    onSelectNode?.(node.key);
    setQuery('');
    setResults([]);
    setIsOpen(false);
  };

  const handleClear = () => {
    setQuery('');
    setResults([]);
    inputRef.current?.focus();
  };

  return (
    <div ref={containerRef} className="relative">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-400" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => results.length > 0 && setIsOpen(true)}
          placeholder="Search entities..."
          className="w-64 bg-dark-800 border border-dark-600 rounded-lg pl-9 pr-8 py-2 text-sm text-dark-100 placeholder-dark-500 focus:outline-none focus:border-dark-400"
        />
        {isLoading && (
          <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-400 animate-spin" />
        )}
        {!isLoading && query && (
          <button
            onClick={handleClear}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-dark-400 hover:text-dark-200"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Results dropdown */}
      {isOpen && results.length > 0 && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-dark-800 border border-dark-600 rounded-lg shadow-xl max-h-64 overflow-y-auto z-50">
          {results.map((node) => (
            <button
              key={node.key}
              onClick={() => handleSelect(node)}
              className="w-full px-3 py-2 text-left hover:bg-dark-700 transition-colors"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm text-dark-100">{node.name}</span>
                <span className="text-xs text-dark-400 bg-dark-700 px-2 py-0.5 rounded">
                  {node.type}
                </span>
              </div>
              {node.summary && (
                <p className="text-xs text-dark-400 mt-1 line-clamp-1">
                  {node.summary}
                </p>
              )}
            </button>
          ))}
        </div>
      )}

      {isOpen && query && results.length === 0 && !isLoading && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-dark-800 border border-dark-600 rounded-lg shadow-xl p-3 text-sm text-dark-400 text-center">
          No results found
        </div>
      )}
    </div>
  );
}
