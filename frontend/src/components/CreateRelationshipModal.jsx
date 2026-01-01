import React, { useState } from 'react';
import { X, Link2 } from 'lucide-react';
import { graphAPI } from '../services/api';

/**
 * CreateRelationshipModal Component
 * 
 * Modal for creating relationships between nodes.
 */
export default function CreateRelationshipModal({
  isOpen,
  onClose,
  sourceNodes,
  targetNodes,
  onRelationshipCreated,
}) {
  const [relationshipType, setRelationshipType] = useState('');
  const [notes, setNotes] = useState('');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState(null);

  // Reset form when modal opens/closes
  React.useEffect(() => {
    if (isOpen) {
      setRelationshipType('');
      setNotes('');
      setError(null);
    }
  }, [isOpen]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    if (!relationshipType.trim()) {
      setError('Relationship type is required.');
      return;
    }

    setCreating(true);

    try {
      // Create relationships between all source nodes and all target nodes
      const relationships = [];
      for (const sourceNode of sourceNodes) {
        for (const targetNode of targetNodes) {
          relationships.push({
            from_key: sourceNode.key,
            to_key: targetNode.key,
            type: relationshipType.trim(),
            notes: notes.trim() || null,
          });
        }
      }

      // Call API to create relationships
      const result = await graphAPI.createRelationships(relationships);

      if (result.success) {
        onRelationshipCreated(result.cypher);
        onClose();
      } else {
        setError(result.error || 'Failed to create relationships.');
      }
    } catch (err) {
      console.error('Error creating relationships:', err);
      setError(err.message || 'An unexpected error occurred.');
    } finally {
      setCreating(false);
    }
  };

  if (!isOpen) return null;

  const sourceCount = sourceNodes.length;
  const targetCount = targetNodes.length;
  const totalRelationships = sourceCount * targetCount;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="w-full max-w-md max-h-[90vh] bg-white rounded-lg shadow-2xl overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-light-200 bg-light-50">
          <div className="flex items-center gap-2">
            <Link2 className="w-5 h-5 text-owl-blue-700" />
            <h2 className="text-lg font-semibold text-owl-blue-900">
              Create Relationship{totalRelationships > 1 ? 's' : ''}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded hover:bg-light-200 text-light-600 transition-colors"
            disabled={creating}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4 text-sm text-red-700">
              {error}
            </div>
          )}

          {/* Source and Target Info */}
          <div className="mb-6 space-y-3">
            <div>
              <label className="block text-xs font-medium text-light-600 mb-1">
                Source Node{sourceCount > 1 ? 's' : ''}
              </label>
              <div className="bg-light-50 rounded-lg p-3 text-sm">
                {sourceNodes.map((node, idx) => (
                  <div key={node.key} className={idx > 0 ? 'mt-2' : ''}>
                    <span className="font-medium text-owl-blue-900">{node.name}</span>
                    <span className="text-light-600 ml-2">({node.type})</span>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-light-600 mb-1">
                Target Node{targetCount > 1 ? 's' : ''}
              </label>
              <div className="bg-light-50 rounded-lg p-3 text-sm">
                {targetNodes.map((node, idx) => (
                  <div key={node.key} className={idx > 0 ? 'mt-2' : ''}>
                    <span className="font-medium text-owl-blue-900">{node.name}</span>
                    <span className="text-light-600 ml-2">({node.type})</span>
                  </div>
                ))}
              </div>
            </div>

            {totalRelationships > 1 && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-xs text-blue-800">
                This will create <strong>{totalRelationships} relationship{totalRelationships > 1 ? 's' : ''}</strong> between the source and target nodes.
              </div>
            )}
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-light-700 mb-1">
                Relationship Type *
              </label>
              <input
                type="text"
                value={relationshipType}
                onChange={(e) => setRelationshipType(e.target.value)}
                className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                placeholder="e.g., WORKS_FOR, OWNS, RELATED_TO, MET_WITH"
                required
                disabled={creating}
                autoFocus
              />
              <p className="text-xs text-light-500 mt-1">
                Use descriptive relationship types (e.g., WORKS_FOR, OWNS, RELATED_TO)
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-light-700 mb-1">
                Notes (optional)
              </label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                rows={3}
                placeholder="Additional notes about this relationship"
                disabled={creating}
              />
            </div>

            <div className="flex justify-end gap-2 pt-4">
              <button
                type="button"
                onClick={onClose}
                disabled={creating}
                className="px-4 py-2 text-light-700 hover:bg-light-100 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={creating || !relationshipType.trim()}
                className="flex items-center gap-2 px-4 py-2 bg-owl-blue-600 text-white rounded-lg hover:bg-owl-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {creating ? 'Creating...' : `Create Relationship${totalRelationships > 1 ? 's' : ''}`}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}




