import React, { useState, useEffect } from 'react';
import { X, Plus, Trash2, Calendar } from 'lucide-react';

/**
 * Deadline Editor Modal
 * 
 * Allows editing trial date, court info, judge, and deadline items
 */
export default function DeadlineEditorModal({
  isOpen,
  onClose,
  caseId,
  deadlineConfig,
  onSave,
}) {
  const [formData, setFormData] = useState({
    trial_date: '',
    trial_court: '',
    judge: '',
    court_division: '',
    deadlines: [],
  });

  useEffect(() => {
    if (deadlineConfig) {
      setFormData({
        trial_date: deadlineConfig.trial_date || '',
        trial_court: deadlineConfig.trial_court || '',
        judge: deadlineConfig.judge || '',
        court_division: deadlineConfig.court_division || '',
        deadlines: deadlineConfig.deadlines || [],
      });
    } else {
      setFormData({
        trial_date: '',
        trial_court: '',
        judge: '',
        court_division: '',
        deadlines: [],
      });
    }
  }, [deadlineConfig, isOpen]);

  const handleAddDeadline = () => {
    setFormData({
      ...formData,
      deadlines: [
        ...formData.deadlines,
        {
          deadline_id: null,
          title: '',
          due_date: '',
          urgency_level: 'STANDARD',
          completed: false,
        },
      ],
    });
  };

  const handleRemoveDeadline = (index) => {
    setFormData({
      ...formData,
      deadlines: formData.deadlines.filter((_, i) => i !== index),
    });
  };

  const handleDeadlineChange = (index, field, value) => {
    const updated = [...formData.deadlines];
    updated[index] = { ...updated[index], [field]: value };
    setFormData({ ...formData, deadlines: updated });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await onSave(formData);
      onClose();
    } catch (err) {
      console.error('Failed to save deadlines:', err);
      alert('Failed to save deadlines: ' + (err.message || 'Unknown error'));
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-3xl max-h-[90vh] overflow-y-auto m-4">
        <div className="sticky top-0 bg-white border-b border-light-200 px-6 py-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-owl-blue-900">Edit Case Deadlines</h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-light-100 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          {/* Trial Date Section */}
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-owl-blue-900">Trial Information</h3>
            
            <div>
              <label className="block text-sm font-medium text-light-700 mb-1">
                Trial Date
              </label>
              <input
                type="date"
                value={formData.trial_date}
                onChange={(e) => setFormData({ ...formData, trial_date: e.target.value })}
                className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-light-700 mb-1">
                Court
              </label>
              <input
                type="text"
                value={formData.trial_court}
                onChange={(e) => setFormData({ ...formData, trial_court: e.target.value })}
                placeholder="e.g., U.S. District Court, E.D. Virginia"
                className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-light-700 mb-1">
                  Judge
                </label>
                <input
                  type="text"
                  value={formData.judge}
                  onChange={(e) => setFormData({ ...formData, judge: e.target.value })}
                  placeholder="e.g., Hon. Patricia M. Richardson"
                  className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-light-700 mb-1">
                  Court Division
                </label>
                <input
                  type="text"
                  value={formData.court_division}
                  onChange={(e) => setFormData({ ...formData, court_division: e.target.value })}
                  placeholder="e.g., Alexandria Division"
                  className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
                />
              </div>
            </div>
          </div>

          {/* Deadlines Section */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-owl-blue-900">Upcoming Deadlines</h3>
              <button
                type="button"
                onClick={handleAddDeadline}
                className="flex items-center gap-2 px-3 py-1.5 text-sm bg-owl-blue-500 text-white rounded-lg hover:bg-owl-blue-600 transition-colors"
              >
                <Plus className="w-4 h-4" />
                Add Deadline
              </button>
            </div>

            {formData.deadlines.length === 0 ? (
              <p className="text-sm text-light-500 italic">No deadlines added yet</p>
            ) : (
              <div className="space-y-3">
                {formData.deadlines.map((deadline, index) => (
                  <div
                    key={index}
                    className="p-4 border border-light-200 rounded-lg bg-light-50 space-y-3"
                  >
                    <div className="flex items-center justify-between">
                      <h4 className="text-sm font-medium text-owl-blue-900">
                        Deadline {index + 1}
                      </h4>
                      <button
                        type="button"
                        onClick={() => handleRemoveDeadline(index)}
                        className="p-1.5 hover:bg-red-100 rounded transition-colors text-red-600"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-light-700 mb-1">
                        Title
                      </label>
                      <input
                        type="text"
                        value={deadline.title}
                        onChange={(e) => handleDeadlineChange(index, 'title', e.target.value)}
                        placeholder="e.g., Expert witness disclosure deadline"
                        className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500 text-sm"
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs font-medium text-light-700 mb-1">
                          Due Date
                        </label>
                        <input
                          type="date"
                          value={deadline.due_date}
                          onChange={(e) => handleDeadlineChange(index, 'due_date', e.target.value)}
                          className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500 text-sm"
                        />
                      </div>

                      <div>
                        <label className="block text-xs font-medium text-light-700 mb-1">
                          Urgency Level
                        </label>
                        <select
                          value={deadline.urgency_level}
                          onChange={(e) => handleDeadlineChange(index, 'urgency_level', e.target.value)}
                          className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500 text-sm"
                        >
                          <option value="STANDARD">Standard</option>
                          <option value="HIGH">High</option>
                          <option value="URGENT">Urgent</option>
                        </select>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        id={`completed-${index}`}
                        checked={deadline.completed}
                        onChange={(e) => handleDeadlineChange(index, 'completed', e.target.checked)}
                        className="w-4 h-4 text-owl-blue-600 border-light-300 rounded focus:ring-owl-blue-500"
                      />
                      <label htmlFor={`completed-${index}`} className="text-xs text-light-700">
                        Completed
                      </label>
                    </div>
                  </div>
                ))}
              </div>
            )}
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
              Save Deadlines
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
