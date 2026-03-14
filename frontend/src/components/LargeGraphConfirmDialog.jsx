import React from 'react';
import { AlertTriangle, X } from 'lucide-react';

/**
 * LargeGraphConfirmDialog - Confirmation dialog before running expensive
 * graph operations on large graphs.
 *
 * Props:
 *   isOpen       – boolean
 *   operationName – e.g. "PageRank Analysis"
 *   nodeCount    – number of nodes that will be analyzed
 *   linkCount    – number of relationships
 *   scope        – description of what's being analyzed ("full graph" / "23 selected nodes")
 *   onConfirm    – callback when user clicks Continue
 *   onCancel     – callback when user clicks Cancel
 */
export default function LargeGraphConfirmDialog({
  isOpen,
  operationName,
  nodeCount,
  linkCount,
  scope,
  onConfirm,
  onCancel,
}) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-[2px]">
      <div className="bg-white rounded-xl shadow-2xl border border-light-200 p-6 max-w-md w-full mx-4">
        {/* Header */}
        <div className="flex items-start gap-3 mb-4">
          <div className="p-2 bg-amber-100 rounded-lg">
            <AlertTriangle className="w-5 h-5 text-amber-600" />
          </div>
          <div className="flex-1">
            <h3 className="text-base font-semibold text-light-900">Large Graph Warning</h3>
            <p className="text-sm text-light-600 mt-1">
              <span className="font-medium">{operationName}</span> on a large graph may take a while or cause performance issues.
            </p>
          </div>
          <button
            onClick={onCancel}
            className="p-1 hover:bg-light-100 rounded transition-colors text-light-500"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Stats */}
        <div className="bg-light-50 rounded-lg p-3 mb-4 border border-light-200">
          <div className="text-xs font-medium text-light-500 uppercase tracking-wide mb-2">
            Analysis Scope: {scope}
          </div>
          <div className="flex gap-6">
            <div>
              <div className="text-lg font-bold text-owl-blue-900">
                {nodeCount?.toLocaleString()}
              </div>
              <div className="text-xs text-light-600">nodes</div>
            </div>
            {linkCount != null && (
              <div>
                <div className="text-lg font-bold text-owl-blue-900">
                  {linkCount?.toLocaleString()}
                </div>
                <div className="text-xs text-light-600">relationships</div>
              </div>
            )}
          </div>
        </div>

        {/* Suggestion */}
        <p className="text-xs text-light-600 mb-4">
          For better performance, consider selecting a smaller subset of nodes first, then running the analysis on the selection.
        </p>

        {/* Actions */}
        <div className="flex gap-2">
          <button
            onClick={onCancel}
            className="flex-1 px-4 py-2 bg-light-100 hover:bg-light-200 text-light-700 rounded-lg text-sm transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="flex-1 px-4 py-2 bg-owl-orange-500 hover:bg-owl-orange-600 text-white rounded-lg text-sm transition-colors font-medium"
          >
            Continue Anyway
          </button>
        </div>
      </div>
    </div>
  );
}
