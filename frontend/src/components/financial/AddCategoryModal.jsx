import { useState, useEffect } from 'react';
import { X, Loader2 } from 'lucide-react';

const COLOR_PALETTE = [
  '#ef4444', '#f97316', '#f59e0b', '#eab308',
  '#84cc16', '#22c55e', '#10b981', '#14b8a6',
  '#06b6d4', '#0ea5e9', '#3b82f6', '#6366f1',
  '#8b5cf6', '#a855f7', '#d946ef', '#ec4899',
];

export default function AddCategoryModal({ isOpen, onClose, onSubmit, existingNames = [] }) {
  const [name, setName] = useState('');
  const [color, setColor] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (isOpen) {
      setName('');
      setColor('');
      setSaving(false);
      setError('');
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError('Name is required');
      return;
    }
    if (existingNames.includes(trimmed)) {
      setError('A category with this name already exists');
      return;
    }
    if (!color) {
      setError('Please select a color');
      return;
    }
    setSaving(true);
    setError('');
    try {
      await onSubmit(trimmed, color);
      onClose();
    } catch (err) {
      setError(err.message || 'Failed to create category');
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-lg shadow-xl w-80 p-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-medium text-light-800">New Category</span>
          <button onClick={onClose} className="p-1 text-light-500 hover:text-light-800 rounded">
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="mb-3">
            <label className="text-xs text-light-600 font-medium block mb-1">Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => { setName(e.target.value); setError(''); }}
              placeholder="e.g. Bribes"
              className="w-full text-sm px-3 py-1.5 border border-light-200 rounded focus:outline-none focus:border-owl-blue-400"
              autoFocus
              disabled={saving}
            />
          </div>

          <div className="mb-3">
            <label className="text-xs text-light-600 font-medium block mb-1">Color</label>
            <div className="flex flex-wrap gap-2">
              {COLOR_PALETTE.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => { setColor(c); setError(''); }}
                  className="w-6 h-6 rounded-full border-2 transition-all"
                  style={{
                    backgroundColor: c,
                    borderColor: color === c ? '#1e293b' : 'transparent',
                    transform: color === c ? 'scale(1.2)' : 'scale(1)',
                  }}
                  disabled={saving}
                />
              ))}
            </div>
          </div>

          {error && (
            <p className="text-xs text-red-500 mb-2">{error}</p>
          )}

          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="text-xs px-3 py-1.5 rounded border border-light-200 text-light-600 hover:bg-light-50"
              disabled={saving}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="text-xs px-3 py-1.5 rounded bg-owl-blue-600 text-white hover:bg-owl-blue-700 disabled:opacity-50 flex items-center gap-1"
            >
              {saving && <Loader2 className="w-3 h-3 animate-spin" />}
              Create
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
