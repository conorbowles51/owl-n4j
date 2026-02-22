import React, { useState, useEffect, useMemo } from 'react';
import { ChevronDown, ChevronRight, FileText, Focus, Pin, CheckCircle2, Calendar, Filter, Link2, Image as ImageIcon, ExternalLink, ChevronUp, FolderOpen, Upload, Files } from 'lucide-react';
import { evidenceAPI, workspaceAPI } from '../../services/api';
import FilePreview from '../FilePreview';
import AttachToTheoryModal from './AttachToTheoryModal';

const isCaseDocument = (file) => {
  const filename = (file.original_filename || file.filename || '').toLowerCase();
  if (filename.startsWith('note_') && filename.endsWith('.txt')) return true;
  if (filename.startsWith('link_') || filename.endsWith('_link.txt')) return true;
  const imageExtensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'];
  if (imageExtensions.some(ext => filename.endsWith(ext))) return true;
  const docExtensions = ['.pdf', '.doc', '.docx', '.txt', '.rtf'];
  if (docExtensions.some(ext => filename.endsWith(ext))) {
    const isSimpleName = filename.split('.').length === 2;
    const hasQuickActionPattern = filename.startsWith('note_') || filename.startsWith('link_');
    if (hasQuickActionPattern || isSimpleName) return true;
  }
  return false;
};

const isImageFile = (filename) => {
  const exts = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'];
  return exts.some(ext => filename.toLowerCase().endsWith(ext));
};

const isLinkFile = (filename) => {
  const lower = filename.toLowerCase();
  return lower.startsWith('link_') || lower.endsWith('_link.txt');
};

const getFileIcon = (filename) => {
  if (isImageFile(filename)) return ImageIcon;
  if (isLinkFile(filename)) return ExternalLink;
  return FileText;
};

const formatDate = (dateString) => {
  if (!dateString) return 'N/A';
  try {
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  } catch { return dateString; }
};

const humanSize = (bytes) => {
  if (!bytes) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
};

const parseLinkContent = (content) => {
  if (!content) return { title: '', url: '', description: '', added: '' };
  const data = { title: '', url: '', description: '', added: '' };
  content.split('\n').forEach(line => {
    if (line.startsWith('Title:')) data.title = line.replace('Title:', '').trim();
    else if (line.startsWith('URL:')) data.url = line.replace('URL:', '').trim();
    else if (line.startsWith('Description:')) data.description = line.replace('Description:', '').trim();
    else if (line.startsWith('Added:')) data.added = line.replace('Added:', '').trim();
  });
  return data;
};

const TABS = [
  { key: 'all', label: 'All Documents', icon: Files },
  { key: 'evidence', label: 'Evidence Files', icon: FolderOpen },
  { key: 'uploaded', label: 'Uploaded', icon: Upload },
];

export default function CaseFilesSection({
  caseId,
  isCollapsed,
  onToggle,
  onFocus,
  pinnedItems = [],
  onRefreshPinned,
  fullHeight = false,
}) {
  const [allFiles, setAllFiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [expandedFileId, setExpandedFileId] = useState(null);
  const [attachModal, setAttachModal] = useState({ open: false, file: null });
  const [fileContents, setFileContents] = useState({});

  useEffect(() => {
    const load = async () => {
      if (!caseId) return;
      setLoading(true);
      try {
        const data = await evidenceAPI.list(caseId);
        const files = data?.files || (Array.isArray(data) ? data : []);
        setAllFiles(files);
        setError(null);
      } catch (err) {
        console.error('[CaseFilesSection] Failed to load files:', err);
        setError(`Failed to load files: ${err.message || err}`);
        setAllFiles([]);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [caseId]);

  useEffect(() => {
    const handleRefresh = () => {
      if (!caseId) return;
      evidenceAPI.list(caseId).then(data => {
        setAllFiles(data?.files || (Array.isArray(data) ? data : []));
      }).catch(() => {});
    };
    window.addEventListener('documents-refresh', handleRefresh);
    return () => window.removeEventListener('documents-refresh', handleRefresh);
  }, [caseId]);

  const evidenceFiles = useMemo(() => allFiles.filter(f => !isCaseDocument(f)), [allFiles]);
  const uploadedFiles = useMemo(() => allFiles.filter(f => isCaseDocument(f)), [allFiles]);

  const displayFiles = useMemo(() => {
    let base;
    if (activeTab === 'evidence') base = evidenceFiles;
    else if (activeTab === 'uploaded') base = uploadedFiles;
    else base = allFiles;

    if (statusFilter === 'processed') return base.filter(f => f.status === 'processed');
    if (statusFilter === 'unprocessed') return base.filter(f => f.status !== 'processed' && f.status !== 'duplicate');
    return base;
  }, [activeTab, statusFilter, allFiles, evidenceFiles, uploadedFiles]);

  const processedCount = useMemo(() => {
    const base = activeTab === 'evidence' ? evidenceFiles : activeTab === 'uploaded' ? uploadedFiles : allFiles;
    return base.filter(f => f.status === 'processed').length;
  }, [activeTab, allFiles, evidenceFiles, uploadedFiles]);

  const unprocessedCount = useMemo(() => {
    const base = activeTab === 'evidence' ? evidenceFiles : activeTab === 'uploaded' ? uploadedFiles : allFiles;
    return base.filter(f => f.status !== 'processed' && f.status !== 'duplicate').length;
  }, [activeTab, allFiles, evidenceFiles, uploadedFiles]);

  const tabCounts = useMemo(() => ({
    all: allFiles.length,
    evidence: evidenceFiles.length,
    uploaded: uploadedFiles.length,
  }), [allFiles, evidenceFiles, uploadedFiles]);

  const isPinned = (fileId) => pinnedItems.some(item => item.item_type === 'evidence' && item.item_id === fileId);
  const getPinId = (fileId) => pinnedItems.find(item => item.item_type === 'evidence' && item.item_id === fileId)?.pin_id;

  const handlePin = async (file, e) => {
    e.stopPropagation();
    try {
      await workspaceAPI.pinItem(caseId, 'evidence', file.id, 0);
      onRefreshPinned?.();
    } catch (err) {
      console.error('Failed to pin:', err);
    }
  };

  const handleUnpin = async (file, e) => {
    e.stopPropagation();
    const pinId = getPinId(file.id);
    if (!pinId) return;
    try {
      await workspaceAPI.unpinItem(caseId, pinId);
      onRefreshPinned?.();
    } catch (err) {
      console.error('Failed to unpin:', err);
    }
  };

  const handleAttachToTheory = async (theory, itemType, itemId) => {
    if (!caseId || !theory) return;
    try {
      const field = itemType === 'document' ? 'attached_document_ids' : 'attached_evidence_ids';
      const existing = theory[field] || [];
      const ids = existing.includes(itemId) ? existing : [...existing, itemId];
      await workspaceAPI.updateTheory(caseId, theory.theory_id, { ...theory, [field]: ids });
    } catch (err) {
      console.error('Failed to attach to theory:', err);
      throw err;
    }
  };

  const loadFileContent = async (doc) => {
    if (fileContents[doc.id]) return;
    try {
      const filename = (doc.original_filename || doc.filename || '').toLowerCase();
      if (isLinkFile(filename) || filename.startsWith('note_')) {
        const response = await fetch(`/api/evidence/${doc.id}/file`);
        if (response.ok) {
          const text = await response.text();
          setFileContents(prev => ({ ...prev, [doc.id]: text }));
        }
      }
    } catch (err) {
      console.error('Failed to load file content:', err);
    }
  };

  useEffect(() => {
    if (expandedFileId) {
      const doc = allFiles.find(d => d.id === expandedFileId);
      if (doc) loadFileContent(doc);
    }
  }, [expandedFileId]);

  const renderFileRow = (file) => {
    const fileIsPinned = isPinned(file.id);
    const isExpanded = expandedFileId === file.id;
    const filename = file.original_filename || file.filename || '';
    const isUploadedDoc = isCaseDocument(file);
    const isLink = isLinkFile(filename);
    const isNote = filename.toLowerCase().startsWith('note_');
    const Icon = isUploadedDoc ? getFileIcon(filename) : FileText;
    const content = fileContents[file.id];

    return (
      <div key={file.id} className="border border-light-200 rounded-lg bg-light-50 hover:bg-light-100 transition-colors">
        <div className="p-3 cursor-pointer" onClick={() => setExpandedFileId(isExpanded ? null : file.id)}>
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-start gap-2 flex-1 min-w-0">
              <Icon className="w-4 h-4 text-owl-blue-600 mt-0.5 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium text-owl-blue-900 truncate">
                    {filename || `File ${file.id}`}
                  </p>
                  {isUploadedDoc && (
                    <span className="text-[10px] text-purple-600 bg-purple-50 px-1.5 py-0.5 rounded font-medium flex-shrink-0">
                      Uploaded
                    </span>
                  )}
                  {file.status === 'processed' && (
                    <CheckCircle2 className="w-3.5 h-3.5 text-green-600 flex-shrink-0" title="Processed" />
                  )}
                  {file.status === 'unprocessed' && (
                    <span className="text-xs text-orange-600 bg-orange-100 px-1.5 py-0.5 rounded">Unprocessed</span>
                  )}
                  {file.status === 'processing' && (
                    <span className="text-xs text-yellow-600 bg-yellow-100 px-1.5 py-0.5 rounded">Processing</span>
                  )}
                  {file.status === 'failed' && (
                    <span className="text-xs text-red-600 bg-red-100 px-1.5 py-0.5 rounded">Failed</span>
                  )}
                </div>
                <div className="flex items-center gap-2 mt-1 text-xs text-light-600">
                  {file.size && <><span>{humanSize(file.size)}</span><span>•</span></>}
                  {file.processed_at && <><Calendar className="w-3 h-3" /><span>{formatDate(file.processed_at)}</span></>}
                  {file.summary && !isUploadedDoc && (
                    <span className="truncate max-w-[200px]">{file.summary}</span>
                  )}
                </div>
                {isLink && content && (() => {
                  try {
                    const ld = parseLinkContent(content);
                    return ld.url ? (
                      <a href={ld.url} target="_blank" rel="noopener noreferrer"
                        className="text-xs text-owl-blue-600 hover:underline truncate block mt-1"
                        onClick={e => e.stopPropagation()}>{ld.url}</a>
                    ) : null;
                  } catch { return null; }
                })()}
                {isNote && content && (
                  <div className="mt-1 text-xs text-light-600 line-clamp-2">
                    {content.substring(0, 100)}{content.length > 100 ? '...' : ''}
                  </div>
                )}
              </div>
            </div>
            <div className="flex items-center gap-1 flex-shrink-0" onClick={e => e.stopPropagation()}>
              {isLink && content && (() => {
                try {
                  const ld = parseLinkContent(content);
                  return ld.url ? (
                    <a href={ld.url} target="_blank" rel="noopener noreferrer"
                      className="p-1.5 hover:bg-owl-blue-100 rounded transition-colors text-owl-blue-600" title="Open link">
                      <ExternalLink className="w-4 h-4" />
                    </a>
                  ) : null;
                } catch { return null; }
              })()}
              <button onClick={e => { e.stopPropagation(); setAttachModal({ open: true, file }); }}
                className="p-1.5 hover:bg-owl-blue-100 rounded transition-colors" title="Attach to theory">
                <Link2 className="w-4 h-4 text-owl-blue-600" />
              </button>
              <button onClick={e => fileIsPinned ? handleUnpin(file, e) : handlePin(file, e)}
                className={`p-1.5 rounded transition-colors ${fileIsPinned ? 'bg-owl-blue-100 text-owl-blue-700 hover:bg-owl-blue-200' : 'hover:bg-light-200 text-light-600'}`}
                title={fileIsPinned ? 'Unpin' : 'Pin'}>
                <Pin className={`w-4 h-4 ${fileIsPinned ? 'fill-current' : ''}`} />
              </button>
            </div>
          </div>
        </div>

        {isExpanded && (
          <div className="px-3 pb-3 border-t border-light-200 pt-3">
            {isLink ? (
              !content ? <p className="text-xs text-light-500">Loading link details...</p> : (() => {
                try {
                  const ld = parseLinkContent(content);
                  return (
                    <div className="space-y-2">
                      {ld.title && <h5 className="text-sm font-semibold text-owl-blue-900">{ld.title}</h5>}
                      {ld.url && <a href={ld.url} target="_blank" rel="noopener noreferrer"
                        className="text-sm text-owl-blue-600 hover:underline break-all block">{ld.url}</a>}
                      {ld.description && <p className="text-sm text-light-700">{ld.description}</p>}
                      {ld.added && <p className="text-xs text-light-500">Added: {new Date(ld.added).toLocaleString()}</p>}
                    </div>
                  );
                } catch { return <div className="text-xs text-light-600 whitespace-pre-wrap">{content}</div>; }
              })()
            ) : isNote ? (
              !content ? <p className="text-xs text-light-500">Loading note...</p>
                : <div className="text-sm text-light-700 whitespace-pre-wrap">{content}</div>
            ) : (
              <FilePreview caseId={caseId} filePath={file.stored_path || ''} fileName={filename} fileType="file"
                onClose={() => setExpandedFileId(null)} />
            )}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className={`border-b border-light-200 ${fullHeight ? 'h-full flex flex-col' : ''}`}>
      {/* Header */}
      <div className={`${fullHeight ? 'flex-shrink-0' : ''} p-4 cursor-pointer hover:bg-light-50 transition-colors flex items-center justify-between`}
        onClick={e => onToggle?.(e)}>
        <div>
          <h3 className="text-sm font-semibold text-owl-blue-900">
            Case Documents ({allFiles.length})
          </h3>
          <p className="text-xs text-gray-500 mt-0.5">All evidence and supplementary files for this case</p>
        </div>
        <div className="flex items-center gap-2">
          {onFocus && (
            <button onClick={e => { e.stopPropagation(); onFocus(e); }}
              className="p-1 hover:bg-light-100 rounded" title="Focus on this section">
              <Focus className="w-4 h-4 text-owl-blue-600" />
            </button>
          )}
          {isCollapsed ? <ChevronRight className="w-4 h-4 text-light-600" /> : <ChevronDown className="w-4 h-4 text-light-600" />}
        </div>
      </div>

      {!isCollapsed && (
        <div className={`px-4 pb-4 ${fullHeight ? 'flex flex-col flex-1 min-h-0' : ''}`}>
          {loading ? (
            <p className="text-xs text-light-500">Loading documents...</p>
          ) : error ? (
            <div className="text-xs space-y-2">
              <p className="text-red-600 font-medium">Error loading documents:</p>
              <p className="text-red-500">{error}</p>
            </div>
          ) : (
            <>
              {/* Tabs */}
              <div className={`mb-3 flex items-center gap-1 bg-light-100 rounded-lg p-1 ${fullHeight ? 'flex-shrink-0' : ''}`}>
                {TABS.map(tab => {
                  const TabIcon = tab.icon;
                  const count = tabCounts[tab.key];
                  const isActive = activeTab === tab.key;
                  return (
                    <button key={tab.key} onClick={() => { setActiveTab(tab.key); setStatusFilter('all'); }}
                      className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md transition-colors font-medium ${
                        isActive ? 'bg-owl-blue-500 text-white shadow-sm' : 'text-light-700 hover:bg-light-200'
                      }`}>
                      <TabIcon className="w-3.5 h-3.5" />
                      {tab.label}
                      <span className={`ml-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-semibold ${
                        isActive ? 'bg-white/20 text-white' : 'bg-light-200 text-light-600'
                      }`}>{count}</span>
                    </button>
                  );
                })}
              </div>

              {/* Status filter (for evidence tab or all tab) */}
              {(activeTab === 'evidence' || activeTab === 'all') && (
                <div className={`mb-3 flex items-center gap-2 ${fullHeight ? 'flex-shrink-0' : ''}`}>
                  <Filter className="w-3.5 h-3.5 text-light-500" />
                  <div className="flex gap-1">
                    {[
                      { key: 'all', label: `All`, color: 'bg-owl-blue-500' },
                      { key: 'processed', label: `Processed (${processedCount})`, color: 'bg-green-500' },
                      { key: 'unprocessed', label: `Unprocessed (${unprocessedCount})`, color: 'bg-orange-500' },
                    ].map(sf => (
                      <button key={sf.key} onClick={() => setStatusFilter(sf.key)}
                        className={`px-2 py-0.5 text-[11px] rounded transition-colors ${
                          statusFilter === sf.key ? `${sf.color} text-white` : 'text-light-600 hover:bg-light-200'
                        }`}>{sf.label}</button>
                    ))}
                  </div>
                </div>
              )}

              {/* File list */}
              {displayFiles.length === 0 ? (
                <p className="text-xs text-light-500 italic">
                  {activeTab === 'uploaded' ? 'No supplementary documents. Upload photos, notes, or links via Quick Actions.'
                    : activeTab === 'evidence' ? 'No evidence files found for this case.'
                    : 'No documents found for this case.'}
                </p>
              ) : (
                <div className={`space-y-2 overflow-y-auto ${fullHeight ? 'flex-1 min-h-0' : 'max-h-[500px]'}`}>
                  {displayFiles.map(renderFileRow)}
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
          itemType={isCaseDocument(attachModal.file) ? 'document' : 'evidence'}
          itemId={attachModal.file.id}
          itemName={attachModal.file.original_filename || attachModal.file.filename || 'File'}
          onAttach={handleAttachToTheory}
        />
      )}
    </div>
  );
}
