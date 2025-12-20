import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  FolderOpen,
  FolderPlus,
  X,
  Trash2,
  Eye,
  Calendar,
  FileText,
  Archive,
  Code,
  ChevronDown,
  ChevronRight,
  Loader2,
  RefreshCw,
  UploadCloud,
} from 'lucide-react';
import { casesAPI, evidenceAPI } from '../services/api';
import CaseModal from './CaseModal';
import BackgroundTasksPanel from './BackgroundTasksPanel';
import DocumentationViewer from './DocumentationViewer';

/**
 * CaseManagementView Component
 * 
 * Main view for managing cases - shown after login
 * Allows viewing, creating, and loading cases
 */
export default function CaseManagementView({
  onLoadCase,
  onCreateCase,
  onLogout,
  isAuthenticated,
  authUsername,
  onGoToGraphView,
  onGoToEvidenceView,
  onLoadLastGraph,
  lastGraphInfo,
  initialCaseToSelect,
  onCaseSelected,
}) {
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedCase, setSelectedCase] = useState(null);
  const [selectedVersion, setSelectedVersion] = useState(null);
  const [showCaseModal, setShowCaseModal] = useState(false);
  const [showCypher, setShowCypher] = useState(false);
  const [showSnapshots, setShowSnapshots] = useState(true);
  const [showVersions, setShowVersions] = useState(true);
  const [isAccountDropdownOpen, setIsAccountDropdownOpen] = useState(false);
  const [evidenceFiles, setEvidenceFiles] = useState([]);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceLogs, setEvidenceLogs] = useState([]);
  const [logsLoading, setLogsLoading] = useState(false);
  const [showBackgroundTasksPanel, setShowBackgroundTasksPanel] = useState(false);
  const [showDocumentation, setShowDocumentation] = useState(false);
  const accountDropdownRef = useRef(null);
  const logoButtonRef = useRef(null);
  const logsContainerRef = useRef(null);

  useEffect(() => {
    loadCases();
  }, []);

  // Handle initial case selection (e.g., from background tasks)
  useEffect(() => {
    if (initialCaseToSelect && initialCaseToSelect.caseId && cases.length > 0 && !loading) {
      const caseToSelect = cases.find(c => c.id === initialCaseToSelect.caseId);
      if (caseToSelect) {
        const selectCase = async () => {
          await handleViewCase(caseToSelect);
          // If a specific version was requested, select it
          if (initialCaseToSelect.version) {
            // Wait a bit for case data to load, then select the version
            setTimeout(async () => {
              try {
                const fullCase = await casesAPI.get(initialCaseToSelect.caseId);
                if (fullCase && fullCase.versions) {
                  const versionToSelect = fullCase.versions.find(
                    v => v.version === initialCaseToSelect.version
                  );
                  if (versionToSelect) {
                    setSelectedVersion(versionToSelect);
                  }
                }
              } catch (err) {
                console.error('Failed to load case for version selection:', err);
              }
              onCaseSelected?.(); // Notify parent that selection is complete
            }, 500);
          } else {
            onCaseSelected?.();
          }
        };
        selectCase();
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialCaseToSelect, cases, loading]);

  // Handle clicks outside account dropdown
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (
        isAccountDropdownOpen &&
        accountDropdownRef.current &&
        logoButtonRef.current &&
        !accountDropdownRef.current.contains(event.target) &&
        !logoButtonRef.current.contains(event.target)
      ) {
        setIsAccountDropdownOpen(false);
      }
    };

    if (isAccountDropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isAccountDropdownOpen]);

  const loadCases = async () => {
    setLoading(true);
    try {
      const data = await casesAPI.list();
      setCases(data);
    } catch (err) {
      console.error('Failed to load cases:', err);
      alert(`Failed to load cases: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleViewCase = async (caseItem) => {
    try {
      const fullCase = await casesAPI.get(caseItem.id);
      // Sort versions by version number descending (most recent first)
      if (fullCase.versions && fullCase.versions.length > 0) {
        fullCase.versions.sort((a, b) => b.version - a.version);
      }
      setSelectedCase(fullCase);
      // Select latest version by default
      if (fullCase.versions && fullCase.versions.length > 0) {
        setSelectedVersion(fullCase.versions[0]);
      }
    } catch (err) {
      console.error('Failed to load case:', err);
      alert(`Failed to load case: ${err.message}`);
    }
  };

  const handleDeleteCase = async (caseId, e) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to delete this case? This will delete all versions.')) {
      return;
    }

    try {
      await casesAPI.delete(caseId);
      await loadCases();
      if (selectedCase?.id === caseId) {
        setSelectedCase(null);
        setSelectedVersion(null);
      }
    } catch (err) {
      console.error('Failed to delete case:', err);
      alert(`Failed to delete case: ${err.message}`);
    }
  };

  const handleLoadCase = () => {
    if (onLoadCase && selectedCase && selectedVersion) {
      onLoadCase(selectedCase, selectedVersion);
    }
  };

  const handleCreateCase = async (caseName, saveNotes) => {
    if (!onCreateCase) {
      console.warn('onCreateCase handler is not provided');
      return;
    }
    try {
      await onCreateCase(caseName, saveNotes);
      setShowCaseModal(false);
    } catch (err) {
      console.error('Failed to create case:', err);
      alert(`Failed to create case: ${err.message}`);
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  const loadEvidenceForCase = useCallback(
    async (caseId) => {
      if (!caseId) return;
      setEvidenceLoading(true);
      try {
        const res = await evidenceAPI.list(caseId);
        setEvidenceFiles(res?.files || []);
      } catch (err) {
        console.error('Failed to load evidence for case:', err);
        // Keep UI non-blocking; errors here aren't critical
      } finally {
        setEvidenceLoading(false);
      }
    },
    []
  );

  const loadEvidenceLogsForCase = useCallback(
    async (caseId) => {
      if (!caseId) return;
      setLogsLoading(true);
      try {
        const res = await evidenceAPI.logs(caseId, 100);
        const logs = res?.logs || [];
        // Show oldest first for readability
        setEvidenceLogs(logs.slice().reverse());
      } catch (err) {
        console.error('Failed to load evidence logs for case:', err);
      } finally {
        setLogsLoading(false);
      }
    },
    []
  );

  // When a case is selected, load its evidence files and logs
  useEffect(() => {
    if (selectedCase) {
      loadEvidenceForCase(selectedCase.id);
      loadEvidenceLogsForCase(selectedCase.id);
    } else {
      setEvidenceFiles([]);
      setEvidenceLogs([]);
    }
  }, [selectedCase, loadEvidenceForCase, loadEvidenceLogsForCase]);

  // Auto-scroll processing history window to bottom as new logs arrive
  useEffect(() => {
    if (!logsContainerRef.current) return;
    const el = logsContainerRef.current;
    el.scrollTop = el.scrollHeight;
  }, [evidenceLogs]);

  return (
    <div className="h-screen w-screen bg-light-50 flex flex-col overflow-hidden">
      {/* Header */}
      <header className="h-16 bg-white border-b border-light-200 flex items-center justify-between px-6 flex-shrink-0 shadow-sm">
        <div className="flex items-center gap-3 relative">
          <button
            ref={logoButtonRef}
            onClick={() => setIsAccountDropdownOpen(prev => !prev)}
            className="group focus:outline-none"
            type="button"
          >
            <img src="/owl-logo.webp" alt="Owl Consultancy Group" className="w-32 h-32 object-contain" />
          </button>

          {isAccountDropdownOpen && (
            <div
              ref={accountDropdownRef}
              className="absolute z-50 mt-2 w-48 rounded-lg bg-white shadow-lg border border-light-200 py-2 right-0"
              style={{ top: '70px', left: '0' }}
            >
              {isAuthenticated ? (
                <div className="px-3 py-1 space-y-1 text-sm text-dark-600">
                  <p className="text-xs uppercase text-dark-400">Signed in as</p>
                  <p className="font-semibold text-dark-800">{authUsername}</p>
                  <button
                    onClick={() => {
                      setShowDocumentation(true);
                      setIsAccountDropdownOpen(false);
                    }}
                    className="w-full text-left px-2 py-1 rounded hover:bg-light-100 transition-colors text-sm text-dark-700"
                  >
                    Documentation
                  </button>
                  <button
                    onClick={async () => {
                      if (onLogout) {
                        await onLogout();
                      }
                      setIsAccountDropdownOpen(false);
                    }}
                    className="w-full text-left px-2 py-1 rounded hover:bg-light-100 transition-colors text-sm text-dark-700"
                  >
                    Logout
                  </button>
                </div>
              ) : (
                <div className="px-3 py-2 space-y-1">
                  <button
                    onClick={() => {
                      setShowDocumentation(true);
                      setIsAccountDropdownOpen(false);
                    }}
                    className="w-full text-left px-2 py-1 rounded hover:bg-light-100 transition-colors text-sm text-dark-700"
                  >
                    Documentation
                  </button>
                  <p className="text-sm text-light-600 pt-1">Not logged in</p>
                </div>
              )}
            </div>
          )}

          <div>
            <h1 className="text-lg font-semibold text-owl-blue-900">Case Management</h1>
            <p className="text-xs text-light-600">Manage and load investigation cases</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
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

          {onLoadLastGraph && (
            <button
              onClick={onLoadLastGraph}
              className="px-3 py-2 text-sm text-owl-blue-900 border border-owl-blue-200 rounded-lg bg-white hover:bg-owl-blue-50 transition-colors"
              title={
                lastGraphInfo?.saved_at
                  ? `Last graph saved at ${formatDate(lastGraphInfo.saved_at)}`
                  : 'Load the last cleared graph (if available)'
              }
              disabled={!lastGraphInfo || !lastGraphInfo.cypher}
            >
              Load Last Graph
            </button>
          )}
          {onGoToGraphView && (
            <button
              onClick={onGoToGraphView}
              className="px-3 py-2 text-sm text-owl-blue-900 border border-owl-blue-200 rounded-lg bg-white hover:bg-owl-blue-50 transition-colors"
            >
              Go to Graph View
            </button>
          )}
          <button
            onClick={() => setShowCaseModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-owl-blue-500 hover:bg-owl-blue-600 text-white rounded-lg transition-colors"
          >
            <FolderPlus className="w-4 h-4" />
            Create New Case
          </button>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Cases List - Left Panel */}
        <div className="w-1/3 border-r border-light-200 bg-white overflow-y-auto">
          <div className="p-4 border-b border-light-200">
            <h2 className="text-md font-semibold text-owl-blue-900 mb-1">
              {authUsername ? `${authUsername.charAt(0).toUpperCase()}${authUsername.slice(1)}'s Cases` : 'Cases'}
            </h2>
            <p className="text-xs text-light-600">
              {loading
                ? 'Loading...'
                : `${cases.length} case${cases.length !== 1 ? 's' : ''} available`}
            </p>
          </div>

          {loading ? (
            <div className="p-8 text-center">
              <Loader2 className="w-8 h-8 mx-auto mb-3 text-owl-blue-600 animate-spin" />
              <p className="text-light-600">Loading cases...</p>
            </div>
          ) : cases.length === 0 ? (
            <div className="p-8 text-center">
              <FolderOpen className="w-16 h-16 mx-auto mb-4 text-light-400" />
              <p className="text-light-700 font-medium mb-2">No cases yet</p>
              <p className="text-sm text-light-600 mb-4">
                Create your first case to start organizing your investigations
              </p>
              <button
                onClick={() => setShowCaseModal(true)}
                className="px-4 py-2 bg-owl-blue-500 hover:bg-owl-blue-600 text-white rounded-lg transition-colors text-sm"
              >
                Create New Case
              </button>
            </div>
          ) : (
            <div className="p-2">
              {cases.map((caseItem) => (
                <div
                  key={caseItem.id}
                  onClick={() => handleViewCase(caseItem)}
                  className={`p-4 mb-2 rounded-lg cursor-pointer transition-colors ${
                    selectedCase?.id === caseItem.id
                      ? 'bg-owl-blue-100 border-2 border-owl-blue-300'
                      : 'bg-light-50 hover:bg-light-100 border-2 border-transparent'
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <h3 className="font-semibold text-owl-blue-900 truncate mb-1">
                        {caseItem.name}
                      </h3>
                      <div className="flex items-center gap-3 text-xs text-light-600">
                        <span className="flex items-center gap-1">
                          <Calendar className="w-3 h-3" />
                          {formatDate(caseItem.updated_at)}
                        </span>
                        <span>{caseItem.version_count || 0} version{(caseItem.version_count || 0) !== 1 ? 's' : ''}</span>
                      </div>
                    </div>
                    <button
                      onClick={(e) => handleDeleteCase(caseItem.id, e)}
                      className="p-1 hover:bg-light-200 rounded transition-colors ml-2 flex-shrink-0"
                      title="Delete case"
                    >
                      <Trash2 className="w-4 h-4 text-red-500" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Case Details - Right Panel */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {selectedCase ? (
            <>
              {/* Case Header */}
              <div className="p-6 border-b border-light-200 bg-white">
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h2 className="text-xl font-semibold text-owl-blue-900 mb-2">
                      {selectedCase.name}
                    </h2>
                    <div className="flex items-center gap-4 text-sm text-light-600">
                      <span>Created: {formatDate(selectedCase.created_at)}</span>
                      <span>•</span>
                      <span>Updated: {formatDate(selectedCase.updated_at)}</span>
                      <span>•</span>
                      <span>
                        {selectedCase.versions?.length || 0} version
                        {(selectedCase.versions?.length || 0) !== 1 ? 's' : ''}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {onGoToEvidenceView && (
                      <button
                        onClick={() => onGoToEvidenceView(selectedCase)}
                        className="flex items-center gap-2 px-4 py-2 border border-owl-blue-300 text-owl-blue-900 rounded-lg bg-white hover:bg-owl-blue-50 transition-colors text-sm"
                      >
                        <UploadCloud className="w-4 h-4" />
                        Process Evidence
                      </button>
                    )}
                    {selectedVersion && (
                      <button
                        onClick={handleLoadCase}
                        className="flex items-center gap-2 px-4 py-2 bg-owl-orange-500 hover:bg-owl-orange-600 text-white rounded-lg transition-colors text-sm"
                      >
                        <Eye className="w-4 h-4" />
                        Load Version {selectedVersion.version}
                      </button>
                    )}
                  </div>
                </div>
              </div>

              {/* Case Content - Scrollable */}
              <div className="flex-1 overflow-y-auto p-6">
                {/* Evidence Files Section */}
                <div className="mb-6">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <FolderOpen className="w-5 h-5 text-owl-blue-700" />
                      <h3 className="text-md font-semibold text-owl-blue-900">
                        Evidence Files
                      </h3>
                      <span className="text-xs text-light-600 bg-white px-2 py-0.5 rounded">
                        {evidenceFiles.length}
                      </span>
                    </div>
                    <button
                      onClick={() => {
                        if (selectedCase) {
                          loadEvidenceForCase(selectedCase.id);
                        }
                      }}
                      className="flex items-center gap-1 text-xs text-light-600 hover:text-owl-blue-700"
                    >
                      <RefreshCw
                        className={`w-3 h-3 ${
                          evidenceLoading ? 'animate-spin' : ''
                        }`}
                      />
                      Refresh
                    </button>
                  </div>
                  <div className="ml-2">
                    {evidenceLoading ? (
                      <div className="flex items-center gap-2 text-xs text-light-600">
                        <Loader2 className="w-4 h-4 animate-spin" />
                        Loading evidence files…
                      </div>
                    ) : evidenceFiles.length === 0 ? (
                      <p className="text-sm text-light-600 italic">
                        No evidence files have been uploaded for this case yet.
                      </p>
                    ) : (
                      <div className="space-y-1">
                        {evidenceFiles.map((file) => (
                          <div
                            key={file.id}
                            className="flex items-center justify-between p-2 bg-white rounded border border-light-200 text-xs"
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <FileText className="w-3 h-3 text-owl-blue-700" />
                              <span className="truncate text-owl-blue-900">
                                {file.original_filename}
                              </span>
                            </div>
                            <div className="flex items-center gap-3 text-light-600 flex-shrink-0 ml-2">
                              <span>{file.status}</span>
                              <span className="hidden sm:inline">
                                {new Date(file.created_at).toLocaleString()}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {/* Processing History Section */}
                <div className="mb-6">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Archive className="w-5 h-5 text-owl-blue-700" />
                      <h3 className="text-md font-semibold text-owl-blue-900">
                        Processing History
                      </h3>
                    </div>
                    <button
                      onClick={() => {
                        if (selectedCase) {
                          loadEvidenceLogsForCase(selectedCase.id);
                        }
                      }}
                      className="flex items-center gap-1 text-xs text-light-600 hover:text-owl-blue-700"
                    >
                      <RefreshCw
                        className={`w-3 h-3 ${
                          logsLoading ? 'animate-spin' : ''
                        }`}
                      />
                      Refresh
                    </button>
                  </div>
                  <div
                    ref={logsContainerRef}
                    className="ml-2 border border-light-200 rounded bg-light-50 max-h-56 overflow-y-auto text-xs font-mono p-2"
                  >
                    {logsLoading ? (
                      <div className="flex items-center gap-2 text-light-600">
                        <Loader2 className="w-4 h-4 animate-spin" />
                        Loading processing history…
                      </div>
                    ) : evidenceLogs.length === 0 ? (
                      <div className="text-light-500 italic">
                        No processing activity recorded yet for this case.
                      </div>
                    ) : (
                      evidenceLogs.map((entry) => (
                        <div key={entry.id} className="mb-1">
                          <span className="text-light-500 mr-2">
                            {new Date(entry.timestamp).toLocaleString()}
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

                {/* Versions Section */}
                <div className="mb-6">
                  <button
                    onClick={() => setShowVersions(!showVersions)}
                    className="w-full flex items-center justify-between p-3 bg-light-100 hover:bg-light-200 rounded-lg transition-colors mb-2"
                  >
                    <div className="flex items-center gap-2">
                      <FileText className="w-5 h-5 text-owl-blue-700" />
                      <h3 className="text-md font-semibold text-owl-blue-900">Versions</h3>
                      <span className="text-xs text-light-600 bg-white px-2 py-0.5 rounded">
                        {selectedCase.versions?.length || 0}
                      </span>
                    </div>
                    {showVersions ? (
                      <ChevronDown className="w-4 h-4 text-light-600" />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-light-600" />
                    )}
                  </button>
                  {showVersions && (
                    <div className="space-y-2 ml-2">
                      {selectedCase.versions && selectedCase.versions.length > 0 ? (
                        selectedCase.versions.map((version) => (
                          <div
                            key={version.version}
                            onClick={() => setSelectedVersion(version)}
                            className={`p-4 rounded-lg cursor-pointer transition-colors border-2 ${
                              selectedVersion?.version === version.version
                                ? 'bg-owl-blue-50 border-owl-blue-300'
                                : 'bg-white hover:bg-light-50 border-light-200'
                            }`}
                          >
                            <div className="flex items-center justify-between mb-2">
                              <div className="flex items-center gap-2">
                                <FileText className="w-4 h-4 text-owl-blue-600" />
                                <span className="font-medium text-owl-blue-900">
                                  Version {version.version}
                                </span>
                                {version.version === selectedCase.versions[0].version && (
                                  <span className="text-xs bg-owl-blue-100 text-owl-blue-700 px-2 py-0.5 rounded">
                                    Latest
                                  </span>
                                )}
                              </div>
                              <span className="text-xs text-light-600">
                                {formatDate(version.timestamp)}
                              </span>
                            </div>
                            {version.save_notes && (
                              <p className="text-sm text-light-700 mb-2 line-clamp-2">
                                {version.save_notes}
                              </p>
                            )}
                            <div className="flex items-center gap-4 text-xs text-light-600">
                              <span>
                                {version.snapshots?.length || 0} snapshot{(version.snapshots?.length || 0) !== 1 ? 's' : ''}
                              </span>
                              <span>•</span>
                              <span>
                                {version.cypher_queries?.split('\n\n').filter(q => q.trim()).length || 0} Cypher statement{(version.cypher_queries?.split('\n\n').filter(q => q.trim()).length || 0) !== 1 ? 's' : ''}
                              </span>
                            </div>
                          </div>
                        ))
                      ) : (
                        <p className="text-sm text-light-600 italic ml-4">No versions available</p>
                      )}
                    </div>
                  )}
                </div>

                {/* Selected Version Details */}
                {selectedVersion && (
                  <>
                    {/* Cypher Queries Section */}
                    <div className="mb-6">
                      <button
                        onClick={() => setShowCypher(!showCypher)}
                        className="w-full flex items-center justify-between p-3 bg-light-100 hover:bg-light-200 rounded-lg transition-colors mb-2"
                      >
                        <div className="flex items-center gap-2">
                          <Code className="w-5 h-5 text-owl-blue-700" />
                          <h3 className="text-md font-semibold text-owl-blue-900">
                            Cypher Queries (Version {selectedVersion.version})
                          </h3>
                        </div>
                        {showCypher ? (
                          <ChevronDown className="w-4 h-4 text-light-600" />
                        ) : (
                          <ChevronRight className="w-4 h-4 text-light-600" />
                        )}
                      </button>
                      {showCypher && (
                        <div className="ml-2 bg-dark-900 rounded-lg p-4 overflow-x-auto">
                          <pre className="text-xs text-light-200 font-mono whitespace-pre-wrap">
                            {selectedVersion.cypher_queries || 'No Cypher queries available'}
                          </pre>
                        </div>
                      )}
                    </div>

                    {/* Snapshots Section */}
                    <div className="mb-6">
                      <button
                        onClick={() => setShowSnapshots(!showSnapshots)}
                        className="w-full flex items-center justify-between p-3 bg-light-100 hover:bg-light-200 rounded-lg transition-colors mb-2"
                      >
                        <div className="flex items-center gap-2">
                          <Archive className="w-5 h-5 text-owl-blue-700" />
                          <h3 className="text-md font-semibold text-owl-blue-900">
                            Snapshots (Version {selectedVersion.version})
                          </h3>
                          <span className="text-xs text-light-600 bg-white px-2 py-0.5 rounded">
                            {selectedVersion.snapshots?.length || 0}
                          </span>
                        </div>
                        {showSnapshots ? (
                          <ChevronDown className="w-4 h-4 text-light-600" />
                        ) : (
                          <ChevronRight className="w-4 h-4 text-light-600" />
                        )}
                      </button>
                      {showSnapshots && (
                        <div className="ml-2 space-y-2">
                          {selectedVersion.snapshots && selectedVersion.snapshots.length > 0 ? (
                            selectedVersion.snapshots.map((snapshot) => (
                              <div
                                key={snapshot.id}
                                className="p-4 bg-white rounded-lg border border-light-200"
                              >
                                <div className="flex items-start justify-between mb-2">
                                  <div className="flex-1">
                                    <h4 className="font-medium text-owl-blue-900 mb-1">
                                      {snapshot.name}
                                    </h4>
                                    {snapshot.notes && (
                                      <p className="text-sm text-light-700 line-clamp-2 mb-2">
                                        {snapshot.notes}
                                      </p>
                                    )}
                                  </div>
                                </div>
                                <div className="flex items-center gap-4 text-xs text-light-600">
                                  <span>{snapshot.node_count || 0} nodes</span>
                                  <span>•</span>
                                  <span>{snapshot.link_count || 0} links</span>
                                  <span>•</span>
                                  <span>{formatDate(snapshot.timestamp)}</span>
                                </div>
                              </div>
                            ))
                          ) : (
                            <p className="text-sm text-light-600 italic ml-4">No snapshots in this version</p>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Version Notes */}
                    {selectedVersion.save_notes && (
                      <div className="mb-6">
                        <h3 className="text-md font-semibold text-owl-blue-900 mb-2">Save Notes</h3>
                        <div className="bg-light-50 rounded-lg p-4 border border-light-200">
                          <p className="text-sm text-light-700 whitespace-pre-wrap">
                            {selectedVersion.save_notes}
                          </p>
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <FolderOpen className="w-16 h-16 mx-auto mb-4 text-light-400" />
                <p className="text-light-700 font-medium mb-2">Select a case to view details</p>
                <p className="text-sm text-light-600">
                  Choose a case from the list to see its versions, Cypher queries, and snapshots
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Create Case Modal */}
      <CaseModal
        isOpen={showCaseModal}
        onClose={() => setShowCaseModal(false)}
        onSave={handleCreateCase}
        existingCaseId={null}
        existingCaseName={null}
        nextVersion={1}
      />

      {/* Background Tasks Panel */}
      <BackgroundTasksPanel
        isOpen={showBackgroundTasksPanel}
        onClose={() => setShowBackgroundTasksPanel(false)}
        authUsername={authUsername}
        onViewCase={async (caseId, version) => {
          setShowBackgroundTasksPanel(false);
          // Find and select the case
          const caseToSelect = cases.find(c => c.id === caseId);
          if (caseToSelect) {
            await handleViewCase(caseToSelect);
            // If a specific version was requested, select it
            if (version) {
              setTimeout(() => {
                const fullCase = cases.find(c => c.id === caseId);
                if (fullCase && fullCase.versions) {
                  const versionToSelect = fullCase.versions.find(v => v.version === version);
                  if (versionToSelect) {
                    setSelectedVersion(versionToSelect);
                  }
                }
              }, 500);
            }
          }
        }}
      />

      {/* Documentation Viewer */}
      <DocumentationViewer
        isOpen={showDocumentation}
        onClose={() => setShowDocumentation(false)}
      />
    </div>
  );
}

