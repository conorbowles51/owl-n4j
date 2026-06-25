import React, { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import UppyEvidenceUploader from './UppyEvidenceUploader';
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
  ChevronRight,
  X,
  Edit,
  Folder,
  FolderOpen,
  HardDrive,
  Radio,
  Copy,
  Smartphone,
  Clock,
} from 'lucide-react';
import { evidenceAPI, profilesAPI, filesystemAPI, backgroundTasksAPI } from '../services/api';
import { useCasePermissions } from '../contexts/CasePermissionContext';
import { normalizeStoredPath } from '../utils/pathUtils';
import BackgroundTasksPanel from './BackgroundTasksPanel';
import ProfileEditor from './ProfileEditor';
import FileNavigator from './FileNavigator';
import FileInfoViewer from './FileInfoViewer';
import FolderProfileModal from './FolderProfileModal';

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

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.min(Math.floor(Math.log10(bytes) / 3), units.length - 1);
  const value = bytes / Math.pow(1000, i);
  // Show one decimal once we're past KB; whole numbers below that.
  return `${i >= 2 ? value.toFixed(1) : Math.round(value)} ${units[i]}`;
}

// Human label + icon for an ingestion/upload task type (used by the status panel).
const TASK_TYPE_META = {
  cellebrite_ingestion: { label: 'Cellebrite report', Icon: Smartphone },
  file_upload: { label: 'File upload', Icon: UploadCloud },
  evidence_processing: { label: 'Evidence processing', Icon: FileText },
  wiretap_processing: { label: 'Wiretap processing', Icon: Radio },
};

// Visual treatment for a task status. Returns { Icon, spin, cls, label }.
function taskStatusMeta(status) {
  switch (status) {
    case 'completed':
      return { Icon: CheckCircle2, spin: false, cls: 'text-green-600', label: 'Done' };
    case 'failed':
      return { Icon: AlertTriangle, spin: false, cls: 'text-red-600', label: 'Failed' };
    case 'cancelled':
      return { Icon: X, spin: false, cls: 'text-light-500', label: 'Cancelled' };
    case 'running':
      return { Icon: Loader2, spin: true, cls: 'text-owl-blue-700', label: 'Processing' };
    default: // pending / queued
      return { Icon: Clock, spin: false, cls: 'text-owl-orange-600', label: 'Queued' };
  }
}

function relativeTime(iso) {
  if (!iso) return '';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const secs = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

export default function EvidenceProcessingView({
  caseId,
  caseName,
  onBackToCases,
  onGoToGraph,
  onLoadProcessedGraph,
  authUsername,
  onViewCase,
}) {
  const { canUploadEvidence } = useCasePermissions();
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(true);

  // Lookup indexes built once per `files` change. The folder-stats matchers
  // used to call `files.find(...)` per file path — O(n²) over the evidence
  // list, which freezes the UI thread for a 93k-file cellebrite phone. Two
  // Maps cover the cheap matches; suffix-style fallbacks were dropped because
  // every record now carries a canonical `stored_path`.
  const evidenceByRelPath = useMemo(() => {
    const map = new Map();
    for (const f of files) {
      const normalized = normalizeStoredPath(f.stored_path, caseId);
      if (normalized && !map.has(normalized)) map.set(normalized, f);
    }
    return map;
  }, [files, caseId]);
  const evidenceByFilename = useMemo(() => {
    const map = new Map();
    for (const f of files) {
      const name = f.original_filename;
      if (name && !map.has(name)) map.set(name, f);
    }
    return map;
  }, [files]);
  const findEvidenceForPath = useCallback((filePath) => {
    const normalizedFP = filePath.replace(/\\/g, '/').replace(/^\/+|\/+$/g, '');
    const exact = evidenceByRelPath.get(normalizedFP);
    if (exact) return exact;
    const fileName = normalizedFP.split('/').pop() || normalizedFP;
    return evidenceByFilename.get(fileName) || null;
  }, [evidenceByRelPath, evidenceByFilename]);

  const [uploading, setUploading] = useState(false);
  // Byte-level progress for the active browser → server upload. null when
  // no upload is in flight. `total` may be 0 if the browser couldn't compute
  // a content length (rare for FormData), in which case we fall back to an
  // indeterminate state.
  const [uploadProgress, setUploadProgress] = useState(null);
  const [processing, setProcessing] = useState(false);
  const [fileNavKey, setFileNavKey] = useState(0); // Increment to force FileNavigator refresh
  const [error, setError] = useState(null);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [logs, setLogs] = useState([]);
  const logContainerRef = useRef(null);
  const completedWiretapTaskIdsRef = useRef(new Set()); // Track completed wiretap task IDs to avoid duplicate refreshes
  const completedUploadTaskIdsRef = useRef(new Set()); // Track completed upload task IDs to avoid duplicate refreshes
  const completedProcessingTaskIdsRef = useRef(new Set()); // Track completed evidence_processing task IDs to avoid duplicate refreshes
  const completedCellebriteTaskIdsRef = useRef(new Set()); // Track completed cellebrite_ingestion task IDs (resumable tus uploads) to avoid duplicate refreshes
  // Files whose resumable (tus) upload has finished but whose server-side
  // unpack+ingest hasn't surfaced a background task yet. Bridges the dead zone
  // between Uppy "complete" and the cellebrite_ingestion task appearing so the
  // user isn't left staring at a vanished file with no feedback.
  const [unpackingFiles, setUnpackingFiles] = useState([]); // [{ name, at }]
  // Ingestion/upload tasks for this case, surfaced as a persistent, always-visible
  // status panel so the user can see what they've uploaded and where it is
  // (queued → processing → done/failed). Auto-ingest / resumable-upload tasks run
  // in a detached worker and previously only triggered a silent log refresh.
  // Only updated on a successful poll so transient backend stalls don't blank it.
  const [caseTasks, setCaseTasks] = useState([]);
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
  const [showFileNavigator, setShowFileNavigator] = useState(true);
  const [showProcessedWiretaps, setShowProcessedWiretaps] = useState(false); // Collapsed by default
  const [showIngestionLog, setShowIngestionLog] = useState(false); // Collapsed by default
  const [selectedFileId, setSelectedFileId] = useState(null);
  const [selectedFilePath, setSelectedFilePath] = useState(null);
  const [selectedFilePaths, setSelectedFilePaths] = useState(new Set()); // Multi-select file paths
  const [selectedFolderInfo, setSelectedFolderInfo] = useState(null);
  const [selectedFolderPaths, setSelectedFolderPaths] = useState(new Set()); // Multi-select folder paths
  const [selectedFoldersInfo, setSelectedFoldersInfo] = useState([]); // Info for all selected folders
  const [wiretapProcessedFolders, setWiretapProcessedFolders] = useState(new Set());
  const [processedWiretapList, setProcessedWiretapList] = useState([]); // List of all processed wiretap folders
  const [showFolderProfileModal, setShowFolderProfileModal] = useState(false);
  const [folderProfilePath, setFolderProfilePath] = useState(null);
  const [editingFolderProfileName, setEditingFolderProfileName] = useState(null); // Profile name being edited in FolderProfileModal
  const [profilesWithFolderProcessing, setProfilesWithFolderProcessing] = useState([]);
  
  // Filters for unprocessed files
  const [unprocessedFilter, setUnprocessedFilter] = useState('');
  const [unprocessedTypeFilter, setUnprocessedTypeFilter] = useState(null);
  
  // Filters for processed files
  const [processedFilter, setProcessedFilter] = useState('');
  const [processedTypeFilter, setProcessedTypeFilter] = useState(null);

  // Parallel processing configuration
  const [maxWorkers, setMaxWorkers] = useState(4);

  // Image processing provider: "tesseract" (local OCR) or "openai" (GPT-4 Vision)
  const [imageProvider, setImageProvider] = useState('tesseract');

  // Delete confirmation state
  const [deleteConfirm, setDeleteConfirm] = useState(null); // { id, filename } or null
  const [deleting, setDeleting] = useState(false);

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
        
        // Load profile details to filter for folder_processing
        const profilesWithFolder = [];
        for (const profile of data || []) {
          try {
            const details = await profilesAPI.get(profile.name);
            if (details.folder_processing) {
              profilesWithFolder.push(details);
            }
          } catch (err) {
            // Skip profiles that fail to load
            console.warn(`Failed to load profile ${profile.name}:`, err);
          }
        }
        setProfilesWithFolderProcessing(profilesWithFolder);
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

  // Load list of processed wiretap folders
  const loadProcessedWiretaps = useCallback(async () => {
    if (!caseId) {
      setProcessedWiretapList([]);
      return;
    }
    try {
      const list = await evidenceAPI.listProcessedWiretaps(caseId);
      setProcessedWiretapList(list || []);
      // Also update the Set for FileNavigator
      const folderPaths = new Set((list || []).map(item => item.folder_path));
      setWiretapProcessedFolders(folderPaths);
    } catch (err) {
      console.error('Failed to load processed wiretaps:', err);
    }
  }, [caseId]);

  // Filesystem sync is gated behind an explicit "Sync from disk" button.
  // On mount we only show what's already in the system — no disk walks,
  // no hashing, no large payloads.
  const [syncing, setSyncing] = useState(false);
  const handleSyncFromDisk = useCallback(async () => {
    if (!caseId || syncing) return;
    setSyncing(true);
    try {
      await evidenceAPI.syncFilesystem(caseId);
      await loadFiles();
    } catch (err) {
      console.error('Filesystem sync failed:', err);
      setError(err?.message || 'Filesystem sync failed');
    } finally {
      setSyncing(false);
    }
  }, [caseId, syncing, loadFiles]);

  useEffect(() => {
    loadFiles();
    loadLogs();
    loadProcessedWiretaps();
  }, [caseId, loadFiles, loadLogs, loadProcessedWiretaps]);

  // Poll logs every 5 seconds only while actively processing
  // Also check for completed wiretap tasks to refresh processed folders list
  // And check for completed file upload tasks to refresh file navigator
  useEffect(() => {
    if (!caseId) {
      // Reset completed task IDs when case changes
      completedWiretapTaskIdsRef.current.clear();
      completedUploadTaskIdsRef.current.clear();
      completedProcessingTaskIdsRef.current.clear();
      completedCellebriteTaskIdsRef.current.clear();
      setUnpackingFiles([]);
      setCaseTasks([]);
      return;
    }
    
    let isActive = false;
    
    // Check if processing is active (either local processing or background tasks)
    const checkActiveProcessing = async () => {
      try {
        // Check for active background tasks for this case
        const tasks = await backgroundTasksAPI.list(null, caseId, null, 50);
        const activeTasks = (tasks?.tasks || []).filter(
          task => task.status === 'running' || task.status === 'pending'
        );
        
        // Check for wiretap processing tasks that just completed
        const wiretapTasks = (tasks?.tasks || []).filter(
          task => task.task_type === 'wiretap_processing'
        );
        
        // Detect newly completed wiretap tasks and refresh processed folders
        for (const task of wiretapTasks) {
          if (task.status === 'completed' && !completedWiretapTaskIdsRef.current.has(task.id)) {
            // Newly completed wiretap task - refresh processed folders list
            await loadProcessedWiretaps();
            completedWiretapTaskIdsRef.current.add(task.id);
          } else if (task.status === 'completed' || task.status === 'failed') {
            // Track completed/failed tasks to avoid duplicate refreshes
            completedWiretapTaskIdsRef.current.add(task.id);
          }
        }
        
        // Check for file upload tasks that just completed and refresh file list
        const uploadTasks = (tasks?.tasks || []).filter(
          task => task.task_type === 'file_upload'
        );
        
        // Detect newly completed upload tasks and refresh file list
        let shouldRefreshFiles = false;
        for (const task of uploadTasks) {
          if (task.status === 'completed' && !completedUploadTaskIdsRef.current.has(task.id)) {
            // Newly completed upload task - mark for refresh
            shouldRefreshFiles = true;
            completedUploadTaskIdsRef.current.add(task.id);
          } else if (task.status === 'failed' && !completedUploadTaskIdsRef.current.has(task.id)) {
            // Surface upload error to user
            const failError = task.error || 'Unknown upload error';
            setError(`Upload failed: ${failError}`);
            completedUploadTaskIdsRef.current.add(task.id);
          } else if (task.status === 'completed' || task.status === 'failed') {
            // Track completed/failed tasks to avoid duplicate refreshes
            completedUploadTaskIdsRef.current.add(task.id);
          }
        }
        
        // Check for evidence processing tasks that just completed
        const processingTasks = (tasks?.tasks || []).filter(
          task => task.task_type === 'evidence_processing'
        );

        for (const task of processingTasks) {
          if (task.status === 'completed' && !completedProcessingTaskIdsRef.current.has(task.id)) {
            shouldRefreshFiles = true;
            completedProcessingTaskIdsRef.current.add(task.id);
          } else if (task.status === 'failed' && !completedProcessingTaskIdsRef.current.has(task.id)) {
            // Surface processing error to user
            const failError = task.error || 'Unknown processing error';
            const failedCount = task.progress_failed || 0;
            setError(`Processing failed${failedCount > 0 ? ` (${failedCount} file(s))` : ''}: ${failError}`);
            shouldRefreshFiles = true;
            completedProcessingTaskIdsRef.current.add(task.id);
          } else if (task.status === 'completed' || task.status === 'failed') {
            completedProcessingTaskIdsRef.current.add(task.id);
          }
        }

        // Check for cellebrite ingestion tasks (resumable tus uploads land here).
        // The post-finish hook unpacks the zip in a detached worker, then creates
        // this task — so its appearance/completion is what we tie the
        // "unpacking & processing" card to.
        const cellebriteTasks = (tasks?.tasks || []).filter(
          task => task.task_type === 'cellebrite_ingestion'
        );

        for (const task of cellebriteTasks) {
          if (task.status === 'completed' && !completedCellebriteTaskIdsRef.current.has(task.id)) {
            shouldRefreshFiles = true;
            completedCellebriteTaskIdsRef.current.add(task.id);
            setUnpackingFiles([]); // ingest finished — drop the bridging card
          } else if (task.status === 'failed' && !completedCellebriteTaskIdsRef.current.has(task.id)) {
            const failError = task.error || 'Unknown ingestion error';
            setError(`Cellebrite ingestion failed: ${failError}`);
            completedCellebriteTaskIdsRef.current.add(task.id);
            setUnpackingFiles([]);
            shouldRefreshFiles = true;
          } else if (task.status === 'completed' || task.status === 'failed') {
            completedCellebriteTaskIdsRef.current.add(task.id);
          }
        }

        // Once the ingestion task actually exists (running/pending), the normal
        // active-processing UI + logs take over, so we can retire the bridging
        // card to avoid showing two "processing" indicators.
        const cellebriteActive = cellebriteTasks.some(
          task => task.status === 'running' || task.status === 'pending'
        );
        if (cellebriteActive) {
          setUnpackingFiles((prev) => (prev.length ? [] : prev));
        }

        // Refresh files if any new upload or processing tasks completed
        if (shouldRefreshFiles) {
          await loadFiles();
        }

        // Persist the upload/ingest tasks for the always-visible status panel,
        // newest first. (Successful poll only — the catch block leaves the last
        // known list in place so a transient backend stall doesn't blank it.)
        const INGEST_TYPES = ['cellebrite_ingestion', 'file_upload', 'evidence_processing', 'wiretap_processing'];
        const relevant = (tasks?.tasks || [])
          .filter(t => INGEST_TYPES.includes(t.task_type))
          .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
        setCaseTasks(relevant);

        // Processing is active if:
        // 1. Local processing state is true, OR
        // 2. There are active background tasks
        isActive = processing || activeTasks.length > 0;
        
        if (isActive) {
          loadLogs();
        }
      } catch (err) {
        // If background tasks check fails, fall back to local processing state
        isActive = processing;
        if (isActive) {
          loadLogs();
        }
      }
    };
    
    // Initial check
    checkActiveProcessing();
    
    // Poll every 5 seconds to check for completed tasks and active processing
    const intervalId = setInterval(() => {
      checkActiveProcessing();
    }, 5000); // 5 seconds as requested
    
    return () => clearInterval(intervalId);
  }, [caseId, processing, loadLogs, loadProcessedWiretaps, loadFiles]);

  // Auto-scroll log window to the bottom (tail behavior) whenever logs change
  useEffect(() => {
    if (!logContainerRef.current) return;
    const el = logContainerRef.current;
    el.scrollTop = el.scrollHeight;
  }, [logs]);

  // Resumable (tus) upload finished sending bytes. The server now unpacks the
  // zip and ingests it asynchronously; show an immediate "unpacking & processing"
  // card so the file doesn't appear to silently vanish, and nudge the pollers so
  // logs/files refresh as soon as the cellebrite_ingestion task surfaces.
  const handleResumableUploadComplete = useCallback((file) => {
    const name = file?.name || file?.meta?.filename || 'uploaded archive';
    setUnpackingFiles((prev) =>
      prev.some((f) => f.name === name) ? prev : [...prev, { name, at: Date.now() }]
    );
    loadLogs();
  }, [loadLogs]);

  const handleFileSelect = async (event) => {
    const fileList = event.target.files;
    if (!fileList || fileList.length === 0) return;
    if (!caseId) {
      alert('Please select or create a case before uploading evidence.');
      return;
    }

    setUploading(true);
    setUploadProgress({ loaded: 0, total: 0, lengthComputable: false });
    setError(null);
    try {
      const result = await evidenceAPI.upload(caseId, fileList, setUploadProgress);

      if (result.task_id) {
        // Background task created (for large uploads >5 files)
        setShowBackgroundTasksPanel(true);
        // Refresh files after a short delay
        setTimeout(() => {
          loadFiles();
          setFileNavKey(k => k + 1);
        }, 2000);
      } else {
        // Synchronous upload completed
        await loadFiles();
        setFileNavKey(k => k + 1);
      }

      event.target.value = ''; // reset input so same files can be re-selected if needed
    } catch (err) {
      console.error('Failed to upload files:', err);
      setError(err.message || 'Failed to upload files');
    } finally {
      setUploading(false);
      setUploadProgress(null);
    }
  };

  const handleFolderSelect = async (event) => {
    const fileList = event.target.files;
    if (!fileList || fileList.length === 0) return;
    if (!caseId) {
      alert('Please select or create a case before uploading evidence.');
      return;
    }

    setUploading(true);
    setUploadProgress({ loaded: 0, total: 0, lengthComputable: false });
    setError(null);
    try {
      // Upload folder as background task
      const result = await evidenceAPI.uploadFolder(caseId, fileList, setUploadProgress);

      if (result.task_id) {
        // Background task created - show message and open background tasks panel
        setShowBackgroundTasksPanel(true);
        // Refresh files after a short delay to catch any quick uploads
        setTimeout(() => {
          loadFiles();
          setFileNavKey(k => k + 1);
        }, 2000);
      } else {
        // Synchronous upload completed
        await loadFiles();
        setFileNavKey(k => k + 1);
      }

      event.target.value = ''; // reset input
    } catch (err) {
      console.error('Failed to upload folder:', err);
      setError(err.message || 'Failed to upload folder');
    } finally {
      setUploading(false);
      setUploadProgress(null);
    }
  };

  const handleArchiveSelect = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!caseId) {
      alert('Please select or create a case before uploading evidence.');
      return;
    }

    setUploading(true);
    // Single-file upload — total is known up front, so the progress bar
    // can be a real percentage rather than the indeterminate animation.
    setUploadProgress({ loaded: 0, total: file.size, lengthComputable: true });
    setError(null);
    try {
      const result = await evidenceAPI.uploadArchive(caseId, file, setUploadProgress);

      if (result.task_id) {
        setShowBackgroundTasksPanel(true);
        setTimeout(() => {
          loadFiles();
          setFileNavKey(k => k + 1);
        }, 2000);
      } else {
        await loadFiles();
        setFileNavKey(k => k + 1);
      }

      event.target.value = '';
    } catch (err) {
      console.error('Failed to upload archive:', err);
      setError(err.message || 'Failed to upload archive');
    } finally {
      setUploading(false);
      setUploadProgress(null);
    }
  };

  const handleFileNavigatorSelect = (filePath, event) => {
    setSelectedFilePath(filePath);
    // Normalize the file path from navigator (relative to case root)
    const normalizedFilePath = filePath.replace(/\\/g, '/').replace(/^\/+|\/+$/g, '');

    // Find matching file in the files list if it exists
    const matchingFile = files.find(f => {
      if (!f.stored_path) return false;

      const normalizedStoredPath = normalizeStoredPath(f.stored_path, caseId);

      // Match by exact path or by filename if paths match
      return normalizedStoredPath === normalizedFilePath ||
             normalizedStoredPath.endsWith('/' + normalizedFilePath) ||
             normalizedFilePath.endsWith('/' + normalizedStoredPath);
    });
    
    if (matchingFile) {
      setSelectedFileId(matchingFile.id);
      // Add to selectedIds so it appears selected in the file lists
      // Support multi-select if Ctrl/Cmd is held
      const isMultiSelect = event && (event.ctrlKey || event.metaKey);
      if (isMultiSelect) {
        // Toggle selection
        setSelectedIds((prev) => {
          const next = new Set(prev);
          if (next.has(matchingFile.id)) {
            next.delete(matchingFile.id);
          } else {
            next.add(matchingFile.id);
          }
          return next;
        });
      } else {
        // Single select - replace selection
        setSelectedIds(new Set([matchingFile.id]));
      }
    }
  };

  const handleFileNavigatorInfo = async (item) => {
    if (item.type === 'file') {
      // Find matching evidence file by path
      const normalizedItemPath = item.path.replace(/\\/g, '/').replace(/^\/+|\/+$/g, '');
      const matchingFile = files.find(f => {
        const normalizedStored = normalizeStoredPath(f.stored_path, caseId);
        // Match by normalized path or by filename
        return normalizedStored === normalizedItemPath ||
               normalizedStored.endsWith('/' + normalizedItemPath) ||
               normalizedItemPath.endsWith('/' + normalizedStored) ||
               normalizedItemPath.endsWith(f.original_filename);
      });
      
      if (matchingFile) {
        // Add to selected files
        setSelectedIds((prev) => {
          const next = new Set(prev);
          next.add(matchingFile.id);
          return next;
        });
        setSelectedFilePath(item.path);
        setSelectedFileId(matchingFile.id);
        setSelectedFolderInfo(null); // Clear folder info
      } else {
        // File not found in evidence list - might be a system file
        // Still select it in the navigator
        setSelectedFilePath(item.path);
        setSelectedFolderInfo(null);
      }
    } else if (item.type === 'directory') {
      // Single folder click - clear multi-select
      setSelectedFolderPaths(new Set());
      setSelectedFoldersInfo([]);
      setSelectedFilePath(item.path);
      setSelectedFolderInfo(null); // Clear while loading

      try {
        // Show folder info immediately with detection checks (fast API calls),
        // then backfill file statistics asynchronously to avoid UI lag on large folders.

        // Run wiretap + cellebrite checks in parallel (fast — header-only parsing)
        const [wiretapResult, cellebriteResult] = await Promise.allSettled([
          evidenceAPI.checkWiretapFolder(caseId, item.path),
          evidenceAPI.checkCellebriteFolder(caseId, item.path),
        ]);

        let wiretapInfo = null;
        if (wiretapResult.status === 'fulfilled') {
          wiretapInfo = wiretapResult.value;
          if (wiretapInfo.processed) {
            setWiretapProcessedFolders(prev => new Set([...prev, item.path]));
          }
        }

        let cellebriteInfo = null;
        if (cellebriteResult.status === 'fulfilled') {
          cellebriteInfo = cellebriteResult.value;
        }

        // Set folder info immediately so the UI responds fast
        const folderInfoBase = {
          path: item.path,
          name: item.name,
          totalFiles: null, // Will be filled in by background scan
          processedCount: null,
          unprocessedCount: null,
          fileTypes: [],
          availableProcessors: profiles.map(p => ({
            name: p.name,
            description: p.description || ''
          })),
          wiretapInfo,
          cellebriteInfo
        };
        setSelectedFolderInfo(folderInfoBase);

        // Clear file selection when showing folder info
        setSelectedIds(new Set());

        // Background: scan folder files for statistics (non-blocking).
        // `totalFiles` is the raw on-disk count from listRecursive — the
        // evidence list is artifact-filtered server-side for Cellebrite
        // report folders (see backend/routers/evidence.py:215, default
        // include_cellebrite_artifacts=False), so matching against `files`
        // can't be used as a file count for those folders. processed/
        // unprocessed counts still come from matched evidence records,
        // which means Cellebrite folders show 0/0 here until ingestion
        // — that's accurate (cellebrite rows aren't tracked individually
        // through this status flow).
        getFolderFilesRecursive(item.path).then(folderFiles => {
          const folderEvidenceFiles = folderFiles
            .map(findEvidenceForPath)
            .filter(Boolean);

          const processedCount = folderEvidenceFiles.filter(f => f.status === 'processed').length;
          const unprocessedCount = folderEvidenceFiles.filter(f => f.status === 'unprocessed' || f.status === 'failed').length;

          // File-type detection: scan filenames from the raw walk (works
          // for both cellebrite-artifact and regular folders).
          const fileTypes = new Set();
          folderFiles.forEach(filePath => {
            const fileName = filePath.split('/').pop() || filePath;
            const ext = fileName.split('.').pop()?.toLowerCase() || '';
            if (!ext) return;
            const imageTypes = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp'];
            const docTypes = ['pdf', 'doc', 'docx', 'txt', 'rtf', 'odt'];
            const audioTypes = ['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a'];
            const videoTypes = ['mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv'];
            const dataTypes = ['xls', 'xlsx', 'csv', 'json', 'xml'];
            if (imageTypes.includes(ext)) fileTypes.add('Image');
            else if (docTypes.includes(ext)) fileTypes.add('Document');
            else if (audioTypes.includes(ext)) fileTypes.add('Audio');
            else if (videoTypes.includes(ext)) fileTypes.add('Video');
            else if (dataTypes.includes(ext)) fileTypes.add('Data');
            else fileTypes.add('Other');
          });

          // Update folder info with file statistics (only if still viewing the same folder)
          setSelectedFolderInfo(prev => {
            if (prev?.path !== item.path) return prev; // User navigated away
            return {
              ...prev,
              totalFiles: folderFiles.length,
              processedCount,
              unprocessedCount,
              fileTypes: Array.from(fileTypes).sort(),
            };
          });
        }).catch(err => {
          console.error('Failed to scan folder files:', err);
        });
      } catch (err) {
        console.error('Failed to load folder information:', err);
        setSelectedFolderInfo({
          path: item.path,
          name: item.name,
          error: 'Failed to load folder information'
        });
      }
    }
  };

  // Helper function to recursively get all files in a folder.
  // Uses the bulk /filesystem/list_recursive endpoint (one round-trip)
  // instead of recursing via /filesystem/list per directory (N round-trips,
  // which timed out the browser on large Cellebrite folders).
  const getFolderFilesRecursive = async (folderPath) => {
    try {
      const result = await filesystemAPI.listRecursive(caseId, folderPath || null);
      return result?.files || [];
    } catch (err) {
      console.error(`Failed to list directory ${folderPath}:`, err);
      return [];
    }
  };

  const handleProcessWiretap = async (folderPaths, onTaskCreated) => {
    if (!caseId) {
      alert('Please select a case first');
      return;
    }

    // Ensure folderPaths is an array
    const pathsArray = Array.isArray(folderPaths) ? folderPaths : [folderPaths];

    try {
      setError(null);
      
      // Process each folder as its own background task
      // The backend will create separate tasks for each folder
      const result = await evidenceAPI.processWiretapFolders(caseId, pathsArray);
      
      if (result.success) {
        // Wiretap processing always uses background tasks
        // Open the background tasks panel to show the tasks
        setShowBackgroundTasksPanel(true);
        
        // Refresh folder info and processed wiretap list after a delay to show updated status
        setTimeout(async () => {
          // Refresh info for all selected folders
          for (const folderPath of pathsArray) {
            const folderItem = { type: 'directory', path: folderPath, name: folderPath.split('/').pop() || folderPath };
            await handleFileNavigatorInfo(folderItem);
          }
          await loadProcessedWiretaps();
        }, 1000);
      } else {
        setError(result.message || 'Wiretap processing failed');
      }
    } catch (err) {
      console.error('Failed to process wiretap folders:', err);
      const errorMessage = err.message && err.message.includes('timed out')
        ? 'Request timed out. The folder validation may be taking longer than expected. Please try again or check if the folder path is correct.'
        : err.message || 'Failed to process wiretap folders';
      setError(errorMessage);
    }
  };

  const handleFolderNavigatorSelect = (folderPath, event) => {
    setSelectedFolderPaths((prev) => {
      const next = new Set(prev);
      if (next.has(folderPath)) {
        next.delete(folderPath);
      } else {
        next.add(folderPath);
      }
      return next;
    });
  };

  const handleFileNavigatorMultiSelect = (filePath, event) => {
    setSelectedFilePaths((prev) => {
      const next = new Set(prev);
      if (next.has(filePath)) {
        next.delete(filePath);
      } else {
        next.add(filePath);
      }
      return next;
    });
    
    // Also sync with selectedIds for processing
    // Normalize the file path from navigator (relative to case root)
    const normalizedFilePath = filePath.replace(/\\/g, '/').replace(/^\/+|\/+$/g, '');

    // Find matching file in the files list
    const matchingFile = files.find(f => {
      if (!f.stored_path) return false;

      const normalizedStoredPath = normalizeStoredPath(f.stored_path, caseId);

      // Match by exact path or by filename if paths match
      return normalizedStoredPath === normalizedFilePath ||
             normalizedStoredPath.endsWith('/' + normalizedFilePath) ||
             normalizedFilePath.endsWith('/' + normalizedStoredPath);
    });
    
    if (matchingFile) {
      // Sync with selectedIds
      setSelectedIds((prev) => {
        const next = new Set(prev);
        if (next.has(matchingFile.id)) {
          next.delete(matchingFile.id);
        } else {
          next.add(matchingFile.id);
        }
        return next;
      });
    }
  };

  // Load info for all selected folders
  useEffect(() => {
    const loadSelectedFoldersInfo = async () => {
      if (selectedFolderPaths.size === 0) {
        setSelectedFoldersInfo([]);
        return;
      }

      const foldersInfoArray = [];
      for (const folderPath of selectedFolderPaths) {
        try {
          // Get folder name from path
          const folderName = folderPath.split('/').pop() || folderPath;
          
          // Get all files in the folder (recursively)
          const folderFiles = await getFolderFilesRecursive(folderPath);
          
          // Match with evidence files via O(1) Map lookup. `folderFiles`
          // is the authoritative on-disk count (used for `totalFiles`);
          // matched evidence is only used for processed/unprocessed —
          // those will read 0 for Cellebrite folders, which is accurate
          // because cellebrite rows are filtered from /api/evidence by
          // default (see EvidenceProcessingView folder-card comment).
          const folderEvidenceFiles = folderFiles
            .map(findEvidenceForPath)
            .filter(Boolean);

          const processedCount = folderEvidenceFiles.filter(f =>
            f.status === 'processed'
          ).length;
          const unprocessedCount = folderEvidenceFiles.filter(f =>
            f.status === 'unprocessed' || f.status === 'failed'
          ).length;

          // File-type detection from raw walk (works for cellebrite too).
          const fileTypes = new Set();
          folderFiles.forEach(filePath => {
            const fileName = filePath.split('/').pop() || filePath;
            const ext = fileName.split('.').pop()?.toLowerCase() || '';
            if (!ext) return;
            const imageTypes = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp'];
            const docTypes = ['pdf', 'doc', 'docx', 'txt', 'rtf', 'odt'];
            const audioTypes = ['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a'];
            const videoTypes = ['mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv'];
            const dataTypes = ['xls', 'xlsx', 'csv', 'json', 'xml'];
            if (imageTypes.includes(ext)) fileTypes.add('Image');
            else if (docTypes.includes(ext)) fileTypes.add('Document');
            else if (audioTypes.includes(ext)) fileTypes.add('Audio');
            else if (videoTypes.includes(ext)) fileTypes.add('Video');
            else if (dataTypes.includes(ext)) fileTypes.add('Data');
            else fileTypes.add('Other');
          });
          
          // Check wiretap suitability
          let wiretapInfo = null;
          try {
            const wiretapCheck = await evidenceAPI.checkWiretapFolder(caseId, folderPath);
            wiretapInfo = wiretapCheck;
            if (wiretapCheck.processed) {
              setWiretapProcessedFolders(prev => new Set([...prev, folderPath]));
            }
          } catch (err) {
            console.error('Failed to check wiretap suitability:', err);
          }

          // Check Cellebrite report suitability
          let cellebriteInfo = null;
          try {
            const cellebriteCheck = await evidenceAPI.checkCellebriteFolder(caseId, folderPath);
            cellebriteInfo = cellebriteCheck;
          } catch (err) {
            // Not a Cellebrite folder — ignore
          }

          foldersInfoArray.push({
            path: folderPath,
            name: folderName,
            totalFiles: folderFiles.length,
            processedCount,
            unprocessedCount,
            fileTypes: Array.from(fileTypes).sort(),
            availableProcessors: profiles.map(p => ({
              name: p.name,
              description: p.description || ''
            })),
            wiretapInfo,
            cellebriteInfo
          });
        } catch (err) {
          console.error(`Failed to load info for folder ${folderPath}:`, err);
          foldersInfoArray.push({
            path: folderPath,
            name: folderPath.split('/').pop() || folderPath,
            error: 'Failed to load folder information'
          });
        }
      }
      
      setSelectedFoldersInfo(foldersInfoArray);
    };

    loadSelectedFoldersInfo();
  }, [selectedFolderPaths, caseId, files, profiles]);

  const toggleSelect = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      // Clear folder info when selecting files
      if (next.size > 0) {
        setSelectedFolderInfo(null);
      }
      return next;
    });
  };

  const selectAll = (ids) => {
    setSelectedIds(new Set(ids));
  };

  const clearSelection = () => {
    setSelectedIds(new Set());
    setSelectedFilePaths(new Set()); // Also clear FileNavigator selections
  };

  // Convert file paths to file IDs
  const getFileIdsFromPaths = useCallback((filePaths) => {
    const fileIds = new Set();
    filePaths.forEach(filePath => {
      // Normalize the file path from navigator (relative to case root)
      const normalizedFilePath = filePath.replace(/\\/g, '/').replace(/^\/+|\/+$/g, '');

      // Find matching file in the files list
      const matchingFile = files.find(f => {
        if (!f.stored_path) return false;

        const normalizedStoredPath = normalizeStoredPath(f.stored_path, caseId);

        // Match by exact path or by filename if paths match
        return normalizedStoredPath === normalizedFilePath ||
               normalizedStoredPath.endsWith('/' + normalizedFilePath) ||
               normalizedFilePath.endsWith('/' + normalizedStoredPath);
      });

      if (matchingFile) {
        fileIds.add(matchingFile.id);
      }
    });
    return Array.from(fileIds);
  }, [files, caseId]);

  const handleProcessSelected = async () => {
    // Combine selectedIds and selectedFilePaths
    const allSelectedIds = new Set(selectedIds);
    
    // Add file IDs from FileNavigator selections
    const navigatorFileIds = getFileIdsFromPaths(selectedFilePaths);
    navigatorFileIds.forEach(id => allSelectedIds.add(id));
    
    if (allSelectedIds.size === 0) {
      alert('Please select one or more files to process.');
      return;
    }
    
    const fileIds = Array.from(allSelectedIds);
    const BATCH_SIZE = 50;

    // Warn if large selection — will be auto-batched
    if (fileIds.length > BATCH_SIZE) {
      const batches = Math.ceil(fileIds.length / BATCH_SIZE);
      if (!window.confirm(
        `You selected ${fileIds.length} files. Processing will be split into ${batches} batches of up to ${BATCH_SIZE} files each. Continue?`
      )) {
        return;
      }
    }

    // Always use background processing - ingestion with AI extraction can take a long time
    try {
      // Split into batches of BATCH_SIZE
      const batches = [];
      for (let i = 0; i < fileIds.length; i += BATCH_SIZE) {
        batches.push(fileIds.slice(i, i + BATCH_SIZE));
      }

      for (const batch of batches) {
        await evidenceAPI.processBackground(caseId, batch, selectedProfile, maxWorkers, imageProvider);
      }

      alert(`Processing ${fileIds.length} file(s) in ${batches.length} batch(es) with ${maxWorkers} parallel worker(s). Check the Background Tasks panel for progress.`);
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

  // Handle deleting an evidence file
  const handleDeleteFile = async (fileId, filename) => {
    setDeleting(true);
    setError(null);
    try {
      const result = await evidenceAPI.delete(fileId, caseId, true);
      // Refresh file list
      await loadFiles();
      setDeleteConfirm(null);
      setSelectedIds((prev) => {
        const next = new Set(prev);
        next.delete(fileId);
        return next;
      });
      // Log summary
      const recycledCount = result?.exclusive_entities_recycled?.length || 0;
      if (recycledCount > 0) {
        console.log(`Deleted ${filename}: ${recycledCount} exclusive entities moved to recycling bin`);
      }
    } catch (err) {
      console.error('Failed to delete file:', err);
      setError(err.message || 'Failed to delete file');
    } finally {
      setDeleting(false);
    }
  };

  // Helper function to get file extension
  const getFileExtension = (filename) => {
    const parts = filename.split('.');
    return parts.length > 1 ? parts[parts.length - 1].toLowerCase() : '';
  };

  // Helper function to get file type from extension
  const getFileType = (extension) => {
    const imageTypes = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp', 'tiff', 'tif'];
    const docTypes = ['pdf', 'doc', 'docx', 'txt', 'rtf', 'odt'];
    const audioTypes = ['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a', 'wma'];
    const videoTypes = ['mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv', 'webm'];
    const dataTypes = ['xls', 'xlsx', 'csv', 'json', 'xml'];

    if (imageTypes.includes(extension)) return 'Image';
    if (docTypes.includes(extension)) return 'Document';
    if (audioTypes.includes(extension)) return 'Audio';
    if (videoTypes.includes(extension)) return 'Video';
    if (dataTypes.includes(extension)) return 'Data';
    return 'Other';
  };

  // Get all unique file types from files
  const getAllFileTypes = (fileList) => {
    const types = new Set();
    fileList.forEach((file) => {
      const ext = getFileExtension(file.original_filename);
      const type = getFileType(ext);
      types.add(type);
    });
    return Array.from(types).sort();
  };

  // Filter unprocessed files (not LLM processed)
  const filterUnprocessed = (fileList) => {
    return fileList.filter((file) => {
      if (file.status !== 'unprocessed' && file.status !== 'failed') return false;
      if (unprocessedFilter && !file.original_filename.toLowerCase().includes(unprocessedFilter.toLowerCase())) {
        return false;
      }
      if (unprocessedTypeFilter) {
        const ext = getFileExtension(file.original_filename);
        const type = getFileType(ext);
        if (type !== unprocessedTypeFilter) return false;
      }
      return true;
    });
  };

  // Filter processed files (LLM processed)
  const filterProcessed = (fileList) => {
    return fileList.filter((file) => {
      if (file.status !== 'processed') return false;
      if (processedFilter && !file.original_filename.toLowerCase().includes(processedFilter.toLowerCase())) {
        return false;
      }
      if (processedTypeFilter) {
        const ext = getFileExtension(file.original_filename);
        const type = getFileType(ext);
        if (type !== processedTypeFilter) return false;
      }
      return true;
    });
  };

  const unprocessed = files.filter(
    (f) => f.status === 'unprocessed' || f.status === 'failed'
  );
  const processed = files.filter(
    (f) => f.status === 'processed'
  );
  const hashCopyCount = useMemo(() => {
    const counts = {};
    for (const f of files) {
      if (f.sha256) {
        counts[f.sha256] = (counts[f.sha256] || 0) + 1;
      }
    }
    return counts;
  }, [files]);

  const filteredUnprocessed = filterUnprocessed(unprocessed);
  const filteredProcessed = filterProcessed(processed);

  // Cap how many file rows we render to keep the page responsive on large
  // cases (e.g. Cellebrite extractions can produce 10k+ files). Users can
  // still see the full count and narrow the list via the filename/type
  // filters above each list.
  const RENDER_CAP = 500;
  const visibleUnprocessed = filteredUnprocessed.slice(0, RENDER_CAP);
  const visibleProcessed = filteredProcessed.slice(0, RENDER_CAP);

  const unprocessedTypes = getAllFileTypes(unprocessed);
  const processedTypes = getAllFileTypes(processed);

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
                        <p className="text-xs text-light-600 italic line-clamp-3">
                          {profileDetails.ingestion?.system_context || 'N/A'}
                        </p>
                      </div>
                      {profileDetails.ingestion?.special_entity_types?.length > 0 && (
                        <div>
                          <p className="text-xs font-medium text-light-700 mb-1">
                            Special Entity Types ({profileDetails.ingestion?.special_entity_types?.length || 0}):
                          </p>
                          <div className="flex flex-wrap gap-1">
                            {profileDetails.ingestion?.special_entity_types?.map((entity, idx) => (
                              <span
                                key={idx}
                                className="px-2 py-0.5 bg-owl-blue-100 text-owl-blue-700 text-xs rounded"
                                title={entity.description || ''}
                              >
                                {entity.name}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                      <div>
                        <p className="text-xs font-medium text-light-700">
                          Temperature: {profileDetails.ingestion?.temperature ?? 1.0}
                        </p>
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
                        <p className="text-xs text-light-600 italic line-clamp-3">
                          {profileDetails.chat?.system_context || 'N/A'}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs font-medium text-light-700 mb-1">Analysis Guidance:</p>
                        <p className="text-xs text-light-600 line-clamp-2">
                          {profileDetails.chat?.analysis_guidance || 'N/A'}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs font-medium text-light-700">
                          Temperature: {profileDetails.chat?.temperature ?? 1.0}
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
      <div className="flex-1 flex flex-row overflow-hidden">
        {/* Left: Upload + File Navigator */}
        <div className="w-1/4 border-r border-light-200 flex flex-col overflow-y-auto">
          {/* Upload Panel */}
          <div className="p-4 border-b border-light-200 bg-white">
            <h2 className="text-md font-semibold text-owl-blue-900 mb-2">
              Upload Evidence
            </h2>
            <p className="text-xs text-light-600 mb-3">
              Upload individual files or an entire folder. For Cellebrite .zip archives (incl. large 30GB+ exports), use the resumable uploader below — it chunks the file and survives network drops.
            </p>
            <div className="flex flex-col gap-2">
              <label className={`flex items-center justify-center gap-2 px-4 py-3 border-2 border-dashed border-light-300 rounded-lg text-sm transition-colors ${
                !canUploadEvidence || uploading || !caseId
                  ? 'text-light-400 bg-light-100 cursor-not-allowed'
                  : 'text-light-700 bg-light-50 hover:bg-light-100 cursor-pointer'
              }`}>
                <UploadCloud className="w-5 h-5 text-owl-blue-700" />
                <span>{uploading ? 'Uploading…' : 'Click to choose files'}</span>
                <input
                  type="file"
                  multiple
                  className="hidden"
                  onChange={handleFileSelect}
                  disabled={!canUploadEvidence || uploading || !caseId}
                />
              </label>
              <label className={`flex items-center justify-center gap-2 px-4 py-3 border-2 border-dashed border-light-300 rounded-lg text-sm transition-colors ${
                !canUploadEvidence || uploading || !caseId
                  ? 'text-light-400 bg-light-100 cursor-not-allowed'
                  : 'text-light-700 bg-light-50 hover:bg-light-100 cursor-pointer'
              }`}>
                <Folder className="w-5 h-5 text-owl-blue-700" />
                <span>{uploading ? 'Uploading…' : 'Click to choose folder'}</span>
                <input
                  type="file"
                  multiple
                  webkitdirectory=""
                  directory=""
                  className="hidden"
                  onChange={handleFolderSelect}
                  disabled={!canUploadEvidence || uploading || !caseId}
                />
              </label>
            </div>
            <div className="mt-3">
              <UppyEvidenceUploader
                caseId={caseId}
                owner={authUsername}
                disabled={!canUploadEvidence || !caseId}
                onUploadComplete={handleResumableUploadComplete}
              />
            </div>
            {/* Persistent ingestion status: what's been uploaded and where it
                is (queued → processing → done/failed). Bridges the gap between
                the upload finishing and the result appearing in a viewer. */}
            {caseId && (
              <div className="mt-3 rounded-lg border border-light-300 bg-white">
                <div className="flex items-center justify-between px-3 py-2 border-b border-light-200">
                  <h4 className="text-xs font-semibold text-owl-blue-900 uppercase tracking-wide">
                    Evidence Ingestion
                  </h4>
                  {(caseTasks.some(t => t.status === 'running' || t.status === 'pending') || unpackingFiles.length > 0) && (
                    <span className="flex items-center gap-1 text-[11px] text-owl-blue-700">
                      <Loader2 className="w-3 h-3 animate-spin" /> processing
                    </span>
                  )}
                </div>
                <div className="max-h-56 overflow-y-auto divide-y divide-light-100">
                  {/* Files whose upload just finished but whose ingest task hasn't surfaced yet */}
                  {unpackingFiles.map((f) => (
                    <div key={`unpack-${f.name}`} className="flex items-start gap-2 px-3 py-2">
                      <Loader2 className="w-4 h-4 mt-0.5 shrink-0 animate-spin text-owl-blue-700" />
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-medium text-dark-800 truncate" title={f.name}>{f.name}</p>
                        <p className="text-[11px] text-owl-blue-700">Upload complete — unpacking &amp; ingesting…</p>
                      </div>
                    </div>
                  ))}

                  {caseTasks.length === 0 && unpackingFiles.length === 0 && (
                    <p className="px-3 py-3 text-[11px] italic text-light-500">
                      Nothing ingested yet for this case. Uploads and Cellebrite ingests will appear here with live status.
                    </p>
                  )}

                  {caseTasks.slice(0, 12).map((t) => {
                    const meta = TASK_TYPE_META[t.task_type] || { label: t.task_type, Icon: FileText };
                    const s = taskStatusMeta(t.status);
                    const total = t.progress?.total || 0;
                    const done = t.progress?.completed || 0;
                    const failed = t.progress?.failed || 0;
                    const TypeIcon = meta.Icon;
                    const StatusIcon = s.Icon;
                    return (
                      <div key={t.id} className="flex items-start gap-2 px-3 py-2">
                        <TypeIcon className="w-4 h-4 mt-0.5 shrink-0 text-light-500" />
                        <div className="min-w-0 flex-1">
                          <p className="text-xs font-medium text-dark-800 truncate" title={t.task_name || meta.label}>
                            {t.task_name || meta.label}
                          </p>
                          <div className="flex items-center gap-1.5 text-[11px] text-light-600">
                            <StatusIcon className={`w-3 h-3 ${s.cls} ${s.spin ? 'animate-spin' : ''}`} />
                            <span className={s.cls}>{s.label}</span>
                            {total > 0 && (
                              <span className="text-light-500">· {done}/{total}{failed > 0 ? ` (${failed} failed)` : ''}</span>
                            )}
                            <span className="text-light-400">· {relativeTime(t.updated_at || t.created_at)}</span>
                          </div>
                          {t.status === 'failed' && t.error && (
                            <p className="mt-0.5 text-[11px] text-red-600 truncate" title={t.error}>{t.error}</p>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
            {uploading && uploadProgress && (() => {
              const { loaded = 0, total = 0, lengthComputable } = uploadProgress;
              const hasTotal = lengthComputable && total > 0;
              const percent = hasTotal ? Math.min(100, Math.round((loaded / total) * 100)) : 0;
              return (
                <div className="mt-3">
                  <div className="flex items-center justify-between text-xs text-light-600 mb-1">
                    <span>
                      {hasTotal
                        ? `${formatBytes(loaded)} of ${formatBytes(total)}`
                        : `${formatBytes(loaded)} uploaded`}
                    </span>
                    {hasTotal && <span>{percent}%</span>}
                  </div>
                  <div className="w-full h-2 bg-light-200 rounded-full overflow-hidden">
                    {hasTotal ? (
                      <div
                        className="h-2 bg-owl-blue-500 transition-all"
                        style={{ width: `${percent}%` }}
                      />
                    ) : (
                      <div className="h-2 bg-owl-blue-500 animate-pulse" style={{ width: '40%' }} />
                    )}
                  </div>
                  <p className="text-[11px] text-light-500 mt-1">
                    Sending bytes to server. Processing will start once the upload finishes.
                  </p>
                </div>
              );
            })()}
            {!caseId && (
              <p className="text-xs text-red-500 mt-2">
                You must create a case before uploading evidence.
              </p>
            )}
            {!canUploadEvidence && caseId && (
              <p className="text-xs text-amber-600 mt-2">
                You have view-only access to this case.
              </p>
            )}
          </div>

          {/* File Navigator */}
          <div className="border-b border-light-200 bg-white p-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold text-owl-blue-900">
                File Navigator
              </h3>
              <button
                onClick={() => setShowFileNavigator(!showFileNavigator)}
                className="p-1 rounded hover:bg-light-100"
                title={showFileNavigator ? 'Hide navigator' : 'Show navigator'}
              >
                {showFileNavigator ? (
                  <ChevronDown className="w-4 h-4 text-light-600" />
                ) : (
                  <ChevronRight className="w-4 h-4 text-light-600" />
                )}
              </button>
            </div>
            {showFileNavigator && (
              <div className="h-64 border border-light-200 rounded bg-white">
                {caseId ? (
                  <FileNavigator
                    key={fileNavKey}
                    caseId={caseId}
                    onFileSelect={handleFileNavigatorSelect}
                    selectedFilePath={selectedFilePath}
                    selectedFilePaths={selectedFilePaths}
                    selectedFolderPaths={selectedFolderPaths}
                    onFileMultiSelect={handleFileNavigatorMultiSelect}
                    onFolderSelect={handleFolderNavigatorSelect}
                    onInfoClick={handleFileNavigatorInfo}
                    wiretapProcessedFolders={wiretapProcessedFolders}
                    evidenceFiles={files}
                  />
                ) : (
                  <div className="flex flex-col items-center justify-center py-12 text-light-600">
                    <HardDrive className="w-12 h-12 mb-3 opacity-50" />
                    <p className="text-sm italic">Select or create a case to browse files</p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Processed Wiretap Folders List */}
          <div className="border-b border-light-200 bg-white p-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold text-owl-blue-900 flex items-center gap-2">
                <Radio className="w-4 h-4 text-green-600" />
                Processed Wiretap Folders ({processedWiretapList.length})
              </h3>
              <div className="flex items-center gap-1">
                <button
                  onClick={loadProcessedWiretaps}
                  className="p-1 rounded hover:bg-light-100"
                  title="Refresh list"
                >
                  <RefreshCw className="w-3.5 h-3.5 text-light-600" />
                </button>
                <button
                  onClick={() => setShowProcessedWiretaps(!showProcessedWiretaps)}
                  className="p-1 rounded hover:bg-light-100"
                  title={showProcessedWiretaps ? 'Collapse' : 'Expand'}
                >
                  {showProcessedWiretaps ? (
                    <ChevronDown className="w-4 h-4 text-light-600" />
                  ) : (
                    <ChevronRight className="w-4 h-4 text-light-600" />
                  )}
                </button>
              </div>
            </div>
            {showProcessedWiretaps && processedWiretapList.length > 0 && (
              <div className="max-h-64 overflow-y-auto border border-green-200 rounded bg-green-50">
                <div className="p-3 space-y-2">
                  {processedWiretapList.map((item, idx) => (
                    <div
                      key={`${item.case_id}-${item.folder_path}-${idx}`}
                      className="flex items-center justify-between p-2 bg-white rounded border border-green-200"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium text-green-900 truncate">
                          {item.folder_path.split('/').pop() || item.folder_path}
                        </div>
                        <div className="text-xs text-green-700 mt-0.5">
                          {item.processed_at ? new Date(item.processed_at).toLocaleString() : 'Unknown date'}
                        </div>
                      </div>
                      <CheckCircle2 className="w-4 h-4 text-green-600 flex-shrink-0 ml-2" />
                    </div>
                  ))}
                </div>
              </div>
            )}
            {showProcessedWiretaps && processedWiretapList.length === 0 && (
              <div className="text-xs text-light-600 italic p-2">
                No processed wiretap folders yet
              </div>
            )}
          </div>

        </div>

        {/* Middle: File Info Viewer */}
        <div className="w-1/3 border-r border-light-200 flex flex-col">
          <div className="p-4 border-b border-light-200 bg-white">
            <h3 className="text-sm font-semibold text-owl-blue-900">
              File & Folder Information
            </h3>
          </div>
          <FileInfoViewer 
            selectedFiles={Array.from(selectedIds)}
            files={files}
            folderInfo={selectedFolderInfo}
            foldersInfo={selectedFoldersInfo}
            caseId={caseId}
            onProcessWiretap={handleProcessWiretap}
            onCreateFolderProfile={(folderPath) => {
              setFolderProfilePath(folderPath);
              setShowFolderProfileModal(true);
            }}
            profilesWithFolderProcessing={profilesWithFolderProcessing}
            onEditProfile={async (profileName) => {
              // Validate profile name before proceeding
              if (!profileName || typeof profileName !== 'string' || !profileName.trim()) {
                console.error('[EvidenceProcessingView] Invalid profile name provided:', profileName);
                alert('Please select a valid profile before editing.');
                return;
              }
              
              const trimmedName = profileName.trim();
              
              // Reject placeholder values
              if (trimmedName === 'profile-name' || trimmedName === '' || trimmedName.toLowerCase() === 'profile name') {
                console.error('[EvidenceProcessingView] Placeholder profile name detected:', trimmedName);
                alert('Please select a valid profile from the dropdown before editing.');
                return;
              }
              
              console.log('[EvidenceProcessingView] Editing profile:', trimmedName);
              
              // Check if this is a folder profile (has folder_processing)
              try {
                const profileDetails = await profilesAPI.get(trimmedName);
                if (profileDetails.folder_processing) {
                  // It's a folder profile - open FolderProfileModal in edit mode
                  setEditingFolderProfileName(trimmedName);
                  setShowFolderProfileModal(true);
                } else {
                  // Regular profile - open ProfileEditor
                  setEditingProfileName(trimmedName);
                  setShowProfileEditor(true);
                }
              } catch (err) {
                console.error('[EvidenceProcessingView] Failed to check profile type:', err);
                // If it's a 404, show a helpful message
                if (err.message && (err.message.includes('404') || err.message.includes('not found'))) {
                  alert(`Profile "${trimmedName}" not found. Please select a valid profile.`);
                  return;
                }
                // Fallback to ProfileEditor for other errors
                setEditingProfileName(trimmedName);
                setShowProfileEditor(true);
              }
            }}
          />
        </div>

        {/* Right: Unprocessed (top) and Processed (bottom) */}
        <div className="w-2/5 flex flex-col">
          {/* Processing Controls */}
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
            <div className="flex items-center gap-3">
              {/* Image provider selector */}
              <div className="flex items-center gap-2">
                <label className="text-xs text-light-600 whitespace-nowrap">Image OCR:</label>
                <select
                  value={imageProvider}
                  onChange={(e) => setImageProvider(e.target.value)}
                  className="px-2 py-1 border border-light-300 rounded text-sm bg-white focus:outline-none focus:border-owl-blue-500"
                >
                  <option value="tesseract">Local (Tesseract)</option>
                  <option value="openai">AI Vision (GPT-4o)</option>
                </select>
              </div>
              {/* Parallel files selector */}
              <div className="flex items-center gap-2">
                <label className="text-xs text-light-600 whitespace-nowrap">Parallel:</label>
                <select
                  value={maxWorkers}
                  onChange={(e) => setMaxWorkers(parseInt(e.target.value))}
                  className="px-2 py-1 border border-light-300 rounded text-sm bg-white focus:outline-none focus:border-owl-blue-500"
                >
                  <option value="1">1</option>
                  <option value="2">2</option>
                  <option value="4">4</option>
                  <option value="8">8</option>
                </select>
              </div>
              <button
                onClick={handleProcessSelected}
                disabled={!canUploadEvidence || processing || (selectedIds.size === 0 && selectedFilePaths.size === 0)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm text-white transition-colors ${
                  !canUploadEvidence || processing || (selectedIds.size === 0 && selectedFilePaths.size === 0)
                    ? 'bg-light-300 cursor-not-allowed'
                    : 'bg-owl-blue-600 hover:bg-owl-blue-700'
                }`}
                title={!canUploadEvidence ? 'Processing requires upload permission' : ''}
              >
                <PlayCircle className="w-4 h-4" />
                {!canUploadEvidence ? 'Process (view-only)' :
                 processing ? 'Processing…' : (() => {
                  // Calculate total selected files (from both sources)
                  const navigatorFileIds = getFileIdsFromPaths(selectedFilePaths);
                  const allSelectedIds = new Set([...selectedIds, ...navigatorFileIds]);
                  const totalCount = allSelectedIds.size;
                  return `Process ${totalCount} file(s)`;
                })()}
              </button>
              {/* Process All shortcut — selects all unprocessed files */}
              {unprocessed.length > 0 && selectedIds.size === 0 && selectedFilePaths.size === 0 && !processing && canUploadEvidence && (
                <button
                  onClick={() => selectAll(unprocessed.map((f) => f.id))}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-owl-blue-700 bg-owl-blue-50 border border-owl-blue-200 hover:bg-owl-blue-100 transition-colors"
                  title="Select all unprocessed files for processing"
                >
                  Select All ({unprocessed.length})
                </button>
              )}
            </div>
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

          {/* Unprocessed Files (Top) */}
          <div className="flex-1 overflow-y-auto border-b border-light-200 flex flex-col">
            <div className="p-4 border-b border-light-200 bg-white flex-shrink-0">
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
                    disabled={selectedIds.size === 0 && selectedFilePaths.size === 0}
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
                  <button
                    onClick={handleSyncFromDisk}
                    disabled={syncing}
                    className="p-1.5 rounded-full hover:bg-light-100 disabled:opacity-50"
                    title="Sync from disk (registers any unregistered files in this case folder — may be slow for large folders)"
                  >
                    <HardDrive className={`w-4 h-4 ${syncing ? 'animate-pulse' : ''}`} />
                  </button>
                </div>
              </div>
              
              {/* Filename Filter */}
              <div className="mb-2">
                <input
                  type="text"
                  placeholder="Filter by filename..."
                  value={unprocessedFilter}
                  onChange={(e) => setUnprocessedFilter(e.target.value)}
                  className="w-full px-3 py-1.5 text-sm border border-light-300 rounded-md focus:outline-none focus:border-owl-blue-500"
                />
              </div>
              
              {/* File Type Pills */}
              {unprocessedTypes.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  <button
                    onClick={() => setUnprocessedTypeFilter(null)}
                    className={`px-2 py-1 text-xs rounded-full border transition-colors ${
                      unprocessedTypeFilter === null
                        ? 'bg-owl-blue-500 text-white border-owl-blue-500'
                        : 'bg-white text-light-700 border-light-300 hover:bg-light-100'
                    }`}
                  >
                    All
                  </button>
                  {unprocessedTypes.map((type) => (
                    <button
                      key={type}
                      onClick={() => setUnprocessedTypeFilter(type)}
                      className={`px-2 py-1 text-xs rounded-full border transition-colors ${
                        unprocessedTypeFilter === type
                          ? 'bg-owl-blue-500 text-white border-owl-blue-500'
                          : 'bg-white text-light-700 border-light-300 hover:bg-light-100'
                      }`}
                    >
                      {type}
                    </button>
                  ))}
                </div>
              )}
            </div>
            
            <div className="flex-1 overflow-y-auto p-4">
              {loading ? (
                <div className="flex items-center justify-center py-12 text-light-600">
                  <RefreshCw className="w-5 h-5 mr-2 animate-spin" />
                  Loading evidence…
                </div>
              ) : filteredUnprocessed.length === 0 ? (
                <p className="text-sm text-light-600 italic">
                  {unprocessed.length === 0
                    ? 'No unprocessed files. Upload new files or select from processed files to re-run ingestion if needed.'
                    : 'No files match the current filters.'}
                </p>
              ) : (
                <>
                {/* Helper text for first-time users */}
                {selectedIds.size === 0 && selectedFilePaths.size === 0 && !processing && (
                  <p className="text-xs text-light-500 mb-3 italic">
                    Select files below and click &quot;Process&quot; above to begin evidence extraction.
                  </p>
                )}
                {filteredUnprocessed.length > RENDER_CAP && (
                  <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2 mb-3">
                    Showing first {RENDER_CAP.toLocaleString()} of {filteredUnprocessed.length.toLocaleString()} files. Use the filename or type filters above to narrow the list.
                  </p>
                )}
                <div className="space-y-2">
                  {visibleUnprocessed.map((file) => (
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
                            {file.sha256 && hashCopyCount[file.sha256] > 1 && (
                              <span className="text-[10px] text-violet-700 bg-violet-100 px-1.5 py-0.5 rounded font-medium flex-shrink-0" title={`${hashCopyCount[file.sha256]} copies of this file in the system`}>
                                ×{hashCopyCount[file.sha256]}
                              </span>
                            )}
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
                      {canUploadEvidence && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setDeleteConfirm({ id: file.id, filename: file.original_filename });
                          }}
                          className="p-1.5 text-light-400 hover:text-red-500 rounded hover:bg-red-50 transition-colors flex-shrink-0"
                          title="Delete file"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
                </>
              )}
            </div>
          </div>

          {/* Processed Files (Bottom) */}
          <div className="flex-1 overflow-y-auto flex flex-col">
            <div className="p-4 border-b border-light-200 bg-white flex-shrink-0">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-owl-blue-900">
                  LLM Processed Files
                </h3>
                <div className="flex items-center gap-2 text-xs text-light-600">
                  <span>
                    {processed.length} file{processed.length === 1 ? '' : 's'}
                  </span>
                </div>
              </div>
              
              {/* Filename Filter */}
              <div className="mb-2">
                <input
                  type="text"
                  placeholder="Filter by filename..."
                  value={processedFilter}
                  onChange={(e) => setProcessedFilter(e.target.value)}
                  className="w-full px-3 py-1.5 text-sm border border-light-300 rounded-md focus:outline-none focus:border-owl-blue-500"
                />
              </div>
              
              {/* File Type Pills */}
              {processedTypes.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  <button
                    onClick={() => setProcessedTypeFilter(null)}
                    className={`px-2 py-1 text-xs rounded-full border transition-colors ${
                      processedTypeFilter === null
                        ? 'bg-owl-blue-500 text-white border-owl-blue-500'
                        : 'bg-white text-light-700 border-light-300 hover:bg-light-100'
                    }`}
                  >
                    All
                  </button>
                  {processedTypes.map((type) => (
                    <button
                      key={type}
                      onClick={() => setProcessedTypeFilter(type)}
                      className={`px-2 py-1 text-xs rounded-full border transition-colors ${
                        processedTypeFilter === type
                          ? 'bg-owl-blue-500 text-white border-owl-blue-500'
                          : 'bg-white text-light-700 border-light-300 hover:bg-light-100'
                      }`}
                    >
                      {type}
                    </button>
                  ))}
                </div>
              )}
            </div>
            
            <div className="flex-1 overflow-y-auto p-4">
              {filteredProcessed.length === 0 ? (
                <p className="text-sm text-light-600 italic">
                  {processed.length === 0
                    ? 'No LLM processed files yet.'
                    : 'No files match the current filters.'}
                </p>
              ) : (
                <>
                {filteredProcessed.length > RENDER_CAP && (
                  <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2 mb-3">
                    Showing first {RENDER_CAP.toLocaleString()} of {filteredProcessed.length.toLocaleString()} files. Use the filename or type filters above to narrow the list.
                  </p>
                )}
                <div className="space-y-2">
                  {visibleProcessed.map((file) => (
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
                            <div className="flex items-center gap-2 min-w-0">
                              <span className="font-medium text-sm text-owl-blue-900 truncate">
                                {file.original_filename}
                              </span>
                              {file.sha256 && hashCopyCount[file.sha256] > 1 && (
                                <span className="text-[10px] text-violet-700 bg-violet-100 px-1.5 py-0.5 rounded font-medium flex-shrink-0" title={`${hashCopyCount[file.sha256]} copies of this file in the system`}>
                                  ×{hashCopyCount[file.sha256]}
                                </span>
                              )}
                            </div>
                            <span className="text-xs text-light-600">
                              {humanSize(file.size)}
                            </span>
                          </div>
                          <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-light-600">
                            <span className="inline-flex items-center gap-1 text-green-700">
                              <CheckCircle2 className="w-3 h-3" />
                              Processed
                            </span>
                            <span>Uploaded: {formatDateTime(file.created_at)}</span>
                            {file.processed_at && (
                              <>
                                <span>•</span>
                                <span>Processed: {formatDateTime(file.processed_at)}</span>
                              </>
                            )}
                          </div>
                        </div>
                      </div>
                      {canUploadEvidence && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setDeleteConfirm({ id: file.id, filename: file.original_filename });
                          }}
                          className="p-1.5 text-light-400 hover:text-red-500 rounded hover:bg-red-50 transition-colors flex-shrink-0 self-center"
                          title="Delete file"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6">
            <div className="flex items-start gap-3 mb-4">
              <div className="p-2 rounded-full bg-red-100">
                <Trash2 className="w-5 h-5 text-red-600" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-light-900">Delete Evidence File</h3>
                <p className="text-sm text-light-600 mt-1">
                  Are you sure you want to delete <strong>{deleteConfirm.filename}</strong>?
                </p>
              </div>
            </div>
            <div className="bg-amber-50 border border-amber-200 rounded-md p-3 mb-4">
              <p className="text-xs text-amber-800">
                <strong>This will:</strong>
              </p>
              <ul className="text-xs text-amber-700 mt-1 ml-4 list-disc space-y-0.5">
                <li>Remove the file from the system</li>
                <li>Delete the document from the knowledge graph</li>
                <li>Move entities exclusive to this file to the recycling bin</li>
                <li>Entities shared with other files will be kept</li>
              </ul>
            </div>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setDeleteConfirm(null)}
                className="px-4 py-2 text-sm border border-light-300 rounded-md hover:bg-light-100"
                disabled={deleting}
              >
                Cancel
              </button>
              <button
                onClick={() => handleDeleteFile(deleteConfirm.id, deleteConfirm.filename)}
                disabled={deleting}
                className="px-4 py-2 text-sm bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50 flex items-center gap-2"
              >
                {deleting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Deleting...
                  </>
                ) : (
                  'Delete File'
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Ingestion Log */}
      <div className="border-t border-light-200 bg-white px-6 py-4">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-owl-blue-900">
              Ingestion Log
            </h3>
            <button
              onClick={() => setShowIngestionLog(!showIngestionLog)}
              className="p-1 rounded hover:bg-light-100"
              title={showIngestionLog ? 'Collapse' : 'Expand'}
            >
              {showIngestionLog ? (
                <ChevronDown className="w-4 h-4 text-light-600" />
              ) : (
                <ChevronRight className="w-4 h-4 text-light-600" />
              )}
            </button>
          </div>
          <div className="flex items-center gap-2 text-xs text-light-600">
            {processing && showIngestionLog && (
              <span className="text-owl-blue-700 font-medium">
                Processing… logs auto-update every few seconds
              </span>
            )}
            {showIngestionLog && (
              <button
                onClick={loadLogs}
                className="px-2 py-1 border border-light-300 rounded-md hover:bg-light-100"
              >
                Refresh Now
              </button>
            )}
          </div>
        </div>
        {showIngestionLog && (
          <div
            ref={logContainerRef}
            className="h-52 w-full border border-light-200 rounded-md bg-light-50 overflow-y-auto text-xs font-mono p-2"
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
        )}
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
        onProfileSaved={async (savedProfileName) => {
          // Reload profiles list
          try {
            const data = await profilesAPI.list();
            setProfiles(data || []);
            // If we were editing a profile, keep it selected; otherwise select the newly saved one
            if (editingProfileName) {
              setSelectedProfile(editingProfileName);
            } else if (savedProfileName) {
              setSelectedProfile(savedProfileName);
            }
            
            // Reload profiles with folder processing
            const profilesWithFolder = [];
            for (const profile of data || []) {
              try {
                const details = await profilesAPI.get(profile.name);
                if (details.folder_processing) {
                  profilesWithFolder.push(details);
                }
              } catch (err) {
                // Skip profiles that fail to load
                console.warn(`Failed to load profile ${profile.name}:`, err);
              }
            }
            setProfilesWithFolderProcessing(profilesWithFolder);
          } catch (err) {
            console.error('Failed to reload profiles:', err);
          }
        }}
      />
      
      {/* Folder Profile Modal */}
      <FolderProfileModal
        isOpen={showFolderProfileModal}
        onClose={() => {
          setShowFolderProfileModal(false);
          setFolderProfilePath(null);
          setEditingFolderProfileName(null);
        }}
        editingProfileName={editingFolderProfileName}
        onProfileSaved={async (savedProfile) => {
          // Reload profiles list to include the newly saved profile
          try {
            const data = await profilesAPI.list();
            setProfiles(data || []);
            
            // Update profilesWithFolderProcessing if the new profile has folder_processing
            if (savedProfile?.folder_processing) {
              // Add the new profile to the list or reload the entire list
              const profilesWithFolder = [];
              for (const profile of data || []) {
                try {
                  const details = await profilesAPI.get(profile.name);
                  if (details.folder_processing) {
                    profilesWithFolder.push(details);
                  }
                } catch (err) {
                  // Skip profiles that fail to load
                  console.warn(`Failed to load profile ${profile.name}:`, err);
                }
              }
              setProfilesWithFolderProcessing(profilesWithFolder);
            }
            
            // If no profile is selected, select the newly saved one
            if (!selectedProfile && savedProfile?.name) {
              setSelectedProfile(savedProfile.name);
            }
            
            // Clear editing state
            setEditingFolderProfileName(null);
          } catch (err) {
            console.error('Failed to reload profiles after save:', err);
          }
        }}
        caseId={caseId}
        folderPath={editingFolderProfileName ? null : (folderProfilePath || '')}
      />
    </div>
  );
}

