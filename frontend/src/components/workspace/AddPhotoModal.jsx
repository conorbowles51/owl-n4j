import React, { useState } from 'react';
import { X, Upload, Image as ImageIcon, Loader2 } from 'lucide-react';
import { evidenceAPI } from '../../services/api';

/**
 * Add Photo Modal
 * 
 * Modal for uploading photos/images
 */
export default function AddPhotoModal({ isOpen, onClose, caseId, onUploaded }) {
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);

  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files);
    // Filter to only image files
    const imageFiles = files.filter(file => file.type.startsWith('image/'));
    setSelectedFiles(imageFiles);
    setError(null);
  };

  const handleUpload = async () => {
    if (!caseId || selectedFiles.length === 0) return;

    setUploading(true);
    setError(null);

    try {
      const fileList = new DataTransfer();
      selectedFiles.forEach(file => fileList.items.add(file));

      await evidenceAPI.upload(caseId, fileList.files);
      
      // Reset form
      setSelectedFiles([]);
      
      // Notify parent to refresh
      if (onUploaded) {
        onUploaded();
      }
      
      onClose();
    } catch (err) {
      console.error('Failed to upload photos:', err);
      setError(err.message || 'Failed to upload photos');
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
          <h2 className="text-lg font-semibold text-owl-blue-900">Add Photo</h2>
          <button onClick={onClose} className="p-1 hover:bg-light-100 rounded" disabled={uploading}>
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>
        <div className="p-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-owl-blue-900 mb-2">
              Select Image Files
            </label>
            <div className="border-2 border-dashed border-light-300 rounded-lg p-6 text-center hover:border-owl-blue-400 transition-colors">
              <input
                type="file"
                accept="image/*"
                multiple
                onChange={handleFileSelect}
                className="hidden"
                id="photo-upload"
                disabled={uploading}
              />
              <label
                htmlFor="photo-upload"
                className="cursor-pointer flex flex-col items-center gap-2"
              >
                <ImageIcon className="w-8 h-8 text-owl-blue-600" />
                <span className="text-sm text-light-600">
                  Click to select images or drag and drop
                </span>
                <span className="text-xs text-light-500">
                  Supports: JPG, PNG, GIF, WebP, etc.
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

          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-600">{error}</p>
            </div>
          )}

          <div className="flex gap-2 pt-2">
            <button
              onClick={handleUpload}
              disabled={uploading || selectedFiles.length === 0}
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
                  Upload {selectedFiles.length > 0 ? `${selectedFiles.length} ` : ''}Photo{selectedFiles.length !== 1 ? 's' : ''}
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
