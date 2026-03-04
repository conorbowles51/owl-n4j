import { useState, useEffect, useCallback } from 'react';
import { Trash2, RotateCcw, AlertTriangle, Loader2, X, ChevronDown, ChevronRight } from 'lucide-react';
import { graphAPI } from '../services/api';

/**
 * RecycleBinPanel — shows soft-deleted entities for a case
 * and allows restoring or permanently deleting them.
 *
 * Props:
 *   caseId: string
 *   isOpen: boolean
 *   onClose: () => void
 *   onRestored: () => void  — called after restoring an entity so the graph can refresh
 */
export default function RecycleBinPanel({ caseId, isOpen, onClose, onRestored }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [actionKey, setActionKey] = useState(null); // key of item currently being acted on
  const [confirmDelete, setConfirmDelete] = useState(null); // key of item to permanently delete

  const loadItems = useCallback(async () => {
    if (!caseId || !isOpen) return;
    setLoading(true);
    setError(null);
    try {
      const res = await graphAPI.listRecycledEntities(caseId);
      setItems(res?.items || []);
    } catch (err) {
      console.error('Failed to load recycling bin:', err);
      setError(err.message || 'Failed to load recycling bin');
    } finally {
      setLoading(false);
    }
  }, [caseId, isOpen]);

  useEffect(() => {
    loadItems();
  }, [loadItems]);

  const handleRestore = async (recycleKey) => {
    setActionKey(recycleKey);
    try {
      await graphAPI.restoreRecycledEntity(recycleKey, caseId);
      await loadItems();
      if (onRestored) onRestored();
    } catch (err) {
      console.error('Failed to restore entity:', err);
      setError(err.message || 'Failed to restore entity');
    } finally {
      setActionKey(null);
    }
  };

  const handlePermanentDelete = async (recycleKey) => {
    setActionKey(recycleKey);
    try {
      await graphAPI.permanentlyDeleteRecycled(recycleKey, caseId);
      setConfirmDelete(null);
      await loadItems();
    } catch (err) {
      console.error('Failed to permanently delete:', err);
      setError(err.message || 'Failed to permanently delete');
    } finally {
      setActionKey(null);
    }
  };

  // Group items by reason
  const groupedItems = items.reduce((acc, item) => {
    const reason = item.reason || 'unknown';
    let label = 'Deleted';
    if (reason.startsWith('merge_into:')) {
      label = 'Merged';
    } else if (reason.startsWith('file_delete:')) {
      label = 'File Removed';
    } else if (reason === 'manual_delete') {
      label = 'Manually Deleted';
    }
    if (!acc[label]) acc[label] = [];
    acc[label].push(item);
    return acc;
  }, {});

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-light-200">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-full bg-light-100">
              <Trash2 className="w-5 h-5 text-light-600" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-owl-blue-900">Recycling Bin</h2>
              <p className="text-xs text-light-500">
                {items.length} item{items.length !== 1 ? 's' : ''} — restore or permanently delete
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 rounded-full hover:bg-light-100">
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>

        {/* Error banner */}
        {error && (
          <div className="mx-6 mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {loading ? (
            <div className="flex items-center justify-center py-12 text-light-600">
              <Loader2 className="w-5 h-5 mr-2 animate-spin" />
              Loading...
            </div>
          ) : items.length === 0 ? (
            <div className="text-center py-12 text-light-500 text-sm">
              <Trash2 className="w-8 h-8 mx-auto mb-3 text-light-300" />
              <p>The recycling bin is empty.</p>
              <p className="text-xs mt-1">Deleted or merged entities will appear here for recovery.</p>
            </div>
          ) : (
            <div className="space-y-4">
              {Object.entries(groupedItems).map(([label, groupItems]) => (
                <RecycleBinGroup
                  key={label}
                  label={label}
                  items={groupItems}
                  actionKey={actionKey}
                  confirmDelete={confirmDelete}
                  onRestore={handleRestore}
                  onRequestDelete={setConfirmDelete}
                  onConfirmDelete={handlePermanentDelete}
                  onCancelDelete={() => setConfirmDelete(null)}
                />
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-light-200 bg-light-50 flex items-center justify-between">
          <p className="text-xs text-light-500">
            Restored entities will reappear in the graph with their original relationships (where possible).
          </p>
          <button
            onClick={onClose}
            className="px-4 py-1.5 text-sm border border-light-300 rounded-md hover:bg-light-100"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

function RecycleBinGroup({ label, items, actionKey, confirmDelete, onRestore, onRequestDelete, onConfirmDelete, onCancelDelete }) {
  const [isExpanded, setIsExpanded] = useState(true);

  return (
    <div>
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-2 text-xs font-semibold text-light-600 uppercase tracking-wide mb-2 hover:text-light-800"
      >
        {isExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        {label} ({items.length})
      </button>
      {isExpanded && (
        <div className="space-y-2">
          {items.map((item) => (
            <div
              key={item.key}
              className="flex items-center justify-between p-3 rounded-lg border border-light-200 bg-white hover:bg-light-50"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm text-owl-blue-900 truncate">
                    {item.original_name}
                  </span>
                </div>
                <div className="flex items-center gap-3 text-xs text-light-500 mt-0.5">
                  <span>
                    Deleted{' '}
                    {item.deleted_at
                      ? new Date(item.deleted_at).toLocaleDateString('en-GB', {
                          day: 'numeric',
                          month: 'short',
                          year: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                        })
                      : 'unknown date'}
                  </span>
                  {item.deleted_by && <span>by {item.deleted_by}</span>}
                </div>
              </div>

              <div className="flex items-center gap-2 flex-shrink-0 ml-4">
                {confirmDelete === item.key ? (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-red-600">Delete forever?</span>
                    <button
                      onClick={() => onConfirmDelete(item.key)}
                      disabled={actionKey === item.key}
                      className="px-2 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
                    >
                      {actionKey === item.key ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        'Yes'
                      )}
                    </button>
                    <button
                      onClick={onCancelDelete}
                      className="px-2 py-1 text-xs border border-light-300 rounded hover:bg-light-100"
                    >
                      No
                    </button>
                  </div>
                ) : (
                  <>
                    <button
                      onClick={() => onRestore(item.key)}
                      disabled={actionKey === item.key}
                      className="inline-flex items-center gap-1 px-2.5 py-1 text-xs bg-green-50 text-green-700 border border-green-200 rounded hover:bg-green-100 disabled:opacity-50"
                      title="Restore entity to graph"
                    >
                      {actionKey === item.key ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <RotateCcw className="w-3 h-3" />
                      )}
                      Restore
                    </button>
                    <button
                      onClick={() => onRequestDelete(item.key)}
                      disabled={actionKey === item.key}
                      className="p-1.5 text-light-400 hover:text-red-500 rounded hover:bg-red-50"
                      title="Permanently delete"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
