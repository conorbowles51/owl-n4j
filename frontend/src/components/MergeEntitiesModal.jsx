import React, { useState, useEffect } from 'react';
import { X, Merge, ArrowRight } from 'lucide-react';

/**
 * MergeEntitiesModal Component
 * 
 * Modal for merging two entities with side-by-side comparison
 */
export default function MergeEntitiesModal({ 
  isOpen, 
  onClose, 
  entity1, 
  entity2, 
  onMerge,
  similarity = null,
}) {
  const [mergedName, setMergedName] = useState('');
  const [mergedSummary, setMergedSummary] = useState('');
  const [mergedNotes, setMergedNotes] = useState('');
  const [mergedType, setMergedType] = useState('');
  const [nameMode, setNameMode] = useState('entity1'); // 'entity1', 'entity2', 'both'
  const [summaryMode, setSummaryMode] = useState('entity1'); // 'entity1', 'entity2', 'both'
  const [useEntity1Notes, setUseEntity1Notes] = useState(true);
  const [isMerging, setIsMerging] = useState(false);
  const [error, setError] = useState(null);

  // Initialize form when modal opens
  useEffect(() => {
    if (isOpen && entity1 && entity2) {
      // Default to entity1's values
      setMergedName(entity1.name || '');
      setMergedSummary(entity1.summary || '');
      setMergedNotes(entity1.notes || '');
      setMergedType(entity1.type || '');
      setNameMode('entity1');
      setSummaryMode('entity1');
      setUseEntity1Notes(true);
      setError(null);
    }
  }, [isOpen, entity1, entity2]);

  // Update merged values when toggles change
  useEffect(() => {
    if (entity1 && entity2) {
      if (nameMode === 'entity1') {
        setMergedName(entity1.name || '');
      } else if (nameMode === 'entity2') {
        setMergedName(entity2.name || '');
      } else if (nameMode === 'both') {
        // Combine both names with a separator
        const name1 = entity1.name || '';
        const name2 = entity2.name || '';
        if (name1 && name2) {
          // Only combine if both exist and are different
          if (name1.toLowerCase() !== name2.toLowerCase()) {
            setMergedName(`${name1} / ${name2}`);
          } else {
            setMergedName(name1);
          }
        } else {
          setMergedName(name1 || name2);
        }
      }
    }
  }, [nameMode, entity1, entity2]);

  useEffect(() => {
    if (entity1 && entity2) {
      if (summaryMode === 'entity1') {
        setMergedSummary(entity1.summary || '');
      } else if (summaryMode === 'entity2') {
        setMergedSummary(entity2.summary || '');
      } else if (summaryMode === 'both') {
        // Combine both summaries
        const summary1 = entity1.summary || '';
        const summary2 = entity2.summary || '';
        if (summary1 && summary2) {
          setMergedSummary(`${summary1}\n\n---\n\n${summary2}`);
        } else {
          setMergedSummary(summary1 || summary2);
        }
      }
    }
  }, [summaryMode, entity1, entity2]);

  useEffect(() => {
    if (entity1 && entity2) {
      let notes = '';
      if (useEntity1Notes && entity1.notes) {
        notes = entity1.notes;
        if (entity2.notes) {
          notes += '\n\n' + entity2.notes;
        }
      } else if (entity2.notes) {
        notes = entity2.notes;
        if (entity1.notes) {
          notes = entity1.notes + '\n\n' + notes;
        }
      } else if (entity1.notes) {
        notes = entity1.notes;
      }
      setMergedNotes(notes);
    }
  }, [useEntity1Notes, entity1, entity2]);

  if (!isOpen || !entity1 || !entity2) return null;

  const handleMerge = async () => {
    if (!mergedName.trim()) {
      setError('Name is required');
      return;
    }

    setError(null);
    setIsMerging(true);

    try {
      // Determine which entity is source and which is target
      // Source will be deleted, target will be kept and updated
      // We'll use entity1 as source and entity2 as target
      const mergedData = {
        name: mergedName.trim(),
        summary: mergedSummary.trim() || null,
        notes: mergedNotes.trim() || null,
        type: mergedType || entity1.type || entity2.type,
        properties: {}, // Can be extended to merge additional properties
      };

      await onMerge(entity1.key, entity2.key, mergedData);
      onClose();
    } catch (err) {
      setError(err.message || 'Failed to merge entities');
    } finally {
      setIsMerging(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Escape') {
      onClose();
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      onClick={onClose}
      onKeyDown={handleKeyDown}
      tabIndex={-1}
      role="dialog"
      aria-modal="true"
      aria-labelledby="merge-entities-title"
    >
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-6xl max-h-[90vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-light-200 bg-owl-blue-50">
          <div className="flex items-center gap-2">
            <Merge className="w-5 h-5 text-owl-blue-600" />
            <h2 id="merge-entities-title" className="text-lg font-semibold text-owl-blue-900">
              Merge Entities
            </h2>
            {similarity !== null && (
              <span className="text-sm text-light-600 ml-2">
                ({Math.round(similarity * 100)}% similarity)
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-light-100 rounded transition-colors"
            aria-label="Close"
          >
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* Side-by-side comparison */}
          <div className="grid grid-cols-2 gap-4 mb-6">
            {/* Entity 1 */}
            <div className="border border-light-200 rounded-lg p-4 bg-light-50">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-owl-blue-900">Entity 1 (Source - will be deleted)</h3>
                <span className="text-xs px-2 py-1 bg-red-100 text-red-800 rounded">Source</span>
              </div>
              <div className="space-y-3">
                <div>
                  <label className="text-xs font-medium text-light-700 uppercase">Name</label>
                  <div className="mt-1 p-2 bg-white border border-light-200 rounded text-sm">
                    {entity1.name || <span className="text-light-400 italic">No name</span>}
                  </div>
                </div>
                <div>
                  <label className="text-xs font-medium text-light-700 uppercase">Type</label>
                  <div className="mt-1 p-2 bg-white border border-light-200 rounded text-sm">
                    {entity1.type || <span className="text-light-400 italic">No type</span>}
                  </div>
                </div>
                <div>
                  <label className="text-xs font-medium text-light-700 uppercase">Summary</label>
                  <div className="mt-1 p-2 bg-white border border-light-200 rounded text-sm max-h-32 overflow-y-auto whitespace-pre-wrap">
                    {entity1.summary || <span className="text-light-400 italic">No summary</span>}
                  </div>
                </div>
                <div>
                  <label className="text-xs font-medium text-light-700 uppercase">Notes</label>
                  <div className="mt-1 p-2 bg-white border border-light-200 rounded text-sm max-h-32 overflow-y-auto whitespace-pre-wrap">
                    {entity1.notes || <span className="text-light-400 italic">No notes</span>}
                  </div>
                </div>
              </div>
            </div>

            {/* Entity 2 */}
            <div className="border border-light-200 rounded-lg p-4 bg-light-50">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-owl-blue-900">Entity 2 (Target - will be kept)</h3>
                <span className="text-xs px-2 py-1 bg-green-100 text-green-800 rounded">Target</span>
              </div>
              <div className="space-y-3">
                <div>
                  <label className="text-xs font-medium text-light-700 uppercase">Name</label>
                  <div className="mt-1 p-2 bg-white border border-light-200 rounded text-sm">
                    {entity2.name || <span className="text-light-400 italic">No name</span>}
                  </div>
                </div>
                <div>
                  <label className="text-xs font-medium text-light-700 uppercase">Type</label>
                  <div className="mt-1 p-2 bg-white border border-light-200 rounded text-sm">
                    {entity2.type || <span className="text-light-400 italic">No type</span>}
                  </div>
                </div>
                <div>
                  <label className="text-xs font-medium text-light-700 uppercase">Summary</label>
                  <div className="mt-1 p-2 bg-white border border-light-200 rounded text-sm max-h-32 overflow-y-auto whitespace-pre-wrap">
                    {entity2.summary || <span className="text-light-400 italic">No summary</span>}
                  </div>
                </div>
                <div>
                  <label className="text-xs font-medium text-light-700 uppercase">Notes</label>
                  <div className="mt-1 p-2 bg-white border border-light-200 rounded text-sm max-h-32 overflow-y-auto whitespace-pre-wrap">
                    {entity2.notes || <span className="text-light-400 italic">No notes</span>}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Merge Configuration */}
          <div className="border-t border-light-200 pt-6">
            <h3 className="font-semibold text-owl-blue-900 mb-4 flex items-center gap-2">
              <ArrowRight className="w-4 h-4" />
              Merged Result
            </h3>
            <div className="space-y-4">
              {/* Name */}
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <label className="text-sm font-medium text-light-800">Name *</label>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setNameMode('entity1')}
                      className={`text-xs px-2 py-1 rounded transition-colors ${
                        nameMode === 'entity1'
                          ? 'bg-owl-blue-500 text-white'
                          : 'bg-light-200 text-light-700 hover:bg-light-300'
                      }`}
                    >
                      Use Entity 1
                    </button>
                    <button
                      onClick={() => setNameMode('entity2')}
                      className={`text-xs px-2 py-1 rounded transition-colors ${
                        nameMode === 'entity2'
                          ? 'bg-owl-blue-500 text-white'
                          : 'bg-light-200 text-light-700 hover:bg-light-300'
                      }`}
                    >
                      Use Entity 2
                    </button>
                    <button
                      onClick={() => setNameMode('both')}
                      className={`text-xs px-2 py-1 rounded transition-colors ${
                        nameMode === 'both'
                          ? 'bg-owl-blue-500 text-white'
                          : 'bg-light-200 text-light-700 hover:bg-light-300'
                      }`}
                    >
                      Use Both
                    </button>
                  </div>
                </div>
                <input
                  type="text"
                  value={mergedName}
                  onChange={(e) => setMergedName(e.target.value)}
                  className="w-full p-2 border border-light-300 rounded-md focus:ring-owl-blue-500 focus:border-owl-blue-500"
                  placeholder="Merged entity name"
                />
                {nameMode === 'both' && (
                  <p className="mt-1 text-xs text-light-600">
                    Names will be combined with " / " separator. You can edit manually.
                  </p>
                )}
              </div>

              {/* Type */}
              <div>
                <label className="text-sm font-medium text-light-800 mb-2 block">Type</label>
                <input
                  type="text"
                  value={mergedType}
                  onChange={(e) => setMergedType(e.target.value)}
                  className="w-full p-2 border border-light-300 rounded-md focus:ring-owl-blue-500 focus:border-owl-blue-500"
                  placeholder="Entity type"
                />
              </div>

              {/* Summary */}
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <label className="text-sm font-medium text-light-800">Summary</label>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setSummaryMode('entity1')}
                      className={`text-xs px-2 py-1 rounded transition-colors ${
                        summaryMode === 'entity1'
                          ? 'bg-owl-blue-500 text-white'
                          : 'bg-light-200 text-light-700 hover:bg-light-300'
                      }`}
                    >
                      Use Entity 1
                    </button>
                    <button
                      onClick={() => setSummaryMode('entity2')}
                      className={`text-xs px-2 py-1 rounded transition-colors ${
                        summaryMode === 'entity2'
                          ? 'bg-owl-blue-500 text-white'
                          : 'bg-light-200 text-light-700 hover:bg-light-300'
                      }`}
                    >
                      Use Entity 2
                    </button>
                    <button
                      onClick={() => setSummaryMode('both')}
                      className={`text-xs px-2 py-1 rounded transition-colors ${
                        summaryMode === 'both'
                          ? 'bg-owl-blue-500 text-white'
                          : 'bg-light-200 text-light-700 hover:bg-light-300'
                      }`}
                    >
                      Use Both
                    </button>
                  </div>
                </div>
                <textarea
                  value={mergedSummary}
                  onChange={(e) => setMergedSummary(e.target.value)}
                  className="w-full p-2 border border-light-300 rounded-md focus:ring-owl-blue-500 focus:border-owl-blue-500"
                  rows={4}
                  placeholder="Merged summary"
                />
                {summaryMode === 'both' && (
                  <p className="mt-1 text-xs text-light-600">
                    Summaries will be combined with a separator. You can edit manually.
                  </p>
                )}
              </div>

              {/* Notes */}
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <label className="text-sm font-medium text-light-800">Notes</label>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setUseEntity1Notes(true)}
                      className={`text-xs px-2 py-1 rounded transition-colors ${
                        useEntity1Notes
                          ? 'bg-owl-blue-500 text-white'
                          : 'bg-light-200 text-light-700 hover:bg-light-300'
                      }`}
                    >
                      Entity 1 First
                    </button>
                    <button
                      onClick={() => setUseEntity1Notes(false)}
                      className={`text-xs px-2 py-1 rounded transition-colors ${
                        !useEntity1Notes
                          ? 'bg-owl-blue-500 text-white'
                          : 'bg-light-200 text-light-700 hover:bg-light-300'
                      }`}
                    >
                      Entity 2 First
                    </button>
                  </div>
                </div>
                <textarea
                  value={mergedNotes}
                  onChange={(e) => setMergedNotes(e.target.value)}
                  className="w-full p-2 border border-light-300 rounded-md focus:ring-owl-blue-500 focus:border-owl-blue-500"
                  rows={6}
                  placeholder="Merged notes (combines both entities)"
                />
              </div>
            </div>
          </div>

          {error && (
            <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded text-red-700 text-sm">
              {error}
            </div>
          )}

          {/* Warning */}
          <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded text-yellow-800 text-sm">
            <strong>Warning:</strong> This action will delete Entity 1 and merge all its relationships into Entity 2. 
            This cannot be undone.
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-4 border-t border-light-200 bg-light-50">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-light-200 text-light-800 rounded-md hover:bg-light-300 transition-colors"
            disabled={isMerging}
          >
            Cancel
          </button>
          <button
            onClick={handleMerge}
            disabled={isMerging || !mergedName.trim()}
            className="px-4 py-2 bg-owl-blue-600 text-white rounded-md hover:bg-owl-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            <Merge className="w-4 h-4" />
            {isMerging ? 'Merging...' : 'Merge Entities'}
          </button>
        </div>
      </div>
    </div>
  );
}
