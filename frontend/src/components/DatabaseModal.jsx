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
  Users,
  BarChart3,
  Layers,
  Tag,
  Sparkles,
  Link,
} from 'lucide-react';
import { databaseAPI, backfillAPI } from '../services/api';

export default function DatabaseModal({ isOpen, onClose, currentUser }) {
  const [documents, setDocuments] = useState([]);
  const [entities, setEntities] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedDocs, setExpandedDocs] = useState(new Set());
  const [expandedEntities, setExpandedEntities] = useState(new Set());
  const [showBackfill, setShowBackfill] = useState(false);
  const [backfilling, setBackfilling] = useState(false);
  const [backfillResult, setBackfillResult] = useState(null);
  const [retrievalHistory, setRetrievalHistory] = useState({}); // doc_id -> history array
  const [selectedDocs, setSelectedDocs] = useState(new Set()); // Selected document IDs for backfill
  const [viewMode, setViewMode] = useState('status'); // 'status' or 'vector' - status shows all docs, vector shows only backfilled
  const [dataType, setDataType] = useState('documents'); // 'documents' or 'entities'
  const [showGapAnalysis, setShowGapAnalysis] = useState(false);
  const [gapAnalysis, setGapAnalysis] = useState(null);
  const [gapLoading, setGapLoading] = useState(false);
  const [chunkBackfilling, setChunkBackfilling] = useState(false);
  const [chunkBackfillResult, setChunkBackfillResult] = useState(null);
  const [entityMetaBackfilling, setEntityMetaBackfilling] = useState(false);
  const [entityMetaBackfillResult, setEntityMetaBackfillResult] = useState(null);
  const [summaryBackfilling, setSummaryBackfilling] = useState(false);
  const [summaryBackfillResult, setSummaryBackfillResult] = useState(null);
  const [caseIdBackfilling, setCaseIdBackfilling] = useState(false);
  const [caseIdBackfillResult, setCaseIdBackfillResult] = useState(null);

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

  const loadEntities = useCallback(async () => {
    setLoading(true);
    try {
      if (viewMode === 'status') {
        // Load entity status (all entities with embedding status)
        const result = await databaseAPI.listEntitiesStatus();
        setEntities(result.entities || []);
      } else {
        // Load only entities in vector DB
        const result = await databaseAPI.listEntities();
        setEntities(result.entities || []);
      }
    } catch (err) {
      console.error('Failed to load entities:', err);
    } finally {
      setLoading(false);
    }
  }, [viewMode]);

  const loadData = useCallback(async () => {
    if (dataType === 'documents') {
      await loadDocuments();
    } else {
      await loadEntities();
    }
  }, [dataType, loadDocuments, loadEntities]);

  const loadRetrievalHistory = useCallback(async (docId) => {
    try {
      const result = await databaseAPI.getRetrievalHistory(docId);
      setRetrievalHistory(prev => ({ ...prev, [docId]: result.history || [] }));
    } catch (err) {
      console.error('Failed to load retrieval history:', err);
      setRetrievalHistory(prev => ({ ...prev, [docId]: [] }));
    }
  }, []);

  const loadGapAnalysis = useCallback(async () => {
    setGapLoading(true);
    try {
      const result = await backfillAPI.getStatus();
      setGapAnalysis(result);
    } catch (err) {
      console.error('Failed to load gap analysis:', err);
      setGapAnalysis(null);
    } finally {
      setGapLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      loadData();
    }
  }, [isOpen, loadData, viewMode, dataType]);

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

  const toggleExpandEntity = (entityKey) => {
    setExpandedEntities(prev => {
      const next = new Set(prev);
      if (next.has(entityKey)) {
        next.delete(entityKey);
      } else {
        next.add(entityKey);
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

  const filteredEntities = entities.filter(ent => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    const entName = viewMode === 'status' ? ent.name : (ent.metadata?.name || '');
    const entKey = viewMode === 'status' ? ent.key : ent.id;
    const entType = viewMode === 'status' ? ent.entity_type : (ent.metadata?.entity_type || '');
    return (
      entName.toLowerCase().includes(query) ||
      entKey?.toLowerCase().includes(query) ||
      entType?.toLowerCase().includes(query) ||
      (viewMode === 'vector' && ent.text?.toLowerCase().includes(query))
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
            {dataType === 'documents' && viewMode === 'status' && documents.length > 0 && (
              <span className="text-sm text-light-600">
                ({documents.filter(d => d.has_embedding).length} backfilled, {documents.filter(d => !d.has_embedding).length} not backfilled)
              </span>
            )}
            {dataType === 'documents' && viewMode === 'vector' && (
              <span className="text-sm text-light-600">
                ({documents.length} documents)
              </span>
            )}
            {dataType === 'entities' && viewMode === 'status' && entities.length > 0 && (
              <span className="text-sm text-light-600">
                ({entities.filter(e => e.has_embedding).length} embedded, {entities.filter(e => !e.has_embedding).length} not embedded)
              </span>
            )}
            {dataType === 'entities' && viewMode === 'vector' && (
              <span className="text-sm text-light-600">
                ({entities.length} entities)
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {/* Data Type Toggle */}
            <div className="flex items-center gap-1 border border-light-300 rounded-lg p-1">
              <button
                onClick={() => setDataType('documents')}
                className={`px-2 py-1 text-xs rounded transition-colors flex items-center gap-1 ${
                  dataType === 'documents'
                    ? 'bg-blue-500 text-white'
                    : 'text-light-600 hover:bg-light-100'
                }`}
                title="Documents"
              >
                <FileText className="w-3 h-3" />
                Documents
              </button>
              <button
                onClick={() => setDataType('entities')}
                className={`px-2 py-1 text-xs rounded transition-colors flex items-center gap-1 ${
                  dataType === 'entities'
                    ? 'bg-blue-500 text-white'
                    : 'text-light-600 hover:bg-light-100'
                }`}
                title="Entities"
              >
                <Users className="w-3 h-3" />
                Entities
              </button>
            </div>
            {/* View Mode Toggle */}
            <div className="flex items-center gap-1 border border-light-300 rounded-lg p-1">
              <button
                onClick={() => setViewMode('status')}
                className={`px-2 py-1 text-xs rounded transition-colors ${
                  viewMode === 'status'
                    ? 'bg-blue-500 text-white'
                    : 'text-light-600 hover:bg-light-100'
                }`}
                title="Status View"
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
            {dataType === 'documents' && (
              <button
                onClick={() => setShowBackfill(!showBackfill)}
                className={`px-3 py-1.5 text-sm rounded transition-colors flex items-center gap-2 ${
                  showBackfill ? 'bg-blue-600 text-white' : 'bg-blue-500 text-white hover:bg-blue-600'
                }`}
              >
                <Upload className="w-4 h-4" />
                Backfill Docs
              </button>
            )}
            <button
              onClick={() => {
                setShowGapAnalysis(!showGapAnalysis);
                if (!showGapAnalysis && !gapAnalysis) {
                  loadGapAnalysis();
                }
              }}
              className={`px-3 py-1.5 text-sm rounded transition-colors flex items-center gap-2 ${
                showGapAnalysis ? 'bg-purple-600 text-white' : 'bg-purple-500 text-white hover:bg-purple-600'
              }`}
            >
              <BarChart3 className="w-4 h-4" />
              RAG Pipeline
            </button>
            <button
              onClick={loadData}
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

        {/* Backfill Section (Documents only) */}
        {showBackfill && dataType === 'documents' && (
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
                      await loadData();
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

        {/* RAG Pipeline / Gap Analysis Section */}
        {showGapAnalysis && (
          <div className="p-4 border-b border-light-200 bg-purple-50">
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <BarChart3 className="w-4 h-4 text-purple-600" />
                  <h3 className="text-sm font-semibold text-purple-900">RAG Pipeline Status</h3>
                </div>
                <button
                  onClick={loadGapAnalysis}
                  disabled={gapLoading}
                  className="px-2 py-1 text-xs border border-purple-300 rounded hover:bg-purple-100 transition-colors flex items-center gap-1 disabled:opacity-50"
                >
                  <RefreshCw className={`w-3 h-3 ${gapLoading ? 'animate-spin' : ''}`} />
                  Refresh
                </button>
              </div>

              {gapLoading && !gapAnalysis ? (
                <div className="flex items-center justify-center py-4">
                  <RefreshCw className="w-5 h-5 animate-spin text-purple-500" />
                  <span className="ml-2 text-sm text-purple-600">Loading gap analysis...</span>
                </div>
              ) : gapAnalysis ? (
                <>
                  {/* Stats Grid */}
                  <div className="grid grid-cols-5 gap-3">
                    {/* Chunk Embeddings Card */}
                    <div className="bg-white rounded-lg border border-purple-200 p-3">
                      <div className="flex items-center gap-2 mb-2">
                        <Layers className="w-4 h-4 text-blue-600" />
                        <span className="text-xs font-semibold text-light-700">Chunk Embeddings</span>
                      </div>
                      <div className="space-y-1">
                        <div className="flex justify-between text-xs">
                          <span className="text-light-600">Total documents</span>
                          <span className="font-medium">{gapAnalysis.documents?.total || 0}</span>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-green-600">With chunks</span>
                          <span className="font-medium text-green-700">{gapAnalysis.documents?.with_chunks || 0}</span>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-orange-600">Missing chunks</span>
                          <span className="font-medium text-orange-700">{gapAnalysis.documents?.missing_chunks || 0}</span>
                        </div>
                        <div className="flex justify-between text-xs border-t border-light-200 pt-1 mt-1">
                          <span className="text-light-600">Total chunks</span>
                          <span className="font-medium">{gapAnalysis.chunks?.total || 0}</span>
                        </div>
                      </div>
                      {/* Progress bar */}
                      {gapAnalysis.documents?.total > 0 && (
                        <div className="mt-2">
                          <div className="w-full bg-light-200 rounded-full h-1.5">
                            <div
                              className="bg-blue-500 h-1.5 rounded-full transition-all"
                              style={{ width: `${Math.round((gapAnalysis.documents.with_chunks / gapAnalysis.documents.total) * 100)}%` }}
                            />
                          </div>
                          <div className="text-[10px] text-light-500 mt-0.5 text-right">
                            {Math.round((gapAnalysis.documents.with_chunks / gapAnalysis.documents.total) * 100)}%
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Entity Embeddings Card */}
                    <div className="bg-white rounded-lg border border-purple-200 p-3">
                      <div className="flex items-center gap-2 mb-2">
                        <Users className="w-4 h-4 text-purple-600" />
                        <span className="text-xs font-semibold text-light-700">Entity Embeddings</span>
                      </div>
                      <div className="space-y-1">
                        <div className="flex justify-between text-xs">
                          <span className="text-light-600">In Neo4j</span>
                          <span className="font-medium">{gapAnalysis.entities?.total_neo4j || 0}</span>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-green-600">In ChromaDB</span>
                          <span className="font-medium text-green-700">{gapAnalysis.entities?.total_chromadb || 0}</span>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-orange-600">Missing embeddings</span>
                          <span className="font-medium text-orange-700">{gapAnalysis.entities?.missing_embeddings || 0}</span>
                        </div>
                      </div>
                      {gapAnalysis.entities?.total_neo4j > 0 && (
                        <div className="mt-2">
                          <div className="w-full bg-light-200 rounded-full h-1.5">
                            <div
                              className="bg-purple-500 h-1.5 rounded-full transition-all"
                              style={{ width: `${Math.round((gapAnalysis.entities.total_chromadb / gapAnalysis.entities.total_neo4j) * 100)}%` }}
                            />
                          </div>
                          <div className="text-[10px] text-light-500 mt-0.5 text-right">
                            {Math.round((gapAnalysis.entities.total_chromadb / gapAnalysis.entities.total_neo4j) * 100)}%
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Entity Metadata Card */}
                    <div className="bg-white rounded-lg border border-purple-200 p-3">
                      <div className="flex items-center gap-2 mb-2">
                        <Tag className="w-4 h-4 text-amber-600" />
                        <span className="text-xs font-semibold text-light-700">Entity Metadata</span>
                      </div>
                      <div className="space-y-1">
                        <div className="flex justify-between text-xs">
                          <span className="text-light-600">In ChromaDB</span>
                          <span className="font-medium">{gapAnalysis.entities?.total_chromadb || 0}</span>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-green-600">With case_id</span>
                          <span className="font-medium text-green-700">{gapAnalysis.entities?.with_case_id_metadata || 0}</span>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-orange-600">Missing case_id</span>
                          <span className="font-medium text-orange-700">{gapAnalysis.entities?.missing_case_id || 0}</span>
                        </div>
                      </div>
                      {gapAnalysis.entities?.total_chromadb > 0 && (
                        <div className="mt-2">
                          <div className="w-full bg-light-200 rounded-full h-1.5">
                            <div
                              className="bg-amber-500 h-1.5 rounded-full transition-all"
                              style={{ width: `${Math.round((gapAnalysis.entities.with_case_id_metadata / gapAnalysis.entities.total_chromadb) * 100)}%` }}
                            />
                          </div>
                          <div className="text-[10px] text-light-500 mt-0.5 text-right">
                            {Math.round((gapAnalysis.entities.with_case_id_metadata / gapAnalysis.entities.total_chromadb) * 100)}%
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Document Summaries Card */}
                    <div className="bg-white rounded-lg border border-purple-200 p-3">
                      <div className="flex items-center gap-2 mb-2">
                        <Sparkles className="w-4 h-4 text-emerald-600" />
                        <span className="text-xs font-semibold text-light-700">Doc Summaries</span>
                      </div>
                      <div className="space-y-1">
                        <div className="flex justify-between text-xs">
                          <span className="text-light-600">Total documents</span>
                          <span className="font-medium">{gapAnalysis.documents?.total || 0}</span>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-green-600">With summary</span>
                          <span className="font-medium text-green-700">{gapAnalysis.documents?.with_summary || 0}</span>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-orange-600">Missing summary</span>
                          <span className="font-medium text-orange-700">{gapAnalysis.documents?.missing_summary || 0}</span>
                        </div>
                      </div>
                      {gapAnalysis.documents?.total > 0 && (
                        <div className="mt-2">
                          <div className="w-full bg-light-200 rounded-full h-1.5">
                            <div
                              className="bg-emerald-500 h-1.5 rounded-full transition-all"
                              style={{ width: `${Math.round(((gapAnalysis.documents.with_summary || 0) / gapAnalysis.documents.total) * 100)}%` }}
                            />
                          </div>
                          <div className="text-[10px] text-light-500 mt-0.5 text-right">
                            {Math.round(((gapAnalysis.documents.with_summary || 0) / gapAnalysis.documents.total) * 100)}%
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Case IDs Card */}
                    <div className="bg-white rounded-lg border border-purple-200 p-3">
                      <div className="flex items-center gap-2 mb-2">
                        <Link className="w-4 h-4 text-rose-600" />
                        <span className="text-xs font-semibold text-light-700">Case IDs</span>
                      </div>
                      <div className="space-y-1">
                        <div className="flex justify-between text-xs">
                          <span className="text-light-600">Neo4j docs</span>
                          <span className="font-medium">
                            <span className="text-green-700">{gapAnalysis.documents?.with_case_id || 0}</span>
                            {(gapAnalysis.documents?.missing_case_id || 0) > 0 && (
                              <span className="text-orange-700"> / {gapAnalysis.documents?.missing_case_id} missing</span>
                            )}
                          </span>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-light-600">Neo4j entities</span>
                          <span className="font-medium">
                            <span className="text-green-700">{gapAnalysis.entities?.neo4j_with_case_id || 0}</span>
                            {(gapAnalysis.entities?.neo4j_missing_case_id || 0) > 0 && (
                              <span className="text-orange-700"> / {gapAnalysis.entities?.neo4j_missing_case_id} missing</span>
                            )}
                          </span>
                        </div>
                        <div className="flex justify-between text-xs border-t border-light-200 pt-1 mt-1">
                          <span className="text-light-600">Chroma docs</span>
                          <span className="font-medium">
                            <span className="text-green-700">{gapAnalysis.documents?.chromadb_with_case_id || 0}</span>
                            {(gapAnalysis.documents?.chromadb_missing_case_id || 0) > 0 && (
                              <span className="text-orange-700"> / {gapAnalysis.documents?.chromadb_missing_case_id} missing</span>
                            )}
                          </span>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-light-600">Chroma chunks</span>
                          <span className="font-medium">
                            <span className="text-green-700">{gapAnalysis.chunks?.with_case_id || 0}</span>
                            {(gapAnalysis.chunks?.missing_case_id || 0) > 0 && (
                              <span className="text-orange-700"> / {gapAnalysis.chunks?.missing_case_id} missing</span>
                            )}
                          </span>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-light-600">Chroma entities</span>
                          <span className="font-medium">
                            <span className="text-green-700">{gapAnalysis.entities?.with_case_id_metadata || 0}</span>
                            {(gapAnalysis.entities?.missing_case_id || 0) > 0 && (
                              <span className="text-orange-700"> / {gapAnalysis.entities?.missing_case_id} missing</span>
                            )}
                          </span>
                        </div>
                      </div>
                      {(() => {
                        const totalItems = (gapAnalysis.documents?.total || 0) + (gapAnalysis.entities?.total_neo4j || 0) + (gapAnalysis.documents?.chromadb_total || 0) + (gapAnalysis.chunks?.total || 0) + (gapAnalysis.entities?.total_chromadb || 0);
                        const withCaseId = (gapAnalysis.documents?.with_case_id || 0) + (gapAnalysis.entities?.neo4j_with_case_id || 0) + (gapAnalysis.documents?.chromadb_with_case_id || 0) + (gapAnalysis.chunks?.with_case_id || 0) + (gapAnalysis.entities?.with_case_id_metadata || 0);
                        const pct = totalItems > 0 ? Math.round((withCaseId / totalItems) * 100) : 0;
                        return totalItems > 0 ? (
                          <div className="mt-2">
                            <div className="w-full bg-light-200 rounded-full h-1.5">
                              <div
                                className="bg-rose-500 h-1.5 rounded-full transition-all"
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                            <div className="text-[10px] text-light-500 mt-0.5 text-right">
                              {pct}%
                            </div>
                          </div>
                        ) : null;
                      })()}
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div className="flex gap-3">
                    {/* Backfill Chunks Button */}
                    <div className="flex-1">
                      <button
                        onClick={async () => {
                          setChunkBackfilling(true);
                          setChunkBackfillResult(null);
                          try {
                            const result = await backfillAPI.backfillChunks({
                              skip_existing: true,
                              dry_run: false,
                            });
                            setChunkBackfillResult({
                              status: result.status,
                              message: result.message || 'Chunk backfill completed',
                            });
                            await loadGapAnalysis();
                          } catch (err) {
                            setChunkBackfillResult({
                              status: 'error',
                              message: err.message || 'Chunk backfill failed',
                            });
                          } finally {
                            setChunkBackfilling(false);
                          }
                        }}
                        disabled={chunkBackfilling || entityMetaBackfilling || (gapAnalysis.documents?.missing_chunks === 0)}
                        className="w-full px-3 py-2 text-sm bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                      >
                        {chunkBackfilling ? (
                          <>
                            <RefreshCw className="w-4 h-4 animate-spin" />
                            Creating Chunks...
                          </>
                        ) : (
                          <>
                            <Layers className="w-4 h-4" />
                            Backfill Chunk Embeddings
                            {gapAnalysis.documents?.missing_chunks > 0 && (
                              <span className="bg-blue-400 text-white text-xs px-1.5 py-0.5 rounded-full">
                                {gapAnalysis.documents.missing_chunks}
                              </span>
                            )}
                          </>
                        )}
                      </button>
                      {chunkBackfillResult && (
                        <div className={`mt-1 p-2 rounded text-xs ${
                          chunkBackfillResult.status === 'complete'
                            ? 'bg-green-50 text-green-700'
                            : 'bg-red-50 text-red-700'
                        }`}>
                          {chunkBackfillResult.message}
                        </div>
                      )}
                    </div>

                    {/* Backfill Entity Metadata Button */}
                    <div className="flex-1">
                      <button
                        onClick={async () => {
                          setEntityMetaBackfilling(true);
                          setEntityMetaBackfillResult(null);
                          try {
                            const result = await backfillAPI.backfillEntityMetadata({
                              dry_run: false,
                            });
                            setEntityMetaBackfillResult({
                              status: result.status,
                              message: result.message || 'Entity metadata backfill completed',
                            });
                            await loadGapAnalysis();
                          } catch (err) {
                            setEntityMetaBackfillResult({
                              status: 'error',
                              message: err.message || 'Entity metadata backfill failed',
                            });
                          } finally {
                            setEntityMetaBackfilling(false);
                          }
                        }}
                        disabled={entityMetaBackfilling || chunkBackfilling || (gapAnalysis.entities?.missing_case_id === 0)}
                        className="w-full px-3 py-2 text-sm bg-amber-500 text-white rounded hover:bg-amber-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                      >
                        {entityMetaBackfilling ? (
                          <>
                            <RefreshCw className="w-4 h-4 animate-spin" />
                            Updating Metadata...
                          </>
                        ) : (
                          <>
                            <Tag className="w-4 h-4" />
                            Backfill Entity Metadata
                            {gapAnalysis.entities?.missing_case_id > 0 && (
                              <span className="bg-amber-400 text-white text-xs px-1.5 py-0.5 rounded-full">
                                {gapAnalysis.entities.missing_case_id}
                              </span>
                            )}
                          </>
                        )}
                      </button>
                      {entityMetaBackfillResult && (
                        <div className={`mt-1 p-2 rounded text-xs ${
                          entityMetaBackfillResult.status === 'complete'
                            ? 'bg-green-50 text-green-700'
                            : 'bg-red-50 text-red-700'
                        }`}>
                          {entityMetaBackfillResult.message}
                        </div>
                      )}
                    </div>

                    {/* Backfill Document Summaries Button */}
                    <div className="flex-1">
                      <button
                        onClick={async () => {
                          setSummaryBackfilling(true);
                          setSummaryBackfillResult(null);
                          try {
                            const result = await backfillAPI.backfillDocumentSummaries({
                              skip_existing: true,
                              dry_run: false,
                            });
                            setSummaryBackfillResult({
                              status: result.status,
                              message: result.message || 'Document summary backfill completed',
                            });
                            await loadGapAnalysis();
                          } catch (err) {
                            setSummaryBackfillResult({
                              status: 'error',
                              message: err.message || 'Document summary backfill failed',
                            });
                          } finally {
                            setSummaryBackfilling(false);
                          }
                        }}
                        disabled={summaryBackfilling || chunkBackfilling || entityMetaBackfilling || (gapAnalysis.documents?.missing_summary === 0)}
                        className="w-full px-3 py-2 text-sm bg-emerald-500 text-white rounded hover:bg-emerald-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                      >
                        {summaryBackfilling ? (
                          <>
                            <RefreshCw className="w-4 h-4 animate-spin" />
                            Generating Summaries...
                          </>
                        ) : (
                          <>
                            <Sparkles className="w-4 h-4" />
                            Backfill Summaries
                            {gapAnalysis.documents?.missing_summary > 0 && (
                              <span className="bg-emerald-400 text-white text-xs px-1.5 py-0.5 rounded-full">
                                {gapAnalysis.documents.missing_summary}
                              </span>
                            )}
                          </>
                        )}
                      </button>
                      {summaryBackfillResult && (
                        <div className={`mt-1 p-2 rounded text-xs ${
                          summaryBackfillResult.status === 'complete'
                            ? 'bg-green-50 text-green-700'
                            : 'bg-red-50 text-red-700'
                        }`}>
                          {summaryBackfillResult.message}
                        </div>
                      )}
                    </div>

                    {/* Backfill Case IDs Button */}
                    <div className="flex-1">
                      <button
                        onClick={async () => {
                          setCaseIdBackfilling(true);
                          setCaseIdBackfillResult(null);
                          try {
                            const result = await backfillAPI.backfillCaseIds({
                              include_entities: true,
                              dry_run: false,
                            });
                            setCaseIdBackfillResult({
                              status: result.status,
                              message: result.message || 'Case ID backfill completed',
                            });
                            await loadGapAnalysis();
                          } catch (err) {
                            setCaseIdBackfillResult({
                              status: 'error',
                              message: err.message || 'Case ID backfill failed',
                            });
                          } finally {
                            setCaseIdBackfilling(false);
                          }
                        }}
                        disabled={caseIdBackfilling || chunkBackfilling || entityMetaBackfilling || summaryBackfilling || (
                          (gapAnalysis.documents?.missing_case_id === 0) &&
                          (gapAnalysis.entities?.neo4j_missing_case_id === 0) &&
                          (gapAnalysis.documents?.chromadb_missing_case_id === 0) &&
                          (gapAnalysis.chunks?.missing_case_id === 0) &&
                          (gapAnalysis.entities?.missing_case_id === 0)
                        )}
                        className="w-full px-3 py-2 text-sm bg-rose-500 text-white rounded hover:bg-rose-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                      >
                        {caseIdBackfilling ? (
                          <>
                            <RefreshCw className="w-4 h-4 animate-spin" />
                            Assigning Case IDs...
                          </>
                        ) : (
                          <>
                            <Link className="w-4 h-4" />
                            Backfill Case IDs
                            {(() => {
                              const totalMissing = (gapAnalysis.documents?.missing_case_id || 0) +
                                (gapAnalysis.entities?.neo4j_missing_case_id || 0) +
                                (gapAnalysis.documents?.chromadb_missing_case_id || 0) +
                                (gapAnalysis.chunks?.missing_case_id || 0) +
                                (gapAnalysis.entities?.missing_case_id || 0);
                              return totalMissing > 0 ? (
                                <span className="bg-rose-400 text-white text-xs px-1.5 py-0.5 rounded-full">
                                  {totalMissing}
                                </span>
                              ) : null;
                            })()}
                          </>
                        )}
                      </button>
                      {caseIdBackfillResult && (
                        <div className={`mt-1 p-2 rounded text-xs ${
                          caseIdBackfillResult.status === 'complete'
                            ? 'bg-green-50 text-green-700'
                            : 'bg-red-50 text-red-700'
                        }`}>
                          {caseIdBackfillResult.message}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Info text */}
                  <p className="text-[11px] text-purple-600 leading-relaxed">
                    <strong>Chunk embeddings</strong> enable passage-level semantic search (no LLM cost, only embedding cost).
                    <strong> Entity metadata</strong> adds case_id to existing entity vectors for filtered search (zero cost, metadata-only update).
                    <strong> Doc summaries</strong> generate AI summaries for documents (uses LLM — small cost per document).
                    <strong> Case IDs</strong> assigns case_id across Neo4j and ChromaDB (docs, chunks, entities) from evidence records (zero cost, metadata-only).
                  </p>
                </>
              ) : (
                <div className="text-sm text-purple-600 py-2">
                  Failed to load gap analysis. Click Refresh to try again.
                </div>
              )}
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
              placeholder={dataType === 'documents' ? 'Search documents...' : 'Search entities...'}
              className="w-full pl-10 pr-3 py-2 text-sm border border-light-300 rounded focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>

        {/* Documents List */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading && (dataType === 'documents' ? documents.length === 0 : entities.length === 0) ? (
            <div className="flex items-center justify-center h-full">
              <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
            </div>
          ) : dataType === 'documents' && filteredDocuments.length === 0 ? (
            <div className="flex items-center justify-center h-full text-light-600">
              {searchQuery ? 'No documents match your search' : 'No documents found'}
            </div>
          ) : dataType === 'entities' && filteredEntities.length === 0 ? (
            <div className="flex items-center justify-center h-full text-light-600">
              {searchQuery ? 'No entities match your search' : 'No entities found'}
            </div>
          ) : dataType === 'documents' ? (
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
          ) : (
            /* Entities List */
            <div className="space-y-3">
              {filteredEntities.map((ent) => {
                const entityKey = viewMode === 'status' ? ent.key : ent.id;
                const isExpanded = expandedEntities.has(entityKey);
                const entName = viewMode === 'status' ? ent.name : (ent.metadata?.name || entityKey);
                const entType = viewMode === 'status' ? ent.entity_type : (ent.metadata?.entity_type || 'Unknown');
                const hasEmbedding = viewMode === 'status' ? ent.has_embedding : true;
                
                return (
                  <div
                    key={entityKey}
                    className="border rounded-lg p-4 hover:bg-light-50 transition-colors border-light-200"
                  >
                    <div className="flex items-start gap-3">
                      <Users className="w-5 h-5 text-purple-600 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-2 flex-wrap">
                          <span className="font-medium text-light-900">
                            {entName}
                          </span>
                          <span className="text-xs text-purple-700 bg-purple-100 px-2 py-0.5 rounded font-medium">
                            {entType}
                          </span>
                          {viewMode === 'status' && (
                            <>
                              {hasEmbedding ? (
                                <span className="text-xs text-green-700 bg-green-100 px-2 py-0.5 rounded font-medium">
                                  ✓ Embedded
                                </span>
                              ) : (
                                <span className="text-xs text-orange-700 bg-orange-100 px-2 py-0.5 rounded font-medium">
                                  ⚠ Not Embedded
                                </span>
                              )}
                            </>
                          )}
                        </div>
                        {viewMode === 'status' && ent.summary && (
                          <div className="text-sm text-light-600 mb-2 line-clamp-2">
                            {ent.summary}
                          </div>
                        )}
                        {viewMode === 'vector' && ent.text && (
                          <div className="text-sm text-light-600 mb-2 line-clamp-2">
                            {ent.text.substring(0, 200)}...
                          </div>
                        )}
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => toggleExpandEntity(entityKey)}
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
                            {/* Entity Info */}
                            <div>
                              <h4 className="text-xs font-semibold text-light-700 mb-1">Entity Info</h4>
                              <div className="p-3 bg-light-100 rounded text-xs space-y-1">
                                <div><strong>Key:</strong> {entityKey}</div>
                                <div><strong>Type:</strong> {entType}</div>
                                {viewMode === 'status' && ent.summary && (
                                  <div><strong>Summary:</strong> {ent.summary}</div>
                                )}
                              </div>
                            </div>
                            {/* Embedding Text (for vector view) */}
                            {viewMode === 'vector' && ent.text && (
                              <div>
                                <h4 className="text-xs font-semibold text-light-700 mb-1">Embedding Text</h4>
                                <pre className="p-3 bg-light-100 rounded text-xs overflow-x-auto max-h-60 overflow-y-auto whitespace-pre-wrap">
                                  {ent.text}
                                </pre>
                              </div>
                            )}
                            {/* Metadata */}
                            {viewMode === 'vector' && ent.metadata && Object.keys(ent.metadata).length > 0 && (
                              <div>
                                <h4 className="text-xs font-semibold text-light-700 mb-1">Metadata</h4>
                                <pre className="p-3 bg-light-100 rounded text-xs overflow-x-auto">
                                  {JSON.stringify(ent.metadata, null, 2)}
                                </pre>
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

