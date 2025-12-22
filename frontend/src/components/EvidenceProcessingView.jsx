import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  UploadCloud,
  FileText,
  Trash2,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  ArrowLeft,
  PlayCircle,
  Loader2,
  Settings,
  ChevronDown,
  ChevronUp,
  X,
  Edit,
} from 'lucide-react';
import { evidenceAPI, profilesAPI } from '../services/api';
import BackgroundTasksPanel from './BackgroundTasksPanel';
import ProfileEditor from './ProfileEditor';

/**
 * EvidenceProcessingView
 *
 * Full-screen view for managing and processing evidence files for a case.
 *
 * Props:
 *  - caseId: string (required)
 *  - caseName: string
 *  - onBackToCases: () => void
 *  - onGoToGraph: () => void  // Opens this case in the main graph view
 */
export default function EvidenceProcessingView({
  caseId,
  caseName,
  onBackToCases,
  onGoToGraph,
  onLoadProcessedGraph,
  authUsername,
  onViewCase,
}) {
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState(null);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [logs, setLogs] = useState([]);
  const logContainerRef = useRef(null);
  const [progress, setProgress] = useState({ current: 0, total: 0 });
  const [lastProcessedVersion, setLastProcessedVersion] = useState(null);
  const [showBackgroundTasksPanel, setShowBackgroundTasksPanel] = useState(false);
  const [profiles, setProfiles] = useState([]);
  const [selectedProfile, setSelectedProfile] = useState(null);
  const [profileDetails, setProfileDetails] = useState(null);
  const [showProfileDetails, setShowProfileDetails] = useState(false);
  const [loadingProfiles, setLoadingProfiles] = useState(false);
  const [showProfileEditor, setShowProfileEditor] = useState(false);
  const [editingProfileName, setEditingProfileName] = useState(null);

  // Simple polling for ingestion logs while on this screen
  const loadLogs = useCallback(async () => {
    if (!caseId) return;
    try {
      const res = await evidenceAPI.logs(caseId, 200);
      const items = res?.logs || [];
      // Backend returns most recent first; display oldest at top
      const ordered = items.slice().reverse();
      setLogs(ordered);

      // Derive progress from latest log entry that has progress info
      const progressLogs = ordered.filter(
        (entry) =>
          typeof entry.progress_total === 'number' &&
          typeof entry.progress_current === 'number'
      );
      if (progressLogs.length > 0) {
        const last = progressLogs[progressLogs.length - 1];
        setProgress({
          current: last.progress_current,
          total: last.progress_total,
        });
      }
    } catch (err) {
      // Don't surface log polling errors aggressively; just console log
      console.warn('Failed to load ingestion logs:', err);
    }
  }, [caseId]);

  const loadFiles = useCallback(async () => {
    if (!caseId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await evidenceAPI.list(caseId);
      setFiles(res?.files || []);
    } catch (err) {
      console.error('Failed to load evidence files:', err);
      setError(err.message || 'Failed to load evidence files');
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  // Load profiles on mount
  useEffect(() => {
    const loadProfiles = async () => {
      setLoadingProfiles(true);
      try {
        const data = await profilesAPI.list();
        setProfiles(data || []);
        // Default to first profile if available
        if (data && data.length > 0 && !selectedProfile) {
          setSelectedProfile(data[0].name);
        }
      } catch (err) {
        console.error('Failed to load profiles:', err);
      } finally {
        setLoadingProfiles(false);
      }
    };
    loadProfiles();
  }, []);

  // Load profile details when selected
  useEffect(() => {
    const loadProfileDetails = async () => {
      if (!selectedProfile) {
        setProfileDetails(null);
        return;
      }
      try {
        const details = await profilesAPI.get(selectedProfile);
        setProfileDetails(details);
      } catch (err) {
        console.error('Failed to load profile details:', err);
        setProfileDetails(null);
      }
    };
    loadProfileDetails();
  }, [selectedProfile]);

  useEffect(() => {
    loadFiles();
    loadLogs();
  }, [loadFiles, loadLogs]);

  // Poll logs every 10 seconds only while actively processing
  useEffect(() => {
    if (!caseId || !processing) return;
    
    // Only poll while processing is active (every 10 seconds for progress updates)
    const intervalId = setInterval(() => {
      loadLogs();
    }, 10000); // 10 seconds as requested
    
    return () => clearInterval(intervalId);
  }, [caseId, processing, loadLogs]);

  // Auto-scroll log window to the bottom (tail behavior) whenever logs change
  useEffect(() => {
    if (!logContainerRef.current) return;
    const el = logContainerRef.current;
    el.scrollTop = el.scrollHeight;
  }, [logs]);

  const handleFileSelect = async (event) => {
    const fileList = event.target.files;
    if (!fileList || fileList.length === 0) return;
    if (!caseId) {
      alert('Please select or create a case before uploading evidence.');
      return;
    }

    setUploading(true);
    setError(null);
    try {
      await evidenceAPI.upload(caseId, fileList);
      await loadFiles();
      event.target.value = ''; // reset input so same files can be re-selected if needed
    } catch (err) {
      console.error('Failed to upload files:', err);
      setError(err.message || 'Failed to upload files');
    } finally {
      setUploading(false);
    }
  };

  const toggleSelect = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const selectAll = (ids) => {
    setSelectedIds(new Set(ids));
  };

  const clearSelection = () => {
    setSelectedIds(new Set());
  };

  const handleProcessSelected = async () => {
    if (selectedIds.size === 0) {
      alert('Please select one or more files to process.');
      return;
    }
    
    const fileIds = Array.from(selectedIds);
    
    // Always use background processing - ingestion with AI extraction can take a long time
    try {
      const res = await evidenceAPI.processBackground(caseId, fileIds, selectedProfile);
      alert(`Processing ${fileIds.length} file(s) in the background. Check the Background Tasks panel for progress.`);
      clearSelection();
      await loadFiles();
    } catch (err) {
      console.error('Failed to start background processing:', err);
      setError(err.message || 'Failed to start background processing');
    }
  };

  const formatDateTime = (value) => {
    if (!value) return '—';
    try {
      return new Date(value).toLocaleString();
    } catch {
      return value;
    }
  };

  const humanSize = (size) => {
    if (!size && size !== 0) return '—';
    if (size < 1024) return `${size} B`;
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
    if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`;
    return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  };

  const unprocessed = files.filter(
    (f) => f.status === 'unprocessed' || f.status === 'failed'
  );
  const processed = files.filter(
    (f) => f.status === 'processed' || f.status === 'duplicate'
  );

  return (
    <div className="h-screen w-screen bg-light-50 flex flex-col overflow-hidden">
      {/* Header */}
      <header className="h-16 bg-white border-b border-light-200 flex items-center justify-between px-6 flex-shrink-0 shadow-sm">
        <div className="flex items-center gap-3">
          <button
            onClick={onBackToCases}
            className="mr-2 p-1.5 rounded-full hover:bg-light-200 transition-colors"
            title="Back to Cases"
          >
            <ArrowLeft className="w-5 h-5 text-light-700" />
          </button>
          <div className="flex items-center gap-2">
            <UploadCloud className="w-6 h-6 text-owl-blue-700" />
            <div>
              <h1 className="text-lg font-semibold text-owl-blue-900">
                Evidence Processing
              </h1>
              <p className="text-xs text-light-600">
                Case: {caseName || caseId || 'New Case'}
              </p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {/* Profile Selection */}
          <div className="relative">
            <div className="flex items-center gap-2">
              <Settings className="w-4 h-4 text-light-600" />
              <label className="text-xs text-light-600 font-medium">LLM Profile:</label>
              <select
                value={selectedProfile || ''}
                onChange={(e) => setSelectedProfile(e.target.value)}
                disabled={loadingProfiles}
                className="px-2 py-1 border border-light-300 rounded text-sm text-light-900 bg-white focus:outline-none focus:border-owl-blue-500 disabled:opacity-50"
              >
                {loadingProfiles ? (
                  <option>Loading...</option>
                ) : profiles.length === 0 ? (
                  <option>No profiles available</option>
                ) : (
                  profiles.map((profile) => (
                    <option key={profile.name} value={profile.name}>
                      {profile.name}
                    </option>
                  ))
                )}
              </select>
              {profileDetails && (
                <>
                  <span className="text-xs text-light-600 max-w-xs truncate" title={profileDetails.description}>
                    {profileDetails.description}
                  </span>
                  <button
                    onClick={() => {
                      setEditingProfileName(selectedProfile);
                      setShowProfileEditor(true);
                    }}
                    className="p-1.5 rounded hover:bg-light-100 text-light-600 transition-colors"
                    title="Edit profile"
                  >
                    <Edit className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setShowProfileDetails(!showProfileDetails)}
                    className="p-1.5 rounded hover:bg-light-100 text-light-600 transition-colors"
                    title="View full profile details"
                  >
                    {showProfileDetails ? (
                      <ChevronUp className="w-4 h-4" />
                    ) : (
                      <ChevronDown className="w-4 h-4" />
                    )}
                  </button>
                </>
              )}
              <button
                onClick={() => {
                  setEditingProfileName(null);
                  setShowProfileEditor(true);
                }}
                className="flex items-center gap-1 px-3 py-1.5 text-sm text-owl-blue-700 hover:bg-owl-blue-50 rounded-lg transition-colors"
                title="Create new profile"
              >
                <Settings className="w-4 h-4" />
                New Profile
              </button>
            </div>
            
            {/* Profile Details Panel */}
            {showProfileDetails && profileDetails && (
              <div className="absolute right-0 top-full mt-2 w-96 bg-white border border-light-300 rounded-lg shadow-lg z-50 p-4 max-h-96 overflow-y-auto">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-semibold text-light-900">{profileDetails.name}</h3>
                  <button
                    onClick={() => setShowProfileDetails(false)}
                    className="p-1 rounded hover:bg-light-100 text-light-600"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
                <p className="text-sm text-light-600 mb-4">{profileDetails.description}</p>
                
                <div className="space-y-4">
                  <div>
                    <h4 className="text-xs font-semibold text-light-700 uppercase tracking-wide mb-2">
                      Ingestion Configuration
                    </h4>
                    <div className="bg-light-50 rounded p-3 space-y-2">
                      <div>
                        <p className="text-xs font-medium text-light-700 mb-1">System Context:</p>
                        <p className="text-xs text-light-600 italic">
                          {profileDetails.ingestion?.system_context || 'N/A'}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs font-medium text-light-700 mb-1">
                          Entity Types ({profileDetails.ingestion?.entity_types?.length || 0}):
                        </p>
                        <div className="flex flex-wrap gap-1">
                          {profileDetails.ingestion?.entity_types?.map((type, idx) => (
                            <span
                              key={idx}
                              className="px-2 py-0.5 bg-owl-blue-100 text-owl-blue-700 text-xs rounded"
                            >
                              {type}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div>
                        <p className="text-xs font-medium text-light-700 mb-1">
                          Relationship Types ({profileDetails.ingestion?.relationship_types?.length || 0}):
                        </p>
                        <div className="flex flex-wrap gap-1">
                          {profileDetails.ingestion?.relationship_types?.map((type, idx) => (
                            <span
                              key={idx}
                              className="px-2 py-0.5 bg-owl-purple-100 text-owl-purple-700 text-xs rounded"
                            >
                              {type}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                  
                  <div>
                    <h4 className="text-xs font-semibold text-light-700 uppercase tracking-wide mb-2">
                      Chat Configuration
                    </h4>
                    <div className="bg-light-50 rounded p-3 space-y-2">
                      <div>
                        <p className="text-xs font-medium text-light-700 mb-1">System Context:</p>
                        <p className="text-xs text-light-600 italic">
                          {profileDetails.chat?.system_context || 'N/A'}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs font-medium text-light-700 mb-1">Analysis Guidance:</p>
                        <p className="text-xs text-light-600">
                          {profileDetails.chat?.analysis_guidance || 'N/A'}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Background Tasks Button */}
          <button
            onClick={() => setShowBackgroundTasksPanel(!showBackgroundTasksPanel)}
            className={`p-2 rounded-lg transition-colors relative ${
              showBackgroundTasksPanel
                ? 'bg-owl-blue-500 text-white'
                : 'hover:bg-light-100 text-light-600'
            }`}
            title="Background Tasks"
          >
            <Loader2 className="w-5 h-5" />
          </button>

          {onLoadProcessedGraph && lastProcessedVersion && (
            <button
              onClick={() =>
                onLoadProcessedGraph(
                  lastProcessedVersion.caseId,
                  lastProcessedVersion.version
                )
              }
              className="flex items-center gap-2 px-3 py-1.5 border border-owl-blue-300 rounded-lg text-sm text-owl-blue-900 hover:bg-owl-blue-50 transition-colors"
              title={`Load processed graph (version ${lastProcessedVersion.version})`}
            >
              <PlayCircle className="w-4 h-4" />
              Load Processed Graph
            </button>
          )}
          <button
            onClick={onGoToGraph}
            disabled={processing}
            className={`flex items-center gap-2 px-3 py-1.5 border border-light-300 rounded-lg text-sm transition-colors ${
              processing
                ? 'text-light-400 bg-light-50 cursor-not-allowed'
                : 'text-light-700 hover:bg-light-100'
            }`}
            title={processing ? 'Cannot open case while files are processing' : 'Open this case in the graph view'}
          >
            <PlayCircle className="w-4 h-4" />
            Open Case in Graph
          </button>
        </div>
      </header>

      {/* Body */}
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
        {/* Left: Upload + Unprocessed */}
        <div className="w-full md:w-1/2 border-r border-light-200 flex flex-col">
          {/* Upload Panel */}
          <div className="p-4 border-b border-light-200 bg-white">
            <h2 className="text-md font-semibold text-owl-blue-900 mb-2">
              Upload Evidence
            </h2>
            <p className="text-xs text-light-600 mb-3">
              Select one or more documents (PDF, TXT, etc.) from your device to upload for
              processing.
            </p>
            <label className="flex items-center justify-center gap-2 px-4 py-3 border-2 border-dashed border-light-300 rounded-lg text-sm text-light-700 bg-light-50 hover:bg-light-100 cursor-pointer transition-colors">
              <UploadCloud className="w-5 h-5 text-owl-blue-700" />
              <span>{uploading ? 'Uploading…' : 'Click to choose files'}</span>
              <input
                type="file"
                multiple
                className="hidden"
                onChange={handleFileSelect}
                disabled={uploading || !caseId}
              />
            </label>
            {!caseId && (
              <p className="text-xs text-red-500 mt-2">
                You must create a case before uploading evidence.
              </p>
            )}
          </div>

          {/* Unprocessed Files */}
          <div className="flex-1 overflow-y-auto p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-owl-blue-900">
                Unprocessed Files
              </h3>
              <div className="flex items-center gap-2 text-xs">
                <button
                  onClick={() => selectAll(unprocessed.map((f) => f.id))}
                  className="px-2 py-1 border border-light-300 rounded-md hover:bg-light-100"
                  disabled={unprocessed.length === 0}
                >
                  Select All
                </button>
                <button
                  onClick={clearSelection}
                  className="px-2 py-1 border border-light-300 rounded-md hover:bg-light-100"
                  disabled={selectedIds.size === 0}
                >
                  Clear
                </button>
                <button
                  onClick={loadFiles}
                  className="p-1.5 rounded-full hover:bg-light-100"
                  title="Refresh"
                >
                  <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                </button>
              </div>
            </div>
            {loading ? (
              <div className="flex items-center justify-center py-12 text-light-600">
                <RefreshCw className="w-5 h-5 mr-2 animate-spin" />
                Loading evidence…
              </div>
            ) : unprocessed.length === 0 ? (
              <p className="text-sm text-light-600 italic">
                No unprocessed files. Upload new files or select from processed files to
                re-run ingestion if needed.
              </p>
            ) : (
              <div className="space-y-2">
                {unprocessed.map((file) => (
                  <div
                    key={file.id}
                    className={`flex items-start gap-3 p-3 rounded-lg border ${
                      selectedIds.has(file.id)
                        ? 'border-owl-blue-400 bg-owl-blue-50'
                        : 'border-light-200 bg-white hover:bg-light-50'
                    } cursor-pointer`}
                    onClick={() => toggleSelect(file.id)}
                  >
                    <input
                      type="checkbox"
                      checked={selectedIds.has(file.id)}
                      onChange={() => toggleSelect(file.id)}
                      onClick={(e) => e.stopPropagation()}
                      className="mt-1"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 min-w-0">
                          <FileText className="w-4 h-4 text-owl-blue-700 flex-shrink-0" />
                          <span className="font-medium text-sm text-owl-blue-900 truncate">
                            {file.original_filename}
                          </span>
                        </div>
                        <span className="text-xs text-light-600">
                          {humanSize(file.size)}
                        </span>
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-light-600">
                        <span>Uploaded: {formatDateTime(file.created_at)}</span>
                        {file.status === 'failed' && (
                          <>
                            <span>•</span>
                            <span className="inline-flex items-center gap-1 text-red-600">
                              <AlertTriangle className="w-3 h-3" />
                              Failed: {file.last_error || 'Unknown error'}
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right: Processed Files, Progress & Actions */}
        <div className="w-full md:w-1/2 flex flex-col">
          <div className="p-4 border-b border-light-200 bg-white flex items-center justify-between">
            <div className="flex flex-col gap-1">
              <h2 className="text-md font-semibold text-owl-blue-900">Processing</h2>
              {progress.total > 0 && (
                <div className="flex flex-col gap-1">
                  <div className="w-full h-2 bg-light-200 rounded-full overflow-hidden">
                    <div
                      className="h-2 bg-owl-blue-500 transition-all"
                      style={{
                        width: `${Math.min(
                          100,
                          (progress.current / progress.total) * 100 || 0
                        )}%`,
                      }}
                    />
                  </div>
                  <div className="text-xs text-light-600">
                    Processing file {Math.min(progress.current + 1, progress.total)} of{' '}
                    {progress.total}
                  </div>
                </div>
              )}
            </div>
            <button
              onClick={handleProcessSelected}
              disabled={processing || selectedIds.size === 0}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm text-white transition-colors ${
                processing || selectedIds.size === 0
                  ? 'bg-light-300 cursor-not-allowed'
                  : 'bg-owl-blue-600 hover:bg-owl-blue-700'
              }`}
            >
              <PlayCircle className="w-4 h-4" />
              {processing ? 'Processing…' : `Process ${selectedIds.size} file(s)`}
            </button>
          </div>

          {/* Error banner */}
          {error && (
            <div className="mx-4 mt-3 mb-1 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 mt-0.5" />
              <div>
                <div className="font-semibold">There was a problem</div>
                <div>{error}</div>
              </div>
            </div>
          )}

          {/* Processed Files */}
          <div className="flex-1 overflow-y-auto p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-owl-blue-900">
              Processed & Duplicate Files
            </h3>
            <div className="flex items-center gap-2 text-xs text-light-600">
              <span>
                {processed.length} file{processed.length === 1 ? '' : 's'}
              </span>
            </div>
          </div>
            {processed.length === 0 ? (
              <p className="text-sm text-light-600 italic">
                No processed or duplicate files yet.
              </p>
            ) : (
              <div className="space-y-2">
                {processed.map((file) => (
                  <div
                    key={file.id}
                    onClick={() => toggleSelect(file.id)}
                    className={`flex items-start gap-3 p-3 rounded-lg border ${
                      selectedIds.has(file.id)
                        ? 'border-owl-blue-400 bg-owl-blue-50'
                        : 'border-light-200 bg-white hover:bg-light-50'
                    } cursor-pointer`}
                  >
                    <input
                      type="checkbox"
                      checked={selectedIds.has(file.id)}
                      onChange={() => toggleSelect(file.id)}
                      onClick={(e) => e.stopPropagation()}
                      className="mt-1"
                    />
                    <div className="flex items-start gap-2 flex-1">
                      <FileText className="w-4 h-4 text-owl-blue-700 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <span className="font-medium text-sm text-owl-blue-900 truncate">
                            {file.original_filename}
                          </span>
                          <span className="text-xs text-light-600">
                            {humanSize(file.size)}
                          </span>
                        </div>
                        <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-light-600">
                          <span className="inline-flex items-center gap-1 text-green-700">
                            <CheckCircle2 className="w-3 h-3" />
                            {file.status === 'duplicate' ? 'Duplicate' : 'Processed'}
                          </span>
                          <span>Uploaded: {formatDateTime(file.created_at)}</span>
                          {file.processed_at && (
                            <>
                              <span>•</span>
                              <span>Processed: {formatDateTime(file.processed_at)}</span>
                            </>
                          )}
                          {file.duplicate_of && (
                            <>
                              <span>•</span>
                              <span>Duplicate of {file.duplicate_of}</span>
                            </>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Ingestion Log */}
      <div className="border-t border-light-200 bg-white px-6 py-4 h-52">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold text-owl-blue-900">
            Ingestion Log
          </h3>
          <div className="flex items-center gap-2 text-xs text-light-600">
            {processing && (
              <span className="text-owl-blue-700 font-medium">
                Processing… logs auto-update every few seconds
              </span>
            )}
            <button
              onClick={loadLogs}
              className="px-2 py-1 border border-light-300 rounded-md hover:bg-light-100"
            >
              Refresh Now
            </button>
          </div>
        </div>
        <div
          ref={logContainerRef}
          className="w-full h-full border border-light-200 rounded-md bg-light-50 overflow-y-auto text-xs font-mono p-2"
        >
          {logs.length === 0 ? (
            <div className="text-light-500 italic">
              No ingestion activity logged yet for this case.
            </div>
          ) : (
            logs.map((entry) => (
              <div key={entry.id} className="mb-1">
                <span className="text-light-500 mr-2">
                  {new Date(entry.timestamp).toLocaleTimeString()}
                </span>
                {entry.filename && (
                  <span className="text-owl-orange-600 mr-1">
                    [{entry.filename}]
                  </span>
                )}
                <span
                  className={`whitespace-pre-wrap ${
                    entry.level === 'error'
                      ? 'text-red-700'
                      : entry.level === 'debug'
                      ? 'text-light-700'
                      : 'text-owl-blue-900'
                  }`}
                >
                  {entry.message}
                </span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Background Tasks Panel */}
      <BackgroundTasksPanel
        isOpen={showBackgroundTasksPanel}
        onClose={() => setShowBackgroundTasksPanel(false)}
        authUsername={authUsername}
        onViewCase={(caseId, version) => {
          setShowBackgroundTasksPanel(false);
          if (onViewCase) {
            onViewCase(caseId, version);
          } else {
            // Fallback: just navigate back
            onBackToCases();
          }
        }}
      />

      {/* Profile Editor */}
      <ProfileEditor
        isOpen={showProfileEditor}
        onClose={() => {
          setShowProfileEditor(false);
          setEditingProfileName(null);
        }}
        profileName={editingProfileName}
      />
    </div>
  );
}

