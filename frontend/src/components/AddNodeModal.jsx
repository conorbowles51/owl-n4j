import React, { useState, useEffect } from 'react';
import { X, Plus, Loader2 } from 'lucide-react';
import { graphAPI } from '../services/api';

/**
 * AddNodeModal Component
 *
 * Modal for creating a new node in the graph
 * @param {Object} props
 * @param {boolean} props.isOpen - Whether the modal is open
 * @param {Function} props.onClose - Callback when modal is closed
 * @param {Function} props.onNodeCreated - Callback when a node is created
 * @param {string} props.caseId - REQUIRED: Case ID for case-specific data
 */
export default function AddNodeModal({ isOpen, onClose, onNodeCreated, caseId }) {
  const [name, setName] = useState('');
  const [type, setType] = useState('');
  const [description, setDescription] = useState('');
  const [summary, setSummary] = useState('');
  const [entityTypes, setEntityTypes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [generatedCypher, setGeneratedCypher] = useState(null);

  useEffect(() => {
    if (isOpen) {
      loadEntityTypes();
      // Reset form
      setName('');
      setType('');
      setDescription('');
      setSummary('');
      setError(null);
      setGeneratedCypher(null);
    }
  }, [isOpen]);

  const loadEntityTypes = async () => {
    if (!caseId) return;
    setLoading(true);
    try {
      const data = await graphAPI.getEntityTypes(caseId);
      setEntityTypes(data.entity_types || []);
      // Set first entity type as default if available
      if (data.entity_types && data.entity_types.length > 0) {
        setType(data.entity_types[0].type);
      }
    } catch (err) {
      console.error('Failed to load entity types:', err);
      setError('Failed to load entity types');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!name.trim()) {
      setError('Node name is required');
      return;
    }
    
    if (!type.trim()) {
      setError('Node type is required');
      return;
    }

    setSaving(true);
    setError(null);
    
    try {
      const result = await graphAPI.createNode({
        name: name.trim(),
        type: type.trim(),
        description: description.trim() || null,
        summary: summary.trim() || null,
      });

      if (result.success) {
        setGeneratedCypher(result.cypher);
        // Notify parent component to refresh graph
        if (onNodeCreated) {
          onNodeCreated(result.node_key);
        }
        // Close modal after a brief delay to show success
        setTimeout(() => {
          onClose();
        }, 1500);
      } else {
        setError(result.error || 'Failed to create node');
      }
    } catch (err) {
      console.error('Failed to create node:', err);
      setError(err.message || 'Failed to create node');
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="w-full max-w-2xl max-h-[90vh] bg-white rounded-lg shadow-2xl overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-light-200 bg-light-50">
          <div className="flex items-center gap-2">
            <Plus className="w-5 h-5 text-owl-blue-700" />
            <h2 className="text-lg font-semibold text-owl-blue-900">
              Add Node to Graph
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded hover:bg-light-200 text-light-600 transition-colors"
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

          {generatedCypher && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-4">
              <p className="text-sm font-semibold text-green-800 mb-2">Node created successfully!</p>
              <details className="text-sm">
                <summary className="cursor-pointer text-green-700 hover:text-green-900 mb-2">
                  Generated Cypher
                </summary>
                <pre className="bg-white border border-green-200 rounded p-3 mt-2 overflow-x-auto text-xs">
                  <code>{generatedCypher}</code>
                </pre>
              </details>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-light-700 mb-1">
                Node Name *
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                placeholder="e.g., John Smith, Company ABC"
                required
                disabled={saving}
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-light-700 mb-1">
                Entity Type *
              </label>
              {loading ? (
                <div className="flex items-center gap-2 text-light-600">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span className="text-sm">Loading entity types...</span>
                </div>
              ) : (
                <>
                  <input
                    type="text"
                    value={type}
                    onChange={(e) => setType(e.target.value)}
                    list="entity-types-list"
                    placeholder="Enter entity type (e.g., Person, Company)"
                    className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                    required
                    disabled={saving}
                  />
                  {entityTypes.length > 0 && (
                    <datalist id="entity-types-list">
                      {entityTypes.map((et) => (
                        <option key={et.type} value={et.type}>
                          {et.type} ({et.count})
                        </option>
                      ))}
                    </datalist>
                  )}
                  <p className="text-xs text-light-500 mt-1">
                    {entityTypes.length > 0 
                      ? `Start typing to see existing types (${entityTypes.length} available) or enter a new type`
                      : 'Enter the entity type (e.g., Person, Company, Location)'
                    }
                  </p>
                </>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-light-700 mb-1">
                Summary
              </label>
              <textarea
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                rows={3}
                placeholder="Brief summary of the node (2-4 sentences)"
                disabled={saving}
              />
              <p className="text-xs text-light-500 mt-1">
                A concise summary describing what this entity is and its significance
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-light-700 mb-1">
                Description
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                rows={4}
                placeholder="Detailed description, notes, or additional information"
                disabled={saving}
              />
              <p className="text-xs text-light-500 mt-1">
                Additional details, context, or notes about this node
              </p>
            </div>

            <div className="flex items-center justify-end gap-3 pt-4">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-light-700 hover:bg-light-200 rounded-lg transition-colors"
                disabled={saving}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving || !name.trim() || !type.trim()}
                className="flex items-center gap-2 px-4 py-2 bg-owl-blue-600 text-white rounded-lg hover:bg-owl-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {saving ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Creating...
                  </>
                ) : (
                  <>
                    <Plus className="w-4 h-4" />
                    Create Node
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

