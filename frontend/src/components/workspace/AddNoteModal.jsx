import React, { useState } from 'react';
import { X, Upload, FileText, Loader2 } from 'lucide-react';
import { evidenceAPI } from '../../services/api';

/**
 * Add Note Modal
 * 
 * Modal for uploading documents or creating text notes (Quick Actions)
 */
export default function AddNoteModal({ isOpen, onClose, caseId, onUploaded }) {
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [noteText, setNoteText] = useState('');
  const [useFileUpload, setUseFileUpload] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);

  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files);
    setSelectedFiles(files);
    setError(null);
  };

  const handleUpload = async () => {
    if (!caseId) return;

    setUploading(true);
    setError(null);

    try {
      if (useFileUpload) {
        if (selectedFiles.length === 0) {
          setError('Please select at least one file');
          setUploading(false);
          return;
        }

        const fileList = new DataTransfer();
        selectedFiles.forEach(file => fileList.items.add(file));

        await evidenceAPI.upload(caseId, fileList.files);
      } else {
        // Create a text file from note content
        if (!noteText.trim()) {
          setError('Please enter note content');
          setUploading(false);
          return;
        }

        const blob = new Blob([noteText], { type: 'text/plain' });
        const file = new File([blob], `note_${Date.now()}.txt`, { type: 'text/plain' });
        const fileList = new DataTransfer();
        fileList.items.add(file);

        await evidenceAPI.upload(caseId, fileList.files);
      }
      
      // Reset form
      setSelectedFiles([]);
      setNoteText('');
      
      // Notify parent to refresh
      if (onUploaded) {
        onUploaded();
      }
      
      onClose();
    } catch (err) {
      console.error('Failed to upload note:', err);
      setError(err.message || 'Failed to upload note');
    } finally {
      setUploading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-md mx-4 max-h-[90vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-light-200">
          <h2 className="text-lg font-semibold text-owl-blue-900">Add Note</h2>
          <button onClick={onClose} className="p-1 hover:bg-light-100 rounded" disabled={uploading}>
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          <div className="flex gap-2 border-b border-light-200 pb-2">
            <button
              onClick={() => setUseFileUpload(true)}
              className={`flex-1 px-3 py-2 text-sm rounded-lg transition-colors ${
                useFileUpload
                  ? 'bg-owl-blue-100 text-owl-blue-700'
                  : 'bg-light-100 text-light-600 hover:bg-light-200'
              }`}
            >
              Upload Document
            </button>
            <button
              onClick={() => setUseFileUpload(false)}
              className={`flex-1 px-3 py-2 text-sm rounded-lg transition-colors ${
                !useFileUpload
                  ? 'bg-owl-blue-100 text-owl-blue-700'
                  : 'bg-light-100 text-light-600 hover:bg-light-200'
              }`}
            >
              Create Text Note
            </button>
          </div>

          {useFileUpload ? (
            <div>
              <label className="block text-sm font-medium text-owl-blue-900 mb-2">
                Select Document Files
              </label>
              <div className="border-2 border-dashed border-light-300 rounded-lg p-6 text-center hover:border-owl-blue-400 transition-colors">
                <input
                  type="file"
                  multiple
                  onChange={handleFileSelect}
                  className="hidden"
                  id="note-upload"
                  disabled={uploading}
                />
                <label
                  htmlFor="note-upload"
                  className="cursor-pointer flex flex-col items-center gap-2"
                >
                  <FileText className="w-8 h-8 text-owl-blue-600" />
                  <span className="text-sm text-light-600">
                    Click to select documents or drag and drop
                  </span>
                  <span className="text-xs text-light-500">
                    Supports: PDF, DOC, DOCX, TXT, etc.
                  </span>
                </label>
              </div>
              {selectedFiles.length > 0 && (
                <div className="mt-3 space-y-1">
                  <p className="text-xs font-medium text-owl-blue-900">
                    Selected files ({selectedFiles.length}):
                  </p>
                  <div className="max-h-32 overflow-y-auto space-y-1">
                    {selectedFiles.map((file, idx) => (
                      <div key={idx} className="text-xs text-light-600 flex items-center justify-between bg-light-50 p-2 rounded">
                        <span className="truncate flex-1">{file.name}</span>
                        <span className="text-light-500 ml-2">
                          {(file.size / 1024 / 1024).toFixed(2)} MB
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div>
              <label className="block text-sm font-medium text-owl-blue-900 mb-2">
                Note Content
              </label>
              <textarea
                value={noteText}
                onChange={(e) => setNoteText(e.target.value)}
                rows={10}
                placeholder="Enter your note here..."
                className="w-full px-3 py-2 border border-light-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-owl-blue-500"
                disabled={uploading}
              />
            </div>
          )}

          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-600">{error}</p>
            </div>
          )}
        </div>

        <div className="p-4 border-t border-light-200">
          <div className="flex gap-2">
            <button
              onClick={handleUpload}
              disabled={uploading || (useFileUpload && selectedFiles.length === 0) || (!useFileUpload && !noteText.trim())}
              className="flex-1 px-4 py-2 bg-owl-blue-600 text-white rounded-lg hover:bg-owl-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {uploading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Uploading...
                </>
              ) : (
                <>
                  <Upload className="w-4 h-4" />
                  {useFileUpload
                    ? `Upload ${selectedFiles.length > 0 ? `${selectedFiles.length} ` : ''}Document${selectedFiles.length !== 1 ? 's' : ''}`
                    : 'Create Note'}
                </>
              )}
            </button>
            <button
              onClick={onClose}
              disabled={uploading}
              className="px-4 py-2 bg-light-200 text-light-700 rounded-lg hover:bg-light-300 disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
