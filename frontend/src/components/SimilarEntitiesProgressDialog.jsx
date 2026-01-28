import React from 'react';
import { X, Loader2, Search, Users } from 'lucide-react';

/**
 * Progress dialog for scanning similar entities with streaming updates.
 */
export default function SimilarEntitiesProgressDialog({
  isOpen,
  onCancel,
  progress,
}) {
  if (!isOpen || !progress) {
    return null;
  }

  const {
    totalEntities = 0,
    totalTypes = 0,
    entityTypes = [],
    currentType = null,
    typeIndex = 0,
    comparisonsTotal = 0,
    comparisonsDone = 0,
    pairsFound = 0,
    isComplete = false,
    error = null,
  } = progress;

  // Calculate overall percentage
  const overallPercentage = comparisonsTotal > 0
    ? Math.round((comparisonsDone / comparisonsTotal) * 100)
    : 0;

  // Calculate type progress (show the index of current type vs total types)
  const typePercentage = totalTypes > 0
    ? Math.round(((typeIndex + 1) / totalTypes) * 100)
    : 0;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[9999]">
      <div className="w-full max-w-md bg-white rounded-lg shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-light-200 bg-light-50">
          <div className="flex items-center gap-2">
            {isComplete ? (
              <Search className="w-5 h-5 text-green-600" />
            ) : (
              <Loader2 className="w-5 h-5 text-owl-blue-700 animate-spin" />
            )}
            <h2 className="text-lg font-semibold text-owl-blue-900">
              {isComplete ? 'Scan Complete' : 'Scanning for Similar Entities'}
            </h2>
          </div>
          {!isComplete && (
            <button
              onClick={onCancel}
              className="p-1.5 rounded hover:bg-light-200 text-light-600 transition-colors"
              title="Cancel scan"
            >
              <X className="w-5 h-5" />
            </button>
          )}
        </div>

        {/* Content */}
        <div className="p-6">
          {/* Error state */}
          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
              {error}
            </div>
          )}

          {/* Stats row */}
          <div className="flex items-center justify-between mb-4 text-sm">
            <div className="flex items-center gap-2 text-light-600">
              <Users className="w-4 h-4" />
              <span>{totalEntities.toLocaleString()} entities</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-owl-blue-900">
                {pairsFound} similar pairs found
              </span>
            </div>
          </div>

          {/* Current type indicator */}
          {currentType && !isComplete && (
            <div className="mb-4">
              <p className="text-sm text-light-600 mb-1">
                Processing type: <span className="font-semibold text-owl-blue-900">{currentType}</span>
              </p>
              <p className="text-xs text-light-500">
                Type {typeIndex + 1} of {totalTypes}
              </p>
            </div>
          )}

          {/* Overall Progress Bar */}
          <div className="mb-4">
            <div className="flex items-center justify-between text-sm text-light-600 mb-2">
              <span>Overall Progress</span>
              <span className="font-semibold text-owl-blue-900">
                {comparisonsDone.toLocaleString()} / {comparisonsTotal.toLocaleString()} comparisons
              </span>
            </div>
            <div className="w-full bg-light-200 rounded-full h-3 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-300 ease-out ${
                  isComplete ? 'bg-green-500' : 'bg-owl-blue-600'
                }`}
                style={{ width: `${overallPercentage}%` }}
              />
            </div>
            <div className="text-xs text-light-500 mt-1 text-right">
              {overallPercentage}%
            </div>
          </div>

          {/* Type Progress Bar (mini version) */}
          {!isComplete && totalTypes > 1 && (
            <div className="mb-4">
              <div className="flex items-center justify-between text-xs text-light-500 mb-1">
                <span>Entity Types</span>
                <span>{typeIndex + 1} / {totalTypes}</span>
              </div>
              <div className="w-full bg-light-100 rounded-full h-1.5 overflow-hidden">
                <div
                  className="bg-owl-blue-400 h-full rounded-full transition-all duration-300 ease-out"
                  style={{ width: `${typePercentage}%` }}
                />
              </div>
            </div>
          )}

          {/* Entity Types List (collapsed) */}
          {entityTypes.length > 0 && (
            <div className="mb-4">
              <p className="text-xs text-light-500 mb-1">Types being scanned:</p>
              <p className="text-xs text-light-600 truncate">
                {entityTypes.slice(0, 5).join(', ')}
                {entityTypes.length > 5 && ` +${entityTypes.length - 5} more`}
              </p>
            </div>
          )}

          {/* Status Message */}
          <div className="text-xs text-light-600 text-center">
            {isComplete ? (
              <span className="text-green-600 font-semibold">
                Scan complete! Found {pairsFound} similar pairs.
              </span>
            ) : (
              <span>
                Comparing entity names... This may take a while for large cases.
              </span>
            )}
          </div>

          {/* Cancel hint */}
          {!isComplete && pairsFound > 0 && (
            <div className="mt-3 text-xs text-center text-light-500">
              Cancelling will show the {pairsFound} pairs found so far.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
