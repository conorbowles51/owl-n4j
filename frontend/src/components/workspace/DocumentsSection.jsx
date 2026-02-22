import React, { useState, useEffect } from 'react';
import { ChevronDown, ChevronRight, FileText, Focus, Link2, Image as ImageIcon, ExternalLink, ChevronUp } from 'lucide-react';
import { evidenceAPI, workspaceAPI } from '../../services/api';
import AttachToTheoryModal from './AttachToTheoryModal';
import FilePreview from '../FilePreview';

/**
 * Documents Section
 * 
 * Displays supplementary documents uploaded via Quick Actions (photos, notes, links)
 * Excludes evidence files - only shows Quick Action uploads
 */
export default function DocumentsSection({
  caseId,
  isCollapsed,
  onToggle,
  onFocus,
}) {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [attachModal, setAttachModal] = useState({ open: false, doc: null });
  const [expandedDocId, setExpandedDocId] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [fileContents, setFileContents] = useState({});

  const loadDocuments = async () => {
    if (!caseId) return;
    
    setLoading(true);
    try {
      // Get evidence files for the case
      const evidence = await evidenceAPI.list(caseId);
      const allFiles = evidence?.files || (Array.isArray(evidence) ? evidence : []);
      
      // Filter to only show Quick Action uploads (supplementary documents):
      // - Files starting with "note_" (text notes from Quick Actions)
      // - Files starting with "link_" or ending with "_link.txt" (links from Quick Actions)
      // - Image files (uploaded via Add Photo in Quick Actions)
      // - Other document files that are likely supplementary (PDFs, DOCs, etc. uploaded via Quick Actions)
      // Exclude evidence files which are typically bulk-uploaded case files
      const quickActionFiles = allFiles.filter((file) => {
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
      });
      
      setDocuments(quickActionFiles);
    } catch (err) {
      console.error('Failed to load documents:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // Load documents even when collapsed to show count
    loadDocuments();
  }, [caseId, refreshKey]);

  // Expose refresh function via window event or prop
  useEffect(() => {
    const handleRefresh = () => {
      setRefreshKey(prev => prev + 1);
    };
    
    window.addEventListener('documents-refresh', handleRefresh);
    return () => window.removeEventListener('documents-refresh', handleRefresh);
  }, []);

  // Load file contents when documents are expanded
  useEffect(() => {
    if (expandedDocId) {
      const doc = documents.find(d => d.id === expandedDocId);
      if (doc) {
        const filename = (doc.original_filename || doc.filename || '').toLowerCase();
        if ((isLinkFile(filename) || filename.startsWith('note_')) && !fileContents[doc.id]) {
          loadFileContent(doc);
        }
      }
    }
  }, [expandedDocId, documents]);

  const handleAttachToTheory = async (theory, itemType, itemId) => {
    if (!caseId || !theory) return;
    try {
      const existing = theory.attached_document_ids || [];
      const ids = existing.includes(itemId) ? existing : [...existing, itemId];
      await workspaceAPI.updateTheory(caseId, theory.theory_id, {
        ...theory,
        attached_document_ids: ids,
      });
    } catch (err) {
      console.error('Failed to attach document to theory:', err);
      throw err;
    }
  };

  const isImageFile = (filename) => {
    const imageExtensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'];
    const lower = filename.toLowerCase();
    return imageExtensions.some(ext => lower.endsWith(ext));
  };

  const isLinkFile = (filename) => {
    const lower = filename.toLowerCase();
    return lower.startsWith('link_') || lower.endsWith('_link.txt');
  };

  const getFileIcon = (filename) => {
    if (isImageFile(filename)) {
      return ImageIcon;
    }
    if (isLinkFile(filename)) {
      return ExternalLink;
    }
    return FileText;
  };

  const loadFileContent = async (doc) => {
    if (fileContents[doc.id]) return fileContents[doc.id];
    
    try {
      // For link files and text notes, fetch the content
      const filename = (doc.original_filename || doc.filename || '').toLowerCase();
      if (isLinkFile(filename) || filename.startsWith('note_')) {
        const response = await fetch(`/api/evidence/${doc.id}/file`);
        if (response.ok) {
          const text = await response.text();
          setFileContents(prev => ({ ...prev, [doc.id]: text }));
          return text;
        }
      }
    } catch (err) {
      console.error('Failed to load file content:', err);
    }
    return null;
  };

  const parseLinkContent = (content) => {
    if (!content) return { title: '', url: '', description: '', added: '' };
    
    // Parse link file content to extract URL, title, description
    const lines = content.split('\n');
    const linkData = {
      title: '',
      url: '',
      description: '',
      added: '',
    };
    
    lines.forEach(line => {
      if (line.startsWith('Title:')) {
        linkData.title = line.replace('Title:', '').trim();
      } else if (line.startsWith('URL:')) {
        linkData.url = line.replace('URL:', '').trim();
      } else if (line.startsWith('Description:')) {
        linkData.description = line.replace('Description:', '').trim();
      } else if (line.startsWith('Added:')) {
        linkData.added = line.replace('Added:', '').trim();
      }
    });
    
    return linkData;
  };

  return (
    <div className="border-b border-light-200">
      <div
        className="p-4 cursor-pointer hover:bg-light-50 transition-colors flex items-center justify-between"
        onClick={(e) => onToggle && onToggle(e)}
      >
        <div>
          <h3 className="text-sm font-semibold text-owl-blue-900">
            Uploaded Documents ({documents.length})
          </h3>
          <p className="text-xs text-gray-500 mt-0.5">Files you have added to this case and processed for analysis</p>
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
        <div className="px-4 pb-4">
          {loading ? (
            <p className="text-xs text-light-500">Loading documents...</p>
          ) : documents.length === 0 ? (
            <p className="text-xs text-light-500 italic">No supplementary documents. Upload photos, notes, or links via Quick Actions.</p>
          ) : (
            <div className="space-y-2">
              {documents.map((doc) => {
                const isExpanded = expandedDocId === doc.id;
                const filename = doc.original_filename || doc.filename || '';
                const Icon = getFileIcon(filename);
                const isLink = isLinkFile(filename);
                const isNote = filename.startsWith('note_');
                const fileContent = fileContents[doc.id];
                
                return (
                  <div
                    key={doc.id}
                    className="border border-light-200 rounded-lg bg-light-50 hover:bg-light-100 transition-colors"
                  >
                    <div className="p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-start gap-2 flex-1 min-w-0">
                          <Icon className="w-4 h-4 text-owl-blue-600 mt-0.5 flex-shrink-0" />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-owl-blue-900 truncate">
                              {doc.original_filename || doc.filename || `Document ${doc.id}`}
                            </p>
                            {doc.summary && (
                              <p className="text-xs text-light-600 mt-1 line-clamp-2">
                                {doc.summary}
                              </p>
                            )}
                            {isLink && fileContent && (
                              <div className="mt-1 text-xs text-light-600">
                                {(() => {
                                  try {
                                    const linkData = parseLinkContent(fileContent);
                                    return linkData.url ? (
                                      <a
                                        href={linkData.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-owl-blue-600 hover:underline truncate block"
                                        onClick={(e) => e.stopPropagation()}
                                      >
                                        {linkData.url}
                                      </a>
                                    ) : null;
                                  } catch {
                                    return null;
                                  }
                                })()}
                              </div>
                            )}
                            {isNote && fileContent && (
                              <div className="mt-1 text-xs text-light-600 line-clamp-2">
                                {fileContent.substring(0, 100)}
                                {fileContent.length > 100 ? '...' : ''}
                              </div>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-1 flex-shrink-0">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setExpandedDocId(isExpanded ? null : doc.id);
                            }}
                            className="p-1.5 hover:bg-light-200 rounded transition-colors text-light-600"
                            title={isExpanded ? 'Collapse' : 'Expand preview'}
                          >
                            {isExpanded ? (
                              <ChevronUp className="w-4 h-4" />
                            ) : (
                              <ChevronDown className="w-4 h-4" />
                            )}
                          </button>
                          {isLink && fileContent && (() => {
                            try {
                              const linkData = parseLinkContent(fileContent);
                              return linkData.url ? (
                                <a
                                  href={linkData.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="p-1.5 hover:bg-owl-blue-100 rounded transition-colors text-owl-blue-600"
                                  title="Open link"
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  <ExternalLink className="w-4 h-4" />
                                </a>
                              ) : null;
                            } catch {
                              return null;
                            }
                          })()}
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setAttachModal({ open: true, doc });
                            }}
                            className="p-1.5 hover:bg-owl-blue-100 rounded transition-colors"
                            title="Attach to theory"
                          >
                            <Link2 className="w-4 h-4 text-owl-blue-600" />
                          </button>
                        </div>
                      </div>
                    </div>

                    {/* Expanded Preview */}
                    {isExpanded && (
                      <div className="px-3 pb-3 border-t border-light-200 pt-3">
                        {isLink ? (
                          // Link Preview
                          !fileContent ? (
                            <p className="text-xs text-light-500">Loading link details...</p>
                          ) : (
                            (() => {
                              try {
                                const linkData = parseLinkContent(fileContent);
                                return (
                                  <div className="space-y-2">
                                    {linkData.title && (
                                      <h5 className="text-sm font-semibold text-owl-blue-900">
                                        {linkData.title}
                                      </h5>
                                    )}
                                    {linkData.url && (
                                      <div>
                                        <p className="text-xs text-light-600 mb-1">URL:</p>
                                        <a
                                          href={linkData.url}
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          className="text-sm text-owl-blue-600 hover:underline break-all"
                                        >
                                          {linkData.url}
                                        </a>
                                      </div>
                                    )}
                                    {linkData.description && (
                                      <div>
                                        <p className="text-xs text-light-600 mb-1">Description:</p>
                                        <p className="text-sm text-light-700">{linkData.description}</p>
                                      </div>
                                    )}
                                    {linkData.added && (
                                      <p className="text-xs text-light-500">
                                        Added: {new Date(linkData.added).toLocaleString()}
                                      </p>
                                    )}
                                  </div>
                                );
                              } catch (err) {
                                return (
                                  <div className="text-xs text-light-600 whitespace-pre-wrap">
                                    {fileContent}
                                  </div>
                                );
                              }
                            })()
                          )
                        ) : isNote ? (
                          // Note Preview
                          !fileContent ? (
                            <p className="text-xs text-light-500">Loading note content...</p>
                          ) : (
                            <div className="text-sm text-light-700 whitespace-pre-wrap">
                              {fileContent}
                            </div>
                          )
                        ) : (
                          // Image/Document Preview
                          <FilePreview
                            caseId={caseId}
                            filePath={doc.stored_path || ''}
                            fileName={doc.original_filename || doc.filename}
                            fileType="file"
                            onClose={() => setExpandedDocId(null)}
                          />
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {attachModal.open && attachModal.doc && (
        <AttachToTheoryModal
          isOpen={attachModal.open}
          onClose={() => setAttachModal({ open: false, doc: null })}
          caseId={caseId}
          itemType="document"
          itemId={attachModal.doc.id}
          itemName={attachModal.doc.filename || attachModal.doc.name || attachModal.doc.original_filename || 'Document'}
          onAttach={handleAttachToTheory}
        />
      )}
    </div>
  );
}
