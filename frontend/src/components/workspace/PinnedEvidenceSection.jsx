import React, { useState, useEffect } from 'react';
import { Pin, ChevronDown, ChevronRight, Focus, FileText, CheckCircle2, Calendar, Link2 } from 'lucide-react';
import { workspaceAPI, evidenceAPI } from '../../services/api';
import FilePreview from '../FilePreview';
import AttachToTheoryModal from './AttachToTheoryModal';

/**
 * Pinned Evidence Section
 *
 * Displays pinned evidence items with the same layout as All Evidence:
 * file cards, expandable preview, AI summary, unpin.
 */
export default function PinnedEvidenceSection({
  caseId,
  pinnedItems,
  onRefresh,
  isCollapsed,
  onToggle,
  onFocus,
  fullHeight = false, // When true, use full height for content panel
}) {
  const [evidence, setEvidence] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedFileId, setExpandedFileId] = useState(null);
  const [attachModal, setAttachModal] = useState({ open: false, file: null });

  const evidencePins = pinnedItems.filter((item) => item.item_type === 'evidence');
  const evidenceCount = evidencePins.length;

  const pinnedIdsStr = evidencePins.map((p) => p.item_id).join(',');

  useEffect(() => {
    const loadPinnedEvidence = async () => {
      if (!caseId || evidencePins.length === 0) {
        setEvidence([]);
        setLoading(false);
        return;
      }

      setLoading(true);
      try {
        const data = await evidenceAPI.list(caseId);
        const allFiles = data?.files || (Array.isArray(data) ? data : []);
        const pinnedIds = new Set(evidencePins.map((p) => p.item_id));
        const pinned = allFiles.filter((f) => pinnedIds.has(f.id));
        setEvidence(pinned);
      } catch (err) {
        console.error('Failed to load pinned evidence:', err);
        setEvidence([]);
      } finally {
        setLoading(false);
      }
    };

    loadPinnedEvidence();
  }, [caseId, pinnedIdsStr, evidencePins.length]);

  const getPinId = (fileId) => {
    const p = pinnedItems.find((item) => item.item_type === 'evidence' && item.item_id === fileId);
    return p?.pin_id;
  };

  const handleUnpin = async (file, e) => {
    e.stopPropagation();
    const pinId = getPinId(file.id);
    if (!pinId) return;
    try {
      await workspaceAPI.unpinItem(caseId, pinId);
      onRefresh?.();
    } catch (err) {
      console.error('Failed to unpin:', err);
    }
  };

  const handleAttachToTheory = async (theory, itemType, itemId) => {
    if (!caseId || !theory) return;
    try {
      const existing = theory.attached_evidence_ids || [];
      const ids = existing.includes(itemId) ? existing : [...existing, itemId];
      await workspaceAPI.updateTheory(caseId, theory.theory_id, {
        ...theory,
        attached_evidence_ids: ids,
      });
    } catch (err) {
      console.error('Failed to attach evidence to theory:', err);
      throw err;
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    try {
      return new Date(dateString).toLocaleDateString('en-US', {
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

  const humanSize = (bytes) => {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
  };

  return (
    <div className={`border-b border-light-200 ${fullHeight ? 'h-full flex flex-col' : ''}`}>
      <div className={`${fullHeight ? 'flex-shrink-0' : ''} p-4 cursor-pointer hover:bg-light-50 transition-colors flex items-center justify-between`}
        onClick={(e) => onToggle?.(e)}
      >
        <h3 className="text-sm font-semibold text-owl-blue-900 flex items-center gap-2">
          <Pin className="w-4 h-4 text-owl-blue-600" />
          Pinned Evidence ({evidenceCount})
        </h3>
        <div className="flex items-center gap-2">
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
        <div className={`px-4 pb-4 ${fullHeight ? 'flex flex-col flex-1 min-h-0' : ''}`}>
          {loading ? (
            <p className="text-xs text-light-500">Loading pinned evidence...</p>
          ) : evidence.length === 0 ? (
            <p className="text-xs text-light-500 italic">No pinned evidence</p>
          ) : (
            <div className={`space-y-2 overflow-y-auto ${fullHeight ? 'flex-1 min-h-0' : 'max-h-96'}`}>
              {evidence.map((file) => {
                const isExpanded = expandedFileId === file.id;
                return (
                  <div
                    key={file.id}
                    className="border border-light-200 rounded-lg bg-light-50 hover:bg-light-100 transition-colors"
                  >
                    <div
                      className="p-3 cursor-pointer"
                      onClick={() => setExpandedFileId(isExpanded ? null : file.id)}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-start gap-2 flex-1 min-w-0">
                          <FileText className="w-4 h-4 text-owl-blue-600 mt-0.5 flex-shrink-0" />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <p className="text-sm font-medium text-owl-blue-900 truncate">
                                {file.original_filename || file.filename || `Evidence ${file.id}`}
                              </p>
                              {file.status === 'processed' && (
                                <CheckCircle2
                                  className="w-3.5 h-3.5 text-green-600 flex-shrink-0"
                                  title="Processed"
                                />
                              )}
                              {file.status === 'unprocessed' && (
                                <span
                                  className="text-xs text-orange-600 bg-orange-100 px-1.5 py-0.5 rounded"
                                  title="Unprocessed"
                                >
                                  Unprocessed
                                </span>
                              )}
                              {file.status === 'processing' && (
                                <span
                                  className="text-xs text-yellow-600 bg-yellow-100 px-1.5 py-0.5 rounded"
                                  title="Processing"
                                >
                                  Processing
                                </span>
                              )}
                              {file.status === 'failed' && (
                                <span
                                  className="text-xs text-red-600 bg-red-100 px-1.5 py-0.5 rounded"
                                  title="Failed"
                                >
                                  Failed
                                </span>
                              )}
                            </div>
                            <div className="flex items-center gap-2 mt-1 text-xs text-light-600">
                              {file.size && (
                                <>
                                  <span>{humanSize(file.size)}</span>
                                  <span>•</span>
                                </>
                              )}
                              {file.processed_at && (
                                <>
                                  <Calendar className="w-3 h-3" />
                                  <span>{formatDate(file.processed_at)}</span>
                                </>
                              )}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-1 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setAttachModal({ open: true, file });
                            }}
                            className="p-1.5 hover:bg-owl-blue-100 rounded transition-colors"
                            title="Attach to theory"
                          >
                            <Link2 className="w-4 h-4 text-owl-blue-600" />
                          </button>
                          <button
                            onClick={(e) => handleUnpin(file, e)}
                            className="p-1.5 rounded transition-colors bg-owl-blue-100 text-owl-blue-700 hover:bg-owl-blue-200"
                            title="Unpin"
                          >
                            <Pin className="w-4 h-4 fill-current" />
                          </button>
                        </div>
                      </div>
                    </div>

                    {isExpanded && (
                      <div className="px-3 pb-3 border-t border-light-200 pt-3">
                        <FilePreview
                          caseId={caseId}
                          filePath={file.stored_path || ''}
                          fileName={file.original_filename || file.filename}
                          fileType="file"
                          onClose={() => setExpandedFileId(null)}
                        />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {attachModal.open && attachModal.file && (
        <AttachToTheoryModal
          isOpen={attachModal.open}
          onClose={() => setAttachModal({ open: false, file: null })}
          caseId={caseId}
          itemType="evidence"
          itemId={attachModal.file.id}
          itemName={attachModal.file.original_filename || attachModal.file.filename || 'Evidence'}
          onAttach={handleAttachToTheory}
        />
      )}
    </div>
  );
}
