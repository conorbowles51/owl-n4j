import React, { useState, useEffect, useCallback } from 'react';
import {
  Folder, FolderOpen, ChevronRight, ChevronUp, Loader2,
  HardDrive, File, X, Check, AlertCircle,
} from 'lucide-react';
import { triageAPI } from '../../services/api';

/**
 * Server-side directory browser for selecting a source path.
 * Fetches directory listings from the backend and lets users
 * navigate into folders, then select one.
 */
export default function DirectoryBrowser({ value, onChange, onBrowseToggle }) {
  const [isOpen, setIsOpen] = useState(false);
  const [currentPath, setCurrentPath] = useState('/');
  const [parentPath, setParentPath] = useState(null);
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const loadDirectory = useCallback(async (path) => {
    setLoading(true);
    setError('');
    try {
      const data = await triageAPI.browseDirectory(path);
      setCurrentPath(data.current_path);
      setParentPath(data.parent_path);
      setEntries(data.entries || []);
    } catch (err) {
      setError(err.message || 'Failed to browse directory');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      // If a value is already set, start browsing from its parent
      const startPath = value ? value : '/';
      loadDirectory(startPath);
    }
  }, [isOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleOpen = () => {
    setIsOpen(true);
    if (onBrowseToggle) onBrowseToggle(true);
  };

  const handleClose = () => {
    setIsOpen(false);
    if (onBrowseToggle) onBrowseToggle(false);
  };

  const handleNavigate = (path) => {
    loadDirectory(path);
  };

  const handleSelect = () => {
    onChange(currentPath);
    handleClose();
  };

  const directories = entries.filter((e) => e.is_dir);
  const files = entries.filter((e) => !e.is_dir);

  // Breadcrumb segments from current path
  const pathSegments = currentPath === '/'
    ? ['/']
    : ['/', ...currentPath.split('/').filter(Boolean)];

  return (
    <div>
      {/* Selected path display + browse button */}
      <div className="flex items-center gap-2">
        <div
          onClick={handleOpen}
          className={`flex-1 flex items-center gap-2 px-3 py-2 border rounded-lg cursor-pointer transition-colors ${
            value
              ? 'border-light-300 bg-white hover:border-owl-blue-400'
              : 'border-dashed border-light-300 bg-light-50 hover:border-owl-blue-400 hover:bg-white'
          }`}
        >
          {value ? (
            <>
              <Folder className="w-4 h-4 text-owl-blue-500 flex-shrink-0" />
              <span className="text-sm font-mono text-light-800 truncate">{value}</span>
            </>
          ) : (
            <>
              <FolderOpen className="w-4 h-4 text-light-400 flex-shrink-0" />
              <span className="text-sm text-light-400">Click to select a directory...</span>
            </>
          )}
        </div>
        {value && (
          <button
            type="button"
            onClick={() => onChange('')}
            className="p-1.5 text-light-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
            title="Clear selection"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Browser modal */}
      {isOpen && (
        <>
          <div className="fixed inset-0 bg-black/30 z-[60]" onClick={handleClose} />
          <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-2xl bg-white rounded-xl shadow-2xl z-[61] flex flex-col max-h-[80vh]">
            {/* Header */}
            <div className="px-5 py-4 border-b border-light-200 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <HardDrive className="w-5 h-5 text-owl-blue-600" />
                <h3 className="text-base font-semibold text-owl-blue-900">Select Directory</h3>
              </div>
              <button onClick={handleClose} className="p-1 hover:bg-light-100 rounded">
                <X className="w-4 h-4 text-light-500" />
              </button>
            </div>

            {/* Breadcrumb */}
            <div className="px-5 py-2.5 border-b border-light-100 bg-light-50 flex items-center gap-1 overflow-x-auto text-xs">
              {pathSegments.map((seg, i) => {
                const fullPath = i === 0
                  ? '/'
                  : '/' + pathSegments.slice(1, i + 1).join('/');
                const isLast = i === pathSegments.length - 1;
                return (
                  <React.Fragment key={i}>
                    {i > 0 && <ChevronRight className="w-3 h-3 text-light-400 flex-shrink-0" />}
                    <button
                      onClick={() => !isLast && handleNavigate(fullPath)}
                      className={`px-1.5 py-0.5 rounded whitespace-nowrap ${
                        isLast
                          ? 'font-semibold text-owl-blue-700 bg-owl-blue-50'
                          : 'text-light-600 hover:text-owl-blue-600 hover:bg-owl-blue-50'
                      }`}
                    >
                      {seg === '/' ? 'Root' : seg}
                    </button>
                  </React.Fragment>
                );
              })}
            </div>

            {/* Current path display */}
            <div className="px-5 py-2 border-b border-light-100 flex items-center gap-2">
              <span className="text-xs text-light-500">Path:</span>
              <span className="text-xs font-mono text-light-700 flex-1 truncate">{currentPath}</span>
            </div>

            {/* Directory listing */}
            <div className="flex-1 overflow-y-auto min-h-[300px] max-h-[400px]">
              {loading ? (
                <div className="flex items-center justify-center py-16">
                  <Loader2 className="w-6 h-6 animate-spin text-owl-blue-500" />
                </div>
              ) : error ? (
                <div className="flex flex-col items-center justify-center py-16 text-red-500">
                  <AlertCircle className="w-8 h-8 mb-2" />
                  <p className="text-sm">{error}</p>
                  <button
                    onClick={() => loadDirectory(parentPath || '/')}
                    className="mt-3 text-xs text-owl-blue-600 hover:underline"
                  >
                    Go back
                  </button>
                </div>
              ) : (
                <div className="divide-y divide-light-100">
                  {/* Go up */}
                  {parentPath && (
                    <button
                      onClick={() => handleNavigate(parentPath)}
                      className="w-full flex items-center gap-3 px-5 py-2.5 hover:bg-light-50 transition-colors text-left"
                    >
                      <ChevronUp className="w-4 h-4 text-light-400" />
                      <span className="text-sm text-light-500">..</span>
                    </button>
                  )}

                  {/* Directories */}
                  {directories.map((entry) => (
                    <button
                      key={entry.path}
                      onClick={() => handleNavigate(entry.path)}
                      className="w-full flex items-center gap-3 px-5 py-2.5 hover:bg-owl-blue-50 transition-colors text-left group"
                    >
                      <Folder className="w-4 h-4 text-amber-500 flex-shrink-0" />
                      <span className="text-sm text-light-800 group-hover:text-owl-blue-700 truncate">
                        {entry.name}
                      </span>
                      <ChevronRight className="w-3.5 h-3.5 text-light-300 ml-auto flex-shrink-0 group-hover:text-owl-blue-400" />
                    </button>
                  ))}

                  {/* Files (dimmed, not selectable) */}
                  {files.slice(0, 20).map((entry) => (
                    <div
                      key={entry.path}
                      className="flex items-center gap-3 px-5 py-2 opacity-40"
                    >
                      <File className="w-4 h-4 text-light-400 flex-shrink-0" />
                      <span className="text-xs text-light-500 truncate">{entry.name}</span>
                    </div>
                  ))}
                  {files.length > 20 && (
                    <div className="px-5 py-2 text-xs text-light-400 text-center">
                      +{files.length - 20} more files
                    </div>
                  )}

                  {directories.length === 0 && files.length === 0 && (
                    <div className="flex items-center justify-center py-12 text-light-400 text-sm">
                      Empty directory
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Footer with select button */}
            <div className="px-5 py-3.5 border-t border-light-200 bg-light-50 flex items-center justify-between gap-3 rounded-b-xl">
              <div className="flex-1 min-w-0">
                <p className="text-xs text-light-500 truncate">
                  Select this directory: <span className="font-mono text-light-700">{currentPath}</span>
                </p>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <button
                  onClick={handleClose}
                  className="px-3 py-1.5 text-sm text-light-600 hover:bg-light-200 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSelect}
                  className="flex items-center gap-1.5 px-4 py-1.5 text-sm bg-owl-blue-600 text-white rounded-lg hover:bg-owl-blue-700 transition-colors"
                >
                  <Check className="w-3.5 h-3.5" />
                  Select
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
