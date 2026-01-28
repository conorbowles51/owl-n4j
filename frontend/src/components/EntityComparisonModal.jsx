import React, { useState, useEffect } from 'react';
import { X, Merge, Loader2 } from 'lucide-react';
import NodeDetails from './NodeDetails';
import { graphAPI } from '../services/api';

/**
 * EntityComparisonModal Component
 *
 * Side-by-side comparison of two entities from similar entities search results.
 * Fetches full entity details and displays them using NodeDetails in compact mode.
 */
export default function EntityComparisonModal({
  isOpen,
  onClose,
  entity1,
  entity2,
  similarity,
  caseId,
  onMerge,
  onReject,
  onSelectNode,
  onViewDocument,
  username,
}) {
  const [entity1Details, setEntity1Details] = useState(null);
  const [entity2Details, setEntity2Details] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  // Fetch full entity details when modal opens
  useEffect(() => {
    if (isOpen && entity1 && entity2 && caseId) {
      setIsLoading(true);
      setError(null);

      Promise.all([
        graphAPI.getNodeDetails(entity1.key, caseId),
        graphAPI.getNodeDetails(entity2.key, caseId),
      ])
        .then(([details1, details2]) => {
          setEntity1Details(details1);
          setEntity2Details(details2);
        })
        .catch((err) => {
          console.error('Failed to fetch entity details:', err);
          setError(err.message || 'Failed to load entity details');
        })
        .finally(() => {
          setIsLoading(false);
        });
    }
  }, [isOpen, entity1, entity2, caseId]);

  // Reset state when modal closes
  useEffect(() => {
    if (!isOpen) {
      setEntity1Details(null);
      setEntity2Details(null);
      setError(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const pair = { entity1, entity2, similarity };

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-6xl max-h-[90vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-light-200 bg-owl-blue-50">
          <div className="flex items-center gap-4">
            <h2 className="text-lg font-semibold text-owl-blue-900">
              Entity Comparison
            </h2>
            {similarity != null && (
              <span className="px-2 py-1 text-sm bg-owl-blue-100 text-owl-blue-700 rounded">
                {Math.round(similarity * 100)}% similar
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-light-100 rounded"
          >
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {isLoading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-8 h-8 text-owl-blue-500 animate-spin" />
              <span className="ml-3 text-light-600">Loading entity details...</span>
            </div>
          ) : error ? (
            <div className="flex items-center justify-center py-16 text-red-600">
              {error}
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-4">
              {/* Entity 1 */}
              <div className="border border-light-200 rounded-lg overflow-hidden">
                {entity1Details ? (
                  <NodeDetails
                    node={entity1Details}
                    onSelectNode={onSelectNode}
                    onViewDocument={onViewDocument}
                    username={username}
                    compact={true}
                    caseId={caseId}
                  />
                ) : (
                  <div className="p-4 text-center text-light-500">
                    No details available
                  </div>
                )}
              </div>

              {/* Entity 2 */}
              <div className="border border-light-200 rounded-lg overflow-hidden">
                {entity2Details ? (
                  <NodeDetails
                    node={entity2Details}
                    onSelectNode={onSelectNode}
                    onViewDocument={onViewDocument}
                    username={username}
                    compact={true}
                    caseId={caseId}
                  />
                ) : (
                  <div className="p-4 text-center text-light-500">
                    No details available
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-4 border-t border-light-200 bg-light-50">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm bg-light-200 text-light-700 rounded hover:bg-light-300 transition-colors"
          >
            Back
          </button>
          <button
            onClick={() => onReject(pair)}
            className="px-4 py-2 text-sm bg-light-200 text-light-700 rounded hover:bg-light-300 transition-colors flex items-center gap-1"
            title="Mark as false positive - won't appear in future scans"
          >
            <X className="w-4 h-4" />
            Reject
          </button>
          <button
            onClick={() => onMerge(pair)}
            className="px-4 py-2 text-sm bg-owl-blue-500 text-white rounded hover:bg-owl-blue-600 transition-colors flex items-center gap-1"
          >
            <Merge className="w-4 h-4" />
            Merge
          </button>
        </div>
      </div>
    </div>
  );
}
