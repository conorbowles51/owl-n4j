import React, { useState, useEffect } from 'react';
import { FileText, X, Loader2, AlertCircle, Image, Music, Film, File as FileIcon, Play, Pause, Sparkles } from 'lucide-react';
import { evidenceAPI, filesystemAPI } from '../services/api';

/**
 * FilePreview Component
 * 
 * Displays a preview of file contents when available.
 * Supports text files, images, and attempts to show content for other types.
 */
export default function FilePreview({ 
  caseId, 
  filePath, 
  fileName,
  fileType,
  onClose 
}) {
  const [content, setContent] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [previewType, setPreviewType] = useState(null); // 'text', 'image', 'binary'
  const [summary, setSummary] = useState(null);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [activeTab, setActiveTab] = useState('content'); // 'content' or 'summary'

  useEffect(() => {
    if (filePath && fileName && caseId) {
      loadFilePreview();
      loadSummary();
    }
  }, [caseId, filePath, fileName]);

  // Update active tab when summary is loaded
  useEffect(() => {
    if (summary) {
      setActiveTab('summary');
    } else if (!loadingSummary) {
      // Only switch to content if summary loading is complete and no summary exists
      setActiveTab('content');
    }
  }, [summary, loadingSummary]);

  const loadSummary = async () => {
    if (!fileName || !caseId) return;
    
    setLoadingSummary(true);
    try {
      const result = await evidenceAPI.getSummary(fileName, caseId);
      if (result.has_summary && result.summary) {
        setSummary(result.summary);
      } else {
        setSummary(null);
      }
    } catch (err) {
      // Summary is optional, don't show error if it fails
      console.warn('Failed to load document summary:', err);
      setSummary(null);
    } finally {
      setLoadingSummary(false);
    }
  };

  const loadFilePreview = async () => {
    setLoading(true);
    setError(null);
    setContent(null);

    try {
      // Determine file type from extension
      const ext = fileName.split('.').pop()?.toLowerCase() || '';
      const textExts = ['txt', 'md', 'json', 'xml', 'csv', 'log', 'rtf', 'sri'];
      const imageExts = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp'];
      const audioExts = ['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a', 'WAV', 'MP3', 'M4A', 'FLAC'];
      
      // Try to get evidence_id - first try findByFilename, but handle errors gracefully
      let evidenceId = null;
      let fileUrl = null;
      let relativePath = null;
      
      try {
        const fileInfo = await evidenceAPI.findByFilename(fileName, caseId);
        if (fileInfo.found && fileInfo.evidence_id) {
          evidenceId = fileInfo.evidence_id;
          fileUrl = `/api/evidence/${evidenceId}/file`;
        }
      } catch (err) {
        // findByFilename failed - this is OK, we'll try alternative methods
        console.warn('findByFilename failed, trying alternative methods:', err);
      }
      
      // If we have filePath (stored_path), try to extract relative path for filesystem API
      if (!fileUrl && filePath && caseId) {
        try {
          // stored_path format: "ingestion/data/{case_id}/path/to/file" or "{case_id}/path/to/file"
          let normalizedPath = filePath.replace(/\\/g, '/');
          // Remove "ingestion/data/" prefix if present
          normalizedPath = normalizedPath.replace(/^ingestion\/data\//, '');
          // Remove case_id prefix if present
          if (normalizedPath.startsWith(`${caseId}/`)) {
            relativePath = normalizedPath.substring(caseId.length + 1);
          } else if (!normalizedPath.startsWith('/')) {
            relativePath = normalizedPath;
          }
        } catch (err) {
          console.warn('Failed to extract relative path from filePath:', err);
        }
      }
      
      if (textExts.includes(ext)) {
        // Try to fetch as text
        setPreviewType('text');
        
        // Prioritize filesystem API if we have a filePath (more reliable for folder files)
        if (relativePath && caseId) {
          try {
            const result = await filesystemAPI.readFile(caseId, relativePath);
            const text = result.content || result;
            const preview = typeof text === 'string' && text.length > 50000 ? text.substring(0, 50000) + '\n\n... (truncated)' : text;
            setContent(preview);
          } catch (fsErr) {
            // If filesystem API fails, try evidence API as fallback
            if (fileUrl && evidenceId) {
              try {
                const token = localStorage.getItem('authToken');
                const headers = {};
                if (token) {
                  headers['Authorization'] = `Bearer ${token}`;
                }
                
                const response = await fetch(fileUrl, {
                  headers,
                  credentials: 'include', // Include cookies for session-based auth
                });
                
                if (response.ok) {
                  const text = await response.text();
                  const preview = text.length > 50000 ? text.substring(0, 50000) + '\n\n... (truncated)' : text;
                  setContent(preview);
                } else if (response.status === 401) {
                  throw new Error('Authentication failed. Please log in again.');
                } else {
                  throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
              } catch (err) {
                setError(`Could not preview file: ${fsErr.message || err.message}`);
              }
            } else {
              setError(`Could not preview file: ${fsErr.message}`);
            }
          }
        } else if (fileUrl && evidenceId) {
          // Try evidence API if no filePath available
          try {
            const token = localStorage.getItem('authToken');
            const headers = {};
            if (token) {
              headers['Authorization'] = `Bearer ${token}`;
            }
            
            const response = await fetch(fileUrl, {
              headers,
              credentials: 'include', // Include cookies for session-based auth
            });
            
            if (response.ok) {
              const text = await response.text();
              // Limit preview to first 50KB for performance
              const preview = text.length > 50000 ? text.substring(0, 50000) + '\n\n... (truncated)' : text;
              setContent(preview);
            } else if (response.status === 401) {
              throw new Error('Authentication failed. Please log in again.');
            } else {
              throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
          } catch (err) {
            setError(`Could not preview file: ${err.message}`);
          }
        } else {
          setError('File not found in evidence records. The file may need to be uploaded first.');
        }
      } else if (imageExts.includes(ext)) {
        setPreviewType('image');
        if (fileUrl) {
          // For images, we can use the URL directly in img src
          // The browser will handle authentication via cookies or we need to add token to URL
          const token = localStorage.getItem('authToken');
          const urlWithAuth = token ? `${fileUrl}?token=${encodeURIComponent(token)}` : fileUrl;
          setContent(fileUrl); // Store URL for image src (browser handles auth via cookies)
        } else if (relativePath && caseId) {
          // Try to construct filesystem URL for images
          // Note: filesystem API doesn't support binary files, so we'll need evidence API
          setError('Image file not found in evidence records. The file may need to be uploaded first.');
        } else {
          setError('File not found in evidence records. The file may need to be uploaded first.');
        }
      } else if (audioExts.includes(ext)) {
        setPreviewType('audio');
        if (fileUrl) {
          setContent(fileUrl); // Store URL for audio src (browser handles auth via cookies)
        } else if (relativePath && caseId) {
          // Note: filesystem API doesn't support binary files, so we'll need evidence API
          setError('Audio file not found in evidence records. The file may need to be uploaded first.');
        } else {
          setError('File not found in evidence records. The file may need to be uploaded first.');
        }
      } else {
        setPreviewType('binary');
        setError('File type not previewable (binary or unsupported format)');
      }
    } catch (err) {
      setError(`Failed to load preview: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  if (!fileName) return null;

  const ext = fileName.split('.').pop()?.toLowerCase() || '';
  const isImage = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp'].includes(ext);
  const isText = ['txt', 'md', 'json', 'xml', 'csv', 'log', 'rtf', 'sri'].includes(ext);
  const isAudio = ['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a'].includes(ext);

  return (
    <div className="border border-light-300 rounded-lg bg-white mt-2">
      <div className="flex items-center justify-between p-2 bg-light-50 border-b border-light-200">
        <div className="flex items-center gap-2">
          {isImage ? (
            <Image className="w-4 h-4 text-owl-blue-600" />
          ) : isAudio ? (
            <Music className="w-4 h-4 text-owl-blue-600" />
          ) : isText ? (
            <FileText className="w-4 h-4 text-owl-blue-600" />
          ) : (
            <FileIcon className="w-4 h-4 text-light-600" />
          )}
          <span className="text-xs font-medium text-light-700">File Preview: {fileName}</span>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="p-1 hover:bg-light-200 rounded transition-colors"
            title="Close preview"
          >
            <X className="w-3 h-3 text-light-600" />
          </button>
        )}
      </div>
      
      {/* Tabs */}
      <div className="flex border-b border-light-200 bg-light-50">
        <button
          onClick={() => setActiveTab('content')}
          className={`flex-1 px-3 py-2 text-xs font-medium transition-colors border-b-2 ${
            activeTab === 'content'
              ? 'border-owl-blue-500 text-owl-blue-700 bg-white'
              : 'border-transparent text-light-600 hover:text-light-800 hover:bg-light-100'
          }`}
        >
          <div className="flex items-center justify-center gap-1.5">
            <FileText className="w-3 h-3" />
            Content
          </div>
        </button>
        <button
          onClick={() => setActiveTab('summary')}
          className={`flex-1 px-3 py-2 text-xs font-medium transition-colors border-b-2 ${
            activeTab === 'summary'
              ? 'border-owl-blue-500 text-owl-blue-700 bg-white'
              : 'border-transparent text-light-600 hover:text-light-800 hover:bg-light-100'
          }`}
          disabled={!summary && !loadingSummary}
        >
          <div className="flex items-center justify-center gap-1.5">
            <Sparkles className="w-3 h-3" />
            AI Summary
            {loadingSummary && <Loader2 className="w-3 h-3 animate-spin" />}
          </div>
        </button>
      </div>
      
      <div className="p-3 max-h-64 overflow-auto">
        {/* Content Tab */}
        {activeTab === 'content' && (
          <>
            {loading && (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="w-4 h-4 animate-spin text-owl-blue-500" />
                <span className="ml-2 text-xs text-light-600">Loading preview...</span>
              </div>
            )}
            
            {error && (
              <div className="flex items-start gap-2 text-xs text-light-600">
                <AlertCircle className="w-4 h-4 text-orange-600 flex-shrink-0 mt-0.5" />
                <span>{error}</span>
              </div>
            )}
            
            {content && !error && (
              <>
                {previewType === 'image' && typeof content === 'string' ? (
                  <img 
                    src={content} 
                    alt={fileName}
                    className="max-w-full h-auto rounded border border-light-200"
                    onError={() => setError('Failed to load image')}
                  />
                ) : previewType === 'audio' && typeof content === 'string' ? (
                  <div className="flex flex-col items-center gap-2 p-3 bg-light-50 rounded border border-light-200">
                    <audio 
                      controls 
                      src={content}
                      className="w-full max-w-md"
                      onError={() => setError('Failed to load audio file')}
                    >
                      Your browser does not support the audio element.
                    </audio>
                    <p className="text-xs text-light-600">Audio file: {fileName}</p>
                  </div>
                ) : previewType === 'text' && typeof content === 'string' ? (
                  <pre className="text-xs text-light-800 bg-light-50 p-2 rounded border border-light-200 overflow-x-auto whitespace-pre-wrap font-mono">
                    {content}
                  </pre>
                ) : null}
              </>
            )}
            
            {!loading && !content && !error && (
              <div className="text-xs text-light-600 italic">
                Preview not available for this file type
              </div>
            )}
          </>
        )}
        
        {/* Summary Tab */}
        {activeTab === 'summary' && (
          <>
            {loadingSummary && (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="w-4 h-4 animate-spin text-owl-blue-500" />
                <span className="ml-2 text-xs text-light-600">Loading summary...</span>
              </div>
            )}
            
            {summary && !loadingSummary && (
              <div className="text-xs text-light-800 bg-owl-blue-50 p-3 rounded border border-owl-blue-200 leading-relaxed whitespace-pre-wrap">
                {summary}
              </div>
            )}
            
            {!summary && !loadingSummary && (
              <div className="text-xs text-light-600 italic">
                No AI summary available for this file. The file may not have been processed yet.
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
