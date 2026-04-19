import React, { useState, useEffect } from 'react';
import {
  BookTemplate, Loader2, Save, Download, Trash2, X,
  ChevronRight, FileText, Plus,
} from 'lucide-react';
import { triageAPI } from '../../services/api';

function SaveTemplateModal({ caseId, onSaved, onClose }) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSave = async () => {
    if (!name.trim()) return;
    setSaving(true);
    setError('');
    try {
      await triageAPI.createTemplate(caseId, { name: name.trim(), description: description.trim() });
      onSaved();
    } catch (err) {
      setError(err.message || 'Failed to save template');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-md p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-owl-blue-900">Save as Template</h3>
          <button onClick={onClose} className="p-1 hover:bg-light-100 rounded">
            <X className="w-4 h-4 text-light-500" />
          </button>
        </div>
        <p className="text-xs text-light-500 mb-4">
          Save this case's custom processing stages as a reusable template.
        </p>

        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-light-700 mb-1">Template Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-light-200 rounded-lg focus:outline-none focus:border-owl-blue-400"
              placeholder="e.g. Windows Full Analysis"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-light-700 mb-1">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-light-200 rounded-lg focus:outline-none focus:border-owl-blue-400 h-20 resize-none"
              placeholder="What this template does..."
            />
          </div>
        </div>

        {error && <p className="text-xs text-red-600 mt-2">{error}</p>}

        <div className="flex justify-end gap-2 mt-4">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-sm text-light-600 hover:bg-light-100 rounded-lg"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={!name.trim() || saving}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-owl-blue-600 text-white rounded-lg hover:bg-owl-blue-700 disabled:opacity-40"
          >
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
            Save Template
          </button>
        </div>
      </div>
    </div>
  );
}

function ApplyTemplateModal({ caseId, onApplied, onClose }) {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    const load = async () => {
      try {
        const data = await triageAPI.listTemplates();
        setTemplates(data.templates || []);
      } catch (err) {
        setError('Failed to load templates');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const handleApply = async (templateId) => {
    setApplying(templateId);
    setError('');
    try {
      await triageAPI.applyTemplate(caseId, { template_id: templateId });
      onApplied();
    } catch (err) {
      setError(err.message || 'Failed to apply template');
    } finally {
      setApplying(null);
    }
  };

  const handleDelete = async (templateId) => {
    try {
      await triageAPI.deleteTemplate(templateId);
      setTemplates((prev) => prev.filter((t) => t.id !== templateId));
    } catch (err) {
      setError('Failed to delete template');
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-owl-blue-900">Apply Template</h3>
          <button onClick={onClose} className="p-1 hover:bg-light-100 rounded">
            <X className="w-4 h-4 text-light-500" />
          </button>
        </div>
        <p className="text-xs text-light-500 mb-4">
          Apply a saved workflow template to add its processing stages to this case.
        </p>

        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-6 h-6 animate-spin text-light-400" />
          </div>
        ) : templates.length === 0 ? (
          <div className="text-center py-8 text-light-400 text-sm">
            No templates saved yet. Process a case and save it as a template.
          </div>
        ) : (
          <div className="space-y-2 max-h-80 overflow-y-auto">
            {templates.map((t) => (
              <div
                key={t.id}
                className="border border-light-200 rounded-lg p-3 hover:bg-light-50"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <BookTemplate className="w-4 h-4 text-owl-blue-500 flex-shrink-0" />
                      <span className="text-sm font-medium text-light-800 truncate">{t.name}</span>
                    </div>
                    {t.description && (
                      <p className="text-xs text-light-500 mt-1 ml-6">{t.description}</p>
                    )}
                    <div className="flex items-center gap-3 mt-1.5 ml-6">
                      <span className="text-[10px] text-light-400">
                        {t.stage_count} stage{t.stage_count !== 1 ? 's' : ''}
                      </span>
                      {t.stages?.map((s, i) => (
                        <span key={i} className="text-[10px] text-light-500 bg-light-100 px-1.5 py-0.5 rounded">
                          {s.name}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button
                      onClick={() => handleApply(t.id)}
                      disabled={applying === t.id}
                      className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-white bg-owl-blue-600 rounded hover:bg-owl-blue-700 disabled:opacity-40"
                    >
                      {applying === t.id ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <Download className="w-3 h-3" />
                      )}
                      Apply
                    </button>
                    <button
                      onClick={() => handleDelete(t.id)}
                      className="p-1 text-light-400 hover:text-red-500 hover:bg-red-50 rounded"
                      title="Delete template"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {error && <p className="text-xs text-red-600 mt-2">{error}</p>}

        <div className="flex justify-end mt-4">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-sm text-light-600 hover:bg-light-100 rounded-lg"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

export { SaveTemplateModal, ApplyTemplateModal };
