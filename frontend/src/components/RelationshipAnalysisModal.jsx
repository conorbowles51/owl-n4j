import React, { useState, useEffect } from 'react';
import { X, Link2, Loader2, CheckSquare, Square } from 'lucide-react';
import { graphAPI } from '../services/api';

/**
 * RelationshipAnalysisModal Component
 * 
 * Modal for displaying relationship analysis results and allowing users to select which relationships to add.
 */
export default function RelationshipAnalysisModal({
  isOpen,
  onClose,
  node,
  onRelationshipsAdded,
}) {
  const [relationships, setRelationships] = useState([]);
  const [selectedRelationships, setSelectedRelationships] = useState(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    if (isOpen && node) {
      // Reset state when modal opens
      setRelationships([]);
      setSelectedRelationships(new Set());
      setError(null);
      // Trigger analysis
      analyzeRelationships();
    }
  }, [isOpen, node]);

  const analyzeRelationships = async () => {
    if (!node) return;

    setLoading(true);
    setError(null);

    try {
      const result = await graphAPI.analyzeNodeRelationships(node.key);
      
      if (result.success) {
        setRelationships(result.relationships || []);
        // Pre-select all relationships by default
        const allIndices = new Set(
          (result.relationships || []).map((_, index) => index)
        );
        setSelectedRelationships(allIndices);
      } else {
        setError(result.error || 'Failed to analyze relationships.');
      }
    } catch (err) {
      console.error('Error analyzing relationships:', err);
      setError(err.message || 'An unexpected error occurred.');
    } finally {
      setLoading(false);
    }
  };

  const handleToggleRelationship = (index) => {
    setSelectedRelationships(prev => {
      const newSet = new Set(prev);
      if (newSet.has(index)) {
        newSet.delete(index);
      } else {
        newSet.add(index);
      }
      return newSet;
    });
  };

  const handleAddRelationships = async () => {
    if (selectedRelationships.size === 0) {
      alert('Please select at least one relationship to add.');
      return;
    }

    setAdding(true);
    setError(null);

    try {
      // Get selected relationships
      const selected = Array.from(selectedRelationships)
        .map(index => relationships[index])
        .map(rel => ({
          from_key: rel.from_key,
          to_key: rel.to_key,
          type: rel.type,
          notes: rel.notes || null,
        }));

      // Create the relationships
      const result = await graphAPI.createRelationships(selected);

      if (result.success) {
        onRelationshipsAdded(result.cypher);
        onClose();
      } else {
        setError(result.error || 'Failed to create relationships.');
      }
    } catch (err) {
      console.error('Error creating relationships:', err);
      setError(err.message || 'An unexpected error occurred.');
    } finally {
      setAdding(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="w-full max-w-3xl max-h-[90vh] bg-white rounded-lg shadow-2xl overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-light-200 bg-light-50">
          <div className="flex items-center gap-2">
            <Link2 className="w-5 h-5 text-owl-blue-700" />
            <h2 className="text-lg font-semibold text-owl-blue-900">
              Relationship Analysis
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded hover:bg-light-200 text-light-600 transition-colors"
            disabled={adding}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* Node Info */}
          <div className="mb-4 pb-4 border-b border-light-200">
            <div className="text-sm text-light-600 mb-1">Analyzing relationships for:</div>
            <div className="text-lg font-semibold text-owl-blue-900">{node?.name}</div>
            <div className="text-sm text-light-600">Type: {node?.type}</div>
          </div>

          {loading && (
            <div className="flex flex-col items-center justify-center py-12">
              <Loader2 className="w-8 h-8 text-owl-blue-600 animate-spin mb-3" />
              <p className="text-light-600">Analyzing relationships with existing nodes...</p>
            </div>
          )}

          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4 text-sm text-red-700">
              {error}
            </div>
          )}

          {!loading && !error && relationships.length === 0 && (
            <div className="text-center py-12 text-light-600">
              <Link2 className="w-12 h-12 mx-auto mb-3 text-light-400" />
              <p>No relationships found.</p>
              <p className="text-sm mt-2">The system could not identify any connections between this node and existing nodes in the graph.</p>
            </div>
          )}

          {!loading && !error && relationships.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center justify-between mb-4">
                <div className="text-sm font-medium text-light-700">
                  Found {relationships.length} potential relationship{relationships.length > 1 ? 's' : ''}
                </div>
                <button
                  onClick={() => {
                    if (selectedRelationships.size === relationships.length) {
                      setSelectedRelationships(new Set());
                    } else {
                      setSelectedRelationships(new Set(relationships.map((_, i) => i)));
                    }
                  }}
                  className="text-sm text-owl-blue-600 hover:text-owl-blue-700"
                >
                  {selectedRelationships.size === relationships.length ? 'Deselect All' : 'Select All'}
                </button>
              </div>

              <div className="space-y-2">
                {relationships.map((rel, index) => {
                  const isSelected = selectedRelationships.has(index);
                  return (
                    <div
                      key={index}
                      onClick={() => handleToggleRelationship(index)}
                      className={`p-4 border rounded-lg cursor-pointer transition-colors ${
                        isSelected
                          ? 'border-owl-blue-500 bg-owl-blue-50'
                          : 'border-light-200 hover:border-light-300 hover:bg-light-50'
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <div className="mt-1">
                          {isSelected ? (
                            <CheckSquare className="w-5 h-5 text-owl-blue-600" />
                          ) : (
                            <Square className="w-5 h-5 text-light-400" />
                          )}
                        </div>
                        <div className="flex-1">
                          <div className="font-medium text-owl-blue-900 mb-1">
                            {rel.from_name || rel.from_key} → {rel.to_name || rel.to_key}
                          </div>
                          <div className="text-sm font-semibold text-owl-blue-600 mb-1">
                            {rel.type}
                          </div>
                          {rel.notes && (
                            <div className="text-sm text-light-600 mt-1">
                              {rel.notes}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-light-200 bg-light-50">
          <div className="flex justify-end gap-2">
            <button
              onClick={onClose}
              disabled={adding}
              className="px-4 py-2 text-light-700 hover:bg-light-100 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Cancel
            </button>
            {relationships.length > 0 && (
              <button
                onClick={handleAddRelationships}
                disabled={adding || selectedRelationships.size === 0}
                className="flex items-center gap-2 px-4 py-2 bg-owl-blue-600 text-white rounded-lg hover:bg-owl-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {adding ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Adding...
                  </>
                ) : (
                  <>
                    <Link2 className="w-4 h-4" />
                    Add {selectedRelationships.size} Relationship{selectedRelationships.size > 1 ? 's' : ''}
                  </>
                )}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}




