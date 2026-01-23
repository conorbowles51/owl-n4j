import React, { useState, useEffect } from 'react';
import { X, Plus, Trash2 } from 'lucide-react';

/**
 * Client Profile Editor Modal
 * 
 * Allows editing client profile, charges, allegations, denials, legal exposure, and defense strategy
 */
export default function ClientProfileEditorModal({
  isOpen,
  onClose,
  caseContext,
  onSave,
}) {
  const [formData, setFormData] = useState({
    client_name: '',
    client_role: '',
    charges: [],
    allegations: [],
    denials: [],
    legal_exposure: {},
    defense_strategy: [],
  });

  useEffect(() => {
    if (caseContext) {
      const clientProfile = caseContext.client_profile || {};
      setFormData({
        client_name: clientProfile.name || '',
        client_role: clientProfile.role || '',
        charges: caseContext.charges || [],
        allegations: caseContext.allegations || [],
        denials: caseContext.denials || [],
        legal_exposure: caseContext.legal_exposure || {},
        defense_strategy: caseContext.defense_strategy || [],
      });
    } else {
      setFormData({
        client_name: '',
        client_role: '',
        charges: [],
        allegations: [],
        denials: [],
        legal_exposure: {},
        defense_strategy: [],
      });
    }
  }, [caseContext, isOpen]);

  const handleAddItem = (field) => {
    setFormData({
      ...formData,
      [field]: [...formData[field], ''],
    });
  };

  const handleRemoveItem = (field, index) => {
    setFormData({
      ...formData,
      [field]: formData[field].filter((_, i) => i !== index),
    });
  };

  const handleItemChange = (field, index, value) => {
    const updated = [...formData[field]];
    updated[index] = value;
    setFormData({ ...formData, [field]: updated });
  };

  const handleAddExposure = () => {
    setFormData({
      ...formData,
      legal_exposure: {
        ...formData.legal_exposure,
        ['']: '',
      },
    });
  };

  const handleRemoveExposure = (key) => {
    const updated = { ...formData.legal_exposure };
    delete updated[key];
    setFormData({ ...formData, legal_exposure: updated });
  };

  const handleExposureChange = (oldKey, newKey, value) => {
    const updated = { ...formData.legal_exposure };
    if (oldKey !== newKey) {
      delete updated[oldKey];
    }
    updated[newKey] = value;
    setFormData({ ...formData, legal_exposure: updated });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const updateData = {
        client_profile: {
          name: formData.client_name,
          role: formData.client_role,
        },
        charges: formData.charges.filter(c => c.trim()),
        allegations: formData.allegations.filter(a => a.trim()),
        denials: formData.denials.filter(d => d.trim()),
        legal_exposure: Object.fromEntries(
          Object.entries(formData.legal_exposure).filter(([k, v]) => k.trim() && v.trim())
        ),
        defense_strategy: formData.defense_strategy.filter(s => s.trim()),
      };
      await onSave(updateData);
      onClose();
    } catch (err) {
      console.error('Failed to save client profile:', err);
      alert('Failed to save client profile: ' + (err.message || 'Unknown error'));
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] overflow-y-auto m-4">
        <div className="sticky top-0 bg-white border-b border-light-200 px-6 py-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-owl-blue-900">Edit Client Profile & Exposure</h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-light-100 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          {/* Client Information */}
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-owl-blue-900">Client Information</h3>
            
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-light-700 mb-1">
                  Client Name
                </label>
                <input
                  type="text"
                  value={formData.client_name}
                  onChange={(e) => setFormData({ ...formData, client_name: e.target.value })}
                  placeholder="e.g., John Smith"
                  className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-light-700 mb-1">
                  Role/Title
                </label>
                <input
                  type="text"
                  value={formData.client_role}
                  onChange={(e) => setFormData({ ...formData, client_role: e.target.value })}
                  placeholder="e.g., CEO"
                  className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
                />
              </div>
            </div>
          </div>

          {/* Charges */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-owl-blue-900">Charges</h3>
              <button
                type="button"
                onClick={() => handleAddItem('charges')}
                className="flex items-center gap-2 px-3 py-1.5 text-sm bg-owl-blue-500 text-white rounded-lg hover:bg-owl-blue-600 transition-colors"
              >
                <Plus className="w-4 h-4" />
                Add Charge
              </button>
            </div>
            <div className="space-y-2">
              {formData.charges.map((charge, index) => (
                <div key={index} className="flex items-center gap-2">
                  <input
                    type="text"
                    value={charge}
                    onChange={(e) => handleItemChange('charges', index, e.target.value)}
                    placeholder="e.g., Wire Fraud (18 USC 1343)"
                    className="flex-1 px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500 text-sm"
                  />
                  <button
                    type="button"
                    onClick={() => handleRemoveItem('charges', index)}
                    className="p-2 hover:bg-red-100 rounded text-red-600"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Allegations */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-owl-blue-900">Allegations</h3>
              <button
                type="button"
                onClick={() => handleAddItem('allegations')}
                className="flex items-center gap-2 px-3 py-1.5 text-sm bg-owl-blue-500 text-white rounded-lg hover:bg-owl-blue-600 transition-colors"
              >
                <Plus className="w-4 h-4" />
                Add Allegation
              </button>
            </div>
            <div className="space-y-2">
              {formData.allegations.map((allegation, index) => (
                <div key={index} className="flex items-center gap-2">
                  <input
                    type="text"
                    value={allegation}
                    onChange={(e) => handleItemChange('allegations', index, e.target.value)}
                    placeholder="e.g., 🔴 Established TaxShield Corp as shell company"
                    className="flex-1 px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500 text-sm"
                  />
                  <button
                    type="button"
                    onClick={() => handleRemoveItem('allegations', index)}
                    className="p-2 hover:bg-red-100 rounded text-red-600"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Denials */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-owl-blue-900">Client Denies</h3>
              <button
                type="button"
                onClick={() => handleAddItem('denials')}
                className="flex items-center gap-2 px-3 py-1.5 text-sm bg-owl-blue-500 text-white rounded-lg hover:bg-owl-blue-600 transition-colors"
              >
                <Plus className="w-4 h-4" />
                Add Denial
              </button>
            </div>
            <div className="space-y-2">
              {formData.denials.map((denial, index) => (
                <div key={index} className="flex items-center gap-2">
                  <input
                    type="text"
                    value={denial}
                    onChange={(e) => handleItemChange('denials', index, e.target.value)}
                    placeholder="e.g., 🟢 Any intent to defraud or conceal assets"
                    className="flex-1 px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500 text-sm"
                  />
                  <button
                    type="button"
                    onClick={() => handleRemoveItem('denials', index)}
                    className="p-2 hover:bg-red-100 rounded text-red-600"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Legal Exposure */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-owl-blue-900">Legal Exposure</h3>
              <button
                type="button"
                onClick={handleAddExposure}
                className="flex items-center gap-2 px-3 py-1.5 text-sm bg-owl-blue-500 text-white rounded-lg hover:bg-owl-blue-600 transition-colors"
              >
                <Plus className="w-4 h-4" />
                Add Exposure
              </button>
            </div>
            <div className="space-y-2">
              {Object.entries(formData.legal_exposure).map(([key, value], index) => (
                <div key={index} className="flex items-center gap-2">
                  <input
                    type="text"
                    value={key}
                    onChange={(e) => handleExposureChange(key, e.target.value, value)}
                    placeholder="e.g., Wire Fraud"
                    className="w-1/3 px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500 text-sm"
                  />
                  <input
                    type="text"
                    value={value}
                    onChange={(e) => handleExposureChange(key, key, e.target.value)}
                    placeholder="e.g., 20 years | Min $1,000+ restitution"
                    className="flex-1 px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500 text-sm"
                  />
                  <button
                    type="button"
                    onClick={() => handleRemoveExposure(key)}
                    className="p-2 hover:bg-red-100 rounded text-red-600"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Defense Strategy */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-owl-blue-900">Defense Strategy Points</h3>
              <button
                type="button"
                onClick={() => handleAddItem('defense_strategy')}
                className="flex items-center gap-2 px-3 py-1.5 text-sm bg-owl-blue-500 text-white rounded-lg hover:bg-owl-blue-600 transition-colors"
              >
                <Plus className="w-4 h-4" />
                Add Strategy Point
              </button>
            </div>
            <div className="space-y-2">
              {formData.defense_strategy.map((strategy, index) => (
                <div key={index} className="flex items-center gap-2">
                  <input
                    type="text"
                    value={strategy}
                    onChange={(e) => handleItemChange('defense_strategy', index, e.target.value)}
                    placeholder="e.g., 🎯 Challenge beneficial ownership nexus"
                    className="flex-1 px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500 text-sm"
                  />
                  <button
                    type="button"
                    onClick={() => handleRemoveItem('defense_strategy', index)}
                    className="p-2 hover:bg-red-100 rounded text-red-600"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
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
              Save Profile
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
