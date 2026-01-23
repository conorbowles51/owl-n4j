import React, { useState, useEffect } from 'react';
import { Plus, Edit2, Trash2, Lightbulb } from 'lucide-react';
import { workspaceAPI } from '../../services/api';
import TheoryEditor from './TheoryEditor';

/**
 * Theories Tab
 * 
 * Displays investigation theories with confidence scores
 */
export default function TheoriesTab({ caseId, authUsername }) {
  const [theories, setTheories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editingTheory, setEditingTheory] = useState(null);
  const [showEditor, setShowEditor] = useState(false);

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

  const getConfidenceColor = (score) => {
    if (!score) return 'text-light-600';
    if (score >= 80) return 'text-green-600';
    if (score >= 50) return 'text-yellow-600';
    return 'text-red-600';
  };

  if (loading) {
    return (
      <div className="p-4 text-center text-light-600">
        Loading theories...
      </div>
    );
  }

  return (
    <>
      <div className="p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-owl-blue-900">Investigation Theories</h3>
          <button
            onClick={handleCreate}
            className="flex items-center gap-2 px-3 py-1.5 text-sm bg-owl-blue-500 text-white rounded hover:bg-owl-blue-600 transition-colors"
          >
            <Plus className="w-4 h-4" />
            New Theory
          </button>
        </div>

        {theories.length === 0 ? (
          <p className="text-sm text-light-500 text-center py-8">No theories yet</p>
        ) : (
          <div className="space-y-3">
            {theories.map((theory) => (
              <div
                key={theory.theory_id}
                className="p-3 bg-light-50 rounded-lg border border-light-200 hover:bg-light-100 transition-colors"
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <Lightbulb className="w-4 h-4 text-yellow-600" />
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
    </>
  );
}
