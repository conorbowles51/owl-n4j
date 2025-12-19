import React, { useState, useEffect, useCallback } from 'react';
import {
  X,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Clock,
  Trash2,
  RefreshCw,
  FileText,
  ChevronDown,
  ChevronRight,
  FolderOpen,
} from 'lucide-react';
import { backgroundTasksAPI } from '../services/api';

/**
 * BackgroundTasksPanel Component
 *
 * Flyout panel from the right showing background task progress.
 */
export default function BackgroundTasksPanel({ isOpen, onClose, authUsername, onViewCase }) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(false);

  const loadTasks = useCallback(async () => {
    setLoading(true);
    try {
      // Don't pass owner parameter - let backend default to current_user
      // This ensures tasks are filtered by the authenticated user's session
      const data = await backgroundTasksAPI.list(null, null, null, 50);
      setTasks(data.tasks || []);
    } catch (err) {
      console.error('Failed to load background tasks:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      loadTasks();
      // Poll for updates every 2 seconds while panel is open
      const interval = setInterval(loadTasks, 2000);
      return () => clearInterval(interval);
    }
  }, [isOpen, loadTasks]);

  const handleDeleteTask = async (taskId, e) => {
    e.stopPropagation();
    try {
      await backgroundTasksAPI.delete(taskId);
      await loadTasks();
    } catch (err) {
      console.error('Failed to delete task:', err);
      alert(`Failed to delete task: ${err.message}`);
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'running':
        return <Loader2 className="w-4 h-4 animate-spin text-owl-blue-600" />;
      case 'completed':
        return <CheckCircle2 className="w-4 h-4 text-green-600" />;
      case 'failed':
        return <AlertCircle className="w-4 h-4 text-red-600" />;
      case 'pending':
        return <Clock className="w-4 h-4 text-light-500" />;
      default:
        return <Clock className="w-4 h-4 text-light-500" />;
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'running':
        return 'text-owl-blue-600';
      case 'completed':
        return 'text-green-600';
      case 'failed':
        return 'text-red-600';
      case 'pending':
        return 'text-light-500';
      default:
        return 'text-light-500';
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    try {
      const date = new Date(dateString);
      return date.toLocaleString();
    } catch {
      return dateString;
    }
  };

  const getProgressPercent = (task) => {
    const { progress } = task;
    if (!progress || progress.total === 0) return 0;
    const completed = progress.completed || 0;
    return Math.round((completed / progress.total) * 100);
  };

  if (!isOpen) return null;

  // Filter to show active tasks first (running, pending), then recent completed/failed
  const activeTasks = tasks.filter((t) => t.status === 'running' || t.status === 'pending');
  const completedTasks = tasks.filter(
    (t) => t.status === 'completed' || t.status === 'failed' || t.status === 'cancelled'
  );

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black bg-opacity-50 z-40"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="fixed right-0 top-0 h-full w-full max-w-2xl bg-white shadow-2xl z-50 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-light-200 bg-white flex-shrink-0">
          <div className="flex items-center gap-3">
            <Loader2 className="w-5 h-5 text-owl-blue-600" />
            <h2 className="text-lg font-semibold text-owl-blue-900">Background Tasks</h2>
            <button
              onClick={loadTasks}
              className="p-1.5 rounded-full hover:bg-light-100 transition-colors"
              title="Refresh"
            >
              <RefreshCw className={`w-4 h-4 text-light-600 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-full hover:bg-light-100 transition-colors"
            title="Close"
          >
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading && tasks.length === 0 ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 animate-spin text-owl-blue-600" />
            </div>
          ) : tasks.length === 0 ? (
            <div className="text-center py-12">
              <Loader2 className="w-16 h-16 mx-auto mb-4 text-light-300" />
              <p className="text-light-700 font-medium">No background tasks</p>
              <p className="text-sm text-light-600 mt-2">
                Tasks will appear here when you process multiple files
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Active Tasks */}
              {activeTasks.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-owl-blue-900 mb-3">
                    Active Tasks ({activeTasks.length})
                  </h3>
                  <div className="space-y-3">
                    {activeTasks.map((task) => (
                      <TaskCard
                        key={task.id}
                        task={task}
                        getStatusIcon={getStatusIcon}
                        getStatusColor={getStatusColor}
                        formatDate={formatDate}
                        getProgressPercent={getProgressPercent}
                        onDelete={handleDeleteTask}
                        onViewCase={onViewCase}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Completed Tasks */}
              {completedTasks.length > 0 && (
                <div className={activeTasks.length > 0 ? 'mt-6' : ''}>
                  <h3 className="text-sm font-semibold text-owl-blue-900 mb-3">
                    Recent Tasks ({completedTasks.length})
                  </h3>
                  <div className="space-y-3">
                    {completedTasks.map((task) => (
                      <TaskCard
                        key={task.id}
                        task={task}
                        getStatusIcon={getStatusIcon}
                        getStatusColor={getStatusColor}
                        formatDate={formatDate}
                        getProgressPercent={getProgressPercent}
                        onDelete={handleDeleteTask}
                        onViewCase={onViewCase}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

/**
 * TaskCard Component - displays individual task information
 */
function TaskCard({ task, getStatusIcon, getStatusColor, formatDate, getProgressPercent, onDelete, onViewCase }) {
  const [expanded, setExpanded] = useState(task.status === 'running');

  const progressPercent = getProgressPercent(task);
  const { progress } = task;

  return (
    <div className="bg-light-50 rounded-lg border border-light-200 p-4">
      {/* Task Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-start gap-3 flex-1 min-w-0">
          <div className="mt-0.5">{getStatusIcon(task.status)}</div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <h4 className="font-medium text-owl-blue-900 truncate">{task.task_name}</h4>
              <span className={`text-xs font-medium ${getStatusColor(task.status)}`}>
                {task.status.toUpperCase()}
              </span>
            </div>
            <div className="text-xs text-light-600">
              Started: {formatDate(task.started_at || task.created_at)}
              {task.completed_at && ` • Completed: ${formatDate(task.completed_at)}`}
            </div>
          </div>
        </div>
        <button
          onClick={(e) => onDelete(task.id, e)}
          className="p-1 hover:bg-light-200 rounded transition-colors flex-shrink-0"
          title="Delete task"
        >
          <Trash2 className="w-4 h-4 text-red-500" />
        </button>
      </div>

      {/* Progress Bar */}
      {(task.status === 'running' || task.status === 'pending') && progress && progress.total > 0 && (
        <div className="mb-3">
          <div className="flex items-center justify-between text-xs text-light-600 mb-1">
            <span>
              {progress.completed || 0} / {progress.total} files
            </span>
            <span>{progressPercent}%</span>
          </div>
          <div className="w-full h-2 bg-light-200 rounded-full overflow-hidden">
            <div
              className="h-2 bg-owl-blue-500 transition-all"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>
      )}

      {/* Error Message */}
      {task.error && (
        <div className="mb-3 p-2 bg-red-50 border border-red-200 rounded text-sm text-red-700">
          {task.error}
        </div>
      )}

      {/* View in Case Button - for completed tasks with case_id */}
      {task.status === 'completed' && task.case_id && onViewCase && (
        <div className="mb-3">
          <button
            onClick={() => onViewCase(task.case_id, task.metadata?.case_version)}
            className="flex items-center gap-2 px-3 py-2 bg-owl-blue-500 hover:bg-owl-blue-600 text-white rounded-lg text-sm transition-colors w-full"
          >
            <FolderOpen className="w-4 h-4" />
            View in Case
            {task.metadata?.case_version && (
              <span className="text-xs opacity-90">(Version {task.metadata.case_version})</span>
            )}
          </button>
        </div>
      )}

      {/* File List (Expandable) */}
      {task.files && task.files.length > 0 && (
        <div>
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-2 text-xs text-owl-blue-700 hover:text-owl-blue-900 font-medium"
          >
            {expanded ? (
              <ChevronDown className="w-3 h-3" />
            ) : (
              <ChevronRight className="w-3 h-3" />
            )}
            {task.files.length} file{task.files.length !== 1 ? 's' : ''}
          </button>
          {expanded && (
            <div className="mt-2 space-y-2">
              {task.files.map((file, idx) => (
                <div
                  key={file.file_id || idx}
                  className="flex items-center gap-2 text-xs bg-white p-2 rounded border border-light-200"
                >
                  <FileText className="w-3 h-3 text-light-500" />
                  <span className="flex-1 truncate">{file.filename || 'Unknown'}</span>
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium ${
                      file.status === 'completed'
                        ? 'bg-green-100 text-green-700'
                        : file.status === 'failed'
                        ? 'bg-red-100 text-red-700'
                        : file.status === 'processing'
                        ? 'bg-owl-blue-100 text-owl-blue-700'
                        : 'bg-light-100 text-light-600'
                    }`}
                  >
                    {file.status || 'pending'}
                  </span>
                  {file.error && (
                    <span className="text-xs text-red-600 truncate max-w-xs" title={file.error}>
                      {file.error}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

