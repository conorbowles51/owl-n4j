import React from 'react';
import { X, Loader2 } from 'lucide-react';

/**
 * Progress dialog for selecting and loading nodes
 */
export default function NodeSelectionProgressDialog({ isOpen, onClose, current, total, message }) {
  if (!isOpen) return null;

  const percentage = total > 0 ? Math.round((current / total) * 100) : 0;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[9999]">
      <div className="w-full max-w-md bg-white rounded-lg shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-light-200 bg-light-50">
          <div className="flex items-center gap-2">
            <Loader2 className="w-5 h-5 text-owl-blue-700 animate-spin" />
            <h2 className="text-lg font-semibold text-owl-blue-900">
              Loading Node Details
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded hover:bg-light-200 text-light-600 transition-colors"
            disabled={current < total}
            title={current < total ? "Loading in progress..." : "Close"}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          <div className="mb-4">
            <p className="text-sm text-light-600">
              {message || 'Loading node details...'}
            </p>
          </div>

          {/* Progress Bar */}
          {total > 0 && (
            <div className="mb-4">
              <div className="flex items-center justify-between text-sm text-light-600 mb-2">
                <span>Progress</span>
                <span className="font-semibold text-owl-blue-900">
                  {current} / {total} nodes
                </span>
              </div>
              <div className="w-full bg-light-200 rounded-full h-3 overflow-hidden">
                <div
                  className="bg-owl-blue-600 h-full rounded-full transition-all duration-300 ease-out"
                  style={{ width: `${percentage}%` }}
                />
              </div>
              <div className="text-xs text-light-500 mt-1 text-right">
                {percentage}%
              </div>
            </div>
          )}

          {/* Status Message */}
          <div className="text-xs text-light-600 text-center">
            {current < total ? (
              <span>Loading node {current + 1} of {total}...</span>
            ) : (
              <span className="text-green-600 font-semibold">All nodes loaded successfully!</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}


