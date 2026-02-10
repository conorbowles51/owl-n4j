import React, { useState, useEffect, useCallback } from 'react';
import { X, Plus, Loader2, Link2, Trash2 } from 'lucide-react';
import { graphAPI } from '../services/api';
import CreateRelationshipModal from './CreateRelationshipModal';

/**
 * AddNodeModal Component
 *
 * Modal for creating a new node in the graph
 * Supports adding relationships after node creation
 * @param {Object} props
 * @param {boolean} props.isOpen - Whether the modal is open
 * @param {Function} props.onClose - Callback when modal is closed
 * @param {Function} props.onNodeCreated - Callback when a node is created
 * @param {string} props.caseId - REQUIRED: Case ID for case-specific data
 * @param {Function} props.onRelationshipCreated - Callback when relationship is created
 */
export default function AddNodeModal({ isOpen, onClose, onNodeCreated, caseId, onRelationshipCreated = null, tableNodes = [], tableColumns = [] }) {
  const [name, setName] = useState('');
  const [type, setType] = useState('');
  const [customType, setCustomType] = useState(''); // For new types not in the list
  const [useCustomType, setUseCustomType] = useState(false); // Whether to use custom type input
  const [description, setDescription] = useState('');
  const [summary, setSummary] = useState('');
  const [entityTypes, setEntityTypes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [generatedCypher, setGeneratedCypher] = useState(null);
  const [createdNodeKey, setCreatedNodeKey] = useState(null);
  const [createdNode, setCreatedNode] = useState(null);
  const [showRelationshipModal, setShowRelationshipModal] = useState(false);
  const [typeFields, setTypeFields] = useState([]); // Fields available for the selected type
  const [typeFieldValues, setTypeFieldValues] = useState({}); // Values for type-specific fields
  const [customFields, setCustomFields] = useState([]); // Array of { name: '', value: '' } for new fields

  // Helper function to flatten node (same as GraphTableView)
  const flattenNode = useCallback((node) => {
    const out = {};
    if (!node) return out;
    for (const k of ['key', 'id', 'name', 'type', 'summary', 'notes']) {
      const v = node[k];
      if (v !== undefined && v !== null) out[k] = v;
    }
    const props = node.properties || {};
    for (const k of Object.keys(props)) {
      if (out[k] !== undefined) continue; // Skip if already in top-level (same as GraphTableView)
      const v = props[k];
      if (v !== undefined && v !== null) {
        out[k] = typeof v === 'object' ? JSON.stringify(v) : v;
      }
    }
    return out;
  }, []);

  // Define loadTypeFields first (before useEffect that uses it)
  const loadTypeFields = useCallback((selectedType) => {
    console.log(`[AddNodeModal] loadTypeFields called with type: "${selectedType}"`);
    console.log(`[AddNodeModal] tableNodes.length: ${tableNodes.length}`);
    
    if (!selectedType) {
      console.log(`[AddNodeModal] No selectedType, clearing fields`);
      setTypeFields([]);
      setTypeFieldValues({});
      return;
    }

    // Filter table nodes by type
    const nodesOfType = tableNodes.filter(n => n.type === selectedType);
    console.log(`[AddNodeModal] Found ${nodesOfType.length} nodes of type "${selectedType}"`);
    console.log(`[AddNodeModal] All node types in tableNodes:`, tableNodes.map(n => n.type));
    
    if (nodesOfType.length === 0) {
      // No existing nodes of this type in table, use default fields
      console.log(`[AddNodeModal] No nodes of type "${selectedType}" found, clearing fields`);
      setTypeFields([]);
      setTypeFieldValues({});
      return;
    }

    // Extract all unique fields from nodes of this type using the same flattenNode logic
    const standardFields = new Set(['key', 'id', 'name', 'type', 'summary', 'notes', 'case_id', 'verified_facts', 'ai_insights']);
    const fieldSet = new Set();
    const allFieldsFound = new Set(); // Track all fields found (including standard ones)
    const excludedFields = new Set(); // Track fields that were excluded
    
    // For each node of this type, flatten it and collect all fields
    nodesOfType.forEach((node, index) => {
      console.log(`[AddNodeModal] Node ${index + 1}/${nodesOfType.length} RAW:`, {
        key: node.key,
        name: node.name,
        type: node.type,
        properties: node.properties,
        propertiesKeys: node.properties ? Object.keys(node.properties) : []
      });
      const flat = flattenNode(node);
      console.log(`[AddNodeModal] Node ${index + 1}/${nodesOfType.length} FLATTENED:`, {
        flattened: flat,
        flattenedKeys: Object.keys(flat)
      });
      
      // Track all fields found
      Object.keys(flat).forEach(key => {
        allFieldsFound.add(key);
        if (standardFields.has(key)) {
          excludedFields.add(key);
        } else {
          fieldSet.add(key);
        }
      });
    });

    // Convert to array and sort
    const fields = Array.from(fieldSet).sort();
    const allFieldsArray = Array.from(allFieldsFound).sort();
    const excludedFieldsArray = Array.from(excludedFields).sort();
    
    console.log(`[AddNodeModal] ===== Type "${selectedType}" Field Analysis =====`);
    console.log(`[AddNodeModal] Total nodes of this type: ${nodesOfType.length}`);
    console.log(`[AddNodeModal] All fields found (${allFieldsArray.length}):`, allFieldsArray);
    console.log(`[AddNodeModal] Excluded (standard) fields (${excludedFieldsArray.length}):`, excludedFieldsArray);
    console.log(`[AddNodeModal] Type-specific fields to display (${fields.length}):`, fields);
    console.log(`[AddNodeModal] ================================================`);
    
    setTypeFields(fields);
    
    // Initialize field values (clear previous values)
    const initialValues = {};
    fields.forEach(field => {
      initialValues[field] = '';
    });
    setTypeFieldValues(initialValues);
  }, [tableNodes, flattenNode]);

  const loadEntityTypes = () => {
    // Extract unique types from table nodes
    const typeMap = new Map();
    tableNodes.forEach(node => {
      const nodeType = node.type;
      if (nodeType) {
        const count = typeMap.get(nodeType) || 0;
        typeMap.set(nodeType, count + 1);
      }
    });
    
    // Convert to array format
    const typesList = Array.from(typeMap.entries()).map(([type, count]) => ({
      type,
      count
    })).sort((a, b) => {
      // Sort by count descending, then by type name
      if (b.count !== a.count) return b.count - a.count;
      return a.type.localeCompare(b.type);
    });
    
    setEntityTypes(typesList);
    // Set first entity type as default if available
    if (typesList.length > 0) {
      setType(typesList[0].type);
    }
  };

  useEffect(() => {
    if (isOpen) {
      // Reset form first (but don't clear type yet - let loadEntityTypes set it)
      setName('');
      setDescription('');
      setSummary('');
      setError(null);
      setGeneratedCypher(null);
      setCreatedNodeKey(null);
      setCreatedNode(null);
      setShowRelationshipModal(false);
      setTypeFields([]);
      setTypeFieldValues({});
      setCustomFields([]);
      setCustomType('');
      setUseCustomType(false);
      // Load entity types (this will set the first type if available)
      loadEntityTypes();
    }
  }, [isOpen, tableNodes]);

  // Load fields for selected type - automatically updates when type changes
  useEffect(() => {
    const selectedType = useCustomType ? customType : type;
    console.log(`[AddNodeModal] useEffect triggered - type: "${type}", customType: "${customType}", selectedType: "${selectedType}", isOpen: ${isOpen}, caseId: ${caseId}, tableNodes.length: ${tableNodes.length}`);
    
    // Don't require caseId for loading fields - we only need it when creating the node
    if (isOpen && selectedType && tableNodes.length > 0) {
      console.log(`[AddNodeModal] All conditions met, calling loadTypeFields("${selectedType}")`);
      loadTypeFields(selectedType);
    } else {
      console.log(`[AddNodeModal] Conditions not met - isOpen: ${isOpen}, selectedType: ${!!selectedType}, tableNodes.length: ${tableNodes.length}`);
      setTypeFields([]);
      setTypeFieldValues({});
    }
  }, [type, customType, useCustomType, isOpen, loadTypeFields, tableNodes]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!name.trim()) {
      setError('Node name is required');
      return;
    }
    
    const selectedType = useCustomType ? customType.trim() : type.trim();
    if (!selectedType) {
      setError('Node type is required');
      return;
    }

    setSaving(true);
    setError(null);
    
    try {
      // Build properties object with type-specific fields
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

      const selectedType = useCustomType ? customType.trim() : type.trim();
      
      // Validate required fields
      if (!caseId) {
        setError('Case ID is required. Please ensure you have a case selected.');
        setIsSaving(false);
        return;
      }
      
      const nodeData = {
        name: name.trim(),
        type: selectedType,
        description: description.trim() || null,
        summary: summary.trim() || null,
        properties: Object.keys(properties).length > 0 ? properties : undefined,
      };
      
      console.log('[AddNodeModal] Creating node with data:', nodeData, 'caseId:', caseId);
      
      const result = await graphAPI.createNode(nodeData, caseId);

      if (result.success) {
        setGeneratedCypher(result.cypher);
        setCreatedNodeKey(result.node_key);
        // Store created node for relationship creation
        const selectedType = useCustomType ? customType.trim() : type.trim();
        setCreatedNode({
          key: result.node_key,
          name: name.trim(),
          type: selectedType,
        });
        // Notify parent component to refresh graph
        if (onNodeCreated) {
          await onNodeCreated(result.node_key);
        }
        // Don't close modal immediately - allow user to add relationships
      } else {
        setError(result.error || 'Failed to create node');
      }
    } catch (err) {
      console.error('Failed to create node:', err);
      // Try to extract more detailed error information
      let errorMessage = 'Failed to create node';
      if (err.message) {
        errorMessage = err.message;
      } else if (typeof err === 'string') {
        errorMessage = err;
      } else if (err.detail) {
        errorMessage = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail);
      } else if (err.error) {
        errorMessage = typeof err.error === 'string' ? err.error : JSON.stringify(err.error);
      } else {
        errorMessage = JSON.stringify(err);
      }
      setError(errorMessage);
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
              <div className="space-y-2">
                  <select
                    value={useCustomType ? '__custom__' : type}
                    onChange={(e) => {
                      if (e.target.value === '__custom__') {
                        setUseCustomType(true);
                        setType('');
                        setCustomType('');
                      } else {
                        setUseCustomType(false);
                        const newType = e.target.value;
                        setType(newType);
                        setCustomType('');
                        // Fields will be loaded by useEffect when type changes
                      }
                    }}
                    className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500 bg-white"
                    required
                    disabled={saving}
                  >
                    <option value="">-- Select Type --</option>
                    {entityTypes.map((et) => (
                      <option key={et.type} value={et.type}>
                        {et.type} ({et.count})
                      </option>
                    ))}
                    <option value="__custom__">+ Create New Type</option>
                  </select>
                  
                  {useCustomType && (
                    <input
                      type="text"
                      value={customType}
                      onChange={(e) => {
                        const newCustomType = e.target.value;
                        setCustomType(newCustomType);
                        // Clear fields for custom types (no existing nodes to derive fields from)
                        if (newCustomType.trim()) {
                          setTypeFields([]);
                          setTypeFieldValues({});
                        }
                      }}
                      placeholder="Enter new entity type (e.g., Person, Company)"
                      className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                      required={useCustomType}
                      disabled={saving}
                    />
                  )}
                  
                  <p className="text-xs text-light-500">
                    {entityTypes.length > 0 
                      ? `Select from ${entityTypes.length} existing types or create a new one. Fields will update automatically when you select a type.`
                      : 'Enter the entity type (e.g., Person, Company, Location)'
                    }
                  </p>
                  {type && !useCustomType && (
                    <div className="text-xs mt-1">
                      {typeFields.length === 0 ? (
                        <p className="text-amber-600">
                          No type-specific fields found for "{type}" in the current table data.
                        </p>
                      ) : (
                        <p className="text-green-600">
                          Found {typeFields.length} field{typeFields.length !== 1 ? 's' : ''} for "{type}".
                        </p>
                      )}
                    </div>
                  )}
                </div>
            </div>

            {/* Type-specific fields */}
            {typeFields.length > 0 && (
              <div key={`type-fields-${type}-${typeFields.join(',')}`} className="border-t border-light-200 pt-4">
                <h3 className="text-sm font-semibold text-owl-blue-900 mb-3">
                  Type-Specific Fields ({typeFields.length})
                </h3>
                <div className="space-y-3">
                  {typeFields.map((field) => (
                    <div key={field}>
                      <label className="block text-sm font-medium text-light-700 mb-1">
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
                        className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                        placeholder={`Enter ${field.replace(/_/g, ' ')}`}
                        disabled={saving}
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Custom/New Fields */}
            <div className="border-t border-light-200 pt-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-owl-blue-900">
                  Custom Fields ({customFields.length})
                </h3>
                <button
                  type="button"
                  onClick={() => {
                    setCustomFields(prev => [...prev, { name: '', value: '' }]);
                  }}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-owl-blue-600 hover:text-owl-blue-700 hover:bg-owl-blue-50 rounded-md transition-colors"
                  disabled={saving}
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
                      className="flex-1 px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                      placeholder="Field name"
                      disabled={saving}
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
                      className="flex-1 px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                      placeholder="Field value"
                      disabled={saving}
                    />
                    <button
                      type="button"
                      onClick={() => {
                        setCustomFields(prev => prev.filter((_, i) => i !== index));
                      }}
                      className="p-2 text-red-600 hover:text-red-700 hover:bg-red-50 rounded-md transition-colors"
                      disabled={saving}
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
                {createdNodeKey ? 'Close' : 'Cancel'}
              </button>
              {!createdNodeKey ? (
                <button
                  type="submit"
                  disabled={saving || !name.trim() || (!type.trim() && !customType.trim())}
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
              ) : (
                <button
                  type="button"
                  onClick={() => setShowRelationshipModal(true)}
                  className="flex items-center gap-2 px-4 py-2 bg-owl-blue-600 text-white rounded-lg hover:bg-owl-blue-700 transition-colors"
                >
                  <Link2 className="w-4 h-4" />
                  Add Relationship
                </button>
              )}
            </div>
          </form>
        </div>
      </div>

      {/* Create Relationship Modal */}
      {showRelationshipModal && caseId && createdNode && (
        <CreateRelationshipModal
          isOpen={showRelationshipModal}
          onClose={() => setShowRelationshipModal(false)}
          sourceNodes={[createdNode]}
          targetNodes={[]} // User will select target nodes
          onRelationshipCreated={(cypher) => {
            setShowRelationshipModal(false);
            if (onRelationshipCreated) {
              onRelationshipCreated(cypher);
            }
            // Close the add modal after relationship is created
            setTimeout(() => {
              onClose();
            }, 500);
          }}
          caseId={caseId}
        />
      )}
    </div>
  );
}

