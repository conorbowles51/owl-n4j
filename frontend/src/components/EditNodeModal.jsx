import React, { useState, useEffect } from 'react';
import { X, Save, Link2, Plus, Trash2 } from 'lucide-react';
import CreateRelationshipModal from './CreateRelationshipModal';

/**
 * EditNodeModal Component
 * 
 * Modal for editing node information (summary and notes) for one or more selected nodes
 * Supports adding relationships to edited nodes
 */
export default function EditNodeModal({ isOpen, onClose, nodes, onSave, caseId = null, onRelationshipCreated = null, tableNodes = [] }) {
  const [name, setName] = useState('');
  const [summary, setSummary] = useState('');
  const [notes, setNotes] = useState('');
  const [typeFields, setTypeFields] = useState([]); // All fields for the node's type
  const [typeFieldValues, setTypeFieldValues] = useState({}); // Values for type-specific fields
  const [customFields, setCustomFields] = useState([]); // Array of { name: '', value: '' } for new fields
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState(null);
  const [showRelationshipModal, setShowRelationshipModal] = useState(false);

  // Load fields for the node's type
  useEffect(() => {
    if (isOpen && nodes && nodes.length > 0 && tableNodes.length > 0) {
      // Get the type from the first node (assuming all selected nodes are the same type)
      const nodeType = nodes[0].type;
      if (nodeType) {
        loadTypeFields(nodeType, nodes);
      } else {
        setTypeFields([]);
        setTypeFieldValues({});
      }
    }
  }, [isOpen, nodes, tableNodes]);

  // Reset form when nodes change or modal opens
  useEffect(() => {
    if (isOpen && nodes && nodes.length > 0) {
      // If editing multiple nodes, start with empty fields (user adds new info)
      // If editing single node, pre-fill with existing values
      if (nodes.length === 1) {
        const node = nodes[0];
        setName(node.name || '');
        setSummary(node.summary || '');
        setNotes(node.notes || '');
        
        // Load type-specific field values
        const flat = flattenNode(node);
        const fieldValues = {};
        typeFields.forEach(field => {
          fieldValues[field] = flat[field] || '';
        });
        setTypeFieldValues(fieldValues);
      } else {
        setName('');
        setSummary('');
        setNotes('');
        // Clear type field values for multiple nodes
        const fieldValues = {};
        typeFields.forEach(field => {
          fieldValues[field] = '';
        });
        setTypeFieldValues(fieldValues);
      }
      setError(null);
    }
  }, [isOpen, nodes, typeFields]);

  // Helper to flatten node (same logic as GraphTableView)
  const flattenNode = (node) => {
    const out = {};
    if (!node) return out;
    for (const k of ['key', 'id', 'name', 'type', 'summary', 'notes']) {
      const v = node[k];
      if (v !== undefined && v !== null) out[k] = v;
    }
    const props = node.properties || {};
    for (const k of Object.keys(props)) {
      if (out[k] === undefined) {
        const v = props[k];
        if (v !== undefined && v !== null) {
          out[k] = typeof v === 'object' ? JSON.stringify(v) : v;
        }
      }
    }
    return out;
  };

  const loadTypeFields = (selectedType, editingNodes) => {
    // Filter table nodes by type
    const nodesOfType = tableNodes.filter(n => n.type === selectedType);
    
    if (nodesOfType.length === 0) {
      setTypeFields([]);
      setTypeFieldValues({});
      return;
    }

    // Extract all unique property keys from nodes of this type
    const standardFields = new Set(['key', 'id', 'name', 'type', 'summary', 'notes', 'case_id', 'verified_facts', 'ai_insights']);
    const fieldSet = new Set();
    
    nodesOfType.forEach(node => {
      const flat = flattenNode(node);
      Object.keys(flat).forEach(key => {
        if (!standardFields.has(key)) {
          fieldSet.add(key);
        }
      });
    });

    // Convert to array and sort
    const fields = Array.from(fieldSet).sort();
    setTypeFields(fields);
    
    // Initialize field values from the first editing node (if single node edit)
    const initialValues = {};
    if (editingNodes && editingNodes.length === 1) {
      const flat = flattenNode(editingNodes[0]);
      fields.forEach(field => {
        initialValues[field] = flat[field] || '';
      });
    } else {
      fields.forEach(field => {
        initialValues[field] = '';
      });
    }
    setTypeFieldValues(initialValues);
  };

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

      // Add type-specific fields
      const properties = {};
      typeFields.forEach(field => {
        const value = typeFieldValues[field];
        if (value !== null && value !== undefined && value !== '') {
          // Try to parse as number or boolean, otherwise keep as string
          if (value === 'true' || value === 'false') {
            properties[field] = value === 'true';
          } else if (!isNaN(value) && value.trim() !== '') {
            properties[field] = parseFloat(value);
          } else {
            properties[field] = value.trim();
          }
        }
      });
      
      // Add custom fields
      customFields.forEach(customField => {
        const fieldName = customField.name.trim();
        const fieldValue = customField.value.trim();
        if (fieldName && fieldValue) {
          // Try to parse as number or boolean, otherwise keep as string
          if (fieldValue === 'true' || fieldValue === 'false') {
            properties[fieldName] = fieldValue === 'true';
          } else if (!isNaN(fieldValue) && fieldValue !== '') {
            properties[fieldName] = parseFloat(fieldValue);
          } else {
            properties[fieldName] = fieldValue;
          }
        }
      });
      
      if (Object.keys(properties).length > 0) {
        updates.properties = properties;
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
      
      // Close modal after successful save
      onClose();
    } catch (err) {
      console.error('Error saving node updates:', err);
      // Extract error message
      let errorMessage = 'Failed to save node updates';
      if (err.message) {
        errorMessage = err.message;
      } else if (err.detail) {
        errorMessage = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail);
      } else if (err.error) {
        errorMessage = typeof err.error === 'string' ? err.error : JSON.stringify(err.error);
      }
      setError(errorMessage);
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

          {/* Type-specific fields */}
          {typeFields.length > 0 && (
            <div className="border-t border-light-200 pt-6">
              <h3 className="text-sm font-semibold text-owl-blue-900 mb-4">
                Type-Specific Fields ({typeFields.length})
              </h3>
              <div className="space-y-4">
                {typeFields.map((field) => (
                  <div key={field}>
                    <label className="block text-sm font-medium text-light-700 mb-2">
                      {field.charAt(0).toUpperCase() + field.slice(1).replace(/_/g, ' ')}
                    </label>
                    <input
                      type="text"
                      value={typeFieldValues[field] || ''}
                      onChange={(e) => {
                        setTypeFieldValues(prev => ({
                          ...prev,
                          [field]: e.target.value,
                        }));
                      }}
                      placeholder={nodeCount > 1 ? `Enter ${field.replace(/_/g, ' ')} to update for all selected nodes...` : `Enter or edit ${field.replace(/_/g, ' ')}...`}
                      className="w-full px-3 py-2 border border-light-300 rounded-md focus:outline-none focus:ring-2 focus:ring-owl-blue-500 focus:border-transparent"
                      disabled={isSaving}
                    />
                    {nodeCount === 1 && nodes[0] && (() => {
                      const flat = flattenNode(nodes[0]);
                      const currentValue = flat[field];
                      return currentValue ? (
                        <p className="text-xs text-light-500 mt-1">
                          Current: {String(currentValue).substring(0, 100)}{String(currentValue).length > 100 ? '...' : ''}
                        </p>
                      ) : null;
                    })()}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Custom/New Fields */}
          <div className="border-t border-light-200 pt-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-owl-blue-900">
                Custom Fields ({customFields.length})
              </h3>
              <button
                type="button"
                onClick={() => {
                  setCustomFields(prev => [...prev, { name: '', value: '' }]);
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-owl-blue-600 hover:text-owl-blue-700 hover:bg-owl-blue-50 rounded-md transition-colors"
                disabled={isSaving}
              >
                <Plus className="w-4 h-4" />
                Add Field
              </button>
            </div>
            <div className="space-y-3">
              {customFields.map((customField, index) => (
                <div key={index} className="flex items-center gap-2">
                  <input
                    type="text"
                    value={customField.name}
                    onChange={(e) => {
                      setCustomFields(prev => {
                        const updated = [...prev];
                        updated[index] = { ...updated[index], name: e.target.value };
                        return updated;
                      });
                    }}
                    className="flex-1 px-3 py-2 border border-light-300 rounded-md focus:outline-none focus:ring-2 focus:ring-owl-blue-500 focus:border-transparent"
                    placeholder="Field name"
                    disabled={isSaving}
                  />
                  <input
                    type="text"
                    value={customField.value}
                    onChange={(e) => {
                      setCustomFields(prev => {
                        const updated = [...prev];
                        updated[index] = { ...updated[index], value: e.target.value };
                        return updated;
                      });
                    }}
                    className="flex-1 px-3 py-2 border border-light-300 rounded-md focus:outline-none focus:ring-2 focus:ring-owl-blue-500 focus:border-transparent"
                    placeholder="Field value"
                    disabled={isSaving}
                  />
                  <button
                    type="button"
                    onClick={() => {
                      setCustomFields(prev => prev.filter((_, i) => i !== index));
                    }}
                    className="p-2 text-red-600 hover:text-red-700 hover:bg-red-50 rounded-md transition-colors"
                    disabled={isSaving}
                    title="Remove field"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
              {customFields.length === 0 && (
                <p className="text-xs text-light-500 italic">
                  No custom fields added. Click "Add Field" to create a new property.
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-light-200 flex items-center justify-between gap-3">
          <div>
            {/* Add Relationship Button - only show for single node editing */}
            {nodeCount === 1 && caseId && (
              <button
                onClick={() => setShowRelationshipModal(true)}
                className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-owl-blue-600 hover:text-owl-blue-700 hover:bg-owl-blue-50 rounded-md transition-colors"
                disabled={isSaving}
              >
                <Link2 className="w-4 h-4" />
                Add Relationship
              </button>
            )}
          </div>
          <div className="flex items-center gap-3">
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

      {/* Create Relationship Modal */}
      {showRelationshipModal && caseId && (
        <CreateRelationshipModal
          isOpen={showRelationshipModal}
          onClose={() => setShowRelationshipModal(false)}
          sourceNodes={nodes}
          targetNodes={[]} // User will select target nodes
          onRelationshipCreated={(cypher) => {
            setShowRelationshipModal(false);
            if (onRelationshipCreated) {
              onRelationshipCreated(cypher);
            }
          }}
          caseId={caseId}
        />
      )}
    </div>
  );
}

