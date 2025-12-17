import React, { useState, useEffect } from 'react';
import { 
  Save, 
  Archive, 
  FolderOpen, 
  X, 
  FileDown,
  Eye,
  Trash2,
  Calendar,
  FileText,
  ChevronDown,
  ChevronRight,
  ArrowLeft
} from 'lucide-react';
import { casesAPI, snapshotsAPI } from '../services/api';

const FileManagementPanel = ({
  isOpen,
  onClose,
  // Snapshot props
  subgraphNodeKeys,
  onSaveSnapshot,
  onExportPDF,
  snapshots: initialSnapshots,
  onLoadSnapshot,
  onDeleteSnapshot,
  // Case props
  currentCaseId,
  currentCaseName,
  currentCaseVersion,
  onSaveCase,
  onLoadCase,
  onReturnToCaseManagement,
}) => {
  const [snapshots, setSnapshots] = useState(initialSnapshots || []);
  const [cases, setCases] = useState([]);
  const [loadingCases, setLoadingCases] = useState(false);
  const [selectedCase, setSelectedCase] = useState(null);
  const [selectedVersion, setSelectedVersion] = useState(null);
  const [snapshotsExpanded, setSnapshotsExpanded] = useState(false);
  const [casesExpanded, setCasesExpanded] = useState(false);
  const [olderVersionsExpanded, setOlderVersionsExpanded] = useState(false);

  useEffect(() => {
    if (isOpen) {
      loadCases();
      loadSnapshots();
    }
  }, [isOpen]);

  const loadSnapshots = async () => {
    try {
      const data = await snapshotsAPI.list();
      setSnapshots(data);
    } catch (err) {
      console.error('Failed to load snapshots:', err);
    }
  };

  const loadCases = async () => {
    setLoadingCases(true);
    try {
      const data = await casesAPI.list();
      setCases(data);
    } catch (err) {
      console.error('Failed to load cases:', err);
    } finally {
      setLoadingCases(false);
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
      // Select latest version by default (now first after sorting)
      if (fullCase.versions && fullCase.versions.length > 0) {
        setSelectedVersion(fullCase.versions[0]);
      }
    } catch (err) {
      console.error('Failed to load case:', err);
      alert(`Failed to load case: ${err.message}`);
    }
  };

  const handleLoadCaseVersion = () => {
    if (onLoadCase && selectedCase && selectedVersion) {
      onLoadCase(selectedCase, selectedVersion);
      onClose();
    }
  };

  const handleDeleteCase = async (caseId) => {
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

  const handleDeleteSnapshot = async (snapshotId) => {
    if (!confirm('Are you sure you want to delete this snapshot?')) {
      return;
    }

    try {
      await onDeleteSnapshot(snapshotId);
      await loadSnapshots();
    } catch (err) {
      console.error('Failed to delete snapshot:', err);
      alert(`Failed to delete snapshot: ${err.message}`);
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div 
        className="fixed inset-0 bg-black/20 z-40 transition-opacity"
        onClick={onClose}
      />
      
      {/* Panel */}
      <div className="fixed left-0 top-0 bottom-0 w-96 bg-white border-r border-light-200 shadow-xl z-50 flex flex-col overflow-hidden transform transition-transform duration-300 ease-in-out">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-light-200 flex-shrink-0">
          <h2 className="text-lg font-semibold text-owl-blue-900">File Management</h2>
          <div className="flex items-center gap-2">
            {onReturnToCaseManagement && (
              <button
                onClick={() => {
                  onClose();
                  onReturnToCaseManagement();
                }}
                className="p-1.5 hover:bg-light-100 rounded transition-colors"
                title="Return to Case Management"
              >
                <ArrowLeft className="w-5 h-5 text-owl-blue-600" />
              </button>
            )}
            <button
              onClick={onClose}
              className="p-1 hover:bg-light-100 rounded transition-colors"
              title="Close panel"
            >
              <X className="w-5 h-5 text-light-600" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {/* Snapshots Section */}
          <div className="p-4 border-b border-light-200">
            <div className="flex items-center gap-2 mb-4">
              <Archive className="w-5 h-5 text-owl-blue-700" />
              <h3 className="text-md font-semibold text-owl-blue-900">Snapshots</h3>
            </div>
            
            {/* Save Snapshot Button */}
            <button
              onClick={() => {
                onSaveSnapshot();
                loadSnapshots();
              }}
              disabled={subgraphNodeKeys.length === 0}
              className={`w-full flex items-center justify-center gap-2 px-4 py-2 rounded-md text-sm transition-colors mb-3 ${
                subgraphNodeKeys.length > 0
                  ? 'bg-owl-orange-500 hover:bg-owl-orange-600 text-white'
                  : 'bg-light-200 text-light-400 cursor-not-allowed'
              }`}
              title={subgraphNodeKeys.length > 0 ? 'Save current selection as snapshot' : 'Select nodes to save'}
            >
              <Save className="w-4 h-4" />
              Save Snapshot
            </button>

            {/* Snapshots List - Collapsible */}
            <div className="space-y-2">
              <button
                onClick={() => setSnapshotsExpanded(!snapshotsExpanded)}
                className="w-full flex items-center justify-between text-sm font-medium text-light-700 hover:text-owl-blue-900 transition-colors"
              >
                <span>Saved Snapshots ({snapshots.length})</span>
                {snapshotsExpanded ? (
                  <ChevronDown className="w-4 h-4" />
                ) : (
                  <ChevronRight className="w-4 h-4" />
                )}
              </button>
              {snapshotsExpanded && (
                <>
                  {snapshots.length === 0 ? (
                    <p className="text-xs text-light-500 italic">No snapshots saved yet</p>
                  ) : (
                    <div className="space-y-2 max-h-64 overflow-y-auto">
                      {snapshots.map((snapshot) => (
                        <div
                          key={snapshot.id}
                          className="p-3 bg-light-50 rounded-lg border border-light-200 hover:border-owl-blue-300 transition-colors"
                        >
                          <div className="flex items-start justify-between gap-2 mb-2">
                            <div className="flex-1 min-w-0">
                              <h5 className="font-medium text-owl-blue-900 truncate text-sm">{snapshot.name}</h5>
                              <p className="text-xs text-light-600 mt-1 line-clamp-2">{snapshot.notes || 'No notes'}</p>
                              <div className="flex items-center gap-2 mt-2 text-xs text-light-500">
                                <span>{snapshot.node_count} nodes</span>
                                <span>•</span>
                                <span>{snapshot.link_count} links</span>
                                {snapshot.case_name && (
                                  <>
                                    <span>•</span>
                                    <span className="text-owl-blue-600">{snapshot.case_name}</span>
                                  </>
                                )}
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-2 mt-2">
                            <button
                              onClick={() => onLoadSnapshot(snapshot)}
                              className="flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 bg-owl-blue-500 hover:bg-owl-blue-600 text-white rounded text-xs transition-colors"
                            >
                              <Eye className="w-3.5 h-3.5" />
                              Load
                            </button>
                            <button
                              onClick={() => onExportPDF(snapshot)}
                              className="flex items-center justify-center gap-1.5 px-2 py-1.5 bg-light-100 hover:bg-light-200 text-light-700 rounded text-xs transition-colors"
                              title="Export to PDF"
                            >
                              <FileDown className="w-3.5 h-3.5" />
                            </button>
                            <button
                              onClick={() => handleDeleteSnapshot(snapshot.id)}
                              className="flex items-center justify-center gap-1.5 px-2 py-1.5 bg-red-50 hover:bg-red-100 text-red-600 rounded text-xs transition-colors"
                              title="Delete snapshot"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>

          {/* Cases Section */}
          <div className="p-4">
            <div className="flex items-center gap-2 mb-4">
              <FolderOpen className="w-5 h-5 text-owl-blue-700" />
              <h3 className="text-md font-semibold text-owl-blue-900">Cases</h3>
            </div>
            
            {/* Save Case Button */}
            <button
              onClick={() => {
                onSaveCase();
                loadCases();
              }}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-owl-blue-500 hover:bg-owl-blue-600 text-white rounded-md text-sm transition-colors mb-3"
              title="Save current case"
            >
              <Save className="w-4 h-4" />
              {currentCaseId ? 'Save Case' : 'New Case'}
            </button>

            {/* Current Case Info */}
            {currentCaseId && (
              <div className="mb-3 p-2 bg-owl-blue-50 rounded border border-owl-blue-200">
                <p className="text-xs text-owl-blue-700 font-medium">Current Case</p>
                <p className="text-sm text-owl-blue-900 font-semibold">{currentCaseName || 'Unnamed Case'}</p>
                <p className="text-xs text-owl-blue-600">Version {currentCaseVersion}</p>
              </div>
            )}

            {/* Cases List - Collapsible */}
            <div className="space-y-2">
              <button
                onClick={() => setCasesExpanded(!casesExpanded)}
                className="w-full flex items-center justify-between text-sm font-medium text-light-700 hover:text-owl-blue-900 transition-colors"
              >
                <span>Saved Cases ({cases.length})</span>
                {casesExpanded ? (
                  <ChevronDown className="w-4 h-4" />
                ) : (
                  <ChevronRight className="w-4 h-4" />
                )}
              </button>
              {casesExpanded && (
                <>
                  {loadingCases ? (
                    <p className="text-xs text-light-500 italic">Loading cases...</p>
                  ) : cases.length === 0 ? (
                    <p className="text-xs text-light-500 italic">No cases saved yet</p>
                  ) : (
                    <div className="space-y-2">
                      {/* Cases List */}
                      <div className="max-h-48 overflow-y-auto space-y-2">
                        {cases.map((caseItem) => (
                          <div
                            key={caseItem.id}
                            onClick={() => handleViewCase(caseItem)}
                            className={`p-3 rounded-lg cursor-pointer transition-colors border ${
                              selectedCase?.id === caseItem.id
                                ? 'bg-owl-blue-100 border-owl-blue-300'
                                : 'bg-light-50 hover:bg-light-100 border-light-200'
                            }`}
                          >
                            <div className="flex items-start justify-between gap-2">
                              <div className="flex-1 min-w-0">
                                <h5 className="font-medium text-owl-blue-900 truncate text-sm">{caseItem.name}</h5>
                                <div className="flex items-center gap-2 mt-1 text-xs text-light-600">
                                  <span className="flex items-center gap-1">
                                    <Calendar className="w-3 h-3" />
                                    {formatDate(caseItem.updated_at)}
                                  </span>
                                  <span>•</span>
                                  <span>{caseItem.version_count || 0} version{(caseItem.version_count || 0) !== 1 ? 's' : ''}</span>
                                </div>
                              </div>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleDeleteCase(caseItem.id);
                                }}
                                className="p-1 hover:bg-light-200 rounded transition-colors"
                                title="Delete case"
                              >
                                <Trash2 className="w-4 h-4 text-red-500" />
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>

                      {/* Selected Case Versions */}
                      {selectedCase && selectedCase.versions && selectedCase.versions.length > 0 && (
                        <div className="mt-4 pt-4 border-t border-light-200">
                          <h5 className="text-sm font-semibold text-owl-blue-900 mb-2">
                            {selectedCase.name} - Versions
                          </h5>
                          
                          {/* Latest Version (Most Recent) */}
                          {selectedCase.versions[0] && (
                            <div className="mb-3">
                              <div className="text-xs text-light-600 mb-1 font-medium">Latest Version</div>
                              <div
                                onClick={() => setSelectedVersion(selectedCase.versions[0])}
                                className={`p-3 rounded-lg cursor-pointer transition-colors border ${
                                  selectedVersion?.version === selectedCase.versions[0].version
                                    ? 'bg-owl-blue-100 border-owl-blue-300'
                                    : 'bg-light-50 hover:bg-light-100 border-light-200'
                                }`}
                              >
                                <div className="flex items-center justify-between">
                                  <div className="flex items-center gap-2">
                                    <FileText className="w-4 h-4 text-owl-blue-600" />
                                    <span className="font-medium text-owl-blue-900 text-sm">Version {selectedCase.versions[0].version}</span>
                                  </div>
                                  <span className="text-xs text-light-600">
                                    {formatDate(selectedCase.versions[0].timestamp)}
                                  </span>
                                </div>
                                {selectedCase.versions[0].save_notes && (
                                  <p className="text-xs text-light-700 mt-1 line-clamp-2">{selectedCase.versions[0].save_notes}</p>
                                )}
                                <div className="text-xs text-light-600 mt-1">
                                  {selectedCase.versions[0].snapshots?.length || 0} snapshot{(selectedCase.versions[0].snapshots?.length || 0) !== 1 ? 's' : ''}
                                </div>
                              </div>
                            </div>
                          )}

                          {/* Older Versions (Collapsible) */}
                          {selectedCase.versions.length > 1 && (
                            <div>
                              <button
                                onClick={() => setOlderVersionsExpanded(!olderVersionsExpanded)}
                                className="w-full flex items-center justify-between text-xs font-medium text-light-700 hover:text-owl-blue-900 transition-colors mb-2"
                              >
                                <span>Older Versions ({selectedCase.versions.length - 1})</span>
                                {olderVersionsExpanded ? (
                                  <ChevronDown className="w-3.5 h-3.5" />
                                ) : (
                                  <ChevronRight className="w-3.5 h-3.5" />
                                )}
                              </button>
                              {olderVersionsExpanded && (
                                <div className="space-y-2 max-h-48 overflow-y-auto">
                                  {selectedCase.versions.slice(1).map((version) => (
                                    <div
                                      key={version.version}
                                      onClick={() => setSelectedVersion(version)}
                                      className={`p-2 rounded-lg cursor-pointer transition-colors border ${
                                        selectedVersion?.version === version.version
                                          ? 'bg-owl-blue-100 border-owl-blue-300'
                                          : 'bg-light-50 hover:bg-light-100 border-light-200'
                                      }`}
                                    >
                                      <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-2">
                                          <FileText className="w-3.5 h-3.5 text-owl-blue-600" />
                                          <span className="font-medium text-owl-blue-900 text-xs">Version {version.version}</span>
                                        </div>
                                        <span className="text-xs text-light-600">
                                          {formatDate(version.timestamp)}
                                        </span>
                                      </div>
                                      {version.save_notes && (
                                        <p className="text-xs text-light-700 mt-1 line-clamp-1">{version.save_notes}</p>
                                      )}
                                      <div className="text-xs text-light-600 mt-1">
                                        {version.snapshots?.length || 0} snapshot{(version.snapshots?.length || 0) !== 1 ? 's' : ''}
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}

                          {/* Load Button */}
                          {selectedVersion && (
                            <button
                              onClick={handleLoadCaseVersion}
                              className="w-full mt-3 flex items-center justify-center gap-2 px-4 py-2 bg-owl-orange-500 hover:bg-owl-orange-600 text-white rounded-lg transition-colors text-sm"
                            >
                              <Eye className="w-4 h-4" />
                              Load Version {selectedVersion.version}
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );
};

export default FileManagementPanel;

