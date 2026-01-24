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
  ChevronRight,
  X,
  Edit,
  Folder,
  FolderOpen,
  HardDrive,
  Radio,
} from 'lucide-react';
import { evidenceAPI, profilesAPI, filesystemAPI, backgroundTasksAPI } from '../services/api';
import { useCasePermissions } from '../contexts/CasePermissionContext';
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
  const [uploading, setUploading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState(null);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [logs, setLogs] = useState([]);
  const logContainerRef = useRef(null);
  const completedWiretapTaskIdsRef = useRef(new Set()); // Track completed wiretap task IDs to avoid duplicate refreshes
  const completedUploadTaskIdsRef = useRef(new Set()); // Track completed upload task IDs to avoid duplicate refreshes
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
  const [showIngestionLog, setShowIngestionLog] = useState(true); // Expanded by default
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

  useEffect(() => {
    loadFiles();
    loadLogs();
    loadProcessedWiretaps();
  }, [loadFiles, loadLogs, loadProcessedWiretaps]);

  // Poll logs every 5 seconds only while actively processing
  // Also check for completed wiretap tasks to refresh processed folders list
  // And check for completed file upload tasks to refresh file navigator
  useEffect(() => {
    if (!caseId) {
      // Reset completed task IDs when case changes
      completedWiretapTaskIdsRef.current.clear();
      completedUploadTaskIdsRef.current.clear();
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
          } else if (task.status === 'completed' || task.status === 'failed') {
            // Track completed/failed tasks to avoid duplicate refreshes
            completedUploadTaskIdsRef.current.add(task.id);
          }
        }
        
        // Refresh files if any new upload tasks completed
        if (shouldRefreshFiles) {
          await loadFiles();
        }
        
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
      const result = await evidenceAPI.upload(caseId, fileList);
      
      if (result.task_id) {
        // Background task created (for large uploads >5 files)
        setShowBackgroundTasksPanel(true);
        // Refresh files after a short delay
        setTimeout(() => loadFiles(), 2000);
      } else {
        // Synchronous upload completed
        await loadFiles();
      }
      
      event.target.value = ''; // reset input so same files can be re-selected if needed
    } catch (err) {
      console.error('Failed to upload files:', err);
      setError(err.message || 'Failed to upload files');
    } finally {
      setUploading(false);
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
    setError(null);
    try {
      // Upload folder as background task
      const result = await evidenceAPI.uploadFolder(caseId, fileList);
      
      if (result.task_id) {
        // Background task created - show message and open background tasks panel
        setShowBackgroundTasksPanel(true);
        // Refresh files after a short delay to catch any quick uploads
        setTimeout(() => loadFiles(), 2000);
      } else {
        // Synchronous upload completed
        await loadFiles();
      }
      
      event.target.value = ''; // reset input
    } catch (err) {
      console.error('Failed to upload folder:', err);
      setError(err.message || 'Failed to upload folder');
    } finally {
      setUploading(false);
    }
  };

  const handleFileNavigatorSelect = (filePath, event) => {
    setSelectedFilePath(filePath);
    // Normalize the file path from navigator (relative to case root)
    const normalizedFilePath = filePath.replace(/\\/g, '/').replace(/^\/+|\/+$/g, '');
    
    // Find matching file in the files list if it exists
    const matchingFile = files.find(f => {
      if (!f.stored_path) return false;
      
      // Normalize stored_path (remove ingestion/data/ and case_id prefixes)
      let normalizedStoredPath = f.stored_path.replace(/\\/g, '/');
      normalizedStoredPath = normalizedStoredPath.replace(/^ingestion\/data\//, '');
      if (caseId) {
        const casePrefix = `${caseId}/`;
        if (normalizedStoredPath.startsWith(casePrefix)) {
          normalizedStoredPath = normalizedStoredPath.substring(casePrefix.length);
        }
      }
      normalizedStoredPath = normalizedStoredPath.replace(/^\/+|\/+$/g, '');
      
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
      const matchingFile = files.find(f => {
        const storedPath = f.stored_path || '';
        // Try to match the file path
        return storedPath.includes(item.path) || 
               item.path.includes(storedPath) ||
               storedPath.endsWith(item.name) ||
               item.path.endsWith(f.original_filename);
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
      // Gather folder statistics
      setSelectedFilePath(item.path);
      setSelectedFolderInfo(null); // Clear while loading
      
      try {
        // Get all files in the folder (recursively)
        const folderFiles = await getFolderFilesRecursive(item.path);
        
        // Match with evidence files
        const folderEvidenceFiles = folderFiles.map(filePath => {
          // Extract filename from path
          const fileName = filePath.split('/').pop() || filePath.split('\\').pop() || filePath;
          // Find matching evidence file
          return files.find(f => {
            const storedPath = f.stored_path || '';
            const originalFilename = f.original_filename || '';
            return storedPath.includes(filePath) || 
                   filePath.includes(storedPath) ||
                   storedPath.endsWith(fileName) ||
                   originalFilename === fileName ||
                   filePath.endsWith(originalFilename);
          });
        }).filter(Boolean);
        
        // Calculate statistics
        const processedCount = folderEvidenceFiles.filter(f => 
          f.status === 'processed' || f.status === 'duplicate'
        ).length;
        const unprocessedCount = folderEvidenceFiles.filter(f => 
          f.status === 'unprocessed' || f.status === 'failed'
        ).length;
        
        // Get file types
        const fileTypes = new Set();
        folderEvidenceFiles.forEach(f => {
          const ext = (f.original_filename || '').split('.').pop()?.toLowerCase() || '';
          if (ext) {
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
            else if (ext) fileTypes.add('Other');
          }
        });
        
        // Check wiretap suitability
        let wiretapInfo = null;
        try {
          const wiretapCheck = await evidenceAPI.checkWiretapFolder(caseId, item.path);
          wiretapInfo = wiretapCheck;
          // Update wiretap processed folders set
          if (wiretapCheck.processed) {
            setWiretapProcessedFolders(prev => new Set([...prev, item.path]));
          }
        } catch (err) {
          console.error('Failed to check wiretap suitability:', err);
        }
        
        setSelectedFolderInfo({
          path: item.path,
          name: item.name,
          totalFiles: folderEvidenceFiles.length,
          processedCount,
          unprocessedCount,
          fileTypes: Array.from(fileTypes).sort(),
          availableProcessors: profiles.map(p => ({
            name: p.name,
            description: p.description || ''
          })),
          wiretapInfo
        });
        
        // Clear file selection when showing folder info
        setSelectedIds(new Set());
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

  // Helper function to recursively get all files in a folder
  const getFolderFilesRecursive = async (folderPath) => {
    const allFiles = [];
    
    const traverse = async (path) => {
      try {
        const result = await filesystemAPI.list(caseId, path || null);
        const items = result?.items || [];
        
        for (const item of items) {
          if (item.type === 'file') {
            allFiles.push(item.path);
          } else if (item.type === 'directory') {
            // Recursively traverse subdirectories
            await traverse(item.path);
          }
        }
      } catch (err) {
        console.error(`Failed to list directory ${path}:`, err);
      }
    };
    
    await traverse(folderPath);
    return allFiles;
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
      
      // Normalize stored_path (remove ingestion/data/ and case_id prefixes)
      let normalizedStoredPath = f.stored_path.replace(/\\/g, '/');
      normalizedStoredPath = normalizedStoredPath.replace(/^ingestion\/data\//, '');
      if (caseId) {
        const casePrefix = `${caseId}/`;
        if (normalizedStoredPath.startsWith(casePrefix)) {
          normalizedStoredPath = normalizedStoredPath.substring(casePrefix.length);
        }
      }
      normalizedStoredPath = normalizedStoredPath.replace(/^\/+|\/+$/g, '');
      
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
          
          // Match with evidence files
          const folderEvidenceFiles = folderFiles.map(filePath => {
            const fileName = filePath.split('/').pop() || filePath.split('\\').pop() || filePath;
            return files.find(f => {
              const storedPath = f.stored_path || '';
              const originalFilename = f.original_filename || '';
              return storedPath.includes(filePath) || 
                     filePath.includes(storedPath) ||
                     storedPath.endsWith(fileName) ||
                     originalFilename === fileName ||
                     filePath.endsWith(originalFilename);
            });
          }).filter(Boolean);
          
          // Calculate statistics
          const processedCount = folderEvidenceFiles.filter(f => 
            f.status === 'processed' || f.status === 'duplicate'
          ).length;
          const unprocessedCount = folderEvidenceFiles.filter(f => 
            f.status === 'unprocessed' || f.status === 'failed'
          ).length;
          
          // Get file types
          const fileTypes = new Set();
          folderEvidenceFiles.forEach(f => {
            const ext = (f.original_filename || '').split('.').pop()?.toLowerCase() || '';
            if (ext) {
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
              else if (ext) fileTypes.add('Other');
            }
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
          
          foldersInfoArray.push({
            path: folderPath,
            name: folderName,
            totalFiles: folderEvidenceFiles.length,
            processedCount,
            unprocessedCount,
            fileTypes: Array.from(fileTypes).sort(),
            availableProcessors: profiles.map(p => ({
              name: p.name,
              description: p.description || ''
            })),
            wiretapInfo
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
        
        // Normalize stored_path (remove ingestion/data/ and case_id prefixes)
        let normalizedStoredPath = f.stored_path.replace(/\\/g, '/');
        normalizedStoredPath = normalizedStoredPath.replace(/^ingestion\/data\//, '');
        if (caseId) {
          const casePrefix = `${caseId}/`;
          if (normalizedStoredPath.startsWith(casePrefix)) {
            normalizedStoredPath = normalizedStoredPath.substring(casePrefix.length);
          }
        }
        normalizedStoredPath = normalizedStoredPath.replace(/^\/+|\/+$/g, '');
        
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
    
    // Always use background processing - ingestion with AI extraction can take a long time
    try {
      const res = await evidenceAPI.processBackground(caseId, fileIds, selectedProfile, maxWorkers);
      alert(`Processing ${fileIds.length} file(s) in the background with ${maxWorkers} parallel worker(s). Check the Background Tasks panel for progress.`);
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

  // Helper function to get file extension
  const getFileExtension = (filename) => {
    const parts = filename.split('.');
    return parts.length > 1 ? parts[parts.length - 1].toLowerCase() : '';
  };

  // Helper function to get file type from extension
  const getFileType = (extension) => {
    const imageTypes = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp'];
    const docTypes = ['pdf', 'doc', 'docx', 'txt', 'rtf', 'odt'];
    const audioTypes = ['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a'];
    const videoTypes = ['mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv'];
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

  // Filter unprocessed files
  const filterUnprocessed = (fileList) => {
    return fileList.filter((file) => {
      // Status filter
      if (file.status !== 'unprocessed' && file.status !== 'failed') return false;
      
      // Filename filter
      if (unprocessedFilter && !file.original_filename.toLowerCase().includes(unprocessedFilter.toLowerCase())) {
        return false;
      }
      
      // Type filter
      if (unprocessedTypeFilter) {
        const ext = getFileExtension(file.original_filename);
        const type = getFileType(ext);
        if (type !== unprocessedTypeFilter) return false;
      }
      
      return true;
    });
  };

  // Filter processed files
  const filterProcessed = (fileList) => {
    return fileList.filter((file) => {
      // Status filter
      if (file.status !== 'processed' && file.status !== 'duplicate') return false;
      
      // Filename filter
      if (processedFilter && !file.original_filename.toLowerCase().includes(processedFilter.toLowerCase())) {
        return false;
      }
      
      // Type filter
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
    (f) => f.status === 'processed' || f.status === 'duplicate'
  );

  const filteredUnprocessed = filterUnprocessed(unprocessed);
  const filteredProcessed = filterProcessed(processed);
  
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
        <div className="w-1/4 border-r border-light-200 flex flex-col">
          {/* Upload Panel */}
          <div className="p-4 border-b border-light-200 bg-white">
            <h2 className="text-md font-semibold text-owl-blue-900 mb-2">
              Upload Evidence
            </h2>
            <p className="text-xs text-light-600 mb-3">
              Upload individual files or entire folders (preserves folder structure).
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
                <div className="space-y-2">
                  {filteredUnprocessed.map((file) => (
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

          {/* Processed Files (Bottom) */}
          <div className="flex-1 overflow-y-auto flex flex-col">
            <div className="p-4 border-b border-light-200 bg-white flex-shrink-0">
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
                    ? 'No processed or duplicate files yet.'
                    : 'No files match the current filters.'}
                </p>
              ) : (
                <div className="space-y-2">
                  {filteredProcessed.map((file) => (
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
      </div>

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

