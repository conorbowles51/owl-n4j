import React from 'react';
import { Loader2, X, AlertCircle } from 'lucide-react';

/**
 * GraphOperationStatus - Overlay showing the current graph operation in progress.
 *
 * Props:
 *   operation  – { active, name, scope, caseName, phase, progress, error }
 *   onCancel   – callback to abort the current operation (optional)
 */
export default function GraphOperationStatus({ operation, onCancel }) {
  if (!operation?.active) return null;

  const { name, scope, caseName, phase, progress, error } = operation;

  return (
    <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/20 backdrop-blur-[2px]">
      <div className="bg-white rounded-xl shadow-xl border border-light-200 p-6 max-w-md w-full mx-4">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div>
            <h3 className="text-base font-semibold text-owl-blue-900">{name || 'Processing...'}</h3>
            {caseName && (
              <p className="text-xs text-light-500 mt-0.5">Case: {caseName}</p>
            )}
          </div>
          {onCancel && !error && (
            <button
              onClick={onCancel}
              className="p-1.5 hover:bg-light-100 rounded-lg transition-colors text-light-500 hover:text-light-700"
              title="Cancel operation"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Error state */}
        {error ? (
          <div className="flex items-start gap-3 bg-red-50 border border-red-200 rounded-lg p-3">
            <AlertCircle className="w-5 h-5 text-red-500 mt-0.5 flex-shrink-0" />
            <div className="flex-1">
              <p className="text-sm font-medium text-red-800">Operation failed</p>
              <p className="text-xs text-red-600 mt-1">{error}</p>
            </div>
          </div>
        ) : (
          <>
            {/* Scope */}
            {scope && (
              <p className="text-sm text-light-700 mb-3">{scope}</p>
            )}

            {/* Progress bar */}
            {progress != null ? (
              <div className="mb-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-light-600">{phase || 'Working...'}</span>
                  <span className="text-xs font-mono text-light-500">{Math.round(progress)}%</span>
                </div>
                <div className="w-full h-2 bg-light-200 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-owl-blue-600 rounded-full transition-all duration-300"
                    style={{ width: `${Math.min(progress, 100)}%` }}
                  />
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-3 mb-3">
                <Loader2 className="w-5 h-5 text-owl-blue-600 animate-spin flex-shrink-0" />
                <span className="text-sm text-light-600">{phase || 'Working...'}</span>
              </div>
            )}
          </>
        )}

        {/* Dismiss error */}
        {error && onCancel && (
          <button
            onClick={onCancel}
            className="mt-3 w-full px-3 py-2 bg-light-100 hover:bg-light-200 text-light-700 rounded-lg text-sm transition-colors"
          >
            Dismiss
          </button>
        )}
      </div>
    </div>
  );
}
