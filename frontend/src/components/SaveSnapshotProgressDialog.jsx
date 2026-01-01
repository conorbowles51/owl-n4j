import React from 'react';
import { Loader2, X } from 'lucide-react';

/**
 * SaveSnapshotProgressDialog Component
 * 
 * Shows progress when saving a snapshot
 */
export default function SaveSnapshotProgressDialog({ isOpen, progress, onClose }) {
  if (!isOpen) return null;

  const progressPercent = progress.total > 0 
    ? Math.round((progress.current / progress.total) * 100) 
    : 0;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[9999]">
      <div className="bg-white rounded-lg p-6 w-full max-w-md border border-light-200 shadow-xl">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-owl-blue-900">Saving Snapshot</h2>
          {onClose && (
            <button
              onClick={onClose}
              className="p-1 hover:bg-light-100 rounded transition-colors"
            >
              <X className="w-5 h-5 text-light-600" />
            </button>
          )}
        </div>

        <div className="space-y-4">
          <div>
            <p className="text-sm text-light-700 mb-2">
              {progress.message || 'Processing snapshot...'}
            </p>
            
            {progress.stage && (
              <div className="mb-3">
                <div className="flex items-center justify-between text-xs text-light-600 mb-1">
                  <span>{progress.stage}</span>
                  {progress.stageProgress && (
                    <span>{progress.stageProgress}</span>
                  )}
                </div>
                {progress.stageTotal > 0 && (
                  <div className="w-full h-2 bg-light-200 rounded-full overflow-hidden">
                    <div
                      className="h-2 bg-owl-blue-500 transition-all"
                      style={{ width: `${Math.round((progress.stageProgress / progress.stageTotal) * 100)}%` }}
                    />
                  </div>
                )}
              </div>
            )}

            {progress.total > 0 && (
              <div>
                <div className="flex items-center justify-between text-xs text-light-600 mb-1">
                  <span>Overall Progress</span>
                  <span>{progressPercent}%</span>
                </div>
                <div className="w-full h-2 bg-light-200 rounded-full overflow-hidden">
                  <div
                    className="h-2 bg-owl-orange-500 transition-all"
                    style={{ width: `${progressPercent}%` }}
                  />
                </div>
              </div>
            )}

            {!progress.total && (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="w-6 h-6 text-owl-blue-500 animate-spin" />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}



