import React, { useState, useEffect } from 'react';
import { X, Save } from 'lucide-react';

/**
 * EditNodeModal Component
 * 
 * Modal for editing node information (summary and notes) for one or more selected nodes
 */
export default function EditNodeModal({ isOpen, onClose, nodes, onSave }) {
  const [name, setName] = useState('');
  const [summary, setSummary] = useState('');
  const [notes, setNotes] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState(null);

  // Reset form when nodes change or modal opens
  useEffect(() => {
    if (isOpen && nodes && nodes.length > 0) {
      // If editing multiple nodes, start with empty fields (user adds new info)
      // If editing single node, pre-fill with existing values
      if (nodes.length === 1) {
        setName(nodes[0].name || '');
        setSummary(nodes[0].summary || '');
        setNotes(nodes[0].notes || '');
      } else {
        setName('');
        setSummary('');
        setNotes('');
      }
      setError(null);
    }
  }, [isOpen, nodes]);

  if (!isOpen || !nodes || nodes.length === 0) return null;

  const handleSave = async () => {
    setError(null);
    setIsSaving(true);

    try {
      // Build updates object with only fields that have values
      const updates = {};
      if (name.trim()) {
        updates.name = name.trim();
      }
      if (summary.trim()) {
        updates.summary = summary.trim();
      }
      if (notes.trim()) {
        updates.notes = notes.trim();
      }

      // Only proceed if at least one field has a value
      if (Object.keys(updates).length === 0) {
        setError('Please enter at least one field to update');
        setIsSaving(false);
        return;
      }

      // Update each node
      const updatePromises = nodes.map(node => onSave(node.key, updates));
      await Promise.all(updatePromises);
      onClose();
    } catch (err) {
      setError(err.message || 'Failed to save node updates');
    } finally {
      setIsSaving(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Escape') {
      onClose();
    }
  };

  const nodeCount = nodes.length;
  const nodeNames = nodes.map(n => n.name).join(', ');

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      onKeyDown={handleKeyDown}
    >
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col m-4">
        {/* Header */}
        <div className="p-6 border-b border-light-200 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-semibold text-owl-blue-900">
              {nodeCount === 1 ? 'Edit Node Information' : `Edit ${nodeCount} Nodes`}
            </h2>
            {nodeCount === 1 && (
              <p className="text-sm text-light-600 mt-1">{nodeNames}</p>
            )}
            {nodeCount > 1 && (
              <p className="text-sm text-light-600 mt-1">
                Updating: {nodeNames.length > 60 ? `${nodeNames.substring(0, 60)}...` : nodeNames}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-light-100 rounded transition-colors"
            disabled={isSaving}
          >
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Error message */}
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
              {error}
            </div>
          )}

          {/* Info message for multiple nodes */}
          {nodeCount > 1 && (
            <div className="bg-blue-50 border border-blue-200 text-blue-700 px-4 py-3 rounded text-sm">
              <strong>Note:</strong> The information you enter will be saved to all {nodeCount} selected nodes. Leave fields empty to keep existing values unchanged.
            </div>
          )}

          {/* Name field */}
          <div>
            <label className="block text-sm font-medium text-light-700 mb-2">
              Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={nodeCount > 1 ? "Enter name to update for all selected nodes..." : "Enter or edit node name..."}
              className="w-full px-3 py-2 border border-light-300 rounded-md focus:outline-none focus:ring-2 focus:ring-owl-blue-500 focus:border-transparent"
              disabled={isSaving}
            />
            {nodeCount === 1 && nodes[0].name && (
              <p className="text-xs text-light-500 mt-1">
                Current: {nodes[0].name}
              </p>
            )}
          </div>

          {/* Summary field */}
          <div>
            <label className="block text-sm font-medium text-light-700 mb-2">
              Summary
            </label>
            <textarea
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              placeholder={nodeCount > 1 ? "Enter summary to add/update for all selected nodes..." : "Enter or edit node summary..."}
              className="w-full px-3 py-2 border border-light-300 rounded-md focus:outline-none focus:ring-2 focus:ring-owl-blue-500 focus:border-transparent resize-none"
              rows={4}
              disabled={isSaving}
            />
            {nodeCount === 1 && nodes[0].summary && (
              <p className="text-xs text-light-500 mt-1">
                Current: {nodes[0].summary.substring(0, 100)}{nodes[0].summary.length > 100 ? '...' : ''}
              </p>
            )}
          </div>

          {/* Notes field */}
          <div>
            <label className="block text-sm font-medium text-light-700 mb-2">
              Notes
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder={nodeCount > 1 ? "Enter notes to add/update for all selected nodes..." : "Enter or edit node notes..."}
              className="w-full px-3 py-2 border border-light-300 rounded-md focus:outline-none focus:ring-2 focus:ring-owl-blue-500 focus:border-transparent resize-none font-mono text-sm"
              rows={6}
              disabled={isSaving}
            />
            {nodeCount === 1 && nodes[0].notes && (
              <p className="text-xs text-light-500 mt-1">
                Current length: {nodes[0].notes.length} characters
              </p>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-light-200 flex items-center justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-light-700 hover:bg-light-100 rounded-md transition-colors"
            disabled={isSaving}
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="px-4 py-2 text-sm font-medium text-white bg-owl-blue-600 hover:bg-owl-blue-700 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {isSaving ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                Save
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

