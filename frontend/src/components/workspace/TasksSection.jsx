import React, { useState, useEffect } from 'react';
import { ChevronDown, ChevronRight, Focus, Plus, Edit2, Trash2, Link2 } from 'lucide-react';
import { workspaceAPI } from '../../services/api';
import TaskEditorModal from './TaskEditorModal';
import AttachToTheoryModal from './AttachToTheoryModal';

/**
 * Tasks Section
 * 
 * Displays pending tasks with color coding based on urgency and status
 * Format: [Urgency Emoji] [Priority] - Due [Date]
 *         [Title]
 *         [Description]
 *         Assigned: [Name] | Status: [Status Text]
 */
export default function TasksSection({
  caseId,
  tasks: externalTasks,
  onRefresh,
  isCollapsed,
  onToggle,
  onFocus,
}) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showEditor, setShowEditor] = useState(false);
  const [editingTask, setEditingTask] = useState(null);
  const [attachModal, setAttachModal] = useState({ open: false, task: null });

  useEffect(() => {
    const loadTasks = async () => {
      if (!caseId) return;
      
      setLoading(true);
      try {
        const data = await workspaceAPI.getTasks(caseId);
        setTasks(data.tasks || []);
      } catch (err) {
        console.error('Failed to load tasks:', err);
        setTasks([]);
      } finally {
        setLoading(false);
      }
    };

    loadTasks();
  }, [caseId]);

  const handleCreate = () => {
    setEditingTask(null);
    setShowEditor(true);
  };

  const handleEdit = (task) => {
    setEditingTask(task);
    setShowEditor(true);
  };

  const handleSave = async (taskData) => {
    try {
      if (editingTask) {
        await workspaceAPI.updateTask(caseId, editingTask.task_id, taskData);
      } else {
        await workspaceAPI.createTask(caseId, taskData);
      }
      setShowEditor(false);
      setEditingTask(null);
      // Reload tasks
      const data = await workspaceAPI.getTasks(caseId);
      setTasks(data.tasks || []);
      if (onRefresh) {
        onRefresh();
      }
    } catch (err) {
      console.error('Failed to save task:', err);
      throw err;
    }
  };

  const handleDelete = async (taskId) => {
    if (!confirm('Are you sure you want to delete this task?')) return;
    
    try {
      await workspaceAPI.deleteTask(caseId, taskId);
      // Reload tasks
      const data = await workspaceAPI.getTasks(caseId);
      setTasks(data.tasks || []);
      if (onRefresh) {
        onRefresh();
      }
    } catch (err) {
      console.error('Failed to delete task:', err);
      alert('Failed to delete task');
    }
  };

  const handleAttachToTheory = async (theory, itemType, itemId) => {
    if (!caseId || !theory) return;
    try {
      const existing = theory.attached_task_ids || [];
      const ids = existing.includes(itemId) ? existing : [...existing, itemId];
      await workspaceAPI.updateTheory(caseId, theory.theory_id, {
        ...theory,
        attached_task_ids: ids,
      });
    } catch (err) {
      console.error('Failed to attach task to theory:', err);
      throw err;
    }
  };

  const getPriorityEmoji = (priority) => {
    switch (priority) {
      case 'URGENT':
        return '🔴';
      case 'HIGH':
        return '🟡';
      default:
        return '🟢';
    }
  };

  const getPriorityLabel = (priority) => {
    switch (priority) {
      case 'URGENT':
        return 'URGENT';
      case 'HIGH':
        return 'HIGH';
      default:
        return 'STANDARD';
    }
  };

  const getPriorityColor = (priority) => {
    switch (priority) {
      case 'URGENT':
        return 'text-red-600 border-red-200 bg-red-50';
      case 'HIGH':
        return 'text-yellow-600 border-yellow-200 bg-yellow-50';
      default:
        return 'text-green-600 border-green-200 bg-green-50';
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return null;
    try {
      return new Date(dateString).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      });
    } catch {
      return dateString;
    }
  };

  const formatShortDate = (dateString) => {
    if (!dateString) return null;
    try {
      return new Date(dateString).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
      });
    } catch {
      return dateString;
    }
  };

  const getStatusText = (task) => {
    if (task.status_text) {
      return task.status_text;
    }
    if (task.completion_percentage > 0 && task.completion_percentage < 100) {
      return `${task.completion_percentage}% Complete`;
    }
    if (task.status === 'COMPLETED') {
      return 'Completed';
    }
    if (task.status === 'IN_PROGRESS') {
      return 'In Progress';
    }
    return 'Not Started';
  };

  const pendingTasks = tasks.filter(t => t.status !== 'COMPLETED');
  const sortedTasks = [...pendingTasks].sort((a, b) => {
    // Sort by priority first (URGENT > HIGH > STANDARD)
    const priorityOrder = { URGENT: 0, HIGH: 1, STANDARD: 2 };
    const priorityDiff = (priorityOrder[a.priority] || 2) - (priorityOrder[b.priority] || 2);
    if (priorityDiff !== 0) return priorityDiff;
    
    // Then by due date
    const dateA = a.due_date ? new Date(a.due_date).getTime() : Infinity;
    const dateB = b.due_date ? new Date(b.due_date).getTime() : Infinity;
    return dateA - dateB;
  });

  return (
    <div className="border-b border-light-200">
      <div
        className="p-4 cursor-pointer hover:bg-light-50 transition-colors flex items-center justify-between"
        onClick={(e) => onToggle && onToggle(e)}
      >
        <h3 className="text-sm font-semibold text-owl-blue-900">
          Pending Tasks ({pendingTasks.length})
        </h3>
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation();
              handleCreate();
            }}
            className="p-1 hover:bg-light-100 rounded"
            title="Add task"
          >
            <Plus className="w-4 h-4 text-owl-blue-600" />
          </button>
          {onFocus && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onFocus(e);
              }}
              className="p-1 hover:bg-light-100 rounded"
              title="Focus on this section"
            >
              <Focus className="w-4 h-4 text-owl-blue-600" />
            </button>
          )}
          {isCollapsed ? (
            <ChevronRight className="w-4 h-4 text-light-600" />
          ) : (
            <ChevronDown className="w-4 h-4 text-light-600" />
          )}
        </div>
      </div>

      {!isCollapsed && (
        <div className="px-4 pb-4 space-y-3">
          {loading ? (
            <p className="text-xs text-light-500">Loading tasks...</p>
          ) : sortedTasks.length === 0 ? (
            <p className="text-xs text-light-500 italic">No pending tasks</p>
          ) : (
            sortedTasks.map((task) => {
              const priorityColor = getPriorityColor(task.priority);
              const priorityEmoji = getPriorityEmoji(task.priority);
              const priorityLabel = getPriorityLabel(task.priority);
              const dueDate = formatShortDate(task.due_date);
              const statusText = getStatusText(task);
              
              return (
                <div
                  key={task.task_id}
                  className={`p-3 rounded-lg border ${priorityColor}`}
                >
                  {/* Header: Priority and Due Date */}
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-xs font-semibold">
                      {priorityEmoji} {priorityLabel}
                      {dueDate && ` - Due ${dueDate}`}
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setAttachModal({ open: true, task });
                        }}
                        className="p-1 hover:bg-white hover:bg-opacity-50 rounded transition-colors"
                        title="Attach to theory"
                      >
                        <Link2 className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => handleEdit(task)}
                        className="p-1 hover:bg-white hover:bg-opacity-50 rounded transition-colors"
                        title="Edit task"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => handleDelete(task.task_id)}
                        className="p-1 hover:bg-white hover:bg-opacity-50 rounded transition-colors text-red-600"
                        title="Delete task"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>

                  {/* Title */}
                  <div className="text-sm font-medium mb-1">
                    {task.title}
                  </div>

                  {/* Description */}
                  {task.description && (
                    <div className="text-xs mb-2 opacity-90">
                      {task.description}
                    </div>
                  )}

                  {/* Assigned and Status */}
                  <div className="text-xs opacity-80">
                    {task.assigned_to && (
                      <span>
                        Assigned: {task.assigned_to}
                      </span>
                    )}
                    {task.assigned_to && statusText && ' | '}
                    {statusText && (
                      <span>
                        Status: {statusText}
                      </span>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}

      {showEditor && (
        <TaskEditorModal
          isOpen={showEditor}
          onClose={() => {
            setShowEditor(false);
            setEditingTask(null);
          }}
          caseId={caseId}
          task={editingTask}
          onSave={handleSave}
        />
      )}

      {attachModal.open && attachModal.task && (
        <AttachToTheoryModal
          isOpen={attachModal.open}
          onClose={() => setAttachModal({ open: false, task: null })}
          caseId={caseId}
          itemType="task"
          itemId={attachModal.task.task_id}
          itemName={attachModal.task.title || 'Task'}
          onAttach={handleAttachToTheory}
        />
      )}
    </div>
  );
}
