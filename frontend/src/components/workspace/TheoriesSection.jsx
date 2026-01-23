import React, { useState, useEffect } from 'react';
import { ChevronDown, ChevronRight, Plus, Edit2, Trash2, Lightbulb, Focus, Link2, Network } from 'lucide-react';
import { workspaceAPI } from '../../services/api';
import TheoryEditor from './TheoryEditor';
import AttachedItemsModal from './AttachedItemsModal';
import BuildTheoryGraphModal from './BuildTheoryGraphModal';

/**
 * Theories Section
 * 
 * Displays investigation theories with confidence scores
 */
export default function TheoriesSection({
  caseId,
  caseName,
  authUsername,
  isCollapsed,
  onToggle,
  onFocus,
  fullHeight = false, // When true, use full height for content panel
}) {
  const [theories, setTheories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editingTheory, setEditingTheory] = useState(null);
  const [showEditor, setShowEditor] = useState(false);
  const [attachedModalTheory, setAttachedModalTheory] = useState(null);
  const [buildGraphTheory, setBuildGraphTheory] = useState(null);

  useEffect(() => {
    const loadTheories = async () => {
      if (!caseId) return;
      
      setLoading(true);
      try {
        const data = await workspaceAPI.getTheories(caseId);
        setTheories(data.theories || []);
      } catch (err) {
        console.error('Failed to load theories:', err);
      } finally {
        setLoading(false);
      }
    };

    loadTheories();
  }, [caseId]);

  const handleCreate = () => {
    setEditingTheory(null);
    setShowEditor(true);
  };

  const handleEdit = (theory) => {
    setEditingTheory(theory);
    setShowEditor(true);
  };

  const handleDelete = async (theoryId) => {
    if (!confirm('Are you sure you want to delete this theory?')) return;
    
    try {
      await workspaceAPI.deleteTheory(caseId, theoryId);
      setTheories(theories.filter(t => t.theory_id !== theoryId));
    } catch (err) {
      console.error('Failed to delete theory:', err);
      alert('Failed to delete theory');
    }
  };

  const handleSave = async (theoryData) => {
    try {
      if (editingTheory) {
        await workspaceAPI.updateTheory(caseId, editingTheory.theory_id, theoryData);
      } else {
        await workspaceAPI.createTheory(caseId, theoryData);
      }
      setShowEditor(false);
      setEditingTheory(null);
      // Reload theories
      const data = await workspaceAPI.getTheories(caseId);
      setTheories(data.theories || []);
    } catch (err) {
      console.error('Failed to save theory:', err);
      alert('Failed to save theory');
    }
  };

  const handleDetachItem = async (type, itemId) => {
    if (!attachedModalTheory) return;
    try {
      const theory = attachedModalTheory;
      const updated = { ...theory };
      
      // Remove the item from the appropriate array
      if (type === 'evidence') {
        updated.attached_evidence_ids = (updated.attached_evidence_ids || []).filter(id => id !== itemId);
      } else if (type === 'witness') {
        updated.attached_witness_ids = (updated.attached_witness_ids || []).filter(id => id !== itemId);
      } else if (type === 'note') {
        updated.attached_note_ids = (updated.attached_note_ids || []).filter(id => id !== itemId);
      } else if (type === 'snapshot') {
        updated.attached_snapshot_ids = (updated.attached_snapshot_ids || []).filter(id => id !== itemId);
      } else if (type === 'document') {
        updated.attached_document_ids = (updated.attached_document_ids || []).filter(id => id !== itemId);
      } else if (type === 'task') {
        updated.attached_task_ids = (updated.attached_task_ids || []).filter(id => id !== itemId);
      }
      
      await workspaceAPI.updateTheory(caseId, theory.theory_id, updated);
      
      // Reload theories
      const data = await workspaceAPI.getTheories(caseId);
      setTheories(data.theories || []);
      
      // Update the modal theory
      const updatedTheory = data.theories.find(t => t.theory_id === theory.theory_id);
      if (updatedTheory) {
        setAttachedModalTheory(updatedTheory);
      }
    } catch (err) {
      console.error('Failed to detach item:', err);
      alert('Failed to detach item');
    }
  };

  const handleBuildGraph = async (includeAttached) => {
    if (!buildGraphTheory || !caseId) return;
    
    try {
      const result = await workspaceAPI.buildTheoryGraph(caseId, buildGraphTheory.theory_id, {
        include_attached_items: includeAttached,
        top_k: 20,
      });
      
      // Dispatch event to update graph view with entity keys
      window.dispatchEvent(new CustomEvent('theory-graph-built', {
        detail: {
          entity_keys: result.entity_keys || [],
          theory_id: buildGraphTheory.theory_id,
          theory_title: buildGraphTheory.title,
        }
      }));
      
      // Reload theories to get the updated theory with attached_graph_data
      const data = await workspaceAPI.getTheories(caseId);
      setTheories(data.theories || []);
      
      // Update the modal theory if it's currently open
      const updatedTheory = data.theories.find(t => t.theory_id === buildGraphTheory.theory_id);
      if (updatedTheory && attachedModalTheory && attachedModalTheory.theory_id === buildGraphTheory.theory_id) {
        setAttachedModalTheory(updatedTheory);
      }
      
      alert(`Theory graph built! Found ${result.entity_keys?.length || 0} relevant entities. The graph view will now show these entities.`);
    } catch (err) {
      console.error('Failed to build theory graph:', err);
      throw err;
    }
  };

  const getConfidenceColor = (score) => {
    if (!score) return 'text-light-600';
    if (score >= 80) return 'text-green-600';
    if (score >= 50) return 'text-yellow-600';
    return 'text-red-600';
  };

  return (
    <>
      <div className="border-b border-light-200">
        <div
          className="p-4 cursor-pointer hover:bg-light-50 transition-colors flex items-center justify-between"
          onClick={(e) => onToggle && onToggle(e)}
        >
          <h3 className="text-sm font-semibold text-owl-blue-900 flex items-center gap-2">
            <Lightbulb className="w-4 h-4" />
            Investigation Theories ({theories.length})
          </h3>
          <div className="flex items-center gap-2">
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleCreate();
              }}
              className="p-1 hover:bg-light-100 rounded"
              title="New Theory"
            >
              <Plus className="w-4 h-4 text-owl-blue-600" />
            </button>
            {onFocus && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onFocus(e);
                }}
                className="p-1 hover:bg-light-100 rounded"
                title="Focus on this section"
              >
                <Focus className="w-4 h-4 text-owl-blue-600" />
              </button>
            )}
            {isCollapsed ? (
              <ChevronRight className="w-4 h-4 text-light-600" />
            ) : (
              <ChevronDown className="w-4 h-4 text-light-600" />
            )}
          </div>
        </div>

        {!isCollapsed && (
          <div className={`px-4 pb-4 ${fullHeight ? 'flex flex-col h-full' : ''}`}>
            {loading ? (
              <p className="text-sm text-light-500 text-center py-8">Loading theories...</p>
            ) : theories.length === 0 ? (
              <p className="text-sm text-light-500 text-center py-8">No theories yet</p>
            ) : (
              <div className={`space-y-3 overflow-y-auto ${fullHeight ? 'flex-1 min-h-0' : 'max-h-96'}`}>
                {theories.map((theory) => (
                  <div
                    key={theory.theory_id}
                    className="p-3 bg-light-50 rounded-lg border border-light-200 hover:bg-light-100 transition-colors"
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <h4 className="text-sm font-medium text-owl-blue-900">{theory.title}</h4>
                          {theory.privilege_level === 'ATTORNEY_ONLY' && (
                            <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded">
                              Attorney Only
                            </span>
                          )}
                        </div>
                        {theory.type && (
                          <span className="text-xs text-light-600">{theory.type}</span>
                        )}
                      </div>
                      {theory.confidence_score !== null && theory.confidence_score !== undefined && (
                        <span className={`text-sm font-medium ${getConfidenceColor(theory.confidence_score)}`}>
                          {theory.confidence_score}%
                        </span>
                      )}
                    </div>
                    {theory.hypothesis && (
                      <p className="text-xs text-light-600 mb-2">{theory.hypothesis}</p>
                    )}
                    {theory.supporting_evidence && theory.supporting_evidence.length > 0 && (
                      <div className="mt-2">
                        <p className="text-xs font-medium text-light-700 mb-1">Supporting Evidence:</p>
                        <ul className="text-xs text-light-600 list-disc list-inside">
                          {theory.supporting_evidence.map((evidence, idx) => (
                            <li key={idx}>{evidence}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    <div className="flex items-center gap-2 mt-3">
                      <button
                        onClick={() => setBuildGraphTheory(theory)}
                        className="p-1 hover:bg-owl-blue-100 rounded transition-colors"
                        title="Build Theory Graph"
                      >
                        <Network className="w-3 h-3 text-owl-blue-600" />
                      </button>
                      <button
                        onClick={() => {
                          // Get the latest version of this theory from the theories array
                          const latestTheory = theories.find(t => t.theory_id === theory.theory_id) || theory;
                          setAttachedModalTheory(latestTheory);
                        }}
                        className="p-1 hover:bg-owl-blue-100 rounded transition-colors"
                        title="View attached items"
                      >
                        <Link2 className="w-3 h-3 text-owl-blue-600" />
                      </button>
                      <button
                        onClick={() => handleEdit(theory)}
                        className="p-1 hover:bg-light-200 rounded transition-colors"
                        title="Edit"
                      >
                        <Edit2 className="w-3 h-3 text-light-600" />
                      </button>
                      <button
                        onClick={() => handleDelete(theory.theory_id)}
                        className="p-1 hover:bg-red-100 rounded transition-colors"
                        title="Delete"
                      >
                        <Trash2 className="w-3 h-3 text-red-600" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {showEditor && (
        <TheoryEditor
          isOpen={showEditor}
          onClose={() => {
            setShowEditor(false);
            setEditingTheory(null);
          }}
          theory={editingTheory}
          onSave={handleSave}
          caseId={caseId}
        />
      )}

      {attachedModalTheory && (
        <AttachedItemsModal
          isOpen={!!attachedModalTheory}
          onClose={() => setAttachedModalTheory(null)}
          theory={attachedModalTheory}
          caseId={caseId}
          caseName={caseName}
          onDetach={handleDetachItem}
        />
      )}

      {buildGraphTheory && (
        <BuildTheoryGraphModal
          isOpen={!!buildGraphTheory}
          onClose={() => setBuildGraphTheory(null)}
          theory={buildGraphTheory}
          onBuild={handleBuildGraph}
        />
      )}
    </>
  );
}
