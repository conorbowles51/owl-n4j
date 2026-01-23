import React, { useState, useEffect } from 'react';
import { ChevronDown, ChevronRight, FileText, Focus, Link2, Plus, Trash2, Calendar } from 'lucide-react';
import { workspaceAPI } from '../../services/api';
import AttachToTheoryModal from './AttachToTheoryModal';
import AddInvestigativeNoteModal from './AddInvestigativeNoteModal';

/**
 * Investigative Notes Section
 * 
 * Displays investigative notes (thoughts, insights, observations)
 * Allows adding, viewing, and attaching notes to theories
 */
export default function InvestigativeNotesSection({
  caseId,
  isCollapsed,
  onToggle,
  onFocus,
}) {
  const [notes, setNotes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [attachModal, setAttachModal] = useState({ open: false, note: null });
  const [showAddModal, setShowAddModal] = useState(false);

  useEffect(() => {
    const loadNotes = async () => {
      if (!caseId) return;
      
      setLoading(true);
      try {
        const data = await workspaceAPI.getNotes(caseId);
        setNotes(data.notes || []);
      } catch (err) {
        console.error('Failed to load investigative notes:', err);
        setNotes([]);
      } finally {
        setLoading(false);
      }
    };

    loadNotes();
  }, [caseId]);

  const handleAddNote = async (content) => {
    if (!caseId || !content.trim()) return;
    
    try {
      await workspaceAPI.createNote(caseId, { content });
      // Reload notes
      const data = await workspaceAPI.getNotes(caseId);
      setNotes(data.notes || []);
    } catch (err) {
      console.error('Failed to create note:', err);
      throw err;
    }
  };

  const handleDeleteNote = async (noteId) => {
    if (!caseId || !confirm('Are you sure you want to delete this note?')) return;
    
    try {
      await workspaceAPI.deleteNote(caseId, noteId);
      // Reload notes
      const data = await workspaceAPI.getNotes(caseId);
      setNotes(data.notes || []);
    } catch (err) {
      console.error('Failed to delete note:', err);
      alert('Failed to delete note');
    }
  };

  const handleAttachToTheory = async (theory, itemType, itemId) => {
    if (!caseId || !theory) return;
    try {
      const existing = theory.attached_note_ids || [];
      const ids = existing.includes(itemId) ? existing : [...existing, itemId];
      await workspaceAPI.updateTheory(caseId, theory.theory_id, {
        ...theory,
        attached_note_ids: ids,
      });
    } catch (err) {
      console.error('Failed to attach note to theory:', err);
      throw err;
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return '';
    try {
      return new Date(dateString).toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateString;
    }
  };

  return (
    <div className="border-b border-light-200">
      <div
        className="p-4 cursor-pointer hover:bg-light-50 transition-colors flex items-center justify-between"
        onClick={(e) => onToggle && onToggle(e)}
      >
        <h3 className="text-sm font-semibold text-owl-blue-900">
          Investigative Notes ({notes.length})
        </h3>
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation();
              setShowAddModal(true);
            }}
            className="p-1 hover:bg-light-100 rounded"
            title="Add Note"
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
        <div className="px-4 pb-4">
          {loading ? (
            <p className="text-xs text-light-500">Loading notes...</p>
          ) : notes.length === 0 ? (
            <p className="text-xs text-light-500 italic">No investigative notes yet. Click the + button to add one.</p>
          ) : (
            <div className="space-y-2">
              {notes.map((note) => {
                const noteId = note.note_id || note.id;
                const noteContent = note.content || note.text || 'Note';
                
                return (
                  <div
                    key={noteId}
                    className="p-3 bg-light-50 rounded-lg border border-light-200 hover:bg-light-100 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <FileText className="w-4 h-4 text-owl-blue-600 flex-shrink-0" />
                          {note.created_at && (
                            <span className="text-xs text-light-500 flex items-center gap-1">
                              <Calendar className="w-3 h-3" />
                              {formatDate(note.created_at)}
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-owl-blue-900 whitespace-pre-wrap">{noteContent}</p>
                      </div>
                      <div className="flex items-center gap-1 flex-shrink-0">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setAttachModal({ open: true, note: { id: noteId, content: noteContent } });
                          }}
                          className="p-1.5 hover:bg-owl-blue-100 rounded transition-colors"
                          title="Attach to theory"
                        >
                          <Link2 className="w-4 h-4 text-owl-blue-600" />
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteNote(noteId);
                          }}
                          className="p-1.5 hover:bg-red-100 rounded transition-colors"
                          title="Delete note"
                        >
                          <Trash2 className="w-4 h-4 text-red-600" />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {showAddModal && (
        <AddInvestigativeNoteModal
          isOpen={showAddModal}
          onClose={() => setShowAddModal(false)}
          onSave={handleAddNote}
        />
      )}

      {attachModal.open && attachModal.note && (
        <AttachToTheoryModal
          isOpen={attachModal.open}
          onClose={() => setAttachModal({ open: false, note: null })}
          caseId={caseId}
          itemType="note"
          itemId={attachModal.note.id}
          itemName={attachModal.note.content || 'Note'}
          onAttach={handleAttachToTheory}
        />
      )}
    </div>
  );
}
