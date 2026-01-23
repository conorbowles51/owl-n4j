import React, { useState, useEffect } from 'react';
import { X, Save, Star } from 'lucide-react';
import { workspaceAPI } from '../../services/api';

/**
 * Witness Interview Modal
 * 
 * Modal for adding or editing a witness interview
 */
export default function WitnessInterviewModal({
  isOpen,
  onClose,
  caseId,
  witness,
  interview = null, // If provided, edit mode; otherwise, add mode
  onSave,
}) {
  const [formData, setFormData] = useState({
    date: '',
    duration: '',
    statement: '',
    status: '',
    credibility_rating: null,
    risk_assessment: '',
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (isOpen) {
      if (interview) {
        // Edit mode - populate with existing interview data
        setFormData({
          date: interview.date || '',
          duration: interview.duration || '',
          statement: interview.statement || '',
          status: interview.status || '',
          credibility_rating: interview.credibility_rating ?? null,
          risk_assessment: interview.risk_assessment || '',
        });
      } else {
        // Add mode - reset form
        setFormData({
          date: new Date().toISOString().split('T')[0], // Today's date
          duration: '',
          statement: '',
          status: '',
          credibility_rating: null,
          risk_assessment: '',
        });
      }
    }
  }, [isOpen, interview]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!caseId || !witness) return;

    setSaving(true);
    try {
      const interviewData = {
        ...formData,
        interview_id: interview?.interview_id || `interview_${Date.now()}`,
        created_at: interview?.created_at || new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      const existingInterviews = witness.interviews || [];
      let updatedInterviews;
      
      if (interview) {
        // Update existing interview
        updatedInterviews = existingInterviews.map((i) =>
          i.interview_id === interview.interview_id ? interviewData : i
        );
      } else {
        // Add new interview
        updatedInterviews = [...existingInterviews, interviewData];
      }

      // Update witness with new interviews array
      const updatedWitness = {
        ...witness,
        interviews: updatedInterviews,
      };

      await workspaceAPI.updateWitness(caseId, witness.witness_id, updatedWitness);
      
      if (onSave) {
        onSave();
      }
      
      onClose();
    } catch (err) {
      console.error('Failed to save interview:', err);
      alert('Failed to save interview');
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-2xl mx-4 max-h-[90vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-light-200">
          <h3 className="text-lg font-semibold text-owl-blue-900">
            {interview ? 'Edit Interview' : 'Add Interview'} - {witness?.name}
          </h3>
          <button onClick={onClose} className="p-1 hover:bg-light-100 rounded">
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-owl-blue-900 mb-1">
              Date *
            </label>
            <input
              type="date"
              value={formData.date}
              onChange={(e) => setFormData({ ...formData, date: e.target.value })}
              className="w-full px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-owl-blue-900 mb-1">
              Duration
            </label>
            <input
              type="text"
              value={formData.duration}
              onChange={(e) => setFormData({ ...formData, duration: e.target.value })}
              placeholder="e.g., 45 minutes, 1 hour 30 minutes"
              className="w-full px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-owl-blue-900 mb-1">
              Statement
            </label>
            <textarea
              value={formData.statement}
              onChange={(e) => setFormData({ ...formData, statement: e.target.value })}
              rows={6}
              placeholder="Enter the witness statement..."
              className="w-full px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-owl-blue-900 mb-1">
              Status
            </label>
            <input
              type="text"
              value={formData.status}
              onChange={(e) => setFormData({ ...formData, status: e.target.value })}
              placeholder="e.g., Cooperating Witness (CW)"
              className="w-full px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-owl-blue-900 mb-1">
              Credibility Rating (1-5)
            </label>
            <div className="flex items-center gap-2">
              {[1, 2, 3, 4, 5].map((rating) => (
                <button
                  key={rating}
                  type="button"
                  onClick={() => setFormData({ ...formData, credibility_rating: rating })}
                  className={`p-2 rounded transition-colors ${
                    formData.credibility_rating === rating
                      ? 'bg-owl-blue-100 text-owl-blue-700'
                      : 'bg-light-100 text-light-600 hover:bg-light-200'
                  }`}
                >
                  <Star
                    className={`w-5 h-5 ${
                      formData.credibility_rating === rating ? 'fill-current' : ''
                    }`}
                  />
                </button>
              ))}
              {formData.credibility_rating && (
                <button
                  type="button"
                  onClick={() => setFormData({ ...formData, credibility_rating: null })}
                  className="text-xs text-light-600 hover:text-red-600 ml-2"
                >
                  Clear
                </button>
              )}
            </div>
            {formData.credibility_rating && (
              <p className="text-xs text-light-600 mt-1">
                Rating: {formData.credibility_rating}/5
                {formData.credibility_rating >= 4 && ' (High)'}
                {formData.credibility_rating === 3 && ' (Medium)'}
                {formData.credibility_rating <= 2 && ' (Low)'}
              </p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-owl-blue-900 mb-1">
              Risk Assessment
            </label>
            <input
              type="text"
              value={formData.risk_assessment}
              onChange={(e) => setFormData({ ...formData, risk_assessment: e.target.value })}
              placeholder="e.g., Prosecution may flip if immunity deal threatened"
              className="w-full px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
            />
          </div>

          <div className="flex gap-2 pt-4 border-t border-light-200">
            <button
              type="submit"
              disabled={saving || !formData.date}
              className="flex-1 px-4 py-2 bg-owl-blue-600 text-white rounded-lg hover:bg-owl-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              <Save className="w-4 h-4" />
              {saving ? 'Saving...' : interview ? 'Update Interview' : 'Add Interview'}
            </button>
            <button
              type="button"
              onClick={onClose}
              disabled={saving}
              className="px-4 py-2 bg-light-200 text-light-700 rounded-lg hover:bg-light-300 disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
