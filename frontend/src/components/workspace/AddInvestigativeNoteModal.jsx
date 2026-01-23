import React, { useState } from 'react';
import { X, Save } from 'lucide-react';

/**
 * Add Investigative Note Modal
 * 
 * Modal for adding investigative notes (thoughts and insights)
 */
export default function AddInvestigativeNoteModal({ isOpen, onClose, onSave }) {
  const [content, setContent] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!content.trim()) return;

    setSaving(true);
    try {
      await onSave(content.trim());
      setContent('');
      onClose();
    } catch (err) {
      console.error('Failed to save note:', err);
      alert('Failed to save note');
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-2xl mx-4 max-h-[90vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-light-200">
          <h3 className="text-lg font-semibold text-owl-blue-900">Add Investigative Note</h3>
          <button onClick={onClose} className="p-1 hover:bg-light-100 rounded" disabled={saving}>
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-4">
          <div>
            <label className="block text-sm font-medium text-owl-blue-900 mb-2">
              Note Content *
            </label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={12}
              placeholder="Enter your thoughts, insights, observations, or findings..."
              className="w-full px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
              required
              disabled={saving}
              autoFocus
            />
            <p className="text-xs text-light-500 mt-1">
              This note will be saved with a timestamp and can be attached to theories.
            </p>
          </div>

          <div className="flex gap-2 pt-4 border-t border-light-200 mt-4">
            <button
              type="submit"
              disabled={saving || !content.trim()}
              className="flex-1 px-4 py-2 bg-owl-blue-600 text-white rounded-lg hover:bg-owl-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              <Save className="w-4 h-4" />
              {saving ? 'Saving...' : 'Save Note'}
            </button>
            <button
              type="button"
              onClick={onClose}
              disabled={saving}
              className="px-4 py-2 bg-light-200 text-light-700 rounded-lg hover:bg-light-300 disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
