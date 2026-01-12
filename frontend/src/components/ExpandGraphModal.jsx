import React, { useState, useEffect } from 'react';
import { X, Maximize2 } from 'lucide-react';

/**
 * ExpandGraphModal Component
 * 
 * Modal for asking user how many hops to expand
 */
export default function ExpandGraphModal({ isOpen, onClose, onExpand, nodeCount = 0 }) {
  const [depth, setDepth] = useState(1);
  const [error, setError] = useState(null);

  // Reset form when modal opens
  useEffect(() => {
    if (isOpen) {
      setDepth(1);
      setError(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleExpand = () => {
    if (depth < 1 || depth > 5) {
      setError('Hops must be between 1 and 5');
      return;
    }
    onExpand(depth);
    onClose();
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Escape') {
      onClose();
    } else if (e.key === 'Enter') {
      handleExpand();
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      onKeyDown={handleKeyDown}
    >
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md m-4">
        {/* Header */}
        <div className="p-6 border-b border-light-200 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Maximize2 className="w-5 h-5 text-owl-blue-600" />
            <h2 className="text-xl font-semibold text-owl-blue-900">
              Expand Graph
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-light-100 rounded transition-colors"
          >
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          <div className="mb-4">
            <p className="text-sm text-light-700 mb-4">
              {nodeCount > 0
                ? `Expand ${nodeCount} selected node${nodeCount > 1 ? 's' : ''} by how many hops?`
                : 'Expand all nodes in the graph by how many hops?'}
            </p>
            <p className="text-xs text-light-500 mb-4">
              Hops determine how many relationship steps to traverse. Higher values will include more distant connections.
            </p>
          </div>

          <div className="mb-4">
            <label className="block text-sm font-medium text-light-700 mb-2">
              Number of Hops (1-5)
            </label>
            <input
              type="number"
              min="1"
              max="5"
              value={depth}
              onChange={(e) => {
                const val = parseInt(e.target.value, 10);
                if (!isNaN(val)) {
                  setDepth(val);
                  setError(null);
                }
              }}
              className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500 focus:border-transparent"
              autoFocus
            />
            {error && (
              <p className="text-sm text-red-600 mt-2">{error}</p>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-light-200 flex items-center justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-light-700 hover:bg-light-100 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleExpand}
            className="px-4 py-2 text-sm bg-owl-blue-500 hover:bg-owl-blue-600 text-white rounded-lg transition-colors"
          >
            Expand
          </button>
        </div>
      </div>
    </div>
  );
}
