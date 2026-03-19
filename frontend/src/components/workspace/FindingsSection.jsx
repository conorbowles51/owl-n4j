import React, { useState, useEffect, useCallback } from 'react';
import { ChevronDown, ChevronRight, Search as SearchIcon, Plus, Pencil, Trash2, Focus, X, Save, FileText, Link2 } from 'lucide-react';
import { workspaceAPI } from '../../services/api';

/**
 * Findings Section
 *
 * Displays investigative findings — key conclusions linked to evidence.
 * Supports create, edit, delete, and evidence linking.
 */
export default function FindingsSection({ caseId, isCollapsed, onToggle, onFocus }) {
  const [findings, setFindings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingFinding, setEditingFinding] = useState(null);

  const loadFindings = useCallback(async () => {
    if (!caseId) return;
    setLoading(true);
    try {
      const data = await workspaceAPI.getFindings(caseId);
      setFindings(data.findings || []);
    } catch (err) {
      console.error('Failed to load findings:', err);
      setFindings([]);
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    loadFindings();
    const handleRefresh = () => loadFindings();
    window.addEventListener('findings-refresh', handleRefresh);
    return () => window.removeEventListener('findings-refresh', handleRefresh);
  }, [loadFindings]);

  const handleDelete = async (findingId) => {
    if (!confirm('Delete this finding?')) return;
    try {
      await workspaceAPI.deleteFinding(caseId, findingId);
      loadFindings();
    } catch (err) {
      console.error('Failed to delete finding:', err);
    }
  };

  const formatDate = (d) => {
    if (!d) return '';
    try { return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }); }
    catch { return d; }
  };

  const priorityColors = {
    HIGH: 'bg-red-100 text-red-700',
    MEDIUM: 'bg-yellow-100 text-yellow-700',
    LOW: 'bg-green-100 text-green-700',
  };

  return (
    <>
      <div className="border-b border-light-200">
        <div
          className="p-4 cursor-pointer hover:bg-light-50 transition-colors flex items-center justify-between"
          onClick={onToggle}
        >
          <h3 className="text-sm font-semibold text-owl-blue-900 flex items-center gap-2">
            <SearchIcon className="w-4 h-4 text-owl-blue-600" />
            Findings ({findings.length})
          </h3>
          <div className="flex items-center gap-2">
            <button
              onClick={(e) => { e.stopPropagation(); setEditingFinding(null); setShowModal(true); }}
              className="p-1 hover:bg-owl-blue-100 rounded transition-colors"
              title="Add finding"
            >
              <Plus className="w-4 h-4 text-owl-blue-600" />
            </button>
            {onFocus && (
              <button
                onClick={(e) => { e.stopPropagation(); onFocus(e); }}
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
              <p className="text-xs text-light-500">Loading findings...</p>
            ) : findings.length === 0 ? (
              <p className="text-xs text-light-500 italic">No findings yet. Click + to add one.</p>
            ) : (
              <div className="space-y-2">
                {findings.map((finding) => (
                  <div key={finding.finding_id} className="p-3 bg-light-50 rounded-lg border border-light-200 hover:bg-light-100 transition-colors">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-sm font-medium text-owl-blue-900">{finding.title}</span>
                          {finding.priority && (
                            <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${priorityColors[finding.priority] || ''}`}>
                              {finding.priority}
                            </span>
                          )}
                        </div>
                        {finding.content && (
                          <p className="text-xs text-light-700 whitespace-pre-wrap">{finding.content}</p>
                        )}
                        <div className="flex items-center gap-2 mt-1 text-[10px] text-light-500">
                          {finding.created_at && <span>{formatDate(finding.created_at)}</span>}
                          {finding.linked_evidence_ids?.length > 0 && (
                            <span className="flex items-center gap-0.5">
                              <Link2 className="w-3 h-3" />
                              {finding.linked_evidence_ids.length} evidence
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-0.5 flex-shrink-0">
                        <button
                          onClick={() => { setEditingFinding(finding); setShowModal(true); }}
                          className="p-1.5 hover:bg-owl-blue-100 rounded transition-colors"
                          title="Edit finding"
                        >
                          <Pencil className="w-3.5 h-3.5 text-owl-blue-600" />
                        </button>
                        <button
                          onClick={() => handleDelete(finding.finding_id)}
                          className="p-1.5 hover:bg-red-100 rounded transition-colors"
                          title="Delete finding"
                        >
                          <Trash2 className="w-3.5 h-3.5 text-red-600" />
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {showModal && (
        <FindingModal
          caseId={caseId}
          finding={editingFinding}
          onClose={() => { setShowModal(false); setEditingFinding(null); }}
          onSaved={() => { setShowModal(false); setEditingFinding(null); loadFindings(); }}
        />
      )}
    </>
  );
}


function FindingModal({ caseId, finding, onClose, onSaved }) {
  const [title, setTitle] = useState(finding?.title || '');
  const [content, setContent] = useState(finding?.content || '');
  const [priority, setPriority] = useState(finding?.priority || '');
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!title.trim()) return;
    setSaving(true);
    try {
      const data = { title: title.trim(), content: content.trim(), priority: priority || null };
      if (finding?.finding_id) {
        await workspaceAPI.updateFinding(caseId, finding.finding_id, data);
      } else {
        await workspaceAPI.createFinding(caseId, data);
      }
      onSaved();
    } catch (err) {
      console.error('Failed to save finding:', err);
      alert('Failed to save finding');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between p-4 border-b border-light-200">
          <h3 className="text-lg font-semibold text-owl-blue-900">{finding ? 'Edit Finding' : 'Add Finding'}</h3>
          <button onClick={onClose} className="p-1 hover:bg-light-100 rounded" disabled={saving}>
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-4 space-y-3">
          <div>
            <label className="block text-sm font-medium text-owl-blue-900 mb-1">Title *</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g., Financial discrepancy in Q3 transactions"
              className="w-full px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
              required
              autoFocus
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-owl-blue-900 mb-1">Details</label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={6}
              placeholder="Describe the finding, evidence supporting it, and its significance..."
              className="w-full px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-owl-blue-900 mb-1">Priority</label>
            <select
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              className="w-full px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
            >
              <option value="">None</option>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>
          </div>
          <div className="flex gap-2 pt-3 border-t border-light-200">
            <button
              type="submit"
              disabled={saving || !title.trim()}
              className="flex-1 px-4 py-2 bg-owl-blue-600 text-white rounded-lg hover:bg-owl-blue-700 disabled:opacity-50 flex items-center justify-center gap-2"
            >
              <Save className="w-4 h-4" />
              {saving ? 'Saving...' : finding ? 'Update' : 'Save Finding'}
            </button>
            <button type="button" onClick={onClose} disabled={saving} className="px-4 py-2 bg-light-200 text-light-700 rounded-lg hover:bg-light-300">
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
