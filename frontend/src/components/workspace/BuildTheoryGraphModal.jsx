import React, { useState } from 'react';
import { X, Loader2 } from 'lucide-react';

/**
 * Build Theory Graph Modal
 * 
 * Allows user to choose whether to include attached items when building theory graph
 */
export default function BuildTheoryGraphModal({
  isOpen,
  onClose,
  theory,
  onBuild,
}) {
  const [includeAttached, setIncludeAttached] = useState(true);
  const [building, setBuilding] = useState(false);

  const handleBuild = async () => {
    setBuilding(true);
    try {
      await onBuild(includeAttached);
      onClose();
    } catch (err) {
      console.error('Failed to build theory graph:', err);
      alert('Failed to build theory graph: ' + (err.message || 'Unknown error'));
    } finally {
      setBuilding(false);
    }
  };

  if (!isOpen) return null;

  const hasAttachedItems = (
    (theory?.attached_evidence_ids?.length || 0) +
    (theory?.attached_document_ids?.length || 0) +
    (theory?.attached_note_ids?.length || 0) +
    (theory?.attached_witness_ids?.length || 0) +
    (theory?.attached_task_ids?.length || 0) +
    (theory?.attached_snapshot_ids?.length || 0)
  ) > 0;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md m-4">
        <div className="border-b border-light-200 px-6 py-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-owl-blue-900">Build Theory Graph</h2>
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
            Build a graph visualization for <span className="font-semibold">{theory?.title || 'this theory'}</span> by finding relevant entities using vector similarity search.
          </p>

          <div className="space-y-3">
            <div className="flex items-start gap-3">
              <input
                type="radio"
                id="text-only"
                name="source"
                checked={!includeAttached}
                onChange={() => setIncludeAttached(false)}
                disabled={building}
                className="mt-1"
              />
              <label htmlFor="text-only" className="flex-1 cursor-pointer">
                <div className="font-medium text-sm text-owl-blue-900">Use theory text only</div>
                <div className="text-xs text-light-600 mt-1">
                  Create embedding from the theory's hypothesis, title, and supporting evidence text only.
                </div>
              </label>
            </div>

            <div className="flex items-start gap-3">
              <input
                type="radio"
                id="with-attached"
                name="source"
                checked={includeAttached}
                onChange={() => setIncludeAttached(true)}
                disabled={building || !hasAttachedItems}
                className="mt-1"
              />
              <label htmlFor="with-attached" className="flex-1 cursor-pointer">
                <div className="font-medium text-sm text-owl-blue-900">
                  Include attached documents and elements
                  {!hasAttachedItems && (
                    <span className="text-xs text-light-500 ml-2">(No attached items)</span>
                  )}
                </div>
                <div className="text-xs text-light-600 mt-1">
                  Extract text from all attached evidence files, documents, and notes, then combine with theory text to create a comprehensive embedding.
                </div>
              </label>
            </div>
          </div>

          {hasAttachedItems && includeAttached && (
            <div className="bg-light-50 border border-light-200 rounded-lg p-3 text-xs text-light-600">
              <div className="font-medium text-light-700 mb-1">Attached items that will be included:</div>
              <ul className="list-disc list-inside space-y-0.5">
                {theory?.attached_evidence_ids?.length > 0 && (
                  <li>{theory.attached_evidence_ids.length} evidence file(s)</li>
                )}
                {theory?.attached_document_ids?.length > 0 && (
                  <li>{theory.attached_document_ids.length} document(s)</li>
                )}
                {theory?.attached_note_ids?.length > 0 && (
                  <li>{theory.attached_note_ids.length} note(s)</li>
                )}
                {theory?.attached_witness_ids?.length > 0 && (
                  <li>{theory.attached_witness_ids.length} witness(es)</li>
                )}
                {theory?.attached_task_ids?.length > 0 && (
                  <li>{theory.attached_task_ids.length} task(s)</li>
                )}
                {theory?.attached_snapshot_ids?.length > 0 && (
                  <li>{theory.attached_snapshot_ids.length} snapshot(s)</li>
                )}
              </ul>
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
              disabled={building || (includeAttached && !hasAttachedItems)}
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
