import React, { useState, useEffect } from 'react';
import { X, Loader2 } from 'lucide-react';
import { workspaceAPI } from '../../services/api';

/**
 * Attach to Theory Modal
 * 
 * Reusable modal for attaching items (evidence, witnesses, notes, snapshots, documents) to theories
 */
export default function AttachToTheoryModal({
  isOpen,
  onClose,
  caseId,
  itemType, // 'evidence', 'witness', 'note', 'snapshot', 'document'
  itemId,
  itemName,
  onAttach,
}) {
  const [theories, setTheories] = useState([]);
  const [loading, setLoading] = useState(false);
  const [attaching, setAttaching] = useState(false);

  useEffect(() => {
    if (isOpen && caseId) {
      setLoading(true);
      workspaceAPI
        .getTheories(caseId)
        .then((r) => setTheories(r.theories || []))
        .catch(() => setTheories([]))
        .finally(() => setLoading(false));
    }
  }, [isOpen, caseId]);

  const handleAttach = async (theory) => {
    if (!itemId || !caseId) return;
    setAttaching(true);
    try {
      await onAttach(theory, itemType, itemId);
      onClose();
    } catch (err) {
      console.error('Failed to attach item to theory:', err);
      alert('Failed to attach item to theory');
    } finally {
      setAttaching(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-md mx-4 max-h-[80vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-light-200">
          <h3 className="text-lg font-semibold text-owl-blue-900">Attach to theory</h3>
          <button onClick={onClose} className="p-1 hover:bg-light-100 rounded">
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>
        <p className="px-4 pt-2 text-sm text-light-600">
          Attach &quot;{itemName}&quot; to a theory:
        </p>
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {loading ? (
            <div className="flex items-center gap-2 py-4 text-sm text-light-500">
              <Loader2 className="w-4 h-4 animate-spin" />
              Loading theories…
            </div>
          ) : theories.length === 0 ? (
            <p className="text-sm text-light-500 italic">No theories found. Create one in the Theories section.</p>
          ) : (
            theories.map((t) => (
              <button
                key={t.theory_id}
                onClick={() => handleAttach(t)}
                disabled={attaching}
                className="w-full text-left p-3 rounded-lg border border-light-200 hover:bg-owl-blue-50 hover:border-owl-blue-200 transition-colors disabled:opacity-50"
              >
                <span className="font-medium text-owl-blue-900">{t.title}</span>
                {t.type && <span className="ml-2 text-xs text-light-600">{t.type}</span>}
              </button>
            ))
          )}
        </div>
        <div className="p-4 border-t border-light-200">
          <button
            onClick={onClose}
            disabled={attaching}
            className="w-full px-4 py-2 bg-light-200 text-light-700 rounded-lg hover:bg-light-300 disabled:opacity-50"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
