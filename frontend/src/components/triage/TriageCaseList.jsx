import React, { useState } from 'react';
import {
  Plus, Loader2, HardDrive, Trash2, FolderOpen, Clock,
  FileText, AlertCircle, CheckCircle2, RefreshCw,
} from 'lucide-react';
import { triageAPI } from '../../services/api';
import DirectoryBrowser from './DirectoryBrowser';

const STATUS_CONFIG = {
  created: { label: 'Created', color: 'bg-light-200 text-light-700', icon: Clock },
  scanning: { label: 'Scanning', color: 'bg-blue-100 text-blue-700', icon: Loader2 },
  scan_complete: { label: 'Scanned', color: 'bg-green-100 text-green-700', icon: CheckCircle2 },
  classifying: { label: 'Classifying', color: 'bg-blue-100 text-blue-700', icon: Loader2 },
  classified: { label: 'Classified', color: 'bg-green-100 text-green-700', icon: CheckCircle2 },
  profiled: { label: 'Profiled', color: 'bg-green-100 text-green-700', icon: CheckCircle2 },
  processing: { label: 'Processing', color: 'bg-amber-100 text-amber-700', icon: Loader2 },
  completed: { label: 'Completed', color: 'bg-green-100 text-green-800', icon: CheckCircle2 },
};

function formatSize(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  let size = bytes;
  while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
  return `${size.toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
}

function formatDate(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleDateString('en-GB', {
      day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}

export default function TriageCaseList({ cases, loading, onRefresh, onOpenCase, authUsername }) {
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newCase, setNewCase] = useState({ name: '', description: '', source_path: '' });
  const [deleting, setDeleting] = useState(null);

  const handleCreate = async () => {
    if (!newCase.name.trim() || !newCase.source_path.trim()) return;
    setCreating(true);
    try {
      const created = await triageAPI.createCase(newCase);
      setShowCreate(false);
      setNewCase({ name: '', description: '', source_path: '' });
      onOpenCase(created.id);
    } catch (err) {
      alert(`Error creating triage case: ${err.message}`);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (caseId, e) => {
    e.stopPropagation();
    if (!confirm('Delete this triage case and all its data?')) return;
    setDeleting(caseId);
    try {
      await triageAPI.deleteCase(caseId);
      onRefresh();
    } catch (err) {
      alert(`Error deleting: ${err.message}`);
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div className="max-w-5xl mx-auto">
      {/* Toolbar */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold text-owl-blue-900">Triage Cases</h2>
          <p className="text-sm text-light-600 mt-1">
            Scan and analyse drives or directories before ingesting into investigations
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={onRefresh}
            className="p-2 hover:bg-light-100 rounded-lg transition-colors"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 text-light-600 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 px-4 py-2 bg-owl-blue-600 text-white rounded-lg hover:bg-owl-blue-700 transition-colors"
          >
            <Plus className="w-4 h-4" />
            New Triage
          </button>
        </div>
      </div>

      {/* Create modal */}
      {showCreate && (
        <>
          <div className="fixed inset-0 bg-black bg-opacity-50 z-40" onClick={() => setShowCreate(false)} />
          <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-lg bg-white rounded-xl shadow-xl z-50">
            <div className="p-6 border-b border-light-200">
              <h3 className="text-lg font-semibold text-owl-blue-900">New Triage Case</h3>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium text-light-700 mb-1">Name</label>
                <input
                  type="text"
                  value={newCase.name}
                  onChange={(e) => setNewCase({ ...newCase, name: e.target.value })}
                  className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
                  placeholder="e.g., Suspect Laptop Drive"
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-light-700 mb-1">Description</label>
                <textarea
                  value={newCase.description}
                  onChange={(e) => setNewCase({ ...newCase, description: e.target.value })}
                  className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
                  rows={2}
                  placeholder="Optional description..."
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-light-700 mb-1">Source Directory</label>
                <DirectoryBrowser
                  value={newCase.source_path}
                  onChange={(path) => setNewCase({ ...newCase, source_path: path })}
                />
                <p className="text-xs text-light-500 mt-1">Select the mounted drive or directory to scan</p>
              </div>
            </div>
            <div className="p-6 border-t border-light-200 flex justify-end gap-3">
              <button
                onClick={() => setShowCreate(false)}
                className="px-4 py-2 text-light-700 hover:bg-light-100 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={creating || !newCase.name.trim() || !newCase.source_path.trim()}
                className="flex items-center gap-2 px-4 py-2 bg-owl-blue-600 text-white rounded-lg hover:bg-owl-blue-700 disabled:opacity-50 transition-colors"
              >
                {creating && <Loader2 className="w-4 h-4 animate-spin" />}
                Create & Open
              </button>
            </div>
          </div>
        </>
      )}

      {/* Case list */}
      {loading && cases.length === 0 ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-8 h-8 animate-spin text-owl-blue-600" />
        </div>
      ) : cases.length === 0 ? (
        <div className="text-center py-20 text-light-500">
          <HardDrive className="w-12 h-12 mx-auto mb-4 text-light-300" />
          <p className="text-lg mb-2">No triage cases yet</p>
          <p className="text-sm">Create a new triage case to scan a drive or directory</p>
        </div>
      ) : (
        <div className="grid gap-4">
          {cases.map((tc) => {
            const cfg = STATUS_CONFIG[tc.status] || STATUS_CONFIG.created;
            const StatusIcon = cfg.icon;
            const stats = tc.scan_stats || {};
            return (
              <div
                key={tc.id}
                onClick={() => onOpenCase(tc.id)}
                className="bg-white rounded-xl border border-light-200 p-5 hover:border-owl-blue-300 hover:shadow-md transition-all cursor-pointer"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 mb-2">
                      <HardDrive className="w-5 h-5 text-owl-blue-600 flex-shrink-0" />
                      <h3 className="text-base font-semibold text-owl-blue-900 truncate">{tc.name}</h3>
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium flex items-center gap-1 ${cfg.color}`}>
                        <StatusIcon className={`w-3 h-3 ${tc.status === 'scanning' || tc.status === 'classifying' || tc.status === 'processing' ? 'animate-spin' : ''}`} />
                        {cfg.label}
                      </span>
                    </div>
                    {tc.description && (
                      <p className="text-sm text-light-600 mb-2 line-clamp-1">{tc.description}</p>
                    )}
                    <div className="flex items-center gap-4 text-xs text-light-500">
                      <span className="flex items-center gap-1 font-mono">
                        <FolderOpen className="w-3 h-3" />
                        {tc.source_path}
                      </span>
                      {stats.total_files > 0 && (
                        <span className="flex items-center gap-1">
                          <FileText className="w-3 h-3" />
                          {stats.total_files.toLocaleString()} files
                        </span>
                      )}
                      {stats.total_size > 0 && (
                        <span>{formatSize(stats.total_size)}</span>
                      )}
                      <span>{formatDate(tc.created_at)}</span>
                    </div>
                  </div>
                  <button
                    onClick={(e) => handleDelete(tc.id, e)}
                    disabled={deleting === tc.id}
                    className="p-2 text-light-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors ml-4"
                    title="Delete triage case"
                  >
                    {deleting === tc.id ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Trash2 className="w-4 h-4" />
                    )}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
