import React, { useState, useEffect, useMemo } from 'react';
import { ChevronDown, ChevronRight, FileText, Focus, Pin, CheckCircle2, Calendar, X, Filter, Link2 } from 'lucide-react';
import { evidenceAPI, workspaceAPI } from '../../services/api';
import FilePreview from '../FilePreview';
import AttachToTheoryModal from './AttachToTheoryModal';

/**
 * All Evidence Section
 * 
 * Displays all evidence items for the case with preview and pinning
 * Allows filtering between processed and unprocessed files
 */
export default function AllEvidenceSection({
  caseId,
  isCollapsed,
  onToggle,
  onFocus,
  pinnedItems = [],
  onRefreshPinned,
  fullHeight = false, // When true, use full height for content panel
}) {
  const [allEvidence, setAllEvidence] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedFileId, setExpandedFileId] = useState(null);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState('all'); // 'all', 'processed', 'unprocessed'
  const [attachModal, setAttachModal] = useState({ open: false, file: null });

  // Helper function to identify Case Documents (Quick Action uploads)
  // Same logic as DocumentsSection to ensure consistency
  const isCaseDocument = (file) => {
    const filename = (file.original_filename || file.filename || '').toLowerCase();
    
    // Text notes from Quick Actions (explicit pattern)
    if (filename.startsWith('note_') && filename.endsWith('.txt')) {
      return true;
    }
    
    // Links from Quick Actions (explicit pattern)
    if (filename.startsWith('link_') || filename.endsWith('_link.txt')) {
      return true;
    }
    
    // Image files (likely from Quick Actions Photo upload)
    const imageExtensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'];
    if (imageExtensions.some(ext => filename.endsWith(ext))) {
      return true;
    }
    
    // Other document types that might be uploaded via Quick Actions
    // (PDFs, Word docs, etc. - but we'll be conservative and only include if they match patterns)
    const docExtensions = ['.pdf', '.doc', '.docx', '.txt', '.rtf'];
    if (docExtensions.some(ext => filename.endsWith(ext))) {
      // Only include if it looks like a Quick Action upload (has note_ or link_ prefix, or is a simple filename)
      // Exclude files that look like evidence (long names, timestamps, etc.)
      const isSimpleName = filename.split('.').length === 2; // Simple: "file.pdf"
      const hasQuickActionPattern = filename.startsWith('note_') || filename.startsWith('link_');
      
      if (hasQuickActionPattern || isSimpleName) {
        return true;
      }
    }
    
    return false;
  };

  useEffect(() => {
    const loadEvidence = async () => {
      if (!caseId) {
        console.log('[AllEvidenceSection] No caseId provided');
        return;
      }
      
      console.log('[AllEvidenceSection] Loading evidence for caseId:', caseId);
      setLoading(true);
      try {
        const data = await evidenceAPI.list(caseId);
        console.log('[AllEvidenceSection] Full API response:', JSON.stringify(data, null, 2));
        // The API returns { files: [...] }
        const allFiles = data?.files || (Array.isArray(data) ? data : []);
        console.log('[AllEvidenceSection] All files found:', allFiles.length);
        
        // Filter out Case Documents (Quick Action uploads)
        const evidenceFiles = allFiles.filter(file => !isCaseDocument(file));
        console.log('[AllEvidenceSection] Evidence files (excluding Case Documents):', evidenceFiles.length);
        
        if (allFiles.length > 0) {
          console.log('[AllEvidenceSection] Sample file:', allFiles[0]);
          console.log('[AllEvidenceSection] File statuses:', allFiles.map(f => ({ 
            id: f.id, 
            filename: f.original_filename || f.filename, 
            status: f.status,
            case_id: f.case_id 
          })));
        } else {
          console.warn('[AllEvidenceSection] No files returned from API. Response:', data);
        }
        setError(null);
        // Store only evidence files (excluding Case Documents)
        setAllEvidence(evidenceFiles);
      } catch (err) {
        console.error('[AllEvidenceSection] Failed to load evidence:', err);
        setError(`Failed to load evidence: ${err.message || err}`);
        setAllEvidence([]);
      } finally {
        setLoading(false);
      }
    };

    loadEvidence();
  }, [caseId]); // Load whenever caseId changes, regardless of collapsed state

  const isPinned = (fileId) => {
    return pinnedItems.some(item => item.item_type === 'evidence' && item.item_id === fileId);
  };

  const getPinId = (fileId) => {
    const pinnedItem = pinnedItems.find(item => item.item_type === 'evidence' && item.item_id === fileId);
    return pinnedItem?.pin_id;
  };

  const handlePin = async (file, e) => {
    e.stopPropagation();
    try {
      await workspaceAPI.pinItem(caseId, 'evidence', file.id, 0);
      if (onRefreshPinned) {
        onRefreshPinned();
      }
    } catch (err) {
      console.error('Failed to pin evidence:', err);
      alert('Failed to pin evidence');
    }
  };

  const handleUnpin = async (file, e) => {
    e.stopPropagation();
    const pinId = getPinId(file.id);
    if (!pinId) return;
    
    try {
      await workspaceAPI.unpinItem(caseId, pinId);
      if (onRefreshPinned) {
        onRefreshPinned();
      }
    } catch (err) {
      console.error('Failed to unpin evidence:', err);
      alert('Failed to unpin evidence');
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

  // Filter evidence based on selected filter
  const filteredEvidence = useMemo(() => {
    if (filter === 'all') {
      return allEvidence;
    } else if (filter === 'processed') {
      return allEvidence.filter(f => f.status === 'processed');
    } else if (filter === 'unprocessed') {
      return allEvidence.filter(f => f.status !== 'processed' && f.status !== 'duplicate');
    }
    return allEvidence;
  }, [allEvidence, filter]);

  const processedCount = allEvidence.filter(f => f.status === 'processed').length;
  const unprocessedCount = allEvidence.filter(f => f.status !== 'processed' && f.status !== 'duplicate').length;

  return (
    <div className={`border-b border-light-200 ${fullHeight ? 'h-full flex flex-col' : ''}`}>
      <div className={`${fullHeight ? 'flex-shrink-0' : ''} p-4 cursor-pointer hover:bg-light-50 transition-colors flex items-center justify-between`}
        onClick={(e) => onToggle && onToggle(e)}
      >
        <div>
          <h3 className="text-sm font-semibold text-owl-blue-900">
            Evidence Files ({allEvidence.length})
          </h3>
          <p className="text-xs text-gray-500 mt-0.5">Prosecution discovery and other evidence documents uploaded for analysis</p>
        </div>
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
            <p className="text-xs text-light-500">Loading evidence...</p>
          ) : error ? (
            <div className="text-xs space-y-2">
              <p className="text-red-600 font-medium">Error loading evidence:</p>
              <p className="text-red-500">{error}</p>
            </div>
          ) : allEvidence.length === 0 ? (
            <div className="text-xs text-light-500 italic space-y-1">
              <p>No evidence files found for this case.</p>
            </div>
          ) : (
            <>
              {/* Filter Toggle */}
              <div className={`mb-3 flex items-center gap-2 ${fullHeight ? 'flex-shrink-0' : ''}`}>
                <Filter className="w-4 h-4 text-light-600" />
                <div className="flex gap-1 bg-light-100 rounded-lg p-1">
                  <button
                    onClick={() => setFilter('all')}
                    className={`px-2 py-1 text-xs rounded transition-colors ${
                      filter === 'all'
                        ? 'bg-owl-blue-500 text-white'
                        : 'text-light-700 hover:bg-light-200'
                    }`}
                  >
                    All ({allEvidence.length})
                  </button>
                  <button
                    onClick={() => setFilter('processed')}
                    className={`px-2 py-1 text-xs rounded transition-colors ${
                      filter === 'processed'
                        ? 'bg-green-500 text-white'
                        : 'text-light-700 hover:bg-light-200'
                    }`}
                  >
                    Processed ({processedCount})
                  </button>
                  <button
                    onClick={() => setFilter('unprocessed')}
                    className={`px-2 py-1 text-xs rounded transition-colors ${
                      filter === 'unprocessed'
                        ? 'bg-orange-500 text-white'
                        : 'text-light-700 hover:bg-light-200'
                    }`}
                  >
                    Unprocessed ({unprocessedCount})
                  </button>
                </div>
              </div>

              {/* Evidence List */}
              {filteredEvidence.length === 0 ? (
                <p className="text-xs text-light-500 italic">
                  No files match the selected filter.
                </p>
              ) : (
                <div className={`space-y-2 overflow-y-auto ${fullHeight ? 'flex-1 min-h-0' : 'max-h-96'}`}>
                  {filteredEvidence.map((file) => {
                const fileIsPinned = isPinned(file.id);
                const isExpanded = expandedFileId === file.id;
                
                return (
                  <div
                    key={file.id}
                    className="border border-light-200 rounded-lg bg-light-50 hover:bg-light-100 transition-colors"
                  >
                    {/* File Header */}
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
                                <CheckCircle2 className="w-3.5 h-3.5 text-green-600 flex-shrink-0" title="Processed" />
                              )}
                              {file.status === 'unprocessed' && (
                                <span className="text-xs text-orange-600 bg-orange-100 px-1.5 py-0.5 rounded" title="Unprocessed">
                                  Unprocessed
                                </span>
                              )}
                              {file.status === 'processing' && (
                                <span className="text-xs text-yellow-600 bg-yellow-100 px-1.5 py-0.5 rounded" title="Processing">
                                  Processing
                                </span>
                              )}
                              {file.status === 'failed' && (
                                <span className="text-xs text-red-600 bg-red-100 px-1.5 py-0.5 rounded" title="Failed">
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
                            onClick={(e) => fileIsPinned ? handleUnpin(file, e) : handlePin(file, e)}
                            className={`p-1.5 rounded transition-colors ${
                              fileIsPinned
                                ? 'bg-owl-blue-100 text-owl-blue-700 hover:bg-owl-blue-200'
                                : 'hover:bg-light-200 text-light-600'
                            }`}
                            title={fileIsPinned ? 'Unpin evidence' : 'Pin evidence'}
                          >
                            <Pin className={`w-4 h-4 ${fileIsPinned ? 'fill-current' : ''}`} />
                          </button>
                        </div>
                      </div>
                    </div>

                    {/* Expanded Content: Preview and Summary */}
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
            </>
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
