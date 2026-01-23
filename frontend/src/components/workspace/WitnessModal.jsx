import React, { useState, useEffect } from 'react';
import { X, Save, Star } from 'lucide-react';
import { workspaceAPI } from '../../services/api';

/**
 * Witness Modal
 * 
 * Modal for adding or editing a witness
 */
export default function WitnessModal({
  isOpen,
  onClose,
  caseId,
  witness = null, // If provided, edit mode; otherwise, add mode
  onSave,
}) {
  const [formData, setFormData] = useState({
    name: '',
    role: '',
    organization: '',
    category: 'NEUTRAL',
    status: '',
    credibility_rating: null,
    statement_summary: '',
    risk_assessment: '',
    strategy_notes: '',
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (isOpen) {
      if (witness) {
        // Edit mode - populate with existing witness data
        setFormData({
          name: witness.name || '',
          role: witness.role || '',
          organization: witness.organization || '',
          category: witness.category || 'NEUTRAL',
          status: witness.status || '',
          credibility_rating: witness.credibility_rating ?? null,
          statement_summary: witness.statement_summary || '',
          risk_assessment: witness.risk_assessment || '',
          strategy_notes: witness.strategy_notes || '',
        });
      } else {
        // Add mode - reset form
        setFormData({
          name: '',
          role: '',
          organization: '',
          category: 'NEUTRAL',
          status: '',
          credibility_rating: null,
          statement_summary: '',
          risk_assessment: '',
          strategy_notes: '',
        });
      }
    }
  }, [isOpen, witness]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!caseId || !formData.name.trim()) return;

    setSaving(true);
    try {
      if (witness) {
        // Update existing witness
        await workspaceAPI.updateWitness(caseId, witness.witness_id, formData);
      } else {
        // Create new witness
        await workspaceAPI.createWitness(caseId, formData);
      }
      
      if (onSave) {
        onSave();
      }
      
      onClose();
    } catch (err) {
      console.error('Failed to save witness:', err);
      alert('Failed to save witness');
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
            {witness ? 'Edit Witness' : 'Add Witness'}
          </h3>
          <button onClick={onClose} className="p-1 hover:bg-light-100 rounded">
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-owl-blue-900 mb-1">
              Name *
            </label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-owl-blue-900 mb-1">
                Role
              </label>
              <input
                type="text"
                value={formData.role}
                onChange={(e) => setFormData({ ...formData, role: e.target.value })}
                placeholder="e.g., Registered Agent"
                className="w-full px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-owl-blue-900 mb-1">
                Organization
              </label>
              <input
                type="text"
                value={formData.organization}
                onChange={(e) => setFormData({ ...formData, organization: e.target.value })}
                placeholder="e.g., TaxShield Corp"
                className="w-full px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-owl-blue-900 mb-1">
              Category *
            </label>
            <select
              value={formData.category}
              onChange={(e) => setFormData({ ...formData, category: e.target.value })}
              className="w-full px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
              required
            >
              <option value="FRIENDLY">Friendly</option>
              <option value="NEUTRAL">Neutral</option>
              <option value="ADVERSE">Adverse</option>
            </select>
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
              Statement Summary
            </label>
            <textarea
              value={formData.statement_summary}
              onChange={(e) => setFormData({ ...formData, statement_summary: e.target.value })}
              rows={4}
              placeholder="Enter a summary of the witness statement..."
              className="w-full px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
            />
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

          <div>
            <label className="block text-sm font-medium text-owl-blue-900 mb-1">
              Strategy Notes
            </label>
            <textarea
              value={formData.strategy_notes}
              onChange={(e) => setFormData({ ...formData, strategy_notes: e.target.value })}
              rows={3}
              placeholder="Enter strategy notes for this witness..."
              className="w-full px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
            />
          </div>

          <div className="flex gap-2 pt-4 border-t border-light-200">
            <button
              type="submit"
              disabled={saving || !formData.name.trim()}
              className="flex-1 px-4 py-2 bg-owl-blue-600 text-white rounded-lg hover:bg-owl-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              <Save className="w-4 h-4" />
              {saving ? 'Saving...' : witness ? 'Update Witness' : 'Add Witness'}
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
