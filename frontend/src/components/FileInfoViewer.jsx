import React, { useEffect, useState } from 'react';
import { FileText, Calendar, CheckCircle2, AlertTriangle, Copy, X, Folder, Settings, Radio, PlayCircle, Loader2 } from 'lucide-react';
import { evidenceAPI, backgroundTasksAPI } from '../services/api';

/**
 * FileInfoViewer
 * 
 * Displays detailed information about selected files/folders:
 * - Upload dates
 * - Processed dates
 * - Types of processing done
 * - List of duplicate files elsewhere in the system
 * - Folder information (file types, processed/unprocessed counts, available processors)
 */
export default function FileInfoViewer({ selectedFiles, files, folderInfo, foldersInfo = [], caseId, onProcessWiretap }) {
  const [duplicates, setDuplicates] = useState({});
  const [loadingDuplicates, setLoadingDuplicates] = useState(false);
  const [activeTask, setActiveTask] = useState(null); // Track active wiretap processing task for this folder
  const [activeTasksByFolder, setActiveTasksByFolder] = useState({}); // Track active tasks for multiple folders: {folderPath: task}

  // Load duplicates for selected files
  useEffect(() => {
    const loadDuplicates = async () => {
      if (!selectedFiles || selectedFiles.length === 0) {
        setDuplicates({});
        return;
      }

      setLoadingDuplicates(true);
      const duplicatesMap = {};

      try {
        for (const fileId of selectedFiles) {
          const file = files.find((f) => f.id === fileId);
          if (file && file.sha256) {
            try {
              const result = await evidenceAPI.findDuplicates(file.sha256);
              // Filter out the current file itself
              duplicatesMap[fileId] = (result?.files || []).filter(
                (f) => f.id !== fileId
              );
            } catch (err) {
              console.error(`Failed to load duplicates for ${fileId}:`, err);
              duplicatesMap[fileId] = [];
            }
          } else {
            duplicatesMap[fileId] = [];
          }
        }
      } finally {
        setLoadingDuplicates(false);
      }

      setDuplicates(duplicatesMap);
    };

    loadDuplicates();
  }, [selectedFiles, files]);

  // Check for active wiretap processing tasks for this folder
  useEffect(() => {
    if (!caseId || !folderInfo?.path) {
      setActiveTask(null);
      return;
    }

    const checkActiveTask = async () => {
      try {
        // Get all tasks for this case (including completed ones to detect when processing finishes)
        const tasks = await backgroundTasksAPI.list(null, caseId, null, 50);
        const folderTasks = (tasks?.tasks || []).filter(
          task => 
            task.task_type === 'wiretap_processing' &&
            task.metadata?.folder_path === folderInfo.path
        );

        // Find active task (running or pending)
        const activeTaskData = folderTasks.find(
          task => task.status === 'running' || task.status === 'pending'
        );

        if (activeTaskData) {
          // Update with current task data
          setActiveTask({
            id: activeTaskData.id,
            status: activeTaskData.status,
            progress: activeTaskData.progress?.completed || 0,
            total: activeTaskData.progress?.total || 0,
          });
        } else {
          // Check if we had a pending task that just completed
          if (activeTask && activeTask.id === 'pending') {
            // Look for a recently completed task
            const completedTask = folderTasks.find(
              task => task.status === 'completed' || task.status === 'failed'
            );
            if (completedTask) {
              // Processing completed, clear the active task state
              setActiveTask(null);
              // Don't call onProcessWiretap - that would restart processing!
              // The folder info will be refreshed elsewhere when needed
            }
          } else if (activeTask && activeTask.id !== 'pending') {
            // Check if the task we were tracking is now completed
            const trackedTask = folderTasks.find(t => t.id === activeTask.id);
            if (trackedTask && (trackedTask.status === 'completed' || trackedTask.status === 'failed')) {
              setActiveTask(null);
              // Don't call onProcessWiretap - that would restart processing!
              // The folder info will be refreshed elsewhere when needed
            } else if (!trackedTask) {
              // Task not found, might have been deleted, clear state
              setActiveTask(null);
            }
          }
        }
      } catch (err) {
        console.error('Failed to check active tasks:', err);
      }
    };

    // Check immediately
    checkActiveTask();

    // Poll every 3 seconds while folder is selected
    const intervalId = setInterval(checkActiveTask, 3000);

    return () => clearInterval(intervalId);
  }, [caseId, folderInfo?.path, activeTask?.id]); // Removed onProcessWiretap from dependencies - we don't want to restart processing when task completes

  // Check for active wiretap processing tasks for multiple folders
  useEffect(() => {
    if (!caseId || !foldersInfo || foldersInfo.length === 0) {
      setActiveTasksByFolder({});
      return;
    }

    const checkActiveTasks = async () => {
      try {
        // Get all tasks for this case
        const tasks = await backgroundTasksAPI.list(null, caseId, null, 50);
        const wiretapTasks = (tasks?.tasks || []).filter(
          task => task.task_type === 'wiretap_processing'
        );

        // Map folder paths to active tasks
        const tasksMap = {};
        foldersInfo.forEach(folder => {
          const folderTask = wiretapTasks.find(
            task => 
              (task.status === 'running' || task.status === 'pending') &&
              task.metadata?.folder_path === folder.path
          );
          if (folderTask) {
            tasksMap[folder.path] = {
              id: folderTask.id,
              status: folderTask.status,
              progress: folderTask.progress?.completed || 0,
              total: folderTask.progress?.total || 0,
            };
          }
        });

        setActiveTasksByFolder(tasksMap);
      } catch (err) {
        console.error('Failed to check active tasks for folders:', err);
      }
    };

    // Check immediately
    checkActiveTasks();

    // Poll every 3 seconds while folders are selected
    const intervalId = setInterval(checkActiveTasks, 3000);

    return () => clearInterval(intervalId);
  }, [caseId, foldersInfo?.map(f => f.path).join(',')]);

  // Show multiple folders info if provided
  if (foldersInfo && foldersInfo.length > 0) {
    // Check if all folders are suitable for wiretap processing and not already processed
    const allSuitable = foldersInfo.every(f => f.wiretapInfo?.suitable && !f.wiretapInfo?.processed);
    const allProcessed = foldersInfo.every(f => f.wiretapInfo?.processed);
    const someProcessed = foldersInfo.some(f => f.wiretapInfo?.processed);
    const anyProcessing = foldersInfo.some(f => activeTasksByFolder[f.path] !== undefined);
    
    return (
      <div className="h-full overflow-y-auto p-4 bg-white">
        <h3 className="text-sm font-semibold text-owl-blue-900 mb-4">
          Selected Folders ({foldersInfo.length})
        </h3>

        <div className="space-y-4">
          {foldersInfo.map((folder, index) => (
            <div key={`${folder.path}-${index}`} className="border border-light-200 rounded-lg p-4 bg-light-50">
              {/* Folder Header */}
              <div className="flex items-start gap-2 mb-4">
                <Folder className="w-5 h-5 text-owl-blue-700 mt-0.5 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <h4 className="font-medium text-sm text-owl-blue-900 truncate">
                    {folder.name}
                  </h4>
                  <p className="text-xs text-light-600 mt-1 truncate" title={folder.path}>
                    {folder.path}
                  </p>
                </div>
              </div>

              {folder.error ? (
                <div className="text-sm text-red-600">{folder.error}</div>
              ) : (
                <>
                  {/* File Counts */}
                  <div className="mb-4">
                    <div className="flex items-center gap-2 text-xs text-light-700 mb-2">
                      <span className="font-medium">File Statistics:</span>
                    </div>
                    <div className="ml-5 space-y-1">
                      <div className="text-xs text-light-600">
                        <span className="font-medium">Total Files:</span> {folder.totalFiles || 0}
                      </div>
                      <div className="text-xs text-light-600">
                        <span className="font-medium text-green-700">Processed:</span> {folder.processedCount || 0}
                      </div>
                      <div className="text-xs text-light-600">
                        <span className="font-medium text-orange-700">Unprocessed:</span> {folder.unprocessedCount || 0}
                      </div>
                    </div>
                  </div>

                  {/* Wiretap Status */}
                  {folder.wiretapInfo && (
                    <div className="mt-4 pt-4 border-t border-light-200">
                      <div className="flex items-center gap-2 text-xs text-light-700 mb-2">
                        <Radio className="w-3 h-3" />
                        <span className="font-medium">Special Wiretap Processing:</span>
                      </div>
                      <div className="ml-5">
                        {folder.wiretapInfo.suitable ? (
                          <div className="space-y-2">
                            {(() => {
                              const folderActiveTask = activeTasksByFolder[folder.path];
                              const isProcessing = folderActiveTask !== undefined;
                              return (
                                <div className={`text-xs p-2 rounded border ${
                                  folder.wiretapInfo.processed 
                                    ? 'bg-green-50 border-green-300 text-green-800' 
                                    : isProcessing
                                    ? 'bg-yellow-50 border-yellow-300 text-yellow-800'
                                    : 'bg-owl-blue-50 border-owl-blue-300 text-owl-blue-800'
                                }`}>
                                  <div className="font-medium mb-1 flex items-center gap-2">
                                    {isProcessing && (
                                      <Loader2 className="w-3 h-3 animate-spin" />
                                    )}
                                    {folder.wiretapInfo.processed 
                                      ? '✓ Processed as Wiretap' 
                                      : isProcessing
                                      ? 'Processing Wiretap'
                                      : 'Suitable for wiretap processing'}
                                  </div>
                              <div className="text-xs mt-1 space-y-0.5">
                                {folder.wiretapInfo.has_audio && (
                                  <div>✓ Audio files: {folder.wiretapInfo.audio_files.length}</div>
                                )}
                                {folder.wiretapInfo.has_sri && (
                                  <div>✓ Metadata (.sri): {folder.wiretapInfo.sri_files.length}</div>
                                )}
                                {folder.wiretapInfo.has_rtf && (
                                  <div>✓ Interpretation (.rtf): {folder.wiretapInfo.rtf_files.length}</div>
                                )}
                                {!folder.wiretapInfo.has_sri && (
                                  <div className="text-orange-700">⚠ Missing .sri metadata file</div>
                                )}
                                {!folder.wiretapInfo.has_rtf && (
                                  <div className="text-orange-700">⚠ Missing .rtf interpretation file</div>
                                )}
                              </div>
                                  {isProcessing && (
                                    <div className="text-xs mt-2 pt-2 border-t border-yellow-200 text-yellow-700">
                                      Wiretap processing in progress...
                                    </div>
                                  )}
                                </div>
                              );
                            })()}
                          </div>
                        ) : (
                          <div className="text-xs text-light-600 p-2 bg-light-100 rounded border border-light-300">
                            {folder.wiretapInfo.message || 'Not suitable for wiretap processing'}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          ))}
        </div>

        {/* Process All as Wiretaps Button */}
        {allSuitable && !anyProcessing && onProcessWiretap && (
          <div className="mt-4 pt-4 border-t border-light-200">
            <button
              onClick={() => {
                const folderPaths = foldersInfo.map(f => f.path);
                onProcessWiretap(folderPaths);
              }}
              className="flex items-center gap-2 px-4 py-2 text-white text-sm rounded transition-colors bg-owl-blue-600 hover:bg-owl-blue-700 w-full justify-center"
            >
              <PlayCircle className="w-4 h-4" />
              Process All {foldersInfo.length} Folders as Wiretaps
            </button>
            <p className="text-xs text-light-600 mt-2 text-center">
              Each folder will be processed as a separate background task
            </p>
          </div>
        )}
        {anyProcessing && (
          <div className="mt-4 pt-4 border-t border-light-200">
            <div className="flex items-center gap-2 px-4 py-2 text-yellow-800 bg-yellow-50 border border-yellow-300 rounded text-sm">
              <Loader2 className="w-4 h-4 animate-spin" />
              One or more folders are currently processing as wiretaps
            </div>
          </div>
        )}
      </div>
    );
  }

  // Show single folder info if provided
  if (folderInfo) {
    return (
      <div className="h-full overflow-y-auto p-4 bg-white">
        <h3 className="text-sm font-semibold text-owl-blue-900 mb-4">
          Folder Information
        </h3>

        <div className="border border-light-200 rounded-lg p-4 bg-light-50">
          {/* Folder Header */}
          <div className="flex items-start gap-2 mb-4">
            <Folder className="w-5 h-5 text-owl-blue-700 mt-0.5 flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <h4 className="font-medium text-sm text-owl-blue-900 truncate">
                {folderInfo.name}
              </h4>
              <p className="text-xs text-light-600 mt-1 truncate" title={folderInfo.path}>
                {folderInfo.path}
              </p>
            </div>
          </div>

          {folderInfo.error ? (
            <div className="text-sm text-red-600">{folderInfo.error}</div>
          ) : (
            <>
              {/* File Counts */}
              <div className="mb-4">
                <div className="flex items-center gap-2 text-xs text-light-700 mb-2">
                  <span className="font-medium">File Statistics:</span>
                </div>
                <div className="ml-5 space-y-1">
                  <div className="text-xs text-light-600">
                    <span className="font-medium">Total Files:</span> {folderInfo.totalFiles || 0}
                  </div>
                  <div className="text-xs text-light-600">
                    <span className="font-medium text-green-700">Processed:</span> {folderInfo.processedCount || 0}
                  </div>
                  <div className="text-xs text-light-600">
                    <span className="font-medium text-orange-700">Unprocessed:</span> {folderInfo.unprocessedCount || 0}
                  </div>
                </div>
              </div>

              {/* File Types */}
              {folderInfo.fileTypes && folderInfo.fileTypes.length > 0 && (
                <div className="mb-4">
                  <div className="flex items-center gap-2 text-xs text-light-700 mb-2">
                    <span className="font-medium">File Types in Folder:</span>
                  </div>
                  <div className="ml-5 flex flex-wrap gap-1">
                    {folderInfo.fileTypes.map((type) => (
                      <span
                        key={type}
                        className="px-2 py-0.5 bg-owl-blue-100 text-owl-blue-700 text-xs rounded"
                      >
                        {type}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Wiretap Processing */}
              {folderInfo.wiretapInfo && (
                <div className="mt-4 pt-4 border-t border-light-200">
                  <div className="flex items-center gap-2 text-xs text-light-700 mb-2">
                    <Radio className="w-3 h-3" />
                    <span className="font-medium">Special Wiretap Processing:</span>
                  </div>
                  <div className="ml-5">
                    {folderInfo.wiretapInfo.suitable ? (
                      <div className="space-y-2">
                        <div className={`text-xs p-2 rounded border ${
                          folderInfo.wiretapInfo.processed 
                            ? 'bg-green-50 border-green-300 text-green-800' 
                            : activeTask !== null
                            ? 'bg-yellow-50 border-yellow-300 text-yellow-800'
                            : 'bg-owl-blue-50 border-owl-blue-300 text-owl-blue-800'
                        }`}>
                          <div className="font-medium mb-1 flex items-center gap-2">
                            {activeTask !== null && (
                              <Loader2 className="w-3 h-3 animate-spin" />
                            )}
                            {folderInfo.wiretapInfo.processed 
                              ? '✓ Processed as Wiretap' 
                              : activeTask !== null
                              ? 'Processing Wiretap'
                              : 'Folder is suitable for wiretap processing'}
                          </div>
                          <div className="text-xs mt-1 space-y-0.5">
                            {folderInfo.wiretapInfo.has_audio && (
                              <div>✓ Audio files: {folderInfo.wiretapInfo.audio_files.length}</div>
                            )}
                            {folderInfo.wiretapInfo.has_sri && (
                              <div>✓ Metadata (.sri): {folderInfo.wiretapInfo.sri_files.length}</div>
                            )}
                            {folderInfo.wiretapInfo.has_rtf && (
                              <div>✓ Interpretation (.rtf): {folderInfo.wiretapInfo.rtf_files.length}</div>
                            )}
                            {!folderInfo.wiretapInfo.has_sri && (
                              <div className="text-orange-700">⚠ Missing .sri metadata file</div>
                            )}
                            {!folderInfo.wiretapInfo.has_rtf && (
                              <div className="text-orange-700">⚠ Missing .rtf interpretation file</div>
                            )}
                          </div>
                        </div>
                        {!folderInfo.wiretapInfo.processed && onProcessWiretap && (
                          <div className="space-y-2">
                            <button
                              onClick={() => {
                                onProcessWiretap(folderInfo.path);
                                // Set temporary state to show immediate feedback
                                setActiveTask({
                                  id: 'pending',
                                  status: 'pending',
                                  progress: 0,
                                  total: 1,
                                });
                              }}
                              disabled={activeTask !== null}
                              className={`flex items-center gap-2 px-3 py-1.5 text-white text-xs rounded transition-colors ${
                                activeTask !== null
                                  ? 'bg-light-300 cursor-not-allowed'
                                  : 'bg-owl-blue-600 hover:bg-owl-blue-700'
                              }`}
                            >
                              {activeTask !== null ? (
                                <>
                                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                  {activeTask.status === 'pending' ? 'Starting...' : 'Processing...'}
                                </>
                              ) : (
                                <>
                                  <PlayCircle className="w-3.5 h-3.5" />
                                  Process as Wiretap
                                </>
                              )}
                            </button>
                            
                            {/* Processing Status */}
                            {activeTask !== null && (
                              <div className="space-y-1">
                                <div className="text-xs text-owl-blue-700 font-medium">
                                  {activeTask.status === 'pending' 
                                    ? 'Starting wiretap processing...'
                                    : `Processing wiretap (${activeTask.progress} / ${activeTask.total})`}
                                </div>
                                {activeTask.status === 'running' && activeTask.total > 0 && (
                                  <div className="w-full h-1.5 bg-light-200 rounded-full overflow-hidden">
                                    <div
                                      className="h-full bg-owl-blue-500 transition-all"
                                      style={{
                                        width: `${Math.min(100, (activeTask.progress / activeTask.total) * 100)}%`,
                                      }}
                                    />
                                  </div>
                                )}
                                <div className="text-xs text-light-600">
                                  View progress in Background Tasks panel
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="text-xs text-light-600 p-2 bg-light-100 rounded border border-light-300">
                        {folderInfo.wiretapInfo.message || 'Folder is not suitable for wiretap processing'}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Available Processors */}
              {folderInfo.availableProcessors && folderInfo.availableProcessors.length > 0 && (
                <div className="mt-4 pt-4 border-t border-light-200">
                  <div className="flex items-center gap-2 text-xs text-light-700 mb-2">
                    <Settings className="w-3 h-3" />
                    <span className="font-medium">Available System Processors:</span>
                  </div>
                  <div className="ml-5 space-y-2">
                    {folderInfo.availableProcessors.map((processor) => (
                      <div
                        key={processor.name}
                        className="text-xs bg-white p-2 rounded border border-light-200"
                      >
                        <div className="font-medium text-owl-blue-900">{processor.name}</div>
                        {processor.description && (
                          <div className="text-light-600 mt-0.5">{processor.description}</div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    );
  }

  if (!selectedFiles || selectedFiles.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-light-600">
        <div className="text-center">
          <FileText className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p className="text-sm italic">Select files or folders to view details</p>
        </div>
      </div>
    );
  }

  const selectedFileObjects = files.filter((f) => selectedFiles.includes(f.id));

  const formatDateTime = (dateStr) => {
    if (!dateStr) return 'N/A';
    try {
      const date = new Date(dateStr);
      return date.toLocaleString();
    } catch {
      return dateStr;
    }
  };

  const getFileExtension = (filename) => {
    const parts = filename.split('.');
    return parts.length > 1 ? parts[parts.length - 1].toLowerCase() : 'unknown';
  };

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

  const humanSize = (bytes) => {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
  };

  return (
    <div className="h-full overflow-y-auto p-4 bg-white">
      <h3 className="text-sm font-semibold text-owl-blue-900 mb-4">
        File Information ({selectedFileObjects.length})
      </h3>

      <div className="space-y-4">
        {selectedFileObjects.map((file) => {
          const fileDuplicates = duplicates[file.id] || [];
          const extension = getFileExtension(file.original_filename);
          const fileType = getFileType(extension);

          return (
            <div
              key={file.id}
              className="border border-light-200 rounded-lg p-4 bg-light-50"
            >
              {/* File Header */}
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-start gap-2 flex-1 min-w-0">
                  <FileText className="w-5 h-5 text-owl-blue-700 mt-0.5 flex-shrink-0" />
                  <div className="min-w-0 flex-1">
                    <h4 className="font-medium text-sm text-owl-blue-900 truncate">
                      {file.original_filename}
                    </h4>
                    <div className="flex items-center gap-2 mt-1 text-xs text-light-600">
                      <span>{fileType}</span>
                      <span>•</span>
                      <span>{humanSize(file.size)}</span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  {file.status === 'processed' && (
                    <CheckCircle2 className="w-4 h-4 text-green-600" />
                  )}
                  {file.status === 'duplicate' && (
                    <Copy className="w-4 h-4 text-orange-600" />
                  )}
                  {file.status === 'failed' && (
                    <AlertTriangle className="w-4 h-4 text-red-600" />
                  )}
                </div>
              </div>

              {/* Upload Date */}
              <div className="mb-2">
                <div className="flex items-center gap-2 text-xs text-light-700 mb-1">
                  <Calendar className="w-3 h-3" />
                  <span className="font-medium">Upload Date:</span>
                </div>
                <p className="text-xs text-light-600 ml-5">
                  {formatDateTime(file.created_at)}
                </p>
              </div>

              {/* Processed Date */}
              {file.processed_at && (
                <div className="mb-2">
                  <div className="flex items-center gap-2 text-xs text-light-700 mb-1">
                    <CheckCircle2 className="w-3 h-3" />
                    <span className="font-medium">Processed Date:</span>
                  </div>
                  <p className="text-xs text-light-600 ml-5">
                    {formatDateTime(file.processed_at)}
                  </p>
                </div>
              )}

              {/* Processing Status */}
              <div className="mb-2">
                <div className="flex items-center gap-2 text-xs text-light-700 mb-1">
                  <span className="font-medium">Status:</span>
                </div>
                <p className="text-xs text-light-600 ml-5 capitalize">
                  {file.status || 'unprocessed'}
                  {file.last_error && (
                    <span className="text-red-600 ml-2">
                      • Error: {file.last_error}
                    </span>
                  )}
                </p>
              </div>

              {/* Duplicate Files */}
              {loadingDuplicates ? (
                <div className="text-xs text-light-600 italic">Loading duplicates...</div>
              ) : fileDuplicates.length > 0 ? (
                <div className="mt-3 pt-3 border-t border-light-200">
                  <div className="flex items-center gap-2 text-xs text-light-700 mb-2">
                    <Copy className="w-3 h-3" />
                    <span className="font-medium">
                      Duplicate Files ({fileDuplicates.length}):
                    </span>
                  </div>
                  <div className="space-y-1 ml-5">
                    {fileDuplicates.map((dup) => (
                      <div
                        key={dup.id}
                        className="text-xs text-light-600 bg-white p-2 rounded border border-light-200"
                      >
                        <div className="font-medium">{dup.original_filename}</div>
                        <div className="text-light-500 mt-0.5">
                          Case: {dup.case_id || 'N/A'} • Uploaded:{' '}
                          {formatDateTime(dup.created_at)}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : file.status === 'duplicate' && file.duplicate_of ? (
                <div className="mt-3 pt-3 border-t border-light-200">
                  <div className="flex items-center gap-2 text-xs text-light-700 mb-2">
                    <Copy className="w-3 h-3" />
                    <span className="font-medium">This is a duplicate of:</span>
                  </div>
                  <p className="text-xs text-light-600 ml-5">
                    File ID: {file.duplicate_of}
                  </p>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

