import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Folder,
  FolderOpen,
  FileText,
  ChevronRight,
  ChevronDown,
  HardDrive,
  ArrowLeft,
  RefreshCw,
  Loader2,
  Info,
  Radio,
  CheckCircle2,
  Filter,
} from 'lucide-react';
import { filesystemAPI } from '../services/api';

/**
 * FileNavigator Component
 * 
 * Browses the file system for a specific case, starting from the case's data folder.
 * 
 * Props:
 *  - caseId: string (required) - Case ID to browse files for
 *  - onFileSelect: (filePath: string, event?: Event) => void - Called when a file is clicked
 *  - selectedFilePath: string | null - Currently selected file path (single select)
 *  - selectedFilePaths: Set<string> - Set of selected file paths (for multi-select)
 *  - selectedFolderPaths: Set<string> - Set of selected folder paths (for multi-select)
 *  - onFileMultiSelect: (filePath: string, event?: Event) => void - Called when a file is multi-selected (Ctrl/Cmd+click)
 *  - onFolderSelect: (folderPath: string, event?: Event) => void - Called when a folder is clicked (for selection, not navigation)
 *  - onInfoClick: (item: {path: string, name: string, type: 'file' | 'directory', size?: number}) => void - Called when info icon is clicked
 *  - wiretapProcessedFolders: Set<string> - Set of folder paths that have been processed as wiretaps
 *  - evidenceFiles: Array<{id: string, stored_path: string, status: string, ...}> - List of evidence files to check processed status
 */
export default function FileNavigator({ caseId, onFileSelect, selectedFilePath, selectedFilePaths = new Set(), selectedFolderPaths = new Set(), onFileMultiSelect, onFolderSelect, onInfoClick, wiretapProcessedFolders = new Set(), evidenceFiles = [] }) {
  const [currentPath, setCurrentPath] = useState('');
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedFolders, setExpandedFolders] = useState(new Set());
  const [filterProcessed, setFilterProcessed] = useState(null); // null = all, true = processed only, false = unprocessed only
  const [filterFileType, setFilterFileType] = useState(null); // null = all, or file extension like 'pdf', 'txt', etc.
  const [processedMapVersion, setProcessedMapVersion] = useState(0); // Force re-render when processedFilesMap changes

  const loadDirectory = useCallback(async (path = '') => {
    if (!caseId) {
      setError('No case selected');
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const result = await filesystemAPI.list(caseId, path || null);
      setItems(result.items || []);
      setCurrentPath(result.current_path || '');
    } catch (err) {
      console.error('Failed to load directory:', err);
      setError(err.message || 'Failed to load directory');
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    loadDirectory();
  }, [loadDirectory]);


  const navigateToFolder = (folderPath) => {
    setExpandedFolders(new Set()); // Clear expanded state when navigating
    loadDirectory(folderPath);
  };

  const navigateUp = () => {
    if (!currentPath) return; // Already at root
    
    // Get parent path
    const pathParts = currentPath.split('/').filter(Boolean);
    pathParts.pop();
    const parentPath = pathParts.join('/');
    
    loadDirectory(parentPath || '');
  };

  const toggleFolder = (folderPath) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(folderPath)) {
        next.delete(folderPath);
      } else {
        next.add(folderPath);
      }
      return next;
    });
  };

  const handleFileClick = (filePath, event) => {
    if (onFileSelect) {
      onFileSelect(filePath, event);
    }
  };

  const handleInfoClick = (e, item) => {
    e.stopPropagation(); // Prevent folder navigation or file selection
    if (onInfoClick) {
      onInfoClick(item);
    }
  };

  const humanSize = (size) => {
    if (!size && size !== 0) return '';
    if (size < 1024) return `${size} B`;
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
    if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`;
    return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  };

  // Create a map of file paths to their processed status
  const processedFilesMap = useMemo(() => {
    const map = new Map();
    if (!evidenceFiles || evidenceFiles.length === 0) {
      return map;
    }
    
    evidenceFiles.forEach(file => {
      if (!file.stored_path) return;
      
      // stored_path is a full path like "ingestion/data/{case_id}/file.txt" or "{case_id}/subfolder/file.txt"
      // We need to extract the relative path from the case root
      let normalizedPath = file.stored_path;
      
      // Remove "ingestion/data/" prefix if present
      normalizedPath = normalizedPath.replace(/^ingestion\/data\//, '');
      
      // Remove case_id prefix if present (format: "case_id/path" or just "path")
      if (caseId) {
        const casePrefix = `${caseId}/`;
        if (normalizedPath.startsWith(casePrefix)) {
          normalizedPath = normalizedPath.substring(casePrefix.length);
        }
      }
      
      // Normalize path separators and remove leading/trailing slashes
      normalizedPath = normalizedPath.replace(/\\/g, '/').replace(/^\/+|\/+$/g, '');
      
      // Only add to map if path is not empty
      if (normalizedPath) {
        map.set(normalizedPath, file.status === 'processed');
      }
    });
    
    return map;
  }, [evidenceFiles, caseId]);

  // Count processed files to detect changes
  const processedCount = useMemo(() => {
    let count = 0;
    for (const isProcessed of processedFilesMap.values()) {
      if (isProcessed) count++;
    }
    return count;
  }, [processedFilesMap]);

  // Update version when processedFilesMap changes to force re-render
  // Include evidenceFiles.length to ensure it triggers on initial load
  useEffect(() => {
    setProcessedMapVersion(prev => prev + 1);
  }, [evidenceFiles?.length || 0, processedFilesMap.size, processedCount]);

  // Check if a folder contains processed files
  const isFolderProcessed = useCallback((folderPath) => {
    if (folderPath === null || folderPath === undefined) {
      return false;
    }
    
    // Normalize folder path - same normalization as file paths in processedFilesMap
    let normalizedFolderPath = String(folderPath).replace(/\\/g, '/').replace(/^\/+|\/+$/g, '');
    
    // Check if folder itself is wiretap processed
    if (wiretapProcessedFolders.has(normalizedFolderPath)) {
      return true;
    }
    
    // If no processed files map, return false
    if (processedFilesMap.size === 0) {
      return false;
    }
    
    // Check if folder contains processed files
    // Handle root folder (empty path) specially
    if (normalizedFolderPath === '' || normalizedFolderPath === '.') {
      // For root, check if any processed files exist (files at root level, no '/' in path)
      for (const [filePath, isProcessed] of processedFilesMap.entries()) {
        if (isProcessed && !filePath.includes('/')) {
          return true;
        }
      }
    } else {
      // For subfolders, check if any file path is in this folder or subfolders
      for (const [filePath, isProcessed] of processedFilesMap.entries()) {
        if (!isProcessed) continue;
        
        // File paths in map are already normalized (no leading/trailing slashes)
        // Check if file is directly in this folder or in a subfolder
        // e.g., folder="subfolder", file="subfolder/file.txt" or "subfolder/nested/file.txt"
        const folderPrefix = normalizedFolderPath + '/';
        if (filePath.startsWith(folderPrefix) || filePath === normalizedFolderPath) {
          return true;
        }
      }
    }
    return false;
  }, [wiretapProcessedFolders, processedFilesMap]);

  // Check if a file is processed
  const isFileProcessed = useCallback((filePath) => {
    if (!filePath) return false;
    // filePath from filesystem API is already relative to case root
    // Normalize to match the format in processedFilesMap (no leading/trailing slashes)
    const normalizedPath = String(filePath).replace(/\\/g, '/').replace(/^\/+|\/+$/g, '');
    return processedFilesMap.get(normalizedPath) || false;
  }, [processedFilesMap]);

  // Get file extension from filename
  const getFileExtension = useCallback((filename) => {
    const parts = filename.split('.');
    return parts.length > 1 ? parts[parts.length - 1].toLowerCase() : '';
  }, []);

  // Separate directories and files
  const allDirectories = items.filter(item => item.type === 'directory');
  const allFiles = items.filter(item => item.type === 'file');

  // Get unique file types from current files
  const availableFileTypes = useMemo(() => {
    const types = new Set();
    allFiles.forEach(file => {
      const ext = getFileExtension(file.name);
      if (ext) {
        types.add(ext);
      }
    });
    return Array.from(types).sort();
  }, [allFiles, getFileExtension]);

  // Filter items based on processed status and file type
  const filterItems = useCallback((items) => {
    let filtered = items;
    
    // Filter by processed status
    if (filterProcessed !== null) {
      filtered = filtered.filter(item => {
        if (item.type === 'directory') {
          const processed = isFolderProcessed(item.path);
          return filterProcessed ? processed : !processed;
        } else {
          const processed = isFileProcessed(item.path);
          return filterProcessed ? processed : !processed;
        }
      });
    }
    
    // Filter by file type (only applies to files, not directories)
    if (filterFileType !== null) {
      filtered = filtered.filter(item => {
        if (item.type === 'directory') {
          return true; // Always show directories
        } else {
          const ext = getFileExtension(item.name);
          return ext === filterFileType;
        }
      });
    }
    
    return filtered;
  }, [filterProcessed, filterFileType, isFolderProcessed, isFileProcessed, getFileExtension]);
  
  // Filter directories and files separately
  const directories = filterItems(allDirectories);
  const files = filterItems(allFiles);

  if (loading && items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-light-600">
        <Loader2 className="w-8 h-8 mb-3 animate-spin text-owl-blue-600" />
        <p className="text-sm">Loading file system...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-light-600">
        <p className="text-sm text-red-600 mb-2">{error}</p>
        <button
          onClick={() => loadDirectory(currentPath)}
          className="px-3 py-1 text-xs border border-light-300 rounded hover:bg-light-100"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header with navigation */}
      <div className="p-2 border-b border-light-200 bg-light-50 flex flex-col gap-2 flex-shrink-0">
        <div className="flex items-center gap-2">
          {currentPath && (
            <button
              onClick={navigateUp}
              className="p-1 rounded hover:bg-light-200 transition-colors"
              title="Go up one level"
            >
              <ArrowLeft className="w-4 h-4 text-light-600" />
            </button>
          )}
          <button
            onClick={() => loadDirectory(currentPath)}
            className="p-1 rounded hover:bg-light-200 transition-colors"
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4 text-light-600" />
          </button>
          <div className="flex-1 min-w-0">
            <div className="text-xs text-light-600 truncate" title={currentPath || 'Root'}>
              {currentPath || '/ (case root)'}
            </div>
          </div>
        </div>
        
        {/* Filter Toggles */}
        <div className="flex flex-col gap-2">
          {/* Processed Status Filter */}
          <div className="flex items-center gap-2">
            <Filter className="w-3.5 h-3.5 text-light-600" />
            <span className="text-xs text-light-600">Status:</span>
            <button
              onClick={() => setFilterProcessed(null)}
              className={`px-2 py-0.5 text-xs rounded transition-colors ${
                filterProcessed === null
                  ? 'bg-owl-blue-600 text-white'
                  : 'bg-light-200 text-light-700 hover:bg-light-300'
              }`}
            >
              All
            </button>
            <button
              onClick={() => setFilterProcessed(true)}
              className={`px-2 py-0.5 text-xs rounded transition-colors ${
                filterProcessed === true
                  ? 'bg-green-600 text-white'
                  : 'bg-light-200 text-light-700 hover:bg-light-300'
              }`}
            >
              Processed
            </button>
            <button
              onClick={() => setFilterProcessed(false)}
              className={`px-2 py-0.5 text-xs rounded transition-colors ${
                filterProcessed === false
                  ? 'bg-orange-600 text-white'
                  : 'bg-light-200 text-light-700 hover:bg-light-300'
              }`}
            >
              Unprocessed
            </button>
          </div>
          
          {/* File Type Filter */}
          {allFiles.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs text-light-600">Type:</span>
              <button
                onClick={() => setFilterFileType(null)}
                className={`px-2 py-0.5 text-xs rounded transition-colors ${
                  filterFileType === null
                    ? 'bg-owl-blue-600 text-white'
                    : 'bg-light-200 text-light-700 hover:bg-light-300'
                }`}
              >
                All
              </button>
              {availableFileTypes.map(ext => (
                <button
                  key={ext}
                  onClick={() => setFilterFileType(ext)}
                  className={`px-2 py-0.5 text-xs rounded transition-colors ${
                    filterFileType === ext
                      ? 'bg-owl-blue-600 text-white'
                      : 'bg-light-200 text-light-700 hover:bg-light-300'
                  }`}
                >
                  .{ext}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* File system contents */}
      <div className="flex-1 overflow-y-auto p-2">
        {items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-light-600">
            <HardDrive className="w-12 h-12 mb-3 opacity-50" />
            <p className="text-sm italic">
              {filterProcessed === null 
                ? 'Directory is empty'
                : filterProcessed 
                  ? 'No processed files or folders'
                  : 'No unprocessed files or folders'}
            </p>
          </div>
        ) : directories.length === 0 && files.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-light-600">
            <Filter className="w-12 h-12 mb-3 opacity-50" />
            <p className="text-sm italic">
              {filterProcessed === true 
                ? 'No processed files or folders in this directory'
                : 'No unprocessed files or folders in this directory'}
            </p>
          </div>
        ) : (
          <div className="space-y-1" key={`file-list-${processedMapVersion}-${evidenceFiles?.length || 0}-${processedFilesMap.size}`}>
            {/* Directories */}
            {directories.map((dir) => {
              const isExpanded = expandedFolders.has(dir.path);
              const isWiretapProcessed = wiretapProcessedFolders.has(dir.path);
              // Always recalculate processed status on every render
              const isProcessed = isFolderProcessed(dir.path);
              return (
                <div
                  key={`${dir.path}-processed-${isProcessed}-v${processedMapVersion}`}
                  className={`flex items-center gap-2 px-2 py-1.5 hover:bg-light-100 cursor-pointer rounded group ${
                    selectedFolderPaths.has(dir.path) ? 'bg-owl-blue-100 border-2 border-owl-blue-500' :
                    isWiretapProcessed ? 'bg-green-50 border border-green-200' : 
                    isProcessed ? 'bg-blue-50 border border-blue-200' : ''
                  }`}
                  onClick={(e) => {
                    // Multi-select: Ctrl/Cmd+click to toggle selection
                    if (e.ctrlKey || e.metaKey) {
                      e.stopPropagation();
                      if (onFolderSelect) {
                        onFolderSelect(dir.path, e);
                      }
                    } else {
                      // Single click: show info
                      if (onInfoClick) {
                        onInfoClick({ ...dir, type: 'directory' });
                      }
                    }
                  }}
                >
                  {isExpanded ? (
                    <FolderOpen className={`w-4 h-4 flex-shrink-0 ${isProcessed ? 'text-green-600' : 'text-owl-blue-600'}`} />
                  ) : (
                    <Folder className={`w-4 h-4 flex-shrink-0 ${isProcessed ? 'text-green-600' : 'text-owl-blue-600'}`} />
                  )}
                  <span className="text-sm text-light-900 flex-1 truncate">{dir.name}</span>
                  {isProcessed && (
                    <CheckCircle2 className="w-3.5 h-3.5 text-green-600 flex-shrink-0" title="Contains processed files" />
                  )}
                  {isWiretapProcessed && (
                    <Radio className="w-3.5 h-3.5 text-green-600 flex-shrink-0" title="Processed as wiretap" />
                  )}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (onInfoClick) {
                        onInfoClick({ ...dir, type: 'directory' });
                      }
                    }}
                    className="p-1 rounded hover:bg-owl-blue-100 text-owl-blue-600 opacity-0 group-hover:opacity-100 transition-opacity"
                    title="View folder information"
                  >
                    <Info className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      navigateToFolder(dir.path);
                    }}
                    className="p-1 rounded hover:bg-owl-blue-100 text-owl-blue-600 opacity-0 group-hover:opacity-100 transition-opacity"
                    title="Open folder"
                  >
                    <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              );
            })}

            {/* Files */}
            {files.map((file) => {
              const isSelected = selectedFilePath === file.path;
              const isMultiSelected = selectedFilePaths.has(file.path);
              // Always recalculate processed status on every render
              const isProcessed = isFileProcessed(file.path);
              return (
                <div
                  key={`${file.path}-processed-${isProcessed}-v${processedMapVersion}`}
                  className={`flex items-center gap-2 px-2 py-1.5 hover:bg-light-100 cursor-pointer rounded group ${
                    isMultiSelected ? 'bg-owl-blue-100 border-2 border-owl-blue-500' :
                    isSelected ? 'bg-owl-blue-50 border border-owl-blue-300' : 
                    isProcessed ? 'bg-blue-50 border border-blue-200' : ''
                  }`}
                  onClick={(e) => {
                    // Multi-select: Ctrl/Cmd+click to toggle selection
                    if (e.ctrlKey || e.metaKey) {
                      e.stopPropagation();
                      if (onFileMultiSelect) {
                        onFileMultiSelect(file.path, e);
                      }
                    } else {
                      // Single click: normal selection
                      handleFileClick(file.path, e);
                    }
                  }}
                >
                  {isMultiSelected && (
                    <CheckCircle2 className="w-4 h-4 flex-shrink-0 text-owl-blue-600" title="Selected" />
                  )}
                  <FileText className={`w-4 h-4 flex-shrink-0 ${isProcessed ? 'text-green-600' : 'text-owl-blue-700'}`} />
                  <span className={`text-sm flex-1 truncate ${
                    isMultiSelected ? 'font-semibold text-owl-blue-900' :
                    isSelected ? 'font-semibold text-owl-blue-900' : 'text-light-900'
                  }`}>
                    {file.name}
                  </span>
                  {isProcessed && (
                    <CheckCircle2 className="w-3.5 h-3.5 text-green-600 flex-shrink-0" title="Processed" />
                  )}
                  {file.size && (
                    <span className="text-xs text-light-500 flex-shrink-0">
                      {humanSize(file.size)}
                    </span>
                  )}
                  <button
                    onClick={(e) => handleInfoClick(e, { ...file, type: 'file' })}
                    className="p-1 rounded hover:bg-owl-blue-100 text-owl-blue-600 opacity-0 group-hover:opacity-100 transition-opacity"
                    title="View file information"
                  >
                    <Info className="w-3.5 h-3.5" />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
