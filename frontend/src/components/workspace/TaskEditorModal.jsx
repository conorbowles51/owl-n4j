import React, { useState, useEffect } from 'react';
import { X } from 'lucide-react';

/**
 * Task Editor Modal
 * 
 * Allows creating and editing tasks
 */
export default function TaskEditorModal({
  isOpen,
  onClose,
  caseId,
  task,
  onSave,
}) {
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    priority: 'STANDARD',
    due_date: '',
    assigned_to: '',
    status: 'PENDING',
    completion_percentage: 0,
    status_text: '',
  });

  useEffect(() => {
    if (task) {
      setFormData({
        title: task.title || '',
        description: task.description || '',
        priority: task.priority || 'STANDARD',
        due_date: task.due_date ? task.due_date.split('T')[0] : '',
        assigned_to: task.assigned_to || '',
        status: task.status || 'PENDING',
        completion_percentage: task.completion_percentage || 0,
        status_text: task.status_text || '',
      });
    } else {
      setFormData({
        title: '',
        description: '',
        priority: 'STANDARD',
        due_date: '',
        assigned_to: '',
        status: 'PENDING',
        completion_percentage: 0,
        status_text: '',
      });
    }
  }, [task, isOpen]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      // Format due_date if provided
      const taskData = {
        ...formData,
        due_date: formData.due_date || null,
        completion_percentage: parseInt(formData.completion_percentage) || 0,
      };
      
      await onSave(taskData);
      onClose();
    } catch (err) {
      console.error('Failed to save task:', err);
      alert('Failed to save task: ' + (err.message || 'Unknown error'));
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto m-4">
        <div className="sticky top-0 bg-white border-b border-light-200 px-6 py-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-owl-blue-900">
            {task ? 'Edit Task' : 'Add Task'}
          </h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-light-100 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-light-700 mb-1">
              Title *
            </label>
            <input
              type="text"
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              required
              className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-light-700 mb-1">
              Description
            </label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              rows={4}
              className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-light-700 mb-1">
                Priority *
              </label>
              <select
                value={formData.priority}
                onChange={(e) => setFormData({ ...formData, priority: e.target.value })}
                required
                className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
              >
                <option value="STANDARD">🟢 Standard</option>
                <option value="HIGH">🟡 High</option>
                <option value="URGENT">🔴 Urgent</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-light-700 mb-1">
                Due Date
              </label>
              <input
                type="date"
                value={formData.due_date}
                onChange={(e) => setFormData({ ...formData, due_date: e.target.value })}
                className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-light-700 mb-1">
              Assigned To
            </label>
            <input
              type="text"
              value={formData.assigned_to}
              onChange={(e) => setFormData({ ...formData, assigned_to: e.target.value })}
              placeholder="e.g., Tom Lee, Sarah Chen"
              className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-light-700 mb-1">
                Status
              </label>
              <select
                value={formData.status}
                onChange={(e) => setFormData({ ...formData, status: e.target.value })}
                className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
              >
                <option value="PENDING">Pending</option>
                <option value="IN_PROGRESS">In Progress</option>
                <option value="COMPLETED">Completed</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-light-700 mb-1">
                Completion Percentage
              </label>
              <input
                type="number"
                min="0"
                max="100"
                value={formData.completion_percentage}
                onChange={(e) => setFormData({ ...formData, completion_percentage: parseInt(e.target.value) || 0 })}
                className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-light-700 mb-1">
              Status Text (Custom)
            </label>
            <input
              type="text"
              value={formData.status_text}
              onChange={(e) => setFormData({ ...formData, status_text: e.target.value })}
              placeholder="e.g., Waiting on Lab Results, Interview Scheduled Jan 28"
              className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
            />
            <p className="text-xs text-light-500 mt-1">
              Optional: Custom status message (overrides default status display)
            </p>
          </div>

          {/* Actions */}
          <div className="flex items-center justify-end gap-3 pt-4 border-t border-light-200">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-light-700 bg-light-100 rounded-lg hover:bg-light-200 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 text-sm font-medium text-white bg-owl-blue-500 rounded-lg hover:bg-owl-blue-600 transition-colors"
            >
              {task ? 'Update Task' : 'Create Task'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
