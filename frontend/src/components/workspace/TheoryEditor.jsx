import React, { useState, useEffect, useCallback } from 'react';
import { X, Save, Link2 } from 'lucide-react';
import { casesAPI } from '../../services/api';

/**
 * Theory Editor Modal
 *
 * Rich text editor for creating/editing investigation theories.
 * Supports attaching case snapshots to a theory.
 */
export default function TheoryEditor({
  isOpen,
  onClose,
  theory,
  onSave,
  caseId,
}) {
  const [formData, setFormData] = useState({
    title: '',
    type: 'PRIMARY',
    confidence_score: null,
    hypothesis: '',
    supporting_evidence: [],
    counter_arguments: [],
    next_steps: [],
    privilege_level: 'PUBLIC',
    attached_snapshot_ids: [],
    attached_evidence_ids: [],
    attached_witness_ids: [],
    attached_note_ids: [],
    attached_document_ids: [],
    attached_task_ids: [],
  });

  const [caseSnapshots, setCaseSnapshots] = useState([]);
  const [addSnapshotId, setAddSnapshotId] = useState('');

  const loadCaseSnapshots = useCallback(async () => {
    if (!caseId) return;
    try {
      const caseData = await casesAPI.get(caseId);
      const versions = caseData?.versions || [];
      const sorted = [...versions].sort((a, b) => (b.version ?? 0) - (a.version ?? 0));
      const latest = sorted[0];
      const raw = latest?.snapshots || [];
      setCaseSnapshots(raw);
    } catch {
      setCaseSnapshots([]);
    }
  }, [caseId]);

  useEffect(() => {
    if (isOpen && caseId) loadCaseSnapshots();
  }, [isOpen, caseId, loadCaseSnapshots]);

  useEffect(() => {
    if (theory) {
      setFormData({
        title: theory.title || '',
        type: theory.type || 'PRIMARY',
        confidence_score: theory.confidence_score ?? null,
        hypothesis: theory.hypothesis || '',
        supporting_evidence: theory.supporting_evidence || [],
        counter_arguments: theory.counter_arguments || [],
        next_steps: theory.next_steps || [],
        privilege_level: theory.privilege_level || 'PUBLIC',
        attached_snapshot_ids: theory.attached_snapshot_ids || [],
        attached_evidence_ids: theory.attached_evidence_ids || [],
        attached_witness_ids: theory.attached_witness_ids || [],
        attached_note_ids: theory.attached_note_ids || [],
        attached_document_ids: theory.attached_document_ids || [],
        attached_task_ids: theory.attached_task_ids || [],
      });
    } else {
      setFormData({
        title: '',
        type: 'PRIMARY',
        confidence_score: null,
        hypothesis: '',
        supporting_evidence: [],
        counter_arguments: [],
        next_steps: [],
        privilege_level: 'PUBLIC',
        attached_snapshot_ids: [],
        attached_evidence_ids: [],
        attached_witness_ids: [],
        attached_note_ids: [],
        attached_document_ids: [],
        attached_task_ids: [],
      });
    }
  }, [theory, isOpen]);

  const handleSubmit = (e) => {
    e.preventDefault();
    onSave(formData);
  };

  const addAttachedSnapshot = () => {
    if (!addSnapshotId || formData.attached_snapshot_ids.includes(addSnapshotId)) return;
    setFormData({
      ...formData,
      attached_snapshot_ids: [...formData.attached_snapshot_ids, addSnapshotId],
    });
    setAddSnapshotId('');
  };

  const removeAttachedSnapshot = (snapshotId) => {
    setFormData({
      ...formData,
      attached_snapshot_ids: formData.attached_snapshot_ids.filter((id) => id !== snapshotId),
    });
  };

  const snapshotName = (id) => {
    const s = caseSnapshots.find((x) => x.id === id);
    return s?.name || id;
  };

  const availableToAdd = caseSnapshots.filter(
    (s) => !formData.attached_snapshot_ids.includes(s.id)
  );

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-light-200">
          <h2 className="text-lg font-semibold text-owl-blue-900">
            {theory ? 'Edit Theory' : 'New Theory'}
          </h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-light-100 rounded"
          >
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-owl-blue-900 mb-1">
              Title *
            </label>
            <input
              type="text"
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              className="w-full px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-owl-blue-900 mb-1">
              Type
            </label>
            <select
              value={formData.type}
              onChange={(e) => setFormData({ ...formData, type: e.target.value })}
              className="w-full px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
            >
              <option value="PRIMARY">Primary</option>
              <option value="SECONDARY">Secondary</option>
              <option value="NOTE">Note</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-owl-blue-900 mb-1">
              Confidence Score (0-100)
            </label>
            <input
              type="number"
              min="0"
              max="100"
              value={formData.confidence_score ?? ''}
              onChange={(e) => setFormData({ ...formData, confidence_score: e.target.value ? parseInt(e.target.value) : null })}
              className="w-full px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-owl-blue-900 mb-1">
              Hypothesis
            </label>
            <textarea
              value={formData.hypothesis}
              onChange={(e) => setFormData({ ...formData, hypothesis: e.target.value })}
              rows={4}
              className="w-full px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-owl-blue-900 mb-1">
              Privilege Level
            </label>
            <select
              value={formData.privilege_level}
              onChange={(e) => setFormData({ ...formData, privilege_level: e.target.value })}
              className="w-full px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
            >
              <option value="PUBLIC">Public</option>
              <option value="ATTORNEY_ONLY">Attorney Only</option>
              <option value="PRIVATE">Private</option>
            </select>
          </div>

          {caseId && (
            <div>
              <label className="block text-sm font-medium text-owl-blue-900 mb-1 flex items-center gap-2">
                <Link2 className="w-4 h-4 text-owl-blue-600" />
                Attached Snapshots
              </label>
              {formData.attached_snapshot_ids.length > 0 && (
                <ul className="mb-2 space-y-1">
                  {formData.attached_snapshot_ids.map((id) => (
                    <li
                      key={id}
                      className="flex items-center justify-between gap-2 px-3 py-2 bg-light-50 rounded-lg border border-light-200"
                    >
                      <span className="text-sm text-owl-blue-900 truncate flex-1">
                        {snapshotName(id)}
                      </span>
                      <button
                        type="button"
                        onClick={() => removeAttachedSnapshot(id)}
                        className="p-1 hover:bg-red-100 rounded text-red-600"
                        title="Remove"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {availableToAdd.length > 0 ? (
                <div className="flex gap-2">
                  <select
                    value={addSnapshotId}
                    onChange={(e) => setAddSnapshotId(e.target.value)}
                    className="flex-1 px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500 text-sm"
                  >
                    <option value="">Add a snapshot…</option>
                    {availableToAdd.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name || 'Unnamed'}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={addAttachedSnapshot}
                    disabled={!addSnapshotId}
                    className="px-3 py-2 bg-owl-blue-100 text-owl-blue-700 rounded-lg hover:bg-owl-blue-200 disabled:opacity-50 text-sm font-medium"
                  >
                    Add
                  </button>
                </div>
              ) : (
                <p className="text-xs text-light-500 italic">
                  {caseSnapshots.length === 0
                    ? 'No snapshots in this case. Save snapshots from the graph view first.'
                    : 'All case snapshots are already attached.'}
                </p>
              )}
            </div>
          )}

          <div className="flex gap-2 pt-4 border-t border-light-200">
            <button
              type="submit"
              className="flex items-center gap-2 px-4 py-2 bg-owl-blue-500 text-white rounded-lg hover:bg-owl-blue-600 transition-colors"
            >
              <Save className="w-4 h-4" />
              Save Theory
            </button>
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 bg-light-200 text-light-700 rounded-lg hover:bg-light-300 transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
