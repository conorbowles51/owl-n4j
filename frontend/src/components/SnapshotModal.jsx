import React, { useState } from 'react';
import { X, Save, FileDown } from 'lucide-react';

/**
 * SnapshotModal Component
 * 
 * Modal for saving a snapshot with name and notes
 */
export default function SnapshotModal({ 
  isOpen, 
  onClose, 
  onSave,
  onExportPDF,
  nodeCount,
  linkCount 
}) {
  const [name, setName] = useState('');
  const [notes, setNotes] = useState('');

  if (!isOpen) return null;

  const handleSave = () => {
    if (!name.trim()) {
      alert('Please enter a name for the snapshot');
      return;
    }
    onSave(name.trim(), notes.trim());
    setName('');
    setNotes('');
  };

  const handleCancel = () => {
    setName('');
    setNotes('');
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 w-full max-w-md border border-light-200 shadow-xl">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-owl-blue-900">Save Snapshot</h2>
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
              Name *
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Enter snapshot name"
              className="w-full px-3 py-2 bg-white border border-light-300 rounded-lg text-light-900 placeholder-light-500 focus:outline-none focus:border-owl-blue-500"
              autoFocus
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-light-700 mb-2">
              Notes
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Add notes to explain this snapshot..."
              rows={4}
              className="w-full px-3 py-2 bg-white border border-light-300 rounded-lg text-light-900 placeholder-light-500 focus:outline-none focus:border-owl-blue-500 resize-none"
            />
          </div>

          <div className="text-xs text-light-600 bg-light-50 rounded p-2 border border-light-200">
            <p>This snapshot will include:</p>
            <ul className="list-disc list-inside mt-1 space-y-0.5">
              <li>{nodeCount} selected nodes</li>
              <li>{linkCount} relationships</li>
              <li>Timeline events for selected nodes</li>
              <li>Node overview details</li>
              <li>AI chat history related to this selection</li>
            </ul>
          </div>

          <div className="flex items-center gap-3 pt-2">
            <button
              onClick={handleSave}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-owl-orange-500 hover:bg-owl-orange-600 text-white rounded-lg transition-colors"
            >
              <Save className="w-4 h-4" />
              Save Snapshot
            </button>
            {onExportPDF && (
              <button
                onClick={() => {
                  if (!name.trim()) {
                    alert('Please enter a name for the snapshot before exporting');
                    return;
                  }
                  onExportPDF(name.trim(), notes.trim());
                }}
                className="flex items-center justify-center gap-2 px-4 py-2 bg-light-100 hover:bg-light-200 text-light-700 rounded-lg transition-colors"
                title="Export to PDF"
              >
                <FileDown className="w-4 h-4" />
                Export PDF
              </button>
            )}
            <button
              onClick={handleCancel}
              className="px-4 py-2 bg-light-100 hover:bg-light-200 text-light-700 rounded-lg transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}



