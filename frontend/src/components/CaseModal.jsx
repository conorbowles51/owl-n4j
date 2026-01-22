import React, { useState, useEffect } from 'react';
import { X, Save, FolderPlus } from 'lucide-react';
import { casesAPI } from '../services/api';

/**
 * CaseModal Component
 *
 * Modal for creating/saving a case with title, description, and notes
 *
 * Note: The new PostgreSQL backend uses 'title' instead of 'name' for cases.
 * This component supports both for backwards compatibility.
 */
export default function CaseModal({
  isOpen,
  onClose,
  onSave,
  existingCaseId = null,
  existingCaseTitle = null,  // New: use title (backward compatible with existingCaseName)
  existingCaseName = null,   // Legacy: kept for backwards compatibility
  existingDescription = null, // New: case description
  nextVersion = 1,
}) {
  const [caseTitle, setCaseTitle] = useState('');
  const [caseDescription, setCaseDescription] = useState('');
  const [saveNotes, setSaveNotes] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (isOpen) {
      // Use existingCaseTitle if available, fallback to existingCaseName for backwards compatibility
      const titleValue = existingCaseTitle || existingCaseName || '';
      setCaseTitle(titleValue);
      setCaseDescription(existingDescription || '');
      setSaveNotes('');
    }
  }, [isOpen, existingCaseTitle, existingCaseName, existingDescription]);

  if (!isOpen) return null;

  const handleSave = async () => {
    if (!caseTitle.trim()) {
      alert('Please enter a title for the case');
      return;
    }

    setIsSaving(true);
    try {
      // Pass title, description, and notes to the save handler
      await onSave(caseTitle.trim(), saveNotes.trim(), caseDescription.trim());
      setCaseTitle('');
      setCaseDescription('');
      setSaveNotes('');
    } catch (err) {
      console.error('Failed to save case:', err);
      alert(`Failed to save case: ${err.message}`);
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancel = () => {
    setCaseTitle('');
    setCaseDescription('');
    setSaveNotes('');
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 w-full max-w-md border border-light-200 shadow-xl">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <FolderPlus className="w-5 h-5 text-owl-blue-600" />
            <h2 className="text-lg font-semibold text-owl-blue-900">
              {existingCaseId ? 'Save Case Version' : 'Create New Case'}
            </h2>
          </div>
          <button
            onClick={handleCancel}
            className="p-1 hover:bg-light-100 rounded transition-colors"
          >
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-light-700 mb-2">
              Case Title *
            </label>
            <input
              type="text"
              value={caseTitle}
              onChange={(e) => setCaseTitle(e.target.value)}
              placeholder="Enter case title"
              className="w-full px-3 py-2 bg-white border border-light-300 rounded-lg text-light-900 placeholder-light-500 focus:outline-none focus:border-owl-blue-500"
              autoFocus
              disabled={isSaving}
            />
            {existingCaseId && (
              <p className="text-xs text-light-600 mt-1">
                Saving as version {nextVersion} of this case
              </p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-light-700 mb-2">
              Description
            </label>
            <textarea
              value={caseDescription}
              onChange={(e) => setCaseDescription(e.target.value)}
              placeholder="Add a description for this case (optional)..."
              rows={2}
              className="w-full px-3 py-2 bg-white border border-light-300 rounded-lg text-light-900 placeholder-light-500 focus:outline-none focus:border-owl-blue-500 resize-none"
              disabled={isSaving}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-light-700 mb-2">
              Save Notes
            </label>
            <textarea
              value={saveNotes}
              onChange={(e) => setSaveNotes(e.target.value)}
              placeholder="Add notes about this save (optional)..."
              rows={2}
              className="w-full px-3 py-2 bg-white border border-light-300 rounded-lg text-light-900 placeholder-light-500 focus:outline-none focus:border-owl-blue-500 resize-none"
              disabled={isSaving}
            />
          </div>

          <div className="text-xs text-light-600 bg-light-50 rounded p-2 border border-light-200">
            <p>This case will include:</p>
            <ul className="list-disc list-inside mt-1 space-y-0.5">
              <li>Current graph (as Cypher queries)</li>
              <li>All saved snapshots</li>
              <li>Version history for this case</li>
            </ul>
          </div>

          <div className="flex items-center gap-3 pt-2">
            <button
              onClick={handleSave}
              disabled={isSaving || !caseTitle.trim()}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-owl-blue-500 hover:bg-owl-blue-600 disabled:bg-light-300 disabled:text-light-500 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
            >
              <Save className="w-4 h-4" />
              {isSaving ? 'Saving...' : existingCaseId ? 'Save Version' : 'Create Case'}
            </button>
            <button
              onClick={handleCancel}
              disabled={isSaving}
              className="px-4 py-2 bg-light-100 hover:bg-light-200 disabled:opacity-50 text-light-700 rounded-lg transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

