import React, { useState } from 'react';
import { X, Upload, Link2, Loader2 } from 'lucide-react';
import { evidenceAPI } from '../../services/api';

/**
 * Link Entity Modal
 * 
 * Modal for adding links/URLs as documents
 */
export default function LinkEntityModal({ isOpen, onClose, caseId, onUploaded }) {
  const [url, setUrl] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!caseId || !url.trim()) return;

    setUploading(true);
    setError(null);

    try {
      // Create a text file with link information
      const linkContent = [
        `Title: ${title || 'Untitled Link'}`,
        `URL: ${url}`,
        description ? `Description: ${description}` : '',
        `Added: ${new Date().toISOString()}`,
      ].filter(Boolean).join('\n\n');

      const blob = new Blob([linkContent], { type: 'text/plain' });
      const fileName = title 
        ? `${title.replace(/[^a-z0-9]/gi, '_').toLowerCase()}_link.txt`
        : `link_${Date.now()}.txt`;
      const file = new File([blob], fileName, { type: 'text/plain' });
      const fileList = new DataTransfer();
      fileList.items.add(file);

      await evidenceAPI.upload(caseId, fileList.files);
      
      // Reset form
      setUrl('');
      setTitle('');
      setDescription('');
      
      // Notify parent to refresh
      if (onUploaded) {
        onUploaded();
      }
      
      onClose();
    } catch (err) {
      console.error('Failed to add link:', err);
      setError(err.message || 'Failed to add link');
    } finally {
      setUploading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-md mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-light-200">
          <h2 className="text-lg font-semibold text-owl-blue-900">Add Link</h2>
          <button onClick={onClose} className="p-1 hover:bg-light-100 rounded" disabled={uploading}>
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-owl-blue-900 mb-1">
              URL *
            </label>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com"
              className="w-full px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
              required
              disabled={uploading}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-owl-blue-900 mb-1">
              Title
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Link title (optional)"
              className="w-full px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
              disabled={uploading}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-owl-blue-900 mb-1">
              Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="Link description (optional)"
              className="w-full px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
              disabled={uploading}
            />
          </div>

          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-600">{error}</p>
            </div>
          )}

          <div className="flex gap-2 pt-2">
            <button
              type="submit"
              disabled={uploading || !url.trim()}
              className="flex-1 px-4 py-2 bg-owl-blue-600 text-white rounded-lg hover:bg-owl-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {uploading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Adding...
                </>
              ) : (
                <>
                  <Link2 className="w-4 h-4" />
                  Add Link
                </>
              )}
            </button>
            <button
              type="button"
              onClick={onClose}
              disabled={uploading}
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
