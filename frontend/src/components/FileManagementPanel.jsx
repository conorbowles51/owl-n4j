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
  const [expandedSnapshotIds, setExpandedSnapshotIds] = useState(new Set());
  const [loadedSnapshotDetails, setLoadedSnapshotDetails] = useState({}); // Store full snapshot data by ID

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
          <div className="flex items-center gap-2">
            {onReturnToCaseManagement && (
              <button
                onClick={() => {
                  onClose();
                  onReturnToCaseManagement();
                }}
                className="p-1.5 hover:bg-light-100 rounded transition-colors"
                title="Case Management"
              >
                <FolderOpen className="w-5 h-5 text-owl-blue-600" />
              </button>
            )}
            <h2 className="text-lg font-semibold text-owl-blue-900">Case Management</h2>
          </div>
          <div className="flex items-center gap-2">
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
                    <div className="space-y-2 max-h-96 overflow-y-auto">
                      {snapshots.map((snapshot) => {
                        const isExpanded = expandedSnapshotIds.has(snapshot.id);
                        // Use loaded snapshot details if available, otherwise use snapshot from list
                        const displaySnapshot = loadedSnapshotDetails[snapshot.id] || snapshot;
                        
                        // Pre-load snapshot details to get ai_overview
                        if (!loadedSnapshotDetails[snapshot.id]) {
                          snapshotsAPI.get(snapshot.id).then(fullSnapshot => {
                            setLoadedSnapshotDetails(prev => ({
                              ...prev,
                              [snapshot.id]: fullSnapshot
                            }));
                          }).catch(err => {
                            console.warn(`Failed to pre-load snapshot ${snapshot.id}:`, err);
                          });
                        }
                        
                        return (
                          <div
                            key={snapshot.id}
                            className="bg-light-50 rounded-lg border border-light-200 hover:border-owl-blue-300 transition-colors"
                          >
                            <div className="p-3">
                              <div className="flex items-start justify-between gap-2 mb-2">
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-2 mb-1">
                                    <h5 className="font-medium text-owl-blue-900 truncate text-sm">{snapshot.name}</h5>
                                    <button
                                      onClick={async () => {
                                        const next = new Set(expandedSnapshotIds);
                                        if (next.has(snapshot.id)) {
                                          next.delete(snapshot.id);
                                        } else {
                                          next.add(snapshot.id);
                                          // Load full snapshot details if not already loaded
                                          if (!loadedSnapshotDetails[snapshot.id]) {
                                            try {
                                              const fullSnapshot = await snapshotsAPI.get(snapshot.id);
                                              setLoadedSnapshotDetails(prev => ({
                                                ...prev,
                                                [snapshot.id]: fullSnapshot
                                              }));
                                            } catch (err) {
                                              console.error('Failed to load snapshot details:', err);
                                            }
                                          }
                                        }
                                        setExpandedSnapshotIds(next);
                                      }}
                                      className="text-xs text-owl-blue-600 hover:text-owl-blue-700 flex items-center gap-1"
                                    >
                                      {isExpanded ? (
                                        <>
                                          <ChevronDown className="w-3 h-3" />
                                          Collapse
                                        </>
                                      ) : (
                                        <>
                                          <ChevronRight className="w-3 h-3" />
                                          Expand
                                        </>
                                      )}
                                    </button>
                                  </div>
                                  {/* AI Overview - Show in collapsed view if available */}
                                  {displaySnapshot.ai_overview && (
                                    <div className="mt-1 mb-1 p-1.5 bg-owl-blue-50 rounded border border-owl-blue-200">
                                      <p className="text-xs font-medium text-owl-blue-900 mb-0.5">AI Overview:</p>
                                      <p className="text-xs text-owl-blue-800 line-clamp-2">{displaySnapshot.ai_overview}</p>
                                    </div>
                                  )}
                                  <p className="text-xs text-light-600 mt-1 whitespace-pre-wrap">{snapshot.notes || 'No notes'}</p>
                                  <div className="flex items-center gap-2 mt-2 text-xs text-light-500">
                                    <span>
                                      {displaySnapshot.subgraph?.nodes?.length || 
                                       displaySnapshot.overview?.nodeCount || 
                                       displaySnapshot.node_count || 
                                       snapshot.node_count || 
                                       0} nodes
                                    </span>
                                    <span>•</span>
                                    <span>
                                      {displaySnapshot.subgraph?.links?.length || 
                                       displaySnapshot.overview?.linkCount || 
                                       displaySnapshot.link_count || 
                                       snapshot.link_count || 
                                       0} links
                                    </span>
                                    {snapshot.case_name && (
                                      <>
                                        <span>•</span>
                                        <span className="text-owl-blue-600">{snapshot.case_name}</span>
                                      </>
                                    )}
                                  </div>
                                </div>
                              </div>
                              
                              {/* Detailed Snapshot Information */}
                              {isExpanded && loadedSnapshotDetails[snapshot.id] && (() => {
                                const fullSnapshot = loadedSnapshotDetails[snapshot.id];
                                // Debug: log to see what we have
                                if (fullSnapshot && !fullSnapshot.ai_overview) {
                                  console.log('Snapshot loaded without ai_overview:', {
                                    id: fullSnapshot.id,
                                    name: fullSnapshot.name,
                                    hasAiOverview: !!fullSnapshot.ai_overview,
                                    keys: Object.keys(fullSnapshot)
                                  });
                                }
                                return (
                                  <div className="mt-3 pt-3 border-t border-light-200 space-y-3">
                                    {/* Snapshot Metadata */}
                                    <div className="mb-3 p-2 bg-light-50 rounded border border-light-200">
                                      <h6 className="text-xs font-semibold text-owl-blue-900 mb-1.5">Snapshot Information</h6>
                                      <div className="space-y-0.5 text-xs">
                                        <div className="flex items-center gap-2">
                                          <span className="text-light-600 w-20">Name:</span>
                                          <span className="font-medium text-owl-blue-900 truncate">{fullSnapshot.name || snapshot.name}</span>
                                        </div>
                                        {(fullSnapshot.timestamp || fullSnapshot.created_at || snapshot.timestamp) && (
                                          <div className="flex items-center gap-2">
                                            <span className="text-light-600 w-20">Created:</span>
                                            <span className="text-light-700 text-xs">{new Date(fullSnapshot.timestamp || fullSnapshot.created_at || snapshot.timestamp).toLocaleString()}</span>
                                          </div>
                                        )}
                                        {fullSnapshot.case_name && (
                                          <div className="flex items-center gap-2">
                                            <span className="text-light-600 w-20">Case:</span>
                                            <span className="text-light-700 truncate">{fullSnapshot.case_name}</span>
                                          </div>
                                        )}
                                        {fullSnapshot.case_version && (
                                          <div className="flex items-center gap-2">
                                            <span className="text-light-600 w-20">Version:</span>
                                            <span className="text-light-700">{fullSnapshot.case_version}</span>
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                    
                                    {/* AI Overview - At the top */}
                                    {fullSnapshot.ai_overview ? (
                                      <div className="mb-3 p-2 bg-owl-blue-50 rounded border border-owl-blue-200">
                                        <p className="text-xs font-medium text-owl-blue-900 mb-1">AI Overview:</p>
                                        <p className="text-xs text-owl-blue-800">{fullSnapshot.ai_overview}</p>
                                      </div>
                                    ) : (
                                      <div className="mb-3 p-2 bg-yellow-50 rounded border border-yellow-200">
                                        <p className="text-xs text-yellow-800 italic">No AI overview available for this snapshot</p>
                                      </div>
                                    )}
                                    
                                    {/* Notes */}
                                    {fullSnapshot.notes && (
                                      <div className="mb-3 p-2 bg-light-50 rounded border border-light-200">
                                        <p className="text-xs font-medium text-owl-blue-900 mb-1">Notes:</p>
                                        <p className="text-xs text-light-700 whitespace-pre-wrap">{fullSnapshot.notes}</p>
                                      </div>
                                    )}
                                    
                                    {/* Overview Nodes */}
                                    {fullSnapshot.overview && fullSnapshot.overview.nodes && fullSnapshot.overview.nodes.length > 0 && (
                                      <div>
                                        <h6 className="text-xs font-semibold text-owl-blue-900 mb-2 flex items-center gap-1">
                                          <FileText className="w-3 h-3" />
                                          Node Overview ({fullSnapshot.overview.nodes.length} nodes)
                                        </h6>
                                        <div className="space-y-2 max-h-48 overflow-y-auto">
                                          {fullSnapshot.overview.nodes.map((node, nodeIdx) => (
                                            <div key={nodeIdx} className="bg-white rounded p-2 border border-light-200">
                                              <div className="flex items-start justify-between gap-2 mb-1">
                                                <h7 className="font-medium text-owl-blue-900 text-xs">
                                                  {node.name || node.key}
                                                </h7>
                                                {node.type && (
                                                  <span className="text-xs px-1.5 py-0.5 rounded bg-owl-purple-100 text-owl-purple-700 flex-shrink-0">
                                                    {node.type}
                                                  </span>
                                                )}
                                              </div>
                                              {node.summary && (
                                                <p className="text-xs text-light-700 mt-1 line-clamp-2">
                                                  {node.summary}
                                                </p>
                                              )}
                                              {node.notes && (
                                                <p className="text-xs text-light-600 mt-1 italic line-clamp-1">
                                                  {node.notes}
                                                </p>
                                              )}
                                            </div>
                                          ))}
                                        </div>
                                      </div>
                                    )}

                                    {/* Citations */}
                                    {fullSnapshot.citations && Object.keys(fullSnapshot.citations).length > 0 && (
                                      <div>
                                        <h6 className="text-xs font-semibold text-owl-blue-900 mb-2 flex items-center gap-1">
                                          <FileText className="w-3 h-3" />
                                          Source Citations
                                        </h6>
                                        <div className="space-y-2 max-h-48 overflow-y-auto">
                                          {Object.values(fullSnapshot.citations).map((nodeCitation, idx) => (
                                            <div key={idx} className="bg-white rounded p-2 border border-light-200">
                                              <div className="font-medium text-owl-blue-900 text-xs mb-1">
                                                {nodeCitation.node_name} ({nodeCitation.node_type})
                                              </div>
                                              <div className="space-y-1">
                                                {nodeCitation.citations.map((citation, cIdx) => (
                                                  <div key={cIdx} className="text-xs text-light-700 pl-2 border-l-2 border-owl-blue-300">
                                                    <div className="flex items-center gap-1 flex-wrap">
                                                      <FileText className="w-3 h-3 text-owl-blue-600" />
                                                      <span className="font-medium">
                                                        {citation.source_doc}
                                                        {citation.page && `, page ${citation.page}`}
                                                      </span>
                                                      <span className="text-light-500">
                                                        ({citation.type === 'verified_fact' ? 'Verified Fact' : citation.type === 'ai_insight' ? 'AI Insight' : 'Property'})
                                                      </span>
                                                    </div>
                                                    {citation.fact_text && (
                                                      <p className="text-light-600 mt-0.5 italic line-clamp-1">
                                                        {citation.fact_text}
                                                      </p>
                                                    )}
                                                    {citation.verified_by && (
                                                      <p className="text-light-500 text-xs mt-0.5">
                                                        Verified by: {citation.verified_by}
                                                      </p>
                                                    )}
                                                  </div>
                                                ))}
                                              </div>
                                            </div>
                                          ))}
                                        </div>
                                      </div>
                                    )}

                                    {/* Timeline Events */}
                                    {fullSnapshot.timeline && Array.isArray(fullSnapshot.timeline) && fullSnapshot.timeline.length > 0 && (
                                      <div>
                                        <h6 className="text-xs font-semibold text-owl-blue-900 mb-2 flex items-center gap-1">
                                          <Calendar className="w-3 h-3" />
                                          Timeline Events ({fullSnapshot.timeline.length} events)
                                        </h6>
                                        <div className="space-y-2 max-h-48 overflow-y-auto">
                                          {fullSnapshot.timeline.slice(0, 5).map((event, eventIdx) => (
                                            <div key={eventIdx} className="bg-white rounded p-2 border border-light-200">
                                              <div className="flex items-start justify-between gap-2 mb-1">
                                                <span className="font-medium text-owl-blue-900 text-xs">
                                                  {event.name || event.key}
                                                </span>
                                                {event.type && (
                                                  <span className="text-xs px-1.5 py-0.5 rounded bg-owl-purple-100 text-owl-purple-700 flex-shrink-0">
                                                    {event.type}
                                                  </span>
                                                )}
                                              </div>
                                              {event.date && (
                                                <p className="text-xs text-light-600 mt-0.5">
                                                  {new Date(event.date).toLocaleDateString()}
                                                  {event.time && ` at ${event.time}`}
                                                </p>
                                              )}
                                              {event.summary && (
                                                <p className="text-xs text-light-700 mt-0.5 line-clamp-1">
                                                  {event.summary}
                                                </p>
                                              )}
                                            </div>
                                          ))}
                                          {fullSnapshot.timeline.length > 5 && (
                                            <p className="text-xs text-light-500 text-center py-1">
                                              ... and {fullSnapshot.timeline.length - 5} more events
                                            </p>
                                          )}
                                        </div>
                                      </div>
                                    )}

                                    {/* Chat History */}
                                    {fullSnapshot.chat_history && fullSnapshot.chat_history.length > 0 && (
                                      <div>
                                        <h6 className="text-xs font-semibold text-owl-blue-900 mb-2 flex items-center gap-1">
                                          <FileText className="w-3 h-3" />
                                          Chat History ({fullSnapshot.chat_history.length} messages)
                                        </h6>
                                        <div className="space-y-1 max-h-48 overflow-y-auto">
                                          {fullSnapshot.chat_history.map((msg, msgIdx) => (
                                            <div key={msgIdx} className="bg-white rounded p-2 border border-light-200">
                                              <div className="flex items-center gap-2 mb-0.5">
                                                <span className="text-xs font-medium text-owl-purple-600">
                                                  {msg.role === 'user' ? 'User' : 'AI'}
                                                </span>
                                                {msg.timestamp && (
                                                  <span className="text-xs text-light-500">
                                                    {new Date(msg.timestamp).toLocaleDateString()}
                                                  </span>
                                                )}
                                              </div>
                                              <p className="text-xs text-light-700 whitespace-pre-wrap line-clamp-2">
                                                {msg.content}
                                              </p>
                                              {msg.cypherUsed && (
                                                <p className="text-xs text-light-500 mt-0.5 italic">
                                                  Cypher query used
                                                </p>
                                              )}
                                            </div>
                                          ))}
                                        </div>
                                      </div>
                                    )}

                                    {/* Subgraph Statistics */}
                                    <div>
                                      <h6 className="text-xs font-semibold text-owl-blue-900 mb-2 flex items-center gap-1">
                                        <FileText className="w-3 h-3" />
                                        Subgraph Statistics
                                      </h6>
                                      <div className="bg-white rounded p-2 border border-light-200 text-xs">
                                        <div className="grid grid-cols-2 gap-2">
                                          <div>
                                            <span className="text-light-600">Nodes:</span>
                                            <span className="ml-2 font-medium text-owl-blue-900">
                                              {fullSnapshot.subgraph?.nodes?.length || fullSnapshot.overview?.nodeCount || fullSnapshot.node_count || snapshot.node_count || 0}
                                            </span>
                                          </div>
                                          <div>
                                            <span className="text-light-600">Links:</span>
                                            <span className="ml-2 font-medium text-owl-blue-900">
                                              {fullSnapshot.subgraph?.links?.length || fullSnapshot.overview?.linkCount || fullSnapshot.link_count || snapshot.link_count || 0}
                                            </span>
                                          </div>
                                          {fullSnapshot.timeline && Array.isArray(fullSnapshot.timeline) && (
                                            <div>
                                              <span className="text-light-600">Timeline:</span>
                                              <span className="ml-2 font-medium text-owl-blue-900">
                                                {fullSnapshot.timeline.length}
                                              </span>
                                            </div>
                                          )}
                                          {fullSnapshot.chat_history && Array.isArray(fullSnapshot.chat_history) && (
                                            <div>
                                              <span className="text-light-600">Chat:</span>
                                              <span className="ml-2 font-medium text-owl-blue-900">
                                                {fullSnapshot.chat_history.length}
                                              </span>
                                            </div>
                                          )}
                                        </div>
                                      </div>
                                    </div>
                                  </div>
                                );
                              })()}
                              
                              <div className="flex items-center gap-2 mt-3">
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
                          </div>
                        );
                      })}
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

