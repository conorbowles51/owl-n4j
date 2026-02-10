import { useState, useRef, useEffect } from 'react';
import { ChevronDown, Plus } from 'lucide-react';

const CATEGORY_COLORS = {
  Suspicious: '#ef4444',
  Legitimate: '#22c55e',
  'Under Review': '#f59e0b',
  Unknown: '#6b7280',
};

export default function CategoryBadge({ category, categories = [], onCategoryChange }) {
  const [isOpen, setIsOpen] = useState(false);
  const [customInput, setCustomInput] = useState('');
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

  const color = CATEGORY_COLORS[category] || '#6b7280';

  const handleSelect = (cat) => {
    onCategoryChange(cat);
    setIsOpen(false);
    setCustomInput('');
  };

  const handleCustomSubmit = (e) => {
    e.preventDefault();
    const trimmed = customInput.trim();
    if (trimmed) {
      handleSelect(trimmed);
    }
  };

  return (
    <div className="relative inline-block" ref={dropdownRef}>
      <button
        onClick={(e) => {
          e.stopPropagation();
          setIsOpen(!isOpen);
        }}
        className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full transition-all hover:opacity-80"
        style={{
          backgroundColor: `${color}20`,
          color,
          border: `1px solid ${color}40`,
        }}
      >
        <span>{category || 'Unknown'}</span>
        <ChevronDown className="w-3 h-3" />
      </button>

      {isOpen && (
        <div className="absolute z-50 mt-1 w-44 bg-white rounded-lg shadow-lg border border-light-200 py-1 left-0"
          onClick={(e) => e.stopPropagation()}
        >
          {(categories.length > 0 ? categories : Object.keys(CATEGORY_COLORS)).map((cat) => {
            const catColor = CATEGORY_COLORS[cat] || '#6b7280';
            const isActive = cat === category;
            return (
              <button
                key={cat}
                onClick={() => handleSelect(cat)}
                className={`w-full text-left px-3 py-1.5 text-xs hover:bg-light-50 flex items-center gap-2 ${isActive ? 'bg-light-50 font-medium' : ''}`}
              >
                <span
                  className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                  style={{ backgroundColor: catColor }}
                />
                <span>{cat}</span>
              </button>
            );
          })}
          <div className="border-t border-light-200 mt-1 pt-1 px-2 pb-1">
            <form onSubmit={handleCustomSubmit} className="flex items-center gap-1">
              <input
                type="text"
                placeholder="Custom..."
                value={customInput}
                onChange={(e) => setCustomInput(e.target.value)}
                className="flex-1 text-xs px-2 py-1 border border-light-200 rounded focus:outline-none focus:border-owl-blue-400"
                onClick={(e) => e.stopPropagation()}
              />
              <button
                type="submit"
                disabled={!customInput.trim()}
                className="p-1 text-light-500 hover:text-owl-blue-600 disabled:opacity-30"
              >
                <Plus className="w-3.5 h-3.5" />
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
