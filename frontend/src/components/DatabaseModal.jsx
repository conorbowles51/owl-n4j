import React, { useState, useEffect, useCallback } from 'react';
import {
  Database,
  X,
  RefreshCw,
  Search,
  FileText,
  ChevronDown,
  ChevronUp,
  User,
  Upload,
  CheckCircle,
  AlertCircle,
  Eye,
  EyeOff,
} from 'lucide-react';
import { databaseAPI, backfillAPI } from '../services/api';

export default function DatabaseModal({ isOpen, onClose, currentUser }) {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedDocs, setExpandedDocs] = useState(new Set());
  const [showBackfill, setShowBackfill] = useState(false);
  const [backfilling, setBackfilling] = useState(false);
  const [backfillResult, setBackfillResult] = useState(null);
  const [retrievalHistory, setRetrievalHistory] = useState({}); // doc_id -> history array
  const [selectedDocs, setSelectedDocs] = useState(new Set()); // Selected document IDs for backfill
  const [viewMode, setViewMode] = useState('status'); // 'status' or 'vector' - status shows all docs, vector shows only backfilled

  const loadDocuments = useCallback(async () => {
    setLoading(true);
    try {
      if (viewMode === 'status') {
        // Load document status (all documents with backfill status)
        const result = await databaseAPI.listDocumentsStatus();
        setDocuments(result.documents || []);
      } else {
        // Load only documents in vector DB
        const result = await databaseAPI.listDocuments();
        setDocuments(result.documents || []);
      }
    } catch (err) {
      console.error('Failed to load documents:', err);
    } finally {
      setLoading(false);
    }
  }, [viewMode]);

  const loadRetrievalHistory = useCallback(async (docId) => {
    try {
      const result = await databaseAPI.getRetrievalHistory(docId);
      setRetrievalHistory(prev => ({ ...prev, [docId]: result.history || [] }));
    } catch (err) {
      console.error('Failed to load retrieval history:', err);
      setRetrievalHistory(prev => ({ ...prev, [docId]: [] }));
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      loadDocuments();
    }
  }, [isOpen, loadDocuments, viewMode]);

  const toggleExpand = (docId) => {
    setExpandedDocs(prev => {
      const next = new Set(prev);
      if (next.has(docId)) {
        next.delete(docId);
      } else {
        next.add(docId);
        // Load retrieval history when expanding
        if (!retrievalHistory[docId]) {
          loadRetrievalHistory(docId);
        }
      }
      return next;
    });
  };

  const toggleSelectDoc = (docId) => {
    setSelectedDocs(prev => {
      const next = new Set(prev);
      if (next.has(docId)) {
        next.delete(docId);
      } else {
        next.add(docId);
      }
      return next;
    });
  };

  const selectAllNotBackfilled = () => {
    const notBackfilled = documents
      .filter(doc => !doc.has_embedding)
      .map(doc => doc.id);
    setSelectedDocs(new Set(notBackfilled));
  };

  const clearSelection = () => {
    setSelectedDocs(new Set());
  };

  const filteredDocuments = documents.filter(doc => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    const docName = viewMode === 'status' ? doc.name : (doc.metadata?.filename || '');
    return (
      docName.toLowerCase().includes(query) ||
      (viewMode === 'vector' && doc.text?.toLowerCase().includes(query)) ||
      doc.id?.toLowerCase().includes(query)
    );
  });

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-5xl h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-light-200">
          <div className="flex items-center gap-3">
            <Database className="w-5 h-5 text-blue-600" />
            <h2 className="text-xl font-semibold text-light-900">Vector Database</h2>
            {viewMode === 'status' && documents.length > 0 && (
              <span className="text-sm text-light-600">
                ({documents.filter(d => d.has_embedding).length} backfilled, {documents.filter(d => !d.has_embedding).length} not backfilled)
              </span>
            )}
            {viewMode === 'vector' && (
              <span className="text-sm text-light-600">
                ({documents.length} documents)
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {/* View Mode Toggle */}
            <div className="flex items-center gap-1 border border-light-300 rounded-lg p-1">
              <button
                onClick={() => setViewMode('status')}
                className={`px-2 py-1 text-xs rounded transition-colors ${
                  viewMode === 'status'
                    ? 'bg-blue-500 text-white'
                    : 'text-light-600 hover:bg-light-100'
                }`}
                title="Document Status View"
              >
                Status
              </button>
              <button
                onClick={() => setViewMode('vector')}
                className={`px-2 py-1 text-xs rounded transition-colors ${
                  viewMode === 'vector'
                    ? 'bg-blue-500 text-white'
                    : 'text-light-600 hover:bg-light-100'
                }`}
                title="Vector DB View"
              >
                Vector DB
              </button>
            </div>
            <button
              onClick={() => setShowBackfill(!showBackfill)}
              className="px-3 py-1.5 text-sm bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors flex items-center gap-2"
            >
              <Upload className="w-4 h-4" />
              Backfill Documents
            </button>
            <button
              onClick={loadDocuments}
              disabled={loading}
              className="p-2 hover:bg-light-100 rounded transition-colors disabled:opacity-50"
              title="Refresh"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={onClose}
              className="p-2 hover:bg-light-100 rounded transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Backfill Section */}
        {showBackfill && (
          <div className="p-4 border-b border-light-200 bg-light-50">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <label className="block text-sm font-medium text-light-700 mb-1">
                    Select Documents to Backfill
                  </label>
                  <p className="text-xs text-light-500">
                    {selectedDocs.size} document{selectedDocs.size !== 1 ? 's' : ''} selected
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={selectAllNotBackfilled}
                    className="px-3 py-1.5 text-xs border border-light-300 rounded hover:bg-light-100 transition-colors"
                  >
                    Select All Not Backfilled
                  </button>
                  <button
                    onClick={clearSelection}
                    className="px-3 py-1.5 text-xs border border-light-300 rounded hover:bg-light-100 transition-colors"
                  >
                    Clear Selection
                  </button>
                </div>
              </div>
              {backfillResult && (
                <div className={`p-2 rounded text-sm ${
                  backfillResult.status === 'complete'
                    ? 'bg-green-50 text-green-700'
                    : 'bg-red-50 text-red-700'
                }`}>
                  {backfillResult.message}
                </div>
              )}
              <div className="flex gap-2">
                <button
                  onClick={async () => {
                    if (selectedDocs.size === 0) {
                      alert('Please select at least one document to backfill');
                      return;
                    }
                    setBackfilling(true);
                    setBackfillResult(null);
                    try {
                      const result = await backfillAPI.backfill({
                        document_ids: Array.from(selectedDocs),
                        skip_existing: true,
                        dry_run: false,
                      });
                      setBackfillResult({
                        status: result.status,
                        message: result.message || 'Backfill completed successfully',
                      });
                      // Clear selection and reload documents after backfill
                      setSelectedDocs(new Set());
                      await loadDocuments();
                    } catch (err) {
                      setBackfillResult({
                        status: 'error',
                        message: err.message || 'Backfill failed',
                      });
                    } finally {
                      setBackfilling(false);
                    }
                  }}
                  disabled={backfilling || selectedDocs.size === 0}
                  className="px-4 py-2 text-sm bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {backfilling ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      Processing...
                    </>
                  ) : (
                    <>
                      <Upload className="w-4 h-4" />
                      Backfill Selected ({selectedDocs.size})
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Search */}
        <div className="p-4 border-b border-light-200">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-light-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search documents..."
              className="w-full pl-10 pr-3 py-2 text-sm border border-light-300 rounded focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>

        {/* Documents List */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading && documents.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
            </div>
          ) : filteredDocuments.length === 0 ? (
            <div className="flex items-center justify-center h-full text-light-600">
              {searchQuery ? 'No documents match your search' : 'No documents found'}
            </div>
          ) : (
            <div className="space-y-3">
              {filteredDocuments.map((doc) => {
                const isExpanded = expandedDocs.has(doc.id);
                const history = retrievalHistory[doc.id] || [];
                const isSelected = selectedDocs.has(doc.id);
                const docName = viewMode === 'status' ? doc.name : (doc.metadata?.filename || doc.id);
                const hasEmbedding = viewMode === 'status' ? doc.has_embedding : true; // In vector view, all docs are backfilled
                
                return (
                  <div
                    key={doc.id}
                    className={`border rounded-lg p-4 hover:bg-light-50 transition-colors ${
                      isSelected ? 'border-blue-500 bg-blue-50' : 'border-light-200'
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      {viewMode === 'status' && (
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleSelectDoc(doc.id)}
                          disabled={hasEmbedding}
                          className="mt-1 w-4 h-4 text-blue-600 border-light-300 rounded focus:ring-blue-500"
                        />
                      )}
                      <FileText className="w-5 h-5 text-blue-600 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-2 flex-wrap">
                          <span className="font-medium text-light-900">
                            {docName}
                          </span>
                          {viewMode === 'status' && (
                            <>
                              {hasEmbedding ? (
                                <span className="text-xs text-green-700 bg-green-100 px-2 py-0.5 rounded font-medium">
                                  ✓ Backfilled
                                </span>
                              ) : (
                                <span className="text-xs text-orange-700 bg-orange-100 px-2 py-0.5 rounded font-medium">
                                  ⚠ Not Backfilled
                                </span>
                              )}
                            </>
                          )}
                          {(viewMode === 'status' ? doc.owner : doc.metadata?.owner) && (
                            <span className="text-xs text-light-600 bg-light-100 px-2 py-0.5 rounded">
                              {viewMode === 'status' ? doc.owner : doc.metadata.owner}
                            </span>
                          )}
                          {history.length > 0 && (
                            <span className="text-xs text-blue-600 bg-blue-50 px-2 py-0.5 rounded">
                              {history.length} retrieval{history.length > 1 ? 's' : ''}
                            </span>
                          )}
                        </div>
                        {viewMode === 'vector' && (
                          <div className="text-sm text-light-600 mb-2">
                            <div className="line-clamp-2">
                              {doc.text?.substring(0, 200)}...
                            </div>
                          </div>
                        )}
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => toggleExpand(doc.id)}
                            className="text-xs text-blue-600 hover:text-blue-700 flex items-center gap-1"
                          >
                            {isExpanded ? (
                              <>
                                <ChevronUp className="w-3 h-3" />
                                Hide Details
                              </>
                            ) : (
                              <>
                                <ChevronDown className="w-3 h-3" />
                                Show Details
                              </>
                            )}
                          </button>
                        </div>
                        {isExpanded && (
                          <div className="mt-3 space-y-3 pt-3 border-t border-light-200">
                            {/* Status Info (for status view) */}
                            {viewMode === 'status' && (
                              <div>
                                <h4 className="text-xs font-semibold text-light-700 mb-1">Document Info</h4>
                                <div className="p-3 bg-light-100 rounded text-xs space-y-1">
                                  <div><strong>ID:</strong> {doc.id}</div>
                                  <div><strong>Key:</strong> {doc.key}</div>
                                  {doc.vector_db_id && (
                                    <div><strong>Vector DB ID:</strong> {doc.vector_db_id}</div>
                                  )}
                                  {doc.case_id && (
                                    <div><strong>Case ID:</strong> {doc.case_id}</div>
                                  )}
                                  {doc.file_path && (
                                    <div><strong>File Path:</strong> {doc.file_path}</div>
                                  )}
                                </div>
                              </div>
                            )}
                            {/* Full Text (for vector view or if available) */}
                            {(viewMode === 'vector' || (viewMode === 'status' && doc.has_embedding)) && (
                              <div>
                                <h4 className="text-xs font-semibold text-light-700 mb-1">Full Text</h4>
                                <pre className="p-3 bg-light-100 rounded text-xs overflow-x-auto max-h-60 overflow-y-auto">
                                  {viewMode === 'vector' ? (doc.text || 'No text content') : 'Text available in vector DB'}
                                </pre>
                              </div>
                            )}
                            {/* Metadata */}
                            {viewMode === 'vector' && doc.metadata && Object.keys(doc.metadata).length > 0 && (
                              <div>
                                <h4 className="text-xs font-semibold text-light-700 mb-1">Metadata</h4>
                                <pre className="p-3 bg-light-100 rounded text-xs overflow-x-auto">
                                  {JSON.stringify(doc.metadata, null, 2)}
                                </pre>
                              </div>
                            )}
                            {/* Retrieval History */}
                            {doc.has_embedding && (
                              <div>
                                <h4 className="text-xs font-semibold text-light-700 mb-1">
                                  Retrieval History ({history.length})
                                </h4>
                                {history.length > 0 ? (
                                  <div className="space-y-2">
                                    {history.map((entry, idx) => (
                                      <div key={idx} className="p-2 bg-light-100 rounded text-xs">
                                        <div className="flex items-center gap-2 mb-1">
                                          <span className="font-medium">{entry.query || 'Unknown query'}</span>
                                          <span className="text-light-500">
                                            {new Date(entry.timestamp).toLocaleString()}
                                          </span>
                                        </div>
                                        {entry.distance !== undefined && (
                                          <div className="text-light-600">
                                            Distance: {entry.distance.toFixed(4)}
                                          </div>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                ) : (
                                  <p className="text-xs text-light-500">No retrieval history</p>
                                )}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

