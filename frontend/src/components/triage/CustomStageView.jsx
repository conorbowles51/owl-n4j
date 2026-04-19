import React, { useState, useEffect, useCallback } from 'react';
import {
  Play, Loader2, CheckCircle2, AlertCircle, Plus,
  Settings, FileText, Filter, ChevronDown, ChevronRight,
  Cpu, Eye, Layers,
} from 'lucide-react';
import { triageAPI } from '../../services/api';

// ── Helpers ─────────────────────────────────────────────────────────

function formatSize(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  let size = bytes;
  while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
  return `${size.toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
}

// ── Stage Builder Modal ─────────────────────────────────────────────

function StageBuilderModal({ caseId, onCreated, onClose }) {
  const [processors, setProcessors] = useState([]);
  const [selectedProcessor, setSelectedProcessor] = useState(null);
  const [stageName, setStageName] = useState('');
  const [filterCategory, setFilterCategory] = useState('');
  const [filterExtension, setFilterExtension] = useState('');
  const [filterPathPrefix, setFilterPathPrefix] = useState('');
  const [filterUserOnly, setFilterUserOnly] = useState(false);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    triageAPI.listProcessors().then(r => setProcessors(r.processors || [])).catch(() => {});
  }, []);

  const handleCreate = async () => {
    if (!selectedProcessor || !stageName.trim()) return;
    setCreating(true);
    try {
      const fileFilter = {};
      if (filterCategory) fileFilter.category = filterCategory;
      if (filterExtension) fileFilter.extension = filterExtension;
      if (filterPathPrefix) fileFilter.path_prefix = filterPathPrefix;
      if (filterUserOnly) fileFilter.is_user_file = true;

      await triageAPI.createStage(caseId, {
        name: stageName.trim(),
        processor_name: selectedProcessor.name,
        config: {},
        file_filter: fileFilter,
      });
      onCreated();
    } catch (err) {
      alert(`Error creating stage: ${err.message}`);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b border-light-200">
          <h3 className="text-lg font-semibold text-owl-blue-900">Create Processing Stage</h3>
          <p className="text-sm text-light-500 mt-1">Select a processor and configure file filters</p>
        </div>

        <div className="p-6 space-y-4">
          {/* Stage name */}
          <div>
            <label className="block text-sm font-medium text-light-700 mb-1">Stage Name</label>
            <input
              type="text"
              value={stageName}
              onChange={(e) => setStageName(e.target.value)}
              placeholder="e.g., Extract PDF text, Parse browser history"
              className="w-full px-3 py-2 border border-light-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-owl-blue-300"
            />
          </div>

          {/* Processor selection */}
          <div>
            <label className="block text-sm font-medium text-light-700 mb-2">Processor</label>
            <div className="space-y-2">
              {processors.map((proc) => (
                <button
                  key={proc.name}
                  onClick={() => {
                    setSelectedProcessor(proc);
                    if (!stageName) setStageName(proc.display_name);
                  }}
                  className={`w-full text-left p-3 rounded-lg border transition-colors ${
                    selectedProcessor?.name === proc.name
                      ? 'border-owl-blue-400 bg-owl-blue-50'
                      : 'border-light-200 hover:bg-light-50'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <Cpu className="w-4 h-4 text-owl-blue-500" />
                    <span className="font-medium text-sm text-owl-blue-900">{proc.display_name}</span>
                    {proc.requires_llm && (
                      <span className="px-1.5 py-0.5 bg-purple-100 text-purple-700 rounded text-xs">LLM</span>
                    )}
                  </div>
                  <p className="text-xs text-light-500 mt-1 ml-6">{proc.description}</p>
                  <div className="flex gap-1.5 mt-1.5 ml-6">
                    {proc.input_types.map(t => (
                      <span key={t} className="px-1.5 py-0.5 bg-light-100 text-light-600 rounded text-xs capitalize">{t}</span>
                    ))}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* File filters */}
          <div>
            <label className="block text-sm font-medium text-light-700 mb-2">File Filters</label>
            <div className="space-y-2">
              <select
                value={filterCategory}
                onChange={(e) => setFilterCategory(e.target.value)}
                className="w-full px-3 py-2 border border-light-200 rounded-lg text-sm bg-white"
              >
                <option value="">All categories</option>
                {['documents', 'images', 'video', 'audio', 'archives', 'executables', 'databases', 'emails', 'web', 'system', 'other'].map(c => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
              <input
                type="text"
                value={filterExtension}
                onChange={(e) => setFilterExtension(e.target.value)}
                placeholder="Extension filter (e.g., .pdf)"
                className="w-full px-3 py-2 border border-light-200 rounded-lg text-sm"
              />
              <input
                type="text"
                value={filterPathPrefix}
                onChange={(e) => setFilterPathPrefix(e.target.value)}
                placeholder="Path prefix filter (e.g., Users/john/)"
                className="w-full px-3 py-2 border border-light-200 rounded-lg text-sm"
              />
              <label className="flex items-center gap-2 text-sm text-light-600">
                <input
                  type="checkbox"
                  checked={filterUserOnly}
                  onChange={(e) => setFilterUserOnly(e.target.checked)}
                  className="rounded border-light-300"
                />
                User files only (exclude system files)
              </label>
            </div>
          </div>
        </div>

        <div className="p-6 border-t border-light-200 flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm text-light-600 hover:text-light-800">Cancel</button>
          <button
            onClick={handleCreate}
            disabled={creating || !selectedProcessor || !stageName.trim()}
            className="flex items-center gap-2 px-4 py-2 bg-owl-blue-600 text-white rounded-lg text-sm hover:bg-owl-blue-700 disabled:opacity-50"
          >
            {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
            Create Stage
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Stage Results View ──────────────────────────────────────────────

function StageResults({ caseId, stageId }) {
  const [results, setResults] = useState(null);
  const [expanded, setExpanded] = useState({});

  useEffect(() => {
    if (!stageId) return;
    triageAPI.getStageResults(caseId, stageId)
      .then(r => setResults(r.artifacts || []))
      .catch(() => setResults([]));
  }, [caseId, stageId]);

  if (!results) return <Loader2 className="w-5 h-5 animate-spin text-owl-blue-500 mx-auto mt-4" />;
  if (results.length === 0) return <p className="text-sm text-light-400 text-center mt-4">No artifacts produced</p>;

  const toggle = (id) => setExpanded(prev => ({ ...prev, [id]: !prev[id] }));

  return (
    <div className="space-y-2 max-h-96 overflow-y-auto">
      {results.map((art) => (
        <div key={art.id} className="border border-light-200 rounded-lg">
          <button
            onClick={() => toggle(art.id)}
            className="w-full flex items-center justify-between p-3 text-left hover:bg-light-50"
          >
            <div className="flex items-center gap-2 min-w-0">
              {art.error ? (
                <AlertCircle className="w-3.5 h-3.5 text-red-500 flex-shrink-0" />
              ) : (
                <FileText className="w-3.5 h-3.5 text-owl-blue-400 flex-shrink-0" />
              )}
              <span className="text-sm text-light-700 truncate">{art.source_path?.split('/').pop() || 'unknown'}</span>
              <span className="px-1.5 py-0.5 bg-light-100 text-light-500 rounded text-xs flex-shrink-0">{art.artifact_type}</span>
            </div>
            {expanded[art.id] ? <ChevronDown className="w-4 h-4 text-light-400" /> : <ChevronRight className="w-4 h-4 text-light-400" />}
          </button>
          {expanded[art.id] && (
            <div className="px-3 pb-3 border-t border-light-100">
              {art.error && <p className="text-sm text-red-600 mt-2">{art.error}</p>}
              {art.content && (
                <pre className="text-xs text-light-600 bg-light-50 p-2 rounded mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap font-mono">
                  {art.content.slice(0, 2000)}{art.content.length > 2000 ? '...' : ''}
                </pre>
              )}
              {art.metadata && Object.keys(art.metadata).length > 0 && (
                <details className="mt-2">
                  <summary className="text-xs text-light-500 cursor-pointer">Metadata</summary>
                  <pre className="text-xs text-light-500 bg-light-50 p-2 rounded mt-1 max-h-32 overflow-y-auto font-mono">
                    {JSON.stringify(art.metadata, null, 2).slice(0, 2000)}
                  </pre>
                </details>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Main Custom Stage View ──────────────────────────────────────────

export default function CustomStageView({ caseId, triageCase, stage, onRefresh }) {
  const [executing, setExecuting] = useState(false);
  const [showBuilder, setShowBuilder] = useState(false);

  const isRunning = stage?.status === 'running';
  const isCompleted = stage?.status === 'completed';
  const isFailed = stage?.status === 'failed';
  const isPending = stage?.status === 'pending';

  const stageConfig = stage?.config || {};
  const processorName = stageConfig.processor_name || '';
  const fileFilter = stageConfig.file_filter || {};

  const handleExecute = async () => {
    setExecuting(true);
    try {
      await triageAPI.executeStage(caseId, stage.id);
      onRefresh();
    } catch (err) {
      alert(`Error executing stage: ${err.message}`);
    } finally {
      setExecuting(false);
    }
  };

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-4">
      <div className="bg-white rounded-xl border border-light-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            {isRunning ? (
              <Loader2 className="w-6 h-6 text-blue-500 animate-spin" />
            ) : isCompleted ? (
              <CheckCircle2 className="w-6 h-6 text-green-500" />
            ) : isFailed ? (
              <AlertCircle className="w-6 h-6 text-red-500" />
            ) : (
              <Layers className="w-6 h-6 text-light-400" />
            )}
            <div>
              <h3 className="text-lg font-semibold text-owl-blue-900">{stage?.name || 'Custom Stage'}</h3>
              <p className="text-sm text-light-500">
                {processorName && <span>Processor: <span className="font-mono">{processorName}</span></span>}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isPending && (
              <button
                onClick={handleExecute}
                disabled={executing}
                className="flex items-center gap-2 px-4 py-2 bg-owl-blue-600 text-white rounded-lg hover:bg-owl-blue-700 disabled:opacity-50 transition-colors"
              >
                {executing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                Execute
              </button>
            )}
            {isFailed && (
              <button
                onClick={handleExecute}
                disabled={executing}
                className="flex items-center gap-2 px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 disabled:opacity-50 transition-colors"
              >
                {executing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                Retry
              </button>
            )}
          </div>
        </div>

        {/* Error */}
        {isFailed && stage?.error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4">
            <p className="text-sm text-red-700">{stage.error}</p>
          </div>
        )}

        {/* Progress */}
        {isRunning && (
          <div className="mb-4">
            <div className="flex justify-between text-sm text-light-600 mb-1">
              <span>Processing files</span>
              <span>{(stage.files_processed || 0).toLocaleString()} / {(stage.files_total || '?').toLocaleString()}</span>
            </div>
            <div className="h-2 bg-light-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-owl-blue-500 rounded-full transition-all duration-500"
                style={{ width: stage.files_total ? `${(stage.files_processed / stage.files_total) * 100}%` : '100%' }}
              />
            </div>
          </div>
        )}

        {/* Filter summary */}
        {Object.keys(fileFilter).length > 0 && (
          <div className="flex items-center gap-2 flex-wrap mt-3">
            <Filter className="w-3.5 h-3.5 text-light-400" />
            {Object.entries(fileFilter).map(([k, v]) => (
              <span key={k} className="px-2 py-0.5 bg-light-100 text-light-600 rounded text-xs">
                {k}: {String(v)}
              </span>
            ))}
          </div>
        )}

        {/* Stage stats */}
        {isCompleted && (
          <div className="grid grid-cols-3 gap-4 mt-4">
            <div className="bg-light-50 rounded-lg p-3 text-center">
              <p className="text-2xl font-bold text-owl-blue-900">{(stage.files_total || 0).toLocaleString()}</p>
              <p className="text-xs text-light-500">Files Processed</p>
            </div>
            <div className="bg-light-50 rounded-lg p-3 text-center">
              <p className="text-2xl font-bold text-owl-blue-900">{(stage.files_processed || 0).toLocaleString()}</p>
              <p className="text-xs text-light-500">Completed</p>
            </div>
            <div className="bg-light-50 rounded-lg p-3 text-center">
              <p className="text-2xl font-bold text-owl-blue-900">{(stage.files_failed || 0).toLocaleString()}</p>
              <p className="text-xs text-light-500">Failed</p>
            </div>
          </div>
        )}
      </div>

      {/* Results */}
      {(isCompleted || isRunning) && stage?.id && (
        <div className="bg-white rounded-xl border border-light-200 p-6">
          <h4 className="text-sm font-medium text-light-700 mb-3">Artifacts</h4>
          <StageResults caseId={caseId} stageId={stage.id} />
        </div>
      )}
    </div>
  );
}

// Export the builder modal separately
export { StageBuilderModal };
