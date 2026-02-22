import React, { useState, useEffect, useCallback } from 'react';
import { FileText, X, Loader2, AlertCircle, Image, Music, Film, File as FileIcon, Sparkles, Grid, ChevronLeft, ChevronRight, Clock, Camera } from 'lucide-react';
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
  const [previewType, setPreviewType] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [activeTab, setActiveTab] = useState('content');
  const [evidenceId, setEvidenceId] = useState(null);
  const [frames, setFrames] = useState(null);
  const [framesLoading, setFramesLoading] = useState(false);
  const [framesError, setFramesError] = useState(null);
  const [selectedFrame, setSelectedFrame] = useState(null);

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
      const videoExts = ['mp4', 'webm', 'mov', 'avi', 'mkv', 'flv', 'wmv'];
      
      let foundEvidenceId = null;
      let fileUrl = null;
      let relativePath = null;
      
      try {
        const fileInfo = await evidenceAPI.findByFilename(fileName, caseId);
        if (fileInfo.found && fileInfo.evidence_id) {
          foundEvidenceId = fileInfo.evidence_id;
          setEvidenceId(foundEvidenceId);
          fileUrl = `/api/evidence/${foundEvidenceId}/file`;
        }
      } catch (err) {
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
          setContent(fileUrl);
        } else if (relativePath && caseId) {
          setError('Audio file not found in evidence records. The file may need to be uploaded first.');
        } else {
          setError('File not found in evidence records. The file may need to be uploaded first.');
        }
      } else if (videoExts.includes(ext)) {
        setPreviewType('video');
        if (fileUrl) {
          setContent(fileUrl);
        } else {
          setError('Video file not found in evidence records. The file may need to be uploaded first.');
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

  const loadFrames = useCallback(async () => {
    if (!evidenceId || framesLoading) return;
    setFramesLoading(true);
    setFramesError(null);
    try {
      const result = await evidenceAPI.getVideoFrames(evidenceId);
      setFrames(result.frames || []);
    } catch (err) {
      setFramesError(err.message || 'Failed to extract frames');
    } finally {
      setFramesLoading(false);
    }
  }, [evidenceId, framesLoading]);

  const ext = fileName.split('.').pop()?.toLowerCase() || '';
  const isImage = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp'].includes(ext);
  const isText = ['txt', 'md', 'json', 'xml', 'csv', 'log', 'rtf', 'sri'].includes(ext);
  const isAudio = ['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a'].includes(ext);
  const isVideo = ['mp4', 'webm', 'mov', 'avi', 'mkv', 'flv', 'wmv'].includes(ext);

  return (
    <div className="border border-light-300 rounded-lg bg-white mt-2">
      <div className="flex items-center justify-between p-2 bg-light-50 border-b border-light-200">
        <div className="flex items-center gap-2">
          {isVideo ? (
            <Film className="w-4 h-4 text-owl-blue-600" />
          ) : isImage ? (
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
            {isVideo ? <Film className="w-3 h-3" /> : <FileText className="w-3 h-3" />}
            {isVideo ? 'Player' : 'Content'}
          </div>
        </button>
        {isVideo && (
          <button
            onClick={() => { setActiveTab('frames'); if (!frames && !framesLoading) loadFrames(); }}
            className={`flex-1 px-3 py-2 text-xs font-medium transition-colors border-b-2 ${
              activeTab === 'frames'
                ? 'border-owl-blue-500 text-owl-blue-700 bg-white'
                : 'border-transparent text-light-600 hover:text-light-800 hover:bg-light-100'
            }`}
          >
            <div className="flex items-center justify-center gap-1.5">
              <Grid className="w-3 h-3" />
              Frames
              {framesLoading && <Loader2 className="w-3 h-3 animate-spin" />}
              {frames && <span className="text-[10px] bg-light-200 px-1 rounded">{frames.length}</span>}
            </div>
          </button>
        )}
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
      
      <div className={`p-3 overflow-auto ${activeTab === 'frames' ? 'max-h-96' : 'max-h-64'}`}>
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
                {previewType === 'video' && typeof content === 'string' ? (
                  <div className="flex flex-col gap-2">
                    <video
                      controls
                      src={content}
                      className="w-full rounded border border-light-200 bg-black"
                      style={{ maxHeight: '320px' }}
                      onError={() => setError('Failed to load video. The format may not be supported by your browser.')}
                      preload="metadata"
                    >
                      Your browser does not support the video element.
                    </video>
                    <p className="text-xs text-light-500 flex items-center gap-1">
                      <Film className="w-3 h-3" />
                      {fileName}
                    </p>
                  </div>
                ) : previewType === 'image' && typeof content === 'string' ? (
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

        {/* Frames Tab (video only) */}
        {activeTab === 'frames' && (
          <>
            {framesLoading && (
              <div className="flex flex-col items-center justify-center py-8 gap-2">
                <Loader2 className="w-5 h-5 animate-spin text-owl-blue-500" />
                <span className="text-xs text-light-600">Extracting video frames...</span>
                <span className="text-[10px] text-light-400">This may take a moment for longer videos</span>
              </div>
            )}

            {framesError && (
              <div className="flex items-start gap-2 text-xs text-light-600">
                <AlertCircle className="w-4 h-4 text-orange-600 flex-shrink-0 mt-0.5" />
                <div>
                  <span>{framesError}</span>
                  <button onClick={loadFrames} className="ml-2 text-owl-blue-600 hover:underline">Retry</button>
                </div>
              </div>
            )}

            {/* Lightbox for selected frame */}
            {selectedFrame && evidenceId && (
              <div className="mb-3 bg-black rounded-lg overflow-hidden border border-light-300">
                <div className="relative">
                  <img
                    src={evidenceAPI.getVideoFrameUrl(evidenceId, selectedFrame.filename)}
                    alt={`Frame at ${selectedFrame.timestamp_str}`}
                    className="w-full h-auto"
                    style={{ maxHeight: '240px', objectFit: 'contain' }}
                  />
                  <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent px-3 py-2 flex items-center justify-between">
                    <div className="flex items-center gap-2 text-white text-xs">
                      <Clock className="w-3 h-3" />
                      <span>{selectedFrame.timestamp_str}</span>
                      <span className="text-white/60">— Frame {selectedFrame.frame_number}</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => {
                          const idx = frames.findIndex(f => f.frame_number === selectedFrame.frame_number);
                          if (idx > 0) setSelectedFrame(frames[idx - 1]);
                        }}
                        disabled={selectedFrame.frame_number === 1}
                        className="p-1 text-white/80 hover:text-white disabled:text-white/30 rounded"
                      >
                        <ChevronLeft className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => {
                          const idx = frames.findIndex(f => f.frame_number === selectedFrame.frame_number);
                          if (idx < frames.length - 1) setSelectedFrame(frames[idx + 1]);
                        }}
                        disabled={!frames || selectedFrame.frame_number === frames.length}
                        className="p-1 text-white/80 hover:text-white disabled:text-white/30 rounded"
                      >
                        <ChevronRight className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => setSelectedFrame(null)}
                        className="p-1 text-white/80 hover:text-white rounded ml-1"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Frame grid */}
            {frames && frames.length > 0 && !framesLoading && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-light-600 flex items-center gap-1">
                    <Camera className="w-3 h-3" />
                    {frames.length} extracted frame{frames.length !== 1 ? 's' : ''}
                  </span>
                  {selectedFrame && (
                    <button onClick={() => setSelectedFrame(null)} className="text-[10px] text-owl-blue-600 hover:underline">
                      Show all
                    </button>
                  )}
                </div>
                <div className="grid grid-cols-4 gap-1.5">
                  {frames.map(frame => (
                    <button
                      key={frame.frame_number}
                      onClick={() => setSelectedFrame(frame)}
                      className={`group relative rounded overflow-hidden border transition-all ${
                        selectedFrame?.frame_number === frame.frame_number
                          ? 'border-owl-blue-500 ring-1 ring-owl-blue-300'
                          : 'border-light-200 hover:border-owl-blue-300'
                      }`}
                    >
                      <img
                        src={evidenceAPI.getVideoFrameUrl(evidenceId, frame.filename)}
                        alt={`Frame ${frame.frame_number}`}
                        className="w-full aspect-video object-cover"
                        loading="lazy"
                      />
                      <div className="absolute bottom-0 left-0 right-0 bg-black/60 px-1 py-0.5">
                        <span className="text-[9px] text-white font-mono">{frame.timestamp_str}</span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {frames && frames.length === 0 && !framesLoading && (
              <div className="text-xs text-light-500 italic text-center py-4">
                No frames could be extracted. FFmpeg may not be installed on the server.
              </div>
            )}

            {!frames && !framesLoading && !framesError && (
              <div className="flex flex-col items-center gap-3 py-6">
                <Grid className="w-8 h-8 text-light-300" />
                <p className="text-xs text-light-600">Extract key frames from this video</p>
                <button
                  onClick={loadFrames}
                  className="text-xs px-3 py-1.5 bg-owl-blue-500 text-white rounded hover:bg-owl-blue-600 transition-colors flex items-center gap-1.5"
                >
                  <Camera className="w-3 h-3" />
                  Extract Frames
                </button>
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
