import React, { useState } from 'react';
import { X, Save, FileDown } from 'lucide-react';

/**
 * ArtifactModal Component
 * 
 * Modal for saving an artifact with name and notes
 */
export default function ArtifactModal({ 
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
      alert('Please enter a name for the artifact');
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
      <div className="bg-dark-800 rounded-lg p-6 w-full max-w-md border border-dark-700">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-dark-100">Save Artifact</h2>
          <button
            onClick={handleCancel}
            className="p-1 hover:bg-dark-700 rounded transition-colors"
          >
            <X className="w-5 h-5 text-dark-400" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-dark-300 mb-2">
              Name *
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Enter artifact name"
              className="w-full px-3 py-2 bg-dark-900 border border-dark-700 rounded-lg text-dark-100 placeholder-dark-500 focus:outline-none focus:border-cyan-500"
              autoFocus
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-dark-300 mb-2">
              Notes
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Add notes to explain this artifact..."
              rows={4}
              className="w-full px-3 py-2 bg-dark-900 border border-dark-700 rounded-lg text-dark-100 placeholder-dark-500 focus:outline-none focus:border-cyan-500 resize-none"
            />
          </div>

          <div className="text-xs text-dark-400 bg-dark-900/50 rounded p-2">
            <p>This artifact will include:</p>
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
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg transition-colors"
            >
              <Save className="w-4 h-4" />
              Save Artifact
            </button>
            {onExportPDF && (
              <button
                onClick={() => {
                  if (!name.trim()) {
                    alert('Please enter a name for the artifact before exporting');
                    return;
                  }
                  onExportPDF(name.trim(), notes.trim());
                }}
                className="flex items-center justify-center gap-2 px-4 py-2 bg-dark-700 hover:bg-dark-600 text-dark-300 rounded-lg transition-colors"
                title="Export to PDF"
              >
                <FileDown className="w-4 h-4" />
                Export PDF
              </button>
            )}
            <button
              onClick={handleCancel}
              className="px-4 py-2 bg-dark-700 hover:bg-dark-600 text-dark-300 rounded-lg transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

