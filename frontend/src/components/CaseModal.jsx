import React, { useState, useEffect } from 'react';
import { X, Save, FolderPlus } from 'lucide-react';
import { casesAPI } from '../services/api';

/**
 * CaseModal Component
 * 
 * Modal for saving a case with name and notes
 */
export default function CaseModal({ 
  isOpen, 
  onClose, 
  onSave,
  existingCaseId = null,
  existingCaseName = null,
  nextVersion = 1,
}) {
  const [caseName, setCaseName] = useState('');
  const [saveNotes, setSaveNotes] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (isOpen) {
      if (existingCaseName) {
        setCaseName(existingCaseName);
      } else {
        setCaseName('');
      }
      setSaveNotes('');
    }
  }, [isOpen, existingCaseName]);

  if (!isOpen) return null;

  const handleSave = async () => {
    if (!caseName.trim()) {
      alert('Please enter a name for the case');
      return;
    }

    setIsSaving(true);
    try {
      await onSave(caseName.trim(), saveNotes.trim());
      setCaseName('');
      setSaveNotes('');
    } catch (err) {
      console.error('Failed to save case:', err);
      alert(`Failed to save case: ${err.message}`);
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancel = () => {
    setCaseName('');
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
              Case Name *
            </label>
            <input
              type="text"
              value={caseName}
              onChange={(e) => setCaseName(e.target.value)}
              placeholder="Enter case name"
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
              Save Notes
            </label>
            <textarea
              value={saveNotes}
              onChange={(e) => setSaveNotes(e.target.value)}
              placeholder="Add notes about this save (optional)..."
              rows={3}
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
              disabled={isSaving || !caseName.trim()}
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

