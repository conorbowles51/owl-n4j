import React, { useState, useEffect } from 'react';
import {
  Upload, Loader2, X, CheckCircle2, AlertCircle,
  FolderInput, FileText, ChevronDown, Search,
} from 'lucide-react';
import { triageAPI, casesAPI } from '../../services/api';

export default function IngestToCase({ caseId, triageCase, onClose, onIngested }) {
  const [step, setStep] = useState('select'); // select | preview | ingesting | done
  const [cases, setCases] = useState([]);
  const [loadingCases, setLoadingCases] = useState(true);
  const [targetCaseId, setTargetCaseId] = useState('');
  const [caseSearch, setCaseSearch] = useState('');
  const [includeArtifacts, setIncludeArtifacts] = useState(true);
  const [fileFilter, setFileFilter] = useState({ is_user_file: true });
  const [useFilter, setUseFilter] = useState(true);
  const [preview, setPreview] = useState(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  // Load Owl investigation cases
  useEffect(() => {
    const load = async () => {
      try {
        const data = await casesAPI.list();
        setCases(data.cases || []);
      } catch (err) {
        console.error('Failed to load cases:', err);
      } finally {
        setLoadingCases(false);
      }
    };
    load();
  }, []);

  const filteredCases = cases.filter((c) => {
    if (!caseSearch) return true;
    const q = caseSearch.toLowerCase();
    return (
      (c.title || '').toLowerCase().includes(q) ||
      (c.id || '').toLowerCase().includes(q)
    );
  });

  const handlePreview = async () => {
    if (!targetCaseId) return;
    setLoadingPreview(true);
    setError('');
    try {
      const data = await triageAPI.ingestPreview(caseId, {
        target_case_id: targetCaseId,
        file_filter: useFilter ? fileFilter : null,
        include_artifacts: includeArtifacts,
      });
      setPreview(data);
      setStep('preview');
    } catch (err) {
      setError(err.message || 'Failed to generate preview');
    } finally {
      setLoadingPreview(false);
    }
  };

  const handleIngest = async () => {
    setIngesting(true);
    setError('');
    try {
      const data = await triageAPI.ingest(caseId, {
        target_case_id: targetCaseId,
        file_filter: useFilter ? fileFilter : null,
        include_artifacts: includeArtifacts,
      });
      setResult(data);
      setStep('done');
    } catch (err) {
      setError(err.message || 'Failed to start ingestion');
    } finally {
      setIngesting(false);
    }
  };

  const formatSize = (bytes) => {
    if (!bytes) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    let size = bytes;
    while (size >= 1024 && i < units.length - 1) {
      size /= 1024;
      i++;
    }
    return `${size.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
  };

  const selectedCase = cases.find((c) => c.id === targetCaseId);

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <FolderInput className="w-5 h-5 text-owl-blue-600" />
            <h3 className="text-lg font-semibold text-owl-blue-900">Ingest to Case</h3>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-light-100 rounded">
            <X className="w-4 h-4 text-light-500" />
          </button>
        </div>

        {/* Step: Select target case */}
        {step === 'select' && (
          <div className="space-y-4">
            <p className="text-xs text-light-500">
              Select an Owl investigation case to ingest triage files into.
            </p>

            {/* Case selector */}
            <div>
              <label className="block text-xs font-medium text-light-700 mb-1">Target Case</label>
              <div className="relative mb-2">
                <Search className="absolute left-2.5 top-2 w-3.5 h-3.5 text-light-400" />
                <input
                  type="text"
                  value={caseSearch}
                  onChange={(e) => setCaseSearch(e.target.value)}
                  placeholder="Search cases..."
                  className="w-full pl-8 pr-3 py-1.5 text-sm border border-light-200 rounded-lg focus:outline-none focus:border-owl-blue-400"
                />
              </div>
              {loadingCases ? (
                <div className="flex items-center justify-center py-4">
                  <Loader2 className="w-5 h-5 animate-spin text-light-400" />
                </div>
              ) : (
                <div className="max-h-40 overflow-y-auto border border-light-200 rounded-lg">
                  {filteredCases.length === 0 ? (
                    <p className="text-xs text-light-400 text-center py-4">No cases found</p>
                  ) : (
                    filteredCases.map((c) => (
                      <button
                        key={c.id}
                        onClick={() => setTargetCaseId(c.id)}
                        className={`w-full text-left px-3 py-2 text-sm border-b border-light-100 last:border-0 transition-colors ${
                          targetCaseId === c.id
                            ? 'bg-owl-blue-50 text-owl-blue-700'
                            : 'hover:bg-light-50 text-light-700'
                        }`}
                      >
                        <div className="font-medium truncate">{c.title || c.id}</div>
                        {c.description && (
                          <div className="text-xs text-light-400 truncate">{c.description}</div>
                        )}
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>

            {/* Filter options */}
            <div className="space-y-2">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={useFilter}
                  onChange={(e) => setUseFilter(e.target.checked)}
                  className="rounded text-owl-blue-600"
                />
                <span className="text-xs text-light-700">Filter files (user files only)</span>
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={includeArtifacts}
                  onChange={(e) => setIncludeArtifacts(e.target.checked)}
                  className="rounded text-owl-blue-600"
                />
                <span className="text-xs text-light-700">Include processed artifacts</span>
              </label>
            </div>

            {error && <p className="text-xs text-red-600">{error}</p>}

            <div className="flex justify-end gap-2">
              <button
                onClick={onClose}
                className="px-3 py-1.5 text-sm text-light-600 hover:bg-light-100 rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={handlePreview}
                disabled={!targetCaseId || loadingPreview}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-owl-blue-600 text-white rounded-lg hover:bg-owl-blue-700 disabled:opacity-40"
              >
                {loadingPreview ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <FileText className="w-3.5 h-3.5" />
                )}
                Preview
              </button>
            </div>
          </div>
        )}

        {/* Step: Preview */}
        {step === 'preview' && preview && (
          <div className="space-y-4">
            <div className="bg-light-50 rounded-lg p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-light-600">Target Case</span>
                <span className="text-sm font-medium text-light-800">
                  {selectedCase?.title || targetCaseId}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-light-600">Files to ingest</span>
                <span className="text-sm font-semibold text-owl-blue-700">
                  {(preview.file_count || 0).toLocaleString()}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-light-600">Total size</span>
                <span className="text-sm text-light-800">
                  {formatSize(preview.total_size)}
                </span>
              </div>
              {includeArtifacts && (
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-light-600">Artifacts included</span>
                  <span className="text-sm text-light-800">
                    {(preview.artifact_count || 0).toLocaleString()}
                  </span>
                </div>
              )}
            </div>

            {preview.file_count === 0 && (
              <div className="flex items-center gap-2 text-amber-600 text-xs">
                <AlertCircle className="w-4 h-4" />
                No files match the current filter. Adjust your selection.
              </div>
            )}

            {error && <p className="text-xs text-red-600">{error}</p>}

            <div className="flex justify-between">
              <button
                onClick={() => setStep('select')}
                className="px-3 py-1.5 text-sm text-light-600 hover:bg-light-100 rounded-lg"
              >
                Back
              </button>
              <button
                onClick={handleIngest}
                disabled={ingesting || preview.file_count === 0}
                className="flex items-center gap-1.5 px-4 py-1.5 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-40"
              >
                {ingesting ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Upload className="w-3.5 h-3.5" />
                )}
                Ingest {preview.file_count.toLocaleString()} Files
              </button>
            </div>
          </div>
        )}

        {/* Step: Done */}
        {step === 'done' && result && (
          <div className="space-y-4 text-center">
            <CheckCircle2 className="w-12 h-12 text-green-500 mx-auto" />
            <div>
              <p className="text-base font-semibold text-light-800">Ingestion Started</p>
              <p className="text-xs text-light-500 mt-1">
                Files are being copied to case{' '}
                <span className="font-medium">{selectedCase?.title || targetCaseId}</span>.
                You can track progress in Background Tasks.
              </p>
            </div>

            {result.task_id && (
              <p className="text-xs text-light-400 font-mono">Task: {result.task_id}</p>
            )}

            <button
              onClick={() => {
                onClose();
                if (onIngested) onIngested(result);
              }}
              className="px-4 py-1.5 text-sm bg-owl-blue-600 text-white rounded-lg hover:bg-owl-blue-700"
            >
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
