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
  ChevronDown,
  ChevronRight,
  ChevronLeft,
  Loader2,
  RefreshCw,
  UploadCloud,
  Search,
  Database,
  Upload,
  Download,
  HardDrive,
  Users,
  Shield,
  Crown,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { casesAPI, evidenceAPI, snapshotsAPI } from '../services/api';
import { useCasePermissions } from '../contexts/CasePermissionContext';
import CaseModal from './CaseModal';
import CreateUserModal from './CreateUserModal';
import BackgroundTasksPanel from './BackgroundTasksPanel';
import DocumentationViewer from './DocumentationViewer';
import SystemLogsPanel from './SystemLogsPanel';
import DatabaseModal from './DatabaseModal';
import FilePreview from './FilePreview';

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
  authDisplayName,
  onGoToEvidenceView,
  onGoToWorkspaceView,
  initialCaseToSelect,
  onCaseSelected,
  onViewDocument,
  onShowCollaboratorModal,
}) {
  // Permission context
  const {
    canEdit,
    canDelete,
    canInvite,
    canUploadEvidence,
    canCreateCase,
    isOwner,
    isSuperAdmin,
    isGuest,
    refreshPermissions,
  } = useCasePermissions();
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedCase, setSelectedCase] = useState(null);
  const [viewMode, setViewMode] = useState('my_cases'); // 'my_cases' or 'all_cases' (super admins only)
  const [selectedVersion, setSelectedVersion] = useState(null);
  const [showCaseModal, setShowCaseModal] = useState(false);
  const [showSnapshots, setShowSnapshots] = useState(true);
  const [showVersions, setShowVersions] = useState(true);
  const [showEvidenceFiles, setShowEvidenceFiles] = useState(true);
  const [showProcessingHistory, setShowProcessingHistory] = useState(true);
  const [isAccountDropdownOpen, setIsAccountDropdownOpen] = useState(false);
  const [evidenceFiles, setEvidenceFiles] = useState([]);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceLogs, setEvidenceLogs] = useState([]);
  const [logsLoading, setLogsLoading] = useState(false);
  const [showBackgroundTasksPanel, setShowBackgroundTasksPanel] = useState(false);
  const [showDocumentation, setShowDocumentation] = useState(false);
  const [showSystemLogs, setShowSystemLogs] = useState(false);
  const [showDatabaseModal, setShowDatabaseModal] = useState(false);
  const [showCreateUserModal, setShowCreateUserModal] = useState(false);
  const [backingUp, setBackingUp] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [restoreFile, setRestoreFile] = useState(null);
  // Filter states
  const [evidenceFilesFilter, setEvidenceFilesFilter] = useState('');
  const [selectedFileTypes, setSelectedFileTypes] = useState(new Set());
  const [versionsFilter, setVersionsFilter] = useState('');
  const [snapshotsFilter, setSnapshotsFilter] = useState('');
  // Collapsed states for versions and snapshots (default to showing only latest)
  const [expandedVersions, setExpandedVersions] = useState(new Set());
  const [expandedSnapshots, setExpandedSnapshots] = useState(new Set());
  const [loadedSnapshotDetails, setLoadedSnapshotDetails] = useState({}); // Store full snapshot data by ID
  const [loadingSnapshotIds, setLoadingSnapshotIds] = useState(new Set()); // Track which snapshots are currently being loaded
  const [showPreviousVersions, setShowPreviousVersions] = useState(false); // Show/hide previous versions
  const [previewedFile, setPreviewedFile] = useState(null); // Track which file is being previewed: {id, name, stored_path}
  // Case opening progress
  const [caseOpeningProgress, setCaseOpeningProgress] = useState({
    isOpen: false,
    caseName: null,
    current: 0,
    total: 0,
    message: '',
  });
  // Pagination states
  const [evidenceFilesPage, setEvidenceFilesPage] = useState(1);
  const [versionsPage, setVersionsPage] = useState(1);
  const [snapshotsPage, setSnapshotsPage] = useState(1);
  const itemsPerPage = 10;
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

  const loadCases = async (mode = viewMode) => {
    setLoading(true);
    try {
      const data = await casesAPI.list(mode);
      // Handle both new format { cases: [...], total: number } and legacy array format
      const casesList = Array.isArray(data) ? data : (data.cases || []);
      setCases(casesList);
    } catch (err) {
      console.error('Failed to load cases:', err);
      alert(`Failed to load cases: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  // Reload cases when viewMode changes (for super admins)
  useEffect(() => {
    if (isSuperAdmin) {
      loadCases(viewMode);
    }
  }, [viewMode, isSuperAdmin]);

  const handleViewCase = async (caseItem) => {
    // Use title if available (new API), fallback to name (legacy API)
    const caseDisplayName = caseItem.title || caseItem.name;

    // Show progress dialog
    setCaseOpeningProgress({
      isOpen: true,
      caseName: caseDisplayName,
      current: 0,
      total: 3, // Loading case, processing versions, loading snapshots
      message: 'Loading case data...',
    });

    // Refresh permissions for this case
    refreshPermissions(caseItem.id);

    try {
      // Step 1: Load case data
      setCaseOpeningProgress(prev => ({
        ...prev,
        current: 1,
        message: 'Fetching case information...',
      }));
      
      const fullCase = await casesAPI.get(caseItem.id);
      
      // Step 2: Process versions and snapshots
      setCaseOpeningProgress(prev => ({
        ...prev,
        current: 2,
        message: 'Processing versions and snapshots...',
      }));
      
      // Sort versions by version number descending (most recent first)
      if (fullCase.versions && fullCase.versions.length > 0) {
        fullCase.versions.sort((a, b) => b.version - a.version);
        // Sort snapshots by timestamp descending (most recent first) for each version
        fullCase.versions.forEach(version => {
          if (version.snapshots && version.snapshots.length > 0) {
            version.snapshots.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
          }
        });
      }
      
      setSelectedCase(fullCase);
      
      // Step 3: Load snapshot details
      setCaseOpeningProgress(prev => ({
        ...prev,
        current: 3,
        message: 'Loading snapshot details...',
      }));
      
      // Select latest version by default and expand only the latest
      if (fullCase.versions && fullCase.versions.length > 0) {
        setSelectedVersion(fullCase.versions[0]);
        // Expand only the latest version by default
        setExpandedVersions(new Set([fullCase.versions[0].version]));
        // Expand only the latest snapshot of the latest version by default
        if (fullCase.versions[0].snapshots && fullCase.versions[0].snapshots.length > 0) {
          const latestSnapshotId = fullCase.versions[0].snapshots[0].id;
          setExpandedSnapshots(new Set([latestSnapshotId]));
          // Load details for the latest snapshot
          await snapshotsAPI.get(latestSnapshotId).then(fullSnapshot => {
            setLoadedSnapshotDetails(prev => ({
              ...prev,
              [latestSnapshotId]: fullSnapshot
            }));
          }).catch(err => {
            console.error('Failed to load latest snapshot details:', err);
          });
        } else {
          setExpandedSnapshots(new Set());
        }
      } else {
        setExpandedVersions(new Set());
        setExpandedSnapshots(new Set());
      }
      
      // Reset filters and states when switching cases
      setEvidenceFilesFilter('');
      setSelectedFileTypes(new Set());
      setVersionsFilter('');
      setSnapshotsFilter('');
      setShowPreviousVersions(false);

      // Close progress dialog
      setCaseOpeningProgress(prev => ({ ...prev, isOpen: false }));
    } catch (err) {
      console.error('Failed to load case:', err);
      setCaseOpeningProgress(prev => ({ ...prev, isOpen: false }));
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

  const handleDeleteSnapshot = async (snapshotId, e) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to delete this snapshot? This action cannot be undone.')) {
      return;
    }

    try {
      await snapshotsAPI.delete(snapshotId);
      
      // Remove from loaded snapshot details
      setLoadedSnapshotDetails(prev => {
        const next = { ...prev };
        delete next[snapshotId];
        return next;
      });
      
      // Remove from expanded snapshots
      setExpandedSnapshots(prev => {
        const next = new Set(prev);
        next.delete(snapshotId);
        return next;
      });
      
      // Reload the case from the server to get the updated state
      // This ensures the snapshot is removed from case versions on the backend
      if (selectedCase) {
        try {
          const updatedCase = await casesAPI.get(selectedCase.id);
          setSelectedCase(updatedCase);
          
          // Update the selected version if it exists
          if (selectedVersion) {
            const updatedVersion = updatedCase.versions?.find(v => v.version === selectedVersion.version);
            if (updatedVersion) {
              setSelectedVersion(updatedVersion);
            }
          }
        } catch (err) {
          console.error('Failed to reload case after snapshot deletion:', err);
          // Fallback to local state update if reload fails
          if (selectedVersion) {
            const updatedVersions = selectedCase.versions.map(version => {
              if (version.version === selectedVersion.version) {
                const updatedSnapshots = (version.snapshots || []).filter(
                  snapshot => snapshot.id !== snapshotId
                );
                return {
                  ...version,
                  snapshots: updatedSnapshots
                };
              }
              return version;
            });
            setSelectedCase({
              ...selectedCase,
              versions: updatedVersions
            });
            const updatedVersion = updatedVersions.find(v => v.version === selectedVersion.version);
            if (updatedVersion) {
              setSelectedVersion(updatedVersion);
            }
          }
        }
      }
    } catch (err) {
      // If snapshot doesn't exist in storage (404), remove it from case version instead
      if (err?.message?.includes('not found') || err?.message?.includes('doesn\'t exist') || err?.status === 404) {
        try {
          console.log(`Snapshot ${snapshotId} not found in storage, removing from case version...`);
          if (!selectedCase) {
            throw new Error('No case selected');
          }
          
          // Collect all snapshots from all versions, filtering out the deleted one
          // This ensures the deleted snapshot won't be preserved when we save a new version
          const allSnapshotIds = new Set();
          const allSnapshots = [];
          
          // Collect from all versions (most recent first)
          const sortedVersions = [...(selectedCase.versions || [])].sort((a, b) => (b.version ?? 0) - (a.version ?? 0));
          for (const version of sortedVersions) {
            if (version.snapshots) {
              for (const snap of version.snapshots) {
                const snapId = snap?.id;
                // Skip the deleted snapshot and avoid duplicates
                if (snapId && snapId !== snapshotId && !allSnapshotIds.has(snapId)) {
                  allSnapshotIds.add(snapId);
                  allSnapshots.push(snap);
                }
              }
            }
          }
          
          // Save case with all snapshots except the deleted one
          await casesAPI.save({
            case_id: selectedCase.id,
            case_name: selectedCase.name,
            snapshots: allSnapshots,
            save_notes: `Removed snapshot ${snapshotId}`,
          });
            
            // Reload the case to get updated state
            const updatedCase = await casesAPI.get(selectedCase.id);
            setSelectedCase(updatedCase);
            
            // Update the selected version if it exists
            if (selectedVersion) {
              const updatedVersion = updatedCase.versions?.find(v => v.version === selectedVersion.version);
              if (updatedVersion) {
                setSelectedVersion(updatedVersion);
              } else {
                // If the selected version no longer exists, use the latest
                const newLatest = updatedCase.versions?.sort((a, b) => (b.version ?? 0) - (a.version ?? 0))[0];
                if (newLatest) {
                  setSelectedVersion(newLatest);
                }
              }
            }
          
          // Remove from loaded snapshot details
          setLoadedSnapshotDetails(prev => {
            const next = { ...prev };
            delete next[snapshotId];
            return next;
          });
          
          // Remove from expanded snapshots
          setExpandedSnapshots(prev => {
            const next = new Set(prev);
            next.delete(snapshotId);
            return next;
          });
        } catch (caseErr) {
          console.error('Failed to remove snapshot from case:', caseErr);
          alert('Snapshot not found in storage. Failed to remove from case version.');
        }
      } else {
        console.error('Failed to delete snapshot:', err);
        alert(`Failed to delete snapshot: ${err.message}`);
      }
    }
  };

  const handleLoadCase = async () => {
    if (!onLoadCase || !selectedCase) {
      return;
    }

    try {
      // Pass a default version object - versions are no longer used but App.jsx still expects the structure
      const defaultVersionData = { version: 1 };
      // Pass the version data to onLoadCase - graph data is loaded via case_id filter
      onLoadCase(selectedCase, defaultVersionData);
    } catch (err) {
      console.error('Failed to load version data:', err);
      alert(`Failed to load case version: ${err.message}`);
    }
  };

  const handleBackupCase = async () => {
    if (!selectedCase) return;
    
    setBackingUp(true);
    try {
      const blob = await casesAPI.backup(selectedCase.id, false); // Don't include files by default (can be large)
      
      // Create download link
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
      const caseName = selectedCase.title || selectedCase.name;
      a.download = `${caseName.replace(/[^a-z0-9]/gi, '_')}_${selectedCase.id}_${timestamp}.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      
      alert('Case backup downloaded successfully!');
    } catch (err) {
      console.error('Failed to backup case:', err);
      alert('Failed to backup case: ' + (err.message || 'Unknown error'));
    } finally {
      setBackingUp(false);
    }
  };

  const handleRestoreCase = async (event) => {
    const file = event.target.files?.[0];
    if (!file || !selectedCase) return;
    
    if (!file.name.endsWith('.zip')) {
      alert('Please select a valid backup ZIP file');
      return;
    }
    
    const restoreCaseName = selectedCase.title || selectedCase.name;
    if (!confirm(`Restore case "${restoreCaseName}" from backup? This will ${selectedCase.versions?.length > 0 ? 'overwrite' : 'create'} the case data.`)) {
      event.target.value = ''; // Reset file input
      return;
    }
    
    setRestoring(true);
    try {
      const result = await casesAPI.restore(selectedCase.id, file, true); // Overwrite existing
      
      if (result.success) {
        alert(`Case restored successfully!\n\nNodes: ${result.results?.nodes_imported || 0}\nRelationships: ${result.results?.relationships_imported || 0}\nDocuments: ${result.results?.documents_imported || 0}`);
        
        // Reload case data
        const updatedCase = await casesAPI.get(selectedCase.id);
        setSelectedCase(updatedCase);
      } else {
        const errors = result.results?.errors || [];
        alert(`Restore completed with errors:\n\n${errors.slice(0, 5).join('\n')}${errors.length > 5 ? `\n... and ${errors.length - 5} more` : ''}`);
      }
    } catch (err) {
      console.error('Failed to restore case:', err);
      alert('Failed to restore case: ' + (err.message || 'Unknown error'));
    } finally {
      setRestoring(false);
      event.target.value = ''; // Reset file input
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

  // Filter functions
  // Extract file extension/type from filename
  const getFileType = (filename) => {
    if (!filename) return 'unknown';
    const parts = filename.split('.');
    if (parts.length < 2) return 'no extension';
    return parts[parts.length - 1].toLowerCase();
  };

  // Get unique file types from evidence files
  const getUniqueFileTypes = (files) => {
    const types = new Set();
    files.forEach(file => {
      const type = getFileType(file.original_filename);
      types.add(type);
    });
    return Array.from(types).sort();
  };

  const filterEvidenceFiles = (files) => {
    let filtered = files;
    
    // Filter by text search
    if (evidenceFilesFilter.trim()) {
      const filterLower = evidenceFilesFilter.toLowerCase();
      filtered = filtered.filter(file => 
        file.original_filename?.toLowerCase().includes(filterLower)
      );
    }
    
    // Filter by file type
    if (selectedFileTypes.size > 0) {
      filtered = filtered.filter(file => {
        const fileType = getFileType(file.original_filename);
        return selectedFileTypes.has(fileType);
      });
    }
    
    return filtered;
  };

  const filterVersions = (versions) => {
    if (!versionsFilter.trim()) return versions;
    const filterLower = versionsFilter.toLowerCase();
    return versions.filter(version => 
      version.version?.toString().includes(filterLower) ||
      version.save_notes?.toLowerCase().includes(filterLower)
    );
  };

  const filterSnapshots = (snapshots) => {
    if (!snapshotsFilter.trim()) return snapshots;
    const filterLower = snapshotsFilter.toLowerCase();
    return snapshots.filter(snapshot => 
      snapshot.name?.toLowerCase().includes(filterLower) ||
      snapshot.notes?.toLowerCase().includes(filterLower)
    );
  };

  // Pagination helper function
  const paginate = (items, currentPage, itemsPerPage) => {
    const startIndex = (currentPage - 1) * itemsPerPage;
    const endIndex = startIndex + itemsPerPage;
    return {
      paginatedItems: items.slice(startIndex, endIndex),
      totalPages: Math.ceil(items.length / itemsPerPage),
      currentPage,
    };
  };

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
                  {isSuperAdmin && (
                    <button
                      onClick={() => {
                        setShowCreateUserModal(true);
                        setIsAccountDropdownOpen(false);
                      }}
                      className="w-full text-left px-2 py-1 rounded hover:bg-light-100 transition-colors text-sm text-dark-700"
                    >
                      Create User
                    </button>
                  )}
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
          {canCreateCase && (
            <button
              onClick={() => setShowCaseModal(true)}
              className="flex items-center gap-2 px-4 py-2 bg-owl-blue-500 hover:bg-owl-blue-600 text-white rounded-lg transition-colors"
            >
              <FolderPlus className="w-4 h-4" />
              Create New Case
            </button>
          )}
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar Flyout */}
        <div className="w-16 bg-white border-r border-light-200 flex flex-col items-center py-4 gap-2 flex-shrink-0">
          {/* System Logs Button */}
          <button
            onClick={() => setShowSystemLogs(!showSystemLogs)}
            className={`p-3 rounded-lg transition-colors relative ${
              showSystemLogs
                ? 'bg-owl-blue-500 text-white'
                : 'hover:bg-light-100 text-light-600'
            }`}
            title="System Logs"
          >
            <FileText className="w-5 h-5" />
          </button>

          {/* Database Button */}
          <button
            onClick={() => setShowDatabaseModal(!showDatabaseModal)}
            className={`p-3 rounded-lg transition-colors relative ${
              showDatabaseModal
                ? 'bg-owl-blue-500 text-white'
                : 'hover:bg-light-100 text-light-600'
            }`}
            title="Vector Database"
          >
            <Database className="w-5 h-5" />
          </button>
        </div>

        {/* Cases List - Left Panel */}
        <div className="w-1/3 border-r border-light-200 bg-white overflow-y-auto">
          <div className="p-4 border-b border-light-200">
            <h2 className="text-md font-semibold text-owl-blue-900 mb-1">
              {viewMode === 'all_cases' ? 'All Cases' : (authDisplayName ? `${authDisplayName.charAt(0).toUpperCase()}${authDisplayName.slice(1)}'s Cases` : 'Cases')}
            </h2>
            <p className="text-xs text-light-600">
              {loading
                ? 'Loading...'
                : `${cases.length} case${cases.length !== 1 ? 's' : ''} available`}
            </p>
          </div>

          {/* Super Admin Toggle */}
          {isSuperAdmin && (
            <div className="flex items-center gap-2 mx-2 mt-2 p-2 bg-purple-50 rounded-lg border border-purple-200">
              <Shield className="w-4 h-4 text-purple-600 flex-shrink-0" />
              <span className="text-sm text-purple-700">View:</span>
              <div className="flex gap-1">
                <button
                  onClick={() => setViewMode('my_cases')}
                  className={`px-2 py-1 text-xs rounded transition-colors ${
                    viewMode === 'my_cases'
                      ? 'bg-purple-600 text-white'
                      : 'bg-white text-purple-700 hover:bg-purple-100 border border-purple-300'
                  }`}
                >
                  My Cases
                </button>
                <button
                  onClick={() => setViewMode('all_cases')}
                  className={`px-2 py-1 text-xs rounded transition-colors ${
                    viewMode === 'all_cases'
                      ? 'bg-purple-600 text-white'
                      : 'bg-white text-purple-700 hover:bg-purple-100 border border-purple-300'
                  }`}
                >
                  All Cases
                </button>
              </div>
            </div>
          )}

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
                {isGuest
                  ? 'You will see cases here when you are invited to collaborate'
                  : 'Create your first case to start organizing your investigations'}
              </p>
              {canCreateCase && (
                <button
                  onClick={() => setShowCaseModal(true)}
                  className="px-4 py-2 bg-owl-blue-500 hover:bg-owl-blue-600 text-white rounded-lg transition-colors text-sm"
                >
                  Create New Case
                </button>
              )}
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
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="font-semibold text-owl-blue-900 truncate">
                          {caseItem.title || caseItem.name}
                        </h3>
                        {/* Role badges */}
                        {caseItem.user_role === 'owner' && (
                          <span className="inline-flex items-center gap-1 text-xs px-1.5 py-0.5 bg-amber-100 text-amber-700 rounded" title="You own this case">
                            <Crown className="w-3 h-3" />
                          </span>
                        )}
                        {caseItem.user_role === 'editor' && (
                          <span className="inline-flex items-center text-xs px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded" title="You can edit this case">
                            Editor
                          </span>
                        )}
                        {caseItem.user_role === 'viewer' && (
                          <span className="inline-flex items-center text-xs px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded" title="View only access">
                            Viewer
                          </span>
                        )}
                        {caseItem.user_role === 'admin_access' && (
                          <span className="inline-flex items-center gap-1 text-xs px-1.5 py-0.5 bg-purple-100 text-purple-700 rounded" title="Admin access">
                            <Shield className="w-3 h-3" />
                          </span>
                        )}
                      </div>
                      {/* Show owner name for non-owned cases */}
                      {!caseItem.is_owner && caseItem.owner_name && (
                        <p className="text-xs text-gray-500 mb-1">
                          by {caseItem.owner_name}
                        </p>
                      )}
                      {caseItem.description && (
                        <p className="text-xs text-light-700 mb-1 line-clamp-1">
                          {caseItem.description}
                        </p>
                      )}
                      <div className="flex items-center gap-3 text-xs text-light-600">
                        <span className="flex items-center gap-1">
                          <Calendar className="w-3 h-3" />
                          {formatDate(caseItem.updated_at)}
                        </span>
                        <span>{caseItem.version_count || 0} version{(caseItem.version_count || 0) !== 1 ? 's' : ''}</span>
                      </div>
                    </div>
                    {/* Delete button: shown for owners, super admins (canDelete), or cases with admin_access */}
                    {(caseItem.is_owner || caseItem.user_role === 'admin_access' || canDelete) && (
                      <button
                        onClick={(e) => handleDeleteCase(caseItem.id, e)}
                        className="p-1 hover:bg-light-200 rounded transition-colors ml-2 flex-shrink-0"
                        title="Delete case"
                      >
                        <Trash2 className="w-4 h-4 text-red-500" />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Case Details - Right Panel */}
        <div className="w-2/3 flex flex-col overflow-hidden">
          {selectedCase ? (
            <>
              {/* Case Header */}
              <div className="p-6 border-b border-light-200 bg-white">
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <div className="flex items-center gap-2 mb-2">
                      <h2 className="text-xl font-semibold text-owl-blue-900">
                        {selectedCase.title || selectedCase.name}
                      </h2>
                      {/* Role badges based on actual case data */}
                      {selectedCase.user_role === 'owner' && (
                        <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 bg-amber-100 text-amber-700 rounded" title="You own this case">
                          <Crown className="w-3 h-3" />
                          Owner
                        </span>
                      )}
                      {selectedCase.user_role === 'editor' && (
                        <span className="inline-flex items-center text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded" title="You can edit this case">
                          Editor
                        </span>
                      )}
                      {selectedCase.user_role === 'viewer' && (
                        <span className="inline-flex items-center text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded" title="View only access">
                          Viewer
                        </span>
                      )}
                      {selectedCase.user_role === 'admin_access' && (
                        <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 bg-purple-100 text-purple-700 rounded" title="Admin access">
                          <Shield className="w-3 h-3" />
                          Admin
                        </span>
                      )}
                    </div>
                    {/* Show owner name for non-owned cases */}
                    {!selectedCase.is_owner && selectedCase.owner_name && (
                      <p className="text-xs text-gray-500 mb-1">
                        Owned by {selectedCase.owner_name}
                      </p>
                    )}
                    {selectedCase.description && (
                      <p className="text-sm text-light-700 mb-2">
                        {selectedCase.description}
                      </p>
                    )}
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
                    {/* Collaborator Management Button - visible when user can invite */}
                    {canInvite && onShowCollaboratorModal && (
                      <button
                        onClick={() => onShowCollaboratorModal(selectedCase)}
                        className="flex items-center gap-2 px-3 py-2 border border-owl-blue-300 text-owl-blue-900 rounded-lg bg-white hover:bg-owl-blue-50 transition-colors text-sm"
                        title="Manage case collaborators"
                      >
                        <Users className="w-4 h-4" />
                        Collaborators
                      </button>
                    )}
                    <button
                      onClick={handleBackupCase}
                      disabled={backingUp}
                      className="flex items-center gap-2 px-3 py-2 border border-owl-blue-300 text-owl-blue-900 rounded-lg bg-white hover:bg-owl-blue-50 transition-colors text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                      title="Backup case data (Neo4j, Vector DB, metadata)"
                    >
                      {backingUp ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Download className="w-4 h-4" />
                      )}
                      {backingUp ? 'Backing up...' : 'Backup'}
                    </button>
                    <label className="flex items-center gap-2 px-3 py-2 border border-owl-blue-300 text-owl-blue-900 rounded-lg bg-white hover:bg-owl-blue-50 transition-colors text-sm cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed">
                      {restoring ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <HardDrive className="w-4 h-4" />
                      )}
                      {restoring ? 'Restoring...' : 'Restore'}
                      <input
                        type="file"
                        accept=".zip"
                        onChange={handleRestoreCase}
                        disabled={restoring}
                        className="hidden"
                      />
                    </label>
                    {/* Process Evidence - visible when user can upload evidence */}
                    {onGoToEvidenceView && canUploadEvidence && (
                      <button
                        onClick={() => onGoToEvidenceView(selectedCase)}
                        className="flex items-center gap-2 px-4 py-2 border border-owl-blue-300 text-owl-blue-900 rounded-lg bg-white hover:bg-owl-blue-50 transition-colors text-sm"
                      >
                        <UploadCloud className="w-4 h-4" />
                        Process Evidence
                      </button>
                    )}
                    {onGoToWorkspaceView && (
                      <button
                        onClick={() => onGoToWorkspaceView(selectedCase)}
                        className="flex items-center gap-2 px-4 py-2 bg-owl-purple-500 hover:bg-owl-purple-600 text-white rounded-lg transition-colors text-sm"
                      >
                        <FolderOpen className="w-4 h-4" />
                        Open Workspace
                      </button>
                    )}     
                    {selectedCase && (
                      <button
                        onClick={handleLoadCase}
                        className="flex items-center gap-2 px-4 py-2 bg-owl-orange-500 hover:bg-owl-orange-600 text-white rounded-lg transition-colors text-sm"
                      >
                        <Eye className="w-4 h-4" />
                        Open Case
                      </button>
                    )}
                  </div>
                </div>
              </div>

              {/* Case Content - Scrollable */}
              <div className="flex-1 overflow-y-auto p-6">
                {/* Selected Version Details - Snapshots at top */}
                {selectedVersion && (
                  <>
                    {/* Snapshots Section - Moved to top of case view */}
                    <div className="mb-6">
                      <div className="flex items-center gap-2 mb-2">
                        <button
                          onClick={() => setShowSnapshots(!showSnapshots)}
                          className="flex-1 flex items-center justify-between p-3 bg-light-100 hover:bg-light-200 rounded-lg transition-colors"
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
                        {showSnapshots && selectedVersion?.snapshots && selectedVersion.snapshots.length > 0 && (
                          <button
                            onClick={async () => {
                              if (!confirm(`Are you sure you want to delete ALL ${selectedVersion.snapshots.length} snapshots? This action cannot be undone.`)) {
                                return;
                              }
                              try {
                                await snapshotsAPI.deleteAll();
                                // Reload the case to reflect changes
                                if (selectedCase) {
                                  const updatedCase = await casesAPI.get(selectedCase.id);
                                  setSelectedCase(updatedCase);
                                  if (selectedVersion) {
                                    const updatedVersion = updatedCase.versions?.find(v => v.version === selectedVersion.version);
                                    if (updatedVersion) {
                                      setSelectedVersion(updatedVersion);
                                    }
                                  }
                                }
                                // Clear loaded snapshot details
                                setLoadedSnapshotDetails({});
                                setExpandedSnapshots(new Set());
                                alert('All snapshots deleted successfully');
                              } catch (err) {
                                console.error('Failed to delete all snapshots:', err);
                                alert(`Failed to delete all snapshots: ${err.message}`);
                              }
                            }}
                            className="px-3 py-2 text-sm text-red-600 hover:text-red-700 hover:bg-red-50 border border-red-300 rounded-lg transition-colors flex items-center gap-2"
                            title="Delete all snapshots"
                          >
                            <Trash2 className="w-4 h-4" />
                            Delete All
                          </button>
                        )}
                      </div>
                      {showSnapshots && (
                        <div className="ml-2">
                          {/* Filter Input */}
                          <div className="mb-2 relative">
                            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-light-400" />
                            <input
                              type="text"
                              placeholder="Filter by name or notes..."
                              value={snapshotsFilter}
                              onChange={(e) => {
                                setSnapshotsFilter(e.target.value);
                                setSnapshotsPage(1); // Reset to first page when filter changes
                              }}
                              className="w-full pl-8 pr-3 py-1.5 text-sm border border-light-300 rounded-md focus:outline-none focus:ring-2 focus:ring-owl-blue-500 focus:border-transparent"
                            />
                          </div>
                          <div className="space-y-2">
                            {selectedVersion.snapshots && selectedVersion.snapshots.length > 0 ? (() => {
                              // Ensure snapshots are sorted by most recent first
                              const sortedSnapshots = [...selectedVersion.snapshots].sort((a, b) => {
                                const dateA = new Date(a.timestamp || a.created_at || 0);
                                const dateB = new Date(b.timestamp || b.created_at || 0);
                                return dateB - dateA; // Most recent first
                              });
                              const filteredSnapshots = filterSnapshots(sortedSnapshots);
                              const { paginatedItems, totalPages, currentPage } = paginate(filteredSnapshots, snapshotsPage, itemsPerPage);
                              
                              return (
                                <>
                                  {paginatedItems.map((snapshot, index) => {
                                const isLatest = index === 0;
                                const isExpanded = expandedSnapshots.has(snapshot.id);
                                const shouldShow = isLatest || isExpanded;
                                // Use loaded snapshot details if available, otherwise use snapshot from version
                                const displaySnapshot = loadedSnapshotDetails[snapshot.id] || snapshot;
                                
                                // Pre-load snapshot details for visible snapshots to get ai_overview
                                // Use useEffect pattern to avoid render loops - check if already loaded or loading
                                if (shouldShow && !loadedSnapshotDetails[snapshot.id] && !loadingSnapshotIds.has(snapshot.id)) {
                                  // Mark as loading to prevent duplicate requests
                                  setLoadingSnapshotIds(prev => new Set(prev).add(snapshot.id));
                                  snapshotsAPI.get(snapshot.id).then(fullSnapshot => {
                                    setLoadedSnapshotDetails(prev => ({
                                      ...prev,
                                      [snapshot.id]: fullSnapshot
                                    }));
                                    // Remove from loading set
                                    setLoadingSnapshotIds(prev => {
                                      const next = new Set(prev);
                                      next.delete(snapshot.id);
                                      return next;
                                    });
                                  }).catch(err => {
                                    console.warn(`Failed to pre-load snapshot ${snapshot.id}:`, err);
                                    // Remove from loading set on error
                                    setLoadingSnapshotIds(prev => {
                                      const next = new Set(prev);
                                      next.delete(snapshot.id);
                                      return next;
                                    });
                                  });
                                }
                                
                                return (
                                  <div
                                    key={snapshot.id}
                                    className="p-4 bg-white rounded-lg border border-light-200"
                                  >
                                    <div className="flex items-start justify-between mb-2">
                                      <div className="flex-1">
                                        <div className="flex items-center gap-2 mb-1">
                                          <h4 className="font-medium text-owl-blue-900">
                                            {snapshot.name}
                                          </h4>
                                          {isLatest && (
                                            <span className="text-xs bg-owl-blue-100 text-owl-blue-700 px-2 py-0.5 rounded">
                                              Latest
                                            </span>
                                          )}
                                          <button
                                            onClick={async () => {
                                              const next = new Set(expandedSnapshots);
                                              if (next.has(snapshot.id)) {
                                                next.delete(snapshot.id);
                                              } else {
                                                next.add(snapshot.id);
                                                // Load full snapshot details if not already loaded or loading
                                                if (!loadedSnapshotDetails[snapshot.id] && !loadingSnapshotIds.has(snapshot.id)) {
                                                  try {
                                                    // Mark as loading to prevent duplicate requests
                                                    setLoadingSnapshotIds(prev => new Set(prev).add(snapshot.id));
                                                    const fullSnapshot = await snapshotsAPI.get(snapshot.id);
                                                    console.log('Loaded snapshot details:', {
                                                      id: fullSnapshot.id,
                                                      hasAiOverview: !!fullSnapshot.ai_overview,
                                                      aiOverview: fullSnapshot.ai_overview?.substring(0, 100) || 'null'
                                                    });
                                                    setLoadedSnapshotDetails(prev => ({
                                                      ...prev,
                                                      [snapshot.id]: fullSnapshot
                                                    }));
                                                    // Remove from loading set
                                                    setLoadingSnapshotIds(prev => {
                                                      const next = new Set(prev);
                                                      next.delete(snapshot.id);
                                                      return next;
                                                    });
                                                  } catch (err) {
                                                    console.error('Failed to load snapshot details:', err);
                                                    // Remove from loading set on error
                                                    setLoadingSnapshotIds(prev => {
                                                      const next = new Set(prev);
                                                      next.delete(snapshot.id);
                                                      return next;
                                                    });
                                                  }
                                                }
                                              }
                                              setExpandedSnapshots(next);
                                            }}
                                            className="text-xs text-owl-blue-600 hover:text-owl-blue-700"
                                          >
                                            {isExpanded ? 'Collapse' : 'Expand'}
                                          </button>
                                        </div>
                                      </div>
                                      <button
                                        onClick={(e) => handleDeleteSnapshot(snapshot.id, e)}
                                        className="p-1 hover:bg-light-200 rounded transition-colors ml-2 flex-shrink-0"
                                        title="Delete snapshot"
                                      >
                                        <Trash2 className="w-4 h-4 text-red-500" />
                                      </button>
                                    </div>
                                    {shouldShow && (
                                      <>
                                        {/* Show summary info only when NOT expanded */}
                                        {!isExpanded && (
                                          <>
                                            {/* AI Overview - Show in collapsed view if available */}
                                            {displaySnapshot.ai_overview && (
                                              <div className="mb-2 p-2 bg-owl-blue-50 rounded border border-owl-blue-200">
                                                <p className="text-xs font-medium text-owl-blue-900 mb-1">AI Overview:</p>
                                                <div className="text-xs text-owl-blue-800 line-clamp-3 prose prose-sm max-w-none">
                                                  <ReactMarkdown>{displaySnapshot.ai_overview}</ReactMarkdown>
                                                </div>
                                              </div>
                                            )}
                                            {snapshot.notes && (
                                              <div className="mb-2 p-2 bg-light-50 rounded border border-light-200">
                                                <p className="text-xs font-medium text-owl-blue-900 mb-1">Notes:</p>
                                                <p className="text-xs text-light-700 line-clamp-2 whitespace-pre-wrap">{snapshot.notes}</p>
                                              </div>
                                            )}
                                            <div className="flex items-center gap-4 text-xs text-light-600 mb-3">
                                              <span>{snapshot.node_count || 0} nodes</span>
                                              <span>•</span>
                                              <span>{snapshot.link_count || 0} links</span>
                                              <span>•</span>
                                              <span>{formatDate(snapshot.timestamp)}</span>
                                            </div>
                                          </>
                                        )}
                                            
                                            {/* Detailed Snapshot Information - Only show when expanded */}
                                            {isExpanded && loadedSnapshotDetails[snapshot.id] && (() => {
                                              const fullSnapshot = loadedSnapshotDetails[snapshot.id];
                                              // Debug: log to see what we have
                                              console.log('Expanded snapshot details:', {
                                                id: fullSnapshot.id,
                                                name: fullSnapshot.name,
                                                hasAiOverview: !!fullSnapshot.ai_overview,
                                                aiOverview: fullSnapshot.ai_overview?.substring(0, 50) || 'null',
                                                hasSubgraph: !!fullSnapshot.subgraph,
                                                subgraphNodes: fullSnapshot.subgraph?.nodes?.length || 0,
                                                subgraphLinks: fullSnapshot.subgraph?.links?.length || 0,
                                                hasOverview: !!fullSnapshot.overview,
                                                overviewNodes: fullSnapshot.overview?.nodes?.length || 0,
                                                hasCitations: !!fullSnapshot.citations,
                                                citationsCount: fullSnapshot.citations ? Object.keys(fullSnapshot.citations).length : 0,
                                                hasTimeline: !!fullSnapshot.timeline,
                                                timelineCount: fullSnapshot.timeline?.length || 0,
                                                nodeCount: fullSnapshot.node_count || snapshot.node_count,
                                                linkCount: fullSnapshot.link_count || snapshot.link_count,
                                                keys: Object.keys(fullSnapshot)
                                              });
                                              return (
                                                <div className="mt-4 space-y-4 border-t border-light-200 pt-4">
                                                  {/* Snapshot Metadata */}
                                                  <div className="mb-3 p-3 bg-light-50 rounded-lg border border-light-200">
                                                    <h5 className="text-sm font-semibold text-owl-blue-900 mb-2">Snapshot Information</h5>
                                                    <div className="space-y-1 text-xs">
                                                      <div className="flex items-center gap-2">
                                                        <span className="text-light-600 w-24">Name:</span>
                                                        <span className="font-medium text-owl-blue-900">{fullSnapshot.name || snapshot.name}</span>
                                                      </div>
                                                      {(fullSnapshot.timestamp || fullSnapshot.created_at || snapshot.timestamp) && (
                                                        <div className="flex items-center gap-2">
                                                          <span className="text-light-600 w-24">Created:</span>
                                                          <span className="text-light-700">{formatDate(fullSnapshot.timestamp || fullSnapshot.created_at || snapshot.timestamp)}</span>
                                                        </div>
                                                      )}
                                                      {fullSnapshot.case_name && (
                                                        <div className="flex items-center gap-2">
                                                          <span className="text-light-600 w-24">Case:</span>
                                                          <span className="text-light-700">{fullSnapshot.case_name}</span>
                                                        </div>
                                                      )}
                                                      {fullSnapshot.case_version && (
                                                        <div className="flex items-center gap-2">
                                                          <span className="text-light-600 w-24">Version:</span>
                                                          <span className="text-light-700">{fullSnapshot.case_version}</span>
                                                        </div>
                                                      )}
                                                      {fullSnapshot.case_id && (
                                                        <div className="flex items-center gap-2">
                                                          <span className="text-light-600 w-24">Case ID:</span>
                                                          <span className="text-light-700 font-mono text-xs">{fullSnapshot.case_id}</span>
                                                        </div>
                                                      )}
                                                      {fullSnapshot.owner && (
                                                        <div className="flex items-center gap-2">
                                                          <span className="text-light-600 w-24">Owner:</span>
                                                          <span className="text-light-700">{fullSnapshot.owner}</span>
                                                        </div>
                                                      )}
                                                    </div>
                                                  </div>
                                                  
                                                  {/* AI Overview - At the top */}
                                                  {fullSnapshot.ai_overview ? (
                                                    <div className="mb-3 p-3 bg-owl-blue-50 rounded-lg border border-owl-blue-200">
                                                      <p className="text-sm font-medium text-owl-blue-900 mb-1">AI Overview:</p>
                                                      <div className="text-sm text-owl-blue-800 prose prose-sm max-w-none">
                                                        <ReactMarkdown>{fullSnapshot.ai_overview}</ReactMarkdown>
                                                      </div>
                                                    </div>
                                                  ) : (
                                                    <div className="mb-3 p-3 bg-yellow-50 rounded-lg border border-yellow-200">
                                                      <p className="text-xs text-yellow-800 italic">No AI overview available for this snapshot</p>
                                                    </div>
                                                  )}
                                                  
                                                  {/* Notes */}
                                                  {fullSnapshot.notes && (
                                                    <div className="mb-3 p-3 bg-light-50 rounded-lg border border-light-200">
                                                      <p className="text-sm font-medium text-owl-blue-900 mb-1">Notes:</p>
                                                      <p className="text-sm text-light-700 whitespace-pre-wrap">{fullSnapshot.notes}</p>
                                                    </div>
                                                  )}
                                                  
                                                  {/* Overview Nodes - Always show section */}
                                                  <div>
                                                    {(() => {
                                                      const nodes = fullSnapshot.overview?.nodes || fullSnapshot.subgraph?.nodes || [];
                                                      return nodes.length > 0 ? (
                                                        <>
                                                          <h5 className="text-sm font-semibold text-owl-blue-900 mb-2 flex items-center gap-2">
                                                            <FileText className="w-4 h-4" />
                                                            Node Overview ({nodes.length} nodes)
                                                          </h5>
                                                          <div className="space-y-3 max-h-64 overflow-y-auto">
                                                            {nodes.map((node, nodeIdx) => (
                                                              <div key={nodeIdx} className="bg-light-50 rounded p-3 border border-light-200">
                                                                <div className="flex items-start justify-between gap-2 mb-1">
                                                                  <h6 className="font-medium text-owl-blue-900 text-sm">
                                                                    {node.name || node.key}
                                                                  </h6>
                                                                  {node.type && (
                                                                    <span className="text-xs px-2 py-0.5 rounded bg-owl-purple-100 text-owl-purple-700 flex-shrink-0">
                                                                      {node.type}
                                                                    </span>
                                                                  )}
                                                                </div>
                                                                {node.summary && (
                                                                  <p className="text-xs text-light-700 mt-1 line-clamp-3">
                                                                    {node.summary}
                                                                  </p>
                                                                )}
                                                                {node.notes && (
                                                                  <p className="text-xs text-light-600 mt-1 italic line-clamp-2">
                                                                    {node.notes}
                                                                  </p>
                                                                )}
                                                              </div>
                                                            ))}
                                                          </div>
                                                        </>
                                                      ) : (
                                                        <>
                                                          <h5 className="text-sm font-semibold text-owl-blue-900 mb-2 flex items-center gap-2">
                                                            <FileText className="w-4 h-4" />
                                                            Node Overview
                                                          </h5>
                                                          <p className="text-xs text-light-500 italic p-2 bg-light-50 rounded border border-light-200">
                                                            No node data available for this snapshot
                                                          </p>
                                                        </>
                                                      );
                                                    })()}
                                                  </div>

                                                  {/* Citations - Always show section */}
                                                  <div>
                                                    <h5 className="text-sm font-semibold text-owl-blue-900 mb-2 flex items-center gap-2">
                                                      <FileText className="w-4 h-4" />
                                                      Source Citations
                                                      {fullSnapshot.citations && Object.keys(fullSnapshot.citations).length > 0 && 
                                                        ` (${Object.keys(fullSnapshot.citations).length} nodes)`}
                                                    </h5>
                                                    {!fullSnapshot.citations || Object.keys(fullSnapshot.citations).length === 0 ? (
                                                      <p className="text-xs text-light-500 italic p-2 bg-light-50 rounded border border-light-200">
                                                        No citations available for this snapshot
                                                      </p>
                                                    ) : (
                                                      <div className="space-y-3 max-h-64 overflow-y-auto">
                                                        {Object.values(fullSnapshot.citations).map((nodeCitation, idx) => (
                                                          <div key={idx} className="bg-light-50 rounded p-3 border border-light-200">
                                                            <div className="font-medium text-owl-blue-900 text-sm mb-2">
                                                              {nodeCitation.node_name} ({nodeCitation.node_type})
                                                            </div>
                                                            <div className="space-y-2">
                                                              {nodeCitation.citations.map((citation, cIdx) => (
                                                                <div key={cIdx} className="text-xs text-light-700 pl-2 border-l-2 border-owl-blue-300" onClick={(e) => e.stopPropagation()}>
                                                                  <div className="flex items-center gap-2 flex-wrap">
                                                                    <FileText className="w-3 h-3 text-owl-blue-600" />
                                                                    {onViewDocument ? (
                                                                      <span
                                                                        onClick={(e) => {
                                                                          e.preventDefault();
                                                                          e.stopPropagation();
                                                                          // Pass the selected case ID if available
                                                                          const caseId = selectedCase?.id || fullSnapshot?.case_id || null;
                                                                          if (onViewDocument && typeof onViewDocument === 'function') {
                                                                            onViewDocument(citation.source_doc, citation.page, caseId);
                                                                          }
                                                                        }}
                                                                        style={{ pointerEvents: 'auto', zIndex: 10, position: 'relative' }}
                                                                        className="font-medium text-owl-blue-600 hover:text-owl-blue-800 hover:underline transition-colors cursor-pointer"
                                                                        title={`View source: ${citation.source_doc}${citation.page ? `, page ${citation.page}` : ''}`}
                                                                        role="button"
                                                                        tabIndex={0}
                                                                        onKeyDown={(e) => {
                                                                          if (e.key === 'Enter' || e.key === ' ') {
                                                                            e.preventDefault();
                                                                            e.stopPropagation();
                                                                            const caseId = selectedCase?.id || fullSnapshot?.case_id || null;
                                                                            onViewDocument(citation.source_doc, citation.page, caseId);
                                                                          }
                                                                        }}
                                                                      >
                                                                        {citation.source_doc}
                                                                        {citation.page && `, page ${citation.page}`}
                                                                      </span>
                                                                    ) : (
                                                                      <span className="font-medium">
                                                                        {citation.source_doc}
                                                                        {citation.page && `, page ${citation.page}`}
                                                                      </span>
                                                                    )}
                                                                    <span className="text-light-500">
                                                                      ({citation.type === 'verified_fact' ? 'Verified Fact' : citation.type === 'ai_insight' ? 'AI Insight' : 'Property'})
                                                                    </span>
                                                                  </div>
                                                                  {citation.fact_text && (
                                                                    <p className="text-light-600 mt-1 italic line-clamp-2">
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
                                                    )}
                                                  </div>
                                                  
                                                  {/* Timeline Events - Always show section */}
                                                  <div>
                                                    <h5 className="text-sm font-semibold text-owl-blue-900 mb-2 flex items-center gap-2">
                                                      <Calendar className="w-4 h-4" />
                                                      Timeline Events
                                                      {fullSnapshot.timeline && Array.isArray(fullSnapshot.timeline) && fullSnapshot.timeline.length > 0 && 
                                                        ` (${fullSnapshot.timeline.length} events)`}
                                                    </h5>
                                                    {!fullSnapshot.timeline || !Array.isArray(fullSnapshot.timeline) || fullSnapshot.timeline.length === 0 ? (
                                                      <p className="text-xs text-light-500 italic p-2 bg-light-50 rounded border border-light-200">
                                                        No timeline events available for this snapshot
                                                      </p>
                                                    ) : (
                                                      <div className="space-y-3 max-h-64 overflow-y-auto">
                                                        {fullSnapshot.timeline.map((event, eventIdx) => (
                                                          <div key={eventIdx} className="bg-light-50 rounded p-3 border border-light-200">
                                                            <div className="flex items-start justify-between gap-2 mb-1">
                                                              <span className="font-medium text-owl-blue-900 text-sm">
                                                                {event.name || event.key}
                                                              </span>
                                                              {event.type && (
                                                                <span className="text-xs px-2 py-0.5 rounded bg-owl-purple-100 text-owl-purple-700 flex-shrink-0">
                                                                  {event.type}
                                                                </span>
                                                              )}
                                                            </div>
                                                            {event.date && (
                                                              <p className="text-xs text-light-600 mt-1">
                                                                {formatDate(event.date)}
                                                                {event.time && ` at ${event.time}`}
                                                              </p>
                                                            )}
                                                            {event.summary && (
                                                              <p className="text-xs text-light-700 mt-1 line-clamp-2">
                                                                {event.summary}
                                                              </p>
                                                            )}
                                                          </div>
                                                        ))}
                                                      </div>
                                                    )}
                                                  </div>
                                                  
                                                  {/* Chat History */}
                                                  {fullSnapshot.chat_history && fullSnapshot.chat_history.length > 0 && (
                                                    <div>
                                                      <h5 className="text-sm font-semibold text-owl-blue-900 mb-2 flex items-center gap-2">
                                                        <FileText className="w-4 h-4" />
                                                        Chat History ({fullSnapshot.chat_history.length} messages)
                                                      </h5>
                                                      <div className="space-y-2 max-h-64 overflow-y-auto">
                                                        {fullSnapshot.chat_history.map((msg, msgIdx) => (
                                                          <div key={msgIdx} className="bg-light-50 rounded p-2 border border-light-200">
                                                            <div className="flex items-center gap-2 mb-1">
                                                              <span className="text-xs font-medium text-owl-purple-600">
                                                                {msg.role === 'user' ? 'User' : 'AI'}
                                                              </span>
                                                              {msg.timestamp && (
                                                                <span className="text-xs text-light-500">
                                                                  {formatDate(msg.timestamp)}
                                                                </span>
                                                              )}
                                                            </div>
                                                            <p className="text-xs text-light-700 whitespace-pre-wrap line-clamp-4">
                                                              {msg.content}
                                                            </p>
                                                            {msg.cypherUsed && (
                                                              <p className="text-xs text-light-500 mt-1 italic">
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
                                                    <h5 className="text-sm font-semibold text-owl-blue-900 mb-2 flex items-center gap-2">
                                                      <FileText className="w-4 h-4" />
                                                      Subgraph Statistics
                                                    </h5>
                                                    <div className="bg-light-50 rounded p-3 border border-light-200 text-xs">
                                                      <div className="grid grid-cols-2 gap-2">
                                                        <div>
                                                          <span className="text-light-600">Nodes:</span>
                                                          <span className="ml-2 font-medium text-owl-blue-900">
                                                            {fullSnapshot.subgraph?.nodes?.length || fullSnapshot.node_count || snapshot.node_count || 0}
                                                          </span>
                                                        </div>
                                                        <div>
                                                          <span className="text-light-600">Links:</span>
                                                          <span className="ml-2 font-medium text-owl-blue-900">
                                                            {fullSnapshot.subgraph?.links?.length || fullSnapshot.link_count || snapshot.link_count || 0}
                                                          </span>
                                                        </div>
                                                      </div>
                                                    </div>
                                                  </div>
                                                </div>
                                              );
                                            })()}
                                      </>
                                    )}
                                  </div>
                                );
                              })}
                              {totalPages > 1 && (
                                    <div className="flex items-center justify-between mt-3 pt-3 border-t border-light-200">
                                      <button
                                        onClick={() => setSnapshotsPage(prev => Math.max(1, prev - 1))}
                                        disabled={currentPage === 1}
                                        className="px-3 py-1 text-xs text-owl-blue-600 hover:text-owl-blue-700 disabled:text-light-400 disabled:cursor-not-allowed flex items-center gap-1"
                                      >
                                        <ChevronLeft className="w-3 h-3" />
                                        Previous
                                      </button>
                                      <span className="text-xs text-light-600">
                                        Page {currentPage} of {totalPages} ({filteredSnapshots.length} total)
                                      </span>
                                      <button
                                        onClick={() => setSnapshotsPage(prev => Math.min(totalPages, prev + 1))}
                                        disabled={currentPage === totalPages}
                                        className="px-3 py-1 text-xs text-owl-blue-600 hover:text-owl-blue-700 disabled:text-light-400 disabled:cursor-not-allowed flex items-center gap-1"
                                      >
                                        Next
                                        <ChevronRight className="w-3 h-3" />
                                      </button>
                                    </div>
                                  )}
                                </>
                              );
                            })() : (
                              <p className="text-sm text-light-600 italic ml-4">No snapshots in this version</p>
                            )}
                            {filterSnapshots(selectedVersion.snapshots || []).length === 0 && selectedVersion.snapshots && selectedVersion.snapshots.length > 0 && (
                              <p className="text-sm text-light-600 italic text-center py-2">
                                No snapshots match the filter
                              </p>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  </>
                )}

                {/* Evidence Files Section */}
                <div className="mb-6">
                  <div className="flex items-center gap-2 mb-2">
                    <button
                      onClick={() => setShowEvidenceFiles(!showEvidenceFiles)}
                      className="flex-1 flex items-center justify-between p-3 bg-light-100 hover:bg-light-200 rounded-lg transition-colors"
                    >
                      <div className="flex items-center gap-2">
                        <FolderOpen className="w-5 h-5 text-owl-blue-700" />
                        <h3 className="text-md font-semibold text-owl-blue-900">
                          Evidence Files
                        </h3>
                        <span className="text-xs text-light-600 bg-white px-2 py-0.5 rounded">
                          {evidenceFiles.length}
                        </span>
                      </div>
                      {showEvidenceFiles ? (
                        <ChevronDown className="w-4 h-4 text-light-600" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-light-600" />
                      )}
                    </button>
                    {showEvidenceFiles && (
                      <button
                        onClick={() => {
                          if (selectedCase) {
                            loadEvidenceForCase(selectedCase.id);
                          }
                        }}
                        className="flex items-center gap-1 px-3 py-2 text-xs text-light-600 hover:text-owl-blue-700 border border-light-300 rounded-lg bg-white hover:bg-light-50 transition-colors"
                        title="Refresh evidence files"
                      >
                        <RefreshCw
                          className={`w-3 h-3 ${
                            evidenceLoading ? 'animate-spin' : ''
                          }`}
                        />
                        Refresh
                      </button>
                    )}
                  </div>
                  {showEvidenceFiles && (
                    <div className="ml-2">
                      {/* File Preview - moved above file list */}
                      {previewedFile && selectedCase && (
                        <div className="mb-4 pb-4 border-b border-light-200">
                          <FilePreview
                            caseId={selectedCase.id}
                            filePath={previewedFile.stored_path}
                            fileName={previewedFile.name}
                            fileType="file"
                            onClose={() => setPreviewedFile(null)}
                          />
                        </div>
                      )}
                      
                      {/* Filter Input */}
                      <div className="mb-2 relative">
                        <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-light-400" />
                        <input
                          type="text"
                          placeholder="Filter by filename..."
                          value={evidenceFilesFilter}
                          onChange={(e) => {
                            setEvidenceFilesFilter(e.target.value);
                            setEvidenceFilesPage(1); // Reset to first page when filter changes
                          }}
                          className="w-full pl-8 pr-3 py-1.5 text-sm border border-light-300 rounded-md focus:outline-none focus:ring-2 focus:ring-owl-blue-500 focus:border-transparent"
                        />
                      </div>
                      {/* File Type Filter Pills */}
                      {evidenceFiles.length > 0 && (() => {
                        const uniqueFileTypes = getUniqueFileTypes(evidenceFiles);
                        if (uniqueFileTypes.length === 0) return null;
                        
                        return (
                          <div className="mb-3 flex flex-wrap gap-2">
                            {uniqueFileTypes.map((fileType) => {
                              const isSelected = selectedFileTypes.has(fileType);
                              return (
                                <button
                                  key={fileType}
                                  onClick={() => {
                                    setSelectedFileTypes(prev => {
                                      const next = new Set(prev);
                                      if (next.has(fileType)) {
                                        next.delete(fileType);
                                      } else {
                                        next.add(fileType);
                                      }
                                      return next;
                                    });
                                    setEvidenceFilesPage(1); // Reset to first page when filter changes
                                  }}
                                  className={`px-3 py-1 text-xs rounded-full transition-colors ${
                                    isSelected
                                      ? 'bg-owl-blue-500 text-white hover:bg-owl-blue-600'
                                      : 'bg-white text-light-700 border border-light-300 hover:bg-light-50 hover:border-owl-blue-300'
                                  }`}
                                >
                                  {fileType}
                                </button>
                              );
                            })}
                            {selectedFileTypes.size > 0 && (
                              <button
                                onClick={() => {
                                  setSelectedFileTypes(new Set());
                                  setEvidenceFilesPage(1);
                                }}
                                className="px-3 py-1 text-xs rounded-full bg-light-200 text-light-700 hover:bg-light-300 border border-light-300 transition-colors"
                              >
                                Clear
                              </button>
                            )}
                          </div>
                        );
                      })()}
                    {evidenceLoading ? (
                      <div className="flex items-center gap-2 text-xs text-light-600">
                        <Loader2 className="w-4 h-4 animate-spin" />
                        Loading evidence files…
                      </div>
                    ) : evidenceFiles.length === 0 ? (
                      <p className="text-sm text-light-600 italic">
                        No evidence files have been uploaded for this case yet.
                      </p>
                    ) : (() => {
                      const filteredFiles = filterEvidenceFiles(evidenceFiles);
                      const { paginatedItems, totalPages, currentPage } = paginate(filteredFiles, evidenceFilesPage, itemsPerPage);
                      
                      return (
                        <>
                          <div className="space-y-1">
                            {paginatedItems.map((file) => {
                              const isSelected = previewedFile?.id === file.id;
                              return (
                                <div
                                  key={file.id}
                                  onClick={() => {
                                    setPreviewedFile(
                                      isSelected
                                        ? null
                                        : {
                                            id: file.id,
                                            name: file.original_filename,
                                            stored_path: file.stored_path,
                                          }
                                    );
                                  }}
                                  className={`flex items-center justify-between p-2 rounded border text-xs group cursor-pointer transition-colors ${
                                    isSelected
                                      ? 'bg-owl-blue-100 border-owl-blue-300'
                                      : 'bg-white border-light-200 hover:bg-light-50'
                                  }`}
                                >
                                  <div className="flex items-center gap-2 min-w-0 flex-1">
                                    <FileText className={`w-3 h-3 flex-shrink-0 ${
                                      isSelected ? 'text-owl-blue-700' : 'text-owl-blue-700'
                                    }`} />
                                    <span className={`truncate ${
                                      isSelected ? 'text-owl-blue-900 font-medium' : 'text-owl-blue-900'
                                    }`}>
                                      {file.original_filename}
                                    </span>
                                  </div>
                                  <div className="flex items-center gap-3 text-light-600 flex-shrink-0 ml-2">
                                    <span>{file.status}</span>
                                    <span className="hidden sm:inline">
                                      {new Date(file.created_at).toLocaleString()}
                                    </span>
                                    <div className={`p-1 rounded flex-shrink-0 ${
                                      isSelected
                                        ? 'bg-owl-blue-200 text-owl-blue-700'
                                        : 'opacity-0 group-hover:opacity-100 bg-light-200 text-owl-blue-600'
                                    } transition-opacity`}>
                                      <Eye className="w-3.5 h-3.5" />
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                            {filteredFiles.length === 0 && evidenceFiles.length > 0 && (
                              <p className="text-sm text-light-600 italic text-center py-2">
                                No files match the filter
                              </p>
                            )}
                          </div>
                          {totalPages > 1 && (
                            <div className="flex items-center justify-between mt-3 pt-3 border-t border-light-200">
                              <button
                                onClick={() => setEvidenceFilesPage(prev => Math.max(1, prev - 1))}
                                disabled={currentPage === 1}
                                className="px-3 py-1 text-xs text-owl-blue-600 hover:text-owl-blue-700 disabled:text-light-400 disabled:cursor-not-allowed flex items-center gap-1"
                              >
                                <ChevronLeft className="w-3 h-3" />
                                Previous
                              </button>
                              <span className="text-xs text-light-600">
                                Page {currentPage} of {totalPages} ({filteredFiles.length} total)
                              </span>
                              <button
                                onClick={() => setEvidenceFilesPage(prev => Math.min(totalPages, prev + 1))}
                                disabled={currentPage === totalPages}
                                className="px-3 py-1 text-xs text-owl-blue-600 hover:text-owl-blue-700 disabled:text-light-400 disabled:cursor-not-allowed flex items-center gap-1"
                              >
                                Next
                                <ChevronRight className="w-3 h-3" />
                              </button>
                            </div>
                          )}
                        </>
                      );
                    })()}
                    </div>
                  )}
                </div>

                {/* Processing History Section */}
                <div className="mb-6">
                  <button
                    onClick={() => setShowProcessingHistory(!showProcessingHistory)}
                    className="w-full flex items-center justify-between p-3 bg-light-100 hover:bg-light-200 rounded-lg transition-colors mb-2"
                  >
                    <div className="flex items-center gap-2">
                      <Archive className="w-5 h-5 text-owl-blue-700" />
                      <h3 className="text-md font-semibold text-owl-blue-900">
                        Processing History
                      </h3>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
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
                      {showProcessingHistory ? (
                        <ChevronDown className="w-4 h-4 text-light-600" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-light-600" />
                      )}
                    </div>
                  </button>
                  {showProcessingHistory && (
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
                  )}
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
                    <div className="ml-2">
                      {/* Filter Input */}
                      <div className="mb-2 relative">
                        <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-light-400" />
                        <input
                          type="text"
                          placeholder="Filter by version number or notes..."
                          value={versionsFilter}
                          onChange={(e) => {
                            setVersionsFilter(e.target.value);
                            setVersionsPage(1); // Reset to first page when filter changes
                          }}
                          className="w-full pl-8 pr-3 py-1.5 text-sm border border-light-300 rounded-md focus:outline-none focus:ring-2 focus:ring-owl-blue-500 focus:border-transparent"
                        />
                      </div>
                      <div className="space-y-2">
                        {selectedCase.versions && selectedCase.versions.length > 0 ? (() => {
                          // Separate latest version from previous versions
                          const latestVersion = selectedCase.versions[0];
                          const previousVersions = selectedCase.versions.slice(1);
                          const filteredPreviousVersions = filterVersions(previousVersions);
                          const { paginatedItems: paginatedPreviousVersions, totalPages, currentPage } = paginate(filteredPreviousVersions, versionsPage, itemsPerPage);
                          
                          return (
                            <>
                              {/* Latest Version - Always shown */}
                              {latestVersion && (
                                <div key={latestVersion.version}>
                                  <div
                                    onClick={() => {
                                      setSelectedVersion(latestVersion);
                                      // Expand only the latest snapshot of the selected version
                                      if (latestVersion.snapshots && latestVersion.snapshots.length > 0) {
                                        setExpandedSnapshots(new Set([latestVersion.snapshots[0].id]));
                                      } else {
                                        setExpandedSnapshots(new Set());
                                      }
                                    }}
                                    className={`p-4 rounded-lg cursor-pointer transition-colors border-2 ${
                                      selectedVersion?.version === latestVersion.version
                                        ? 'bg-owl-blue-50 border-owl-blue-300'
                                        : 'bg-white hover:bg-light-50 border-light-200'
                                    }`}
                                  >
                                    <div className="flex items-center justify-between mb-2">
                                      <div className="flex items-center gap-2">
                                        <FileText className="w-4 h-4 text-owl-blue-600" />
                                        <span className="font-medium text-owl-blue-900">
                                          Version {latestVersion.version}
                                        </span>
                                        <span className="text-xs bg-owl-blue-100 text-owl-blue-700 px-2 py-0.5 rounded">
                                          Latest
                                        </span>
                                      </div>
                                      <span className="text-xs text-light-600">
                                        {formatDate(latestVersion.timestamp)}
                                      </span>
                                    </div>
                                    {latestVersion.save_notes && (
                                      <p className="text-sm text-light-700 mb-2 line-clamp-2">
                                        {latestVersion.save_notes}
                                      </p>
                                    )}
                                    <div className="flex items-center gap-4 text-xs text-light-600">
                                      <span>
                                        {latestVersion.snapshots?.length || 0} snapshot{(latestVersion.snapshots?.length || 0) !== 1 ? 's' : ''}
                                      </span>
                                    </div>
                                  </div>
                                </div>
                              )}

                              {/* Previous Versions - Collapsible */}
                              {previousVersions.length > 0 && (
                                <div className="mt-3">
                                  <button
                                    onClick={() => setShowPreviousVersions(!showPreviousVersions)}
                                    className="w-full flex items-center justify-between p-2 bg-light-50 hover:bg-light-100 rounded-lg transition-colors border border-light-200"
                                  >
                                    <div className="flex items-center gap-2">
                                      <span className="text-sm font-medium text-owl-blue-900">
                                        Previous Versions ({previousVersions.length})
                                      </span>
                                    </div>
                                    {showPreviousVersions ? (
                                      <ChevronDown className="w-4 h-4 text-light-600" />
                                    ) : (
                                      <ChevronRight className="w-4 h-4 text-light-600" />
                                    )}
                                  </button>
                                  {showPreviousVersions && (
                                    <div className="mt-2 space-y-2">
                                      {paginatedPreviousVersions.map((version) => {
                                        const isExpanded = expandedVersions.has(version.version);
                                        return (
                                          <div key={version.version}>
                                            <div
                                              onClick={() => {
                                                setSelectedVersion(version);
                                                // Expand only the latest snapshot of the selected version
                                                if (version.snapshots && version.snapshots.length > 0) {
                                                  setExpandedSnapshots(new Set([version.snapshots[0].id]));
                                                } else {
                                                  setExpandedSnapshots(new Set());
                                                }
                                              }}
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
                                                  <button
                                                    onClick={(e) => {
                                                      e.stopPropagation();
                                                      setExpandedVersions(prev => {
                                                        const next = new Set(prev);
                                                        if (next.has(version.version)) {
                                                          next.delete(version.version);
                                                        } else {
                                                          next.add(version.version);
                                                        }
                                                        return next;
                                                      });
                                                    }}
                                                    className="text-xs text-owl-blue-600 hover:text-owl-blue-700"
                                                  >
                                                    {isExpanded ? 'Collapse' : 'Expand'}
                                                  </button>
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
                                              {isExpanded && (
                                                <div className="flex items-center gap-4 text-xs text-light-600">
                                                  <span>
                                                    {version.snapshots?.length || 0} snapshot{(version.snapshots?.length || 0) !== 1 ? 's' : ''}
                                                  </span>
                                                </div>
                                              )}
                                            </div>
                                          </div>
                                        );
                                      })}
                                      {totalPages > 1 && (
                                        <div className="flex items-center justify-between mt-3 pt-3 border-t border-light-200">
                                          <button
                                            onClick={() => setVersionsPage(prev => Math.max(1, prev - 1))}
                                            disabled={currentPage === 1}
                                            className="px-3 py-1 text-xs text-owl-blue-600 hover:text-owl-blue-700 disabled:text-light-400 disabled:cursor-not-allowed flex items-center gap-1"
                                          >
                                            <ChevronLeft className="w-3 h-3" />
                                            Previous
                                          </button>
                                          <span className="text-xs text-light-600">
                                            Page {currentPage} of {totalPages} ({filteredPreviousVersions.length} total)
                                          </span>
                                          <button
                                            onClick={() => setVersionsPage(prev => Math.min(totalPages, prev + 1))}
                                            disabled={currentPage === totalPages}
                                            className="px-3 py-1 text-xs text-owl-blue-600 hover:text-owl-blue-700 disabled:text-light-400 disabled:cursor-not-allowed flex items-center gap-1"
                                          >
                                            Next
                                            <ChevronRight className="w-3 h-3" />
                                          </button>
                                        </div>
                                      )}
                                    </div>
                                  )}
                                </div>
                              )}
                            </>
                          );
                        })() : (
                          <p className="text-sm text-light-600 italic ml-4">No versions available</p>
                        )}
                      </div>
                    </div>
                  )}
                </div>

                {/* Selected Version Details */}
                {selectedVersion && (
                  <>
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
                  Choose a case from the list to see its versions and snapshots
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

      {/* Create User Modal (Super Admin only) */}
      <CreateUserModal
        isOpen={showCreateUserModal}
        onClose={() => setShowCreateUserModal(false)}
        onUserCreated={() => {
          // Optional: could refresh user list or show success message
        }}
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

      {/* Case Opening Progress Dialog */}
      {caseOpeningProgress.isOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[9999]">
          <div className="w-full max-w-md bg-white rounded-lg shadow-2xl overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-light-200 bg-light-50">
              <div className="flex items-center gap-2">
                <Loader2 className="w-5 h-5 text-owl-blue-700 animate-spin" />
                <h2 className="text-lg font-semibold text-owl-blue-900">
                  Opening Case
                </h2>
              </div>
            </div>

            {/* Content */}
            <div className="p-6">
              <div className="mb-4">
                <p className="text-sm text-light-700 mb-1">
                  <span className="font-semibold">{caseOpeningProgress.caseName}</span>
                </p>
                <p className="text-sm text-light-600">
                  {caseOpeningProgress.message}
                </p>
              </div>

              {/* Progress Bar */}
              <div className="mb-4">
                <div className="flex items-center justify-between text-sm text-light-600 mb-2">
                  <span>Progress</span>
                  <span className="font-semibold text-owl-blue-900">
                    {caseOpeningProgress.current} / {caseOpeningProgress.total} steps
                  </span>
                </div>
                <div className="w-full bg-light-200 rounded-full h-3 overflow-hidden">
                  <div
                    className="bg-owl-blue-600 h-full rounded-full transition-all duration-300 ease-out"
                    style={{ width: `${caseOpeningProgress.total > 0 ? Math.round((caseOpeningProgress.current / caseOpeningProgress.total) * 100) : 0}%` }}
                  />
                </div>
                <div className="text-xs text-light-500 mt-1 text-right">
                  {caseOpeningProgress.total > 0 ? Math.round((caseOpeningProgress.current / caseOpeningProgress.total) * 100) : 0}%
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* System Logs Panel */}
      <SystemLogsPanel
        isOpen={showSystemLogs}
        onClose={() => setShowSystemLogs(false)}
      />

      {/* Database Modal */}
      <DatabaseModal
        isOpen={showDatabaseModal}
        onClose={() => setShowDatabaseModal(false)}
        currentUser={authUsername}
      />
    </div>
  );
}

