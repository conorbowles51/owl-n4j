import React, { useState } from 'react';
import { X, Loader2, Network } from 'lucide-react';

/**
 * Build Graph From Text Modal
 *
 * Simple confirmation modal for building a graph visualization from
 * witness statements or investigative notes via vector similarity search.
 */
export default function BuildGraphFromTextModal({
  isOpen,
  onClose,
  title,
  description,
  onBuild,
}) {
  const [building, setBuilding] = useState(false);

  const handleBuild = async () => {
    setBuilding(true);
    try {
      await onBuild();
      onClose();
    } catch (err) {
      console.error('Failed to build graph:', err);
      alert('Failed to build graph: ' + (err.message || 'Unknown error'));
    } finally {
      setBuilding(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md m-4">
        <div className="border-b border-light-200 px-6 py-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-owl-blue-900 flex items-center gap-2">
            <Network className="w-5 h-5" />
            Build Graph
          </h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-light-100 rounded-lg transition-colors"
            disabled={building}
          >
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          <p className="text-sm text-light-700">
            Find related entities for <span className="font-semibold">{title}</span> by
            creating a vector embedding from the text and searching for similar entities in the graph.
          </p>

          {description && (
            <div className="bg-light-50 border border-light-200 rounded-lg p-3 text-xs text-light-600 max-h-32 overflow-y-auto">
              <div className="font-medium text-light-700 mb-1">Text that will be used:</div>
              <p className="whitespace-pre-wrap">{description.length > 500 ? description.slice(0, 500) + '...' : description}</p>
            </div>
          )}

          <div className="flex items-center justify-end gap-3 pt-4 border-t border-light-200">
            <button
              type="button"
              onClick={onClose}
              disabled={building}
              className="px-4 py-2 text-sm font-medium text-light-700 bg-light-100 rounded-lg hover:bg-light-200 transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              onClick={handleBuild}
              disabled={building}
              className="px-4 py-2 text-sm font-medium text-white bg-owl-blue-500 rounded-lg hover:bg-owl-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {building ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Building...
                </>
              ) : (
                'Build Graph'
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
