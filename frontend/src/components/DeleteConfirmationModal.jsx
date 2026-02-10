import React from 'react';
import { X, AlertTriangle, Trash2 } from 'lucide-react';

/**
 * DeleteConfirmationModal Component
 * 
 * Modal for confirming deletion of one or more nodes
 */
export default function DeleteConfirmationModal({ isOpen, onClose, nodes, onConfirm, isDeleting = false }) {
  if (!isOpen || !nodes || nodes.length === 0) return null;

  const nodeCount = nodes.length;
  const nodeNames = nodes.map(n => n.name || n.key).slice(0, 5);
  const hasMore = nodeCount > 5;

  const handleConfirm = () => {
    onConfirm(nodes);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Escape' && !isDeleting) {
      onClose();
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isDeleting) onClose();
      }}
      onKeyDown={handleKeyDown}
      tabIndex={-1}
    >
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md m-4">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-light-200 bg-red-50">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-red-100 rounded-full">
              <AlertTriangle className="w-5 h-5 text-red-600" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-red-900">
                {nodeCount === 1 ? 'Delete Node' : `Delete ${nodeCount} Nodes`}
              </h2>
              <p className="text-sm text-red-700 mt-1">
                This action cannot be undone
              </p>
            </div>
          </div>
          {!isDeleting && (
            <button
              onClick={onClose}
              className="p-1 hover:bg-red-100 rounded transition-colors"
            >
              <X className="w-5 h-5 text-red-600" />
            </button>
          )}
        </div>

        {/* Content */}
        <div className="p-6">
          <div className="mb-4">
            <p className="text-sm text-light-700 mb-3">
              {nodeCount === 1
                ? 'Are you sure you want to delete this node? This will permanently delete the node and all its relationships.'
                : `Are you sure you want to delete these ${nodeCount} nodes? This will permanently delete all selected nodes and their relationships.`}
            </p>
            
            <div className="bg-light-50 border border-light-200 rounded-lg p-3 max-h-48 overflow-y-auto">
              <div className="space-y-1">
                {nodeNames.map((name, idx) => (
                  <div key={idx} className="text-sm text-light-700 font-medium">
                    • {name}
                  </div>
                ))}
                {hasMore && (
                  <div className="text-sm text-light-500 italic">
                    ... and {nodeCount - 5} more
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
            <p className="text-xs text-yellow-800">
              <strong>Warning:</strong> This action cannot be undone. All relationships connected to these nodes will also be deleted.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-6 border-t border-light-200 bg-light-50">
          <button
            onClick={onClose}
            disabled={isDeleting}
            className="px-4 py-2 text-sm font-medium text-light-700 hover:bg-light-100 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={isDeleting}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isDeleting ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Deleting...
              </>
            ) : (
              <>
                <Trash2 className="w-4 h-4" />
                Delete {nodeCount === 1 ? 'Node' : `${nodeCount} Nodes`}
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
