import React, { useState, useEffect, useRef } from 'react';
import ReactDOM from 'react-dom';
import { X, ExternalLink, FileText, ChevronLeft, ChevronRight, Loader2, Image as ImageIcon, Film, Music, File } from 'lucide-react';

const IMAGE_EXTS = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.tiff', '.tif'];
const AUDIO_EXTS = ['.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a', '.wma'];
const VIDEO_EXTS = ['.mp4', '.webm', '.mov', '.avi', '.mkv', '.flv', '.wmv'];
const PDF_EXTS = ['.pdf'];
const TEXT_EXTS = ['.txt', '.md', '.json', '.xml', '.csv', '.log', '.rtf'];

function getFileType(filename) {
  if (!filename) return 'unknown';
  const ext = ('.' + filename.split('.').pop()).toLowerCase();
  if (PDF_EXTS.includes(ext)) return 'pdf';
  if (IMAGE_EXTS.includes(ext)) return 'image';
  if (AUDIO_EXTS.includes(ext)) return 'audio';
  if (VIDEO_EXTS.includes(ext)) return 'video';
  if (TEXT_EXTS.includes(ext)) return 'text';
  return 'unknown';
}

function getFileIcon(type) {
  switch (type) {
    case 'image': return ImageIcon;
    case 'audio': return Music;
    case 'video': return Film;
    default: return FileText;
  }
}

export default function DocumentViewer({
  isOpen,
  onClose,
  documentUrl,
  documentName,
  initialPage = 1,
  highlightText = null,
}) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [currentPage, setCurrentPage] = useState(initialPage);
  const [textContent, setTextContent] = useState(null);
  const iframeRef = useRef(null);

  const fileType = getFileType(documentName);
  const IconComponent = getFileIcon(fileType);

  useEffect(() => {
    if (isOpen) {
      setLoading(true);
      setError(null);
      setCurrentPage(initialPage);
      setTextContent(null);

      if (documentUrl && fileType === 'text') {
        fetch(documentUrl)
          .then(res => {
            if (!res.ok) throw new Error('Failed to load');
            return res.text();
          })
          .then(text => {
            setTextContent(text);
            setLoading(false);
          })
          .catch(() => {
            setError('Failed to load text document');
            setLoading(false);
          });
      } else if (documentUrl && (fileType === 'image' || fileType === 'audio' || fileType === 'video')) {
        setLoading(false);
      }
    }
  }, [isOpen, documentUrl, initialPage, fileType]);

  useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === 'Escape' && isOpen) onClose();
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const pdfUrlWithPage = documentUrl && fileType === 'pdf'
    ? `${documentUrl}#page=${currentPage}`
    : null;

  const handleIframeLoad = () => setLoading(false);
  const handleIframeError = () => { setLoading(false); setError('Failed to load document'); };

  const handleOpenInNewTab = () => {
    if (documentUrl) window.open(fileType === 'pdf' ? pdfUrlWithPage : documentUrl, '_blank');
  };

  const isPdf = fileType === 'pdf';

  const renderContent = () => {
    if (!documentUrl) {
      return (
        <div className="absolute inset-0 flex items-center justify-center bg-light-50">
          <div className="flex flex-col items-center gap-3 text-center p-6">
            <div className="p-3 bg-light-200 rounded-full">
              <FileText className="w-8 h-8 text-light-500" />
            </div>
            <p className="text-lg font-medium text-light-800">No document selected</p>
            <p className="text-sm text-light-600">
              Click on a citation link to view the source document.
            </p>
          </div>
        </div>
      );
    }

    switch (fileType) {
      case 'image':
        return (
          <div className="absolute inset-0 flex items-center justify-center bg-light-100 p-4 overflow-auto">
            <img
              src={documentUrl}
              alt={documentName}
              className="max-w-full max-h-full object-contain rounded shadow-lg"
              onLoad={() => setLoading(false)}
              onError={() => { setLoading(false); setError('Failed to load image'); }}
            />
          </div>
        );

      case 'audio':
        return (
          <div className="absolute inset-0 flex items-center justify-center bg-light-100">
            <div className="flex flex-col items-center gap-4 p-8">
              <div className="p-4 bg-owl-blue-100 rounded-full">
                <Music className="w-12 h-12 text-owl-blue-600" />
              </div>
              <p className="text-sm font-medium text-owl-blue-900">{documentName}</p>
              <audio
                controls
                src={documentUrl}
                className="w-full max-w-md"
                onCanPlay={() => setLoading(false)}
                onError={() => { setLoading(false); setError('Failed to load audio'); }}
                preload="metadata"
              >
                Your browser does not support the audio element.
              </audio>
            </div>
          </div>
        );

      case 'video':
        return (
          <div className="absolute inset-0 flex items-center justify-center bg-black p-4">
            <video
              controls
              src={documentUrl}
              className="max-w-full max-h-full rounded"
              onCanPlay={() => setLoading(false)}
              onError={() => { setLoading(false); setError('Failed to load video'); }}
              preload="metadata"
            >
              Your browser does not support the video element.
            </video>
          </div>
        );

      case 'text':
        return (
          <div className="absolute inset-0 overflow-auto bg-white p-6">
            {textContent !== null ? (
              <pre className="text-sm text-light-800 whitespace-pre-wrap font-mono leading-relaxed">
                {textContent}
              </pre>
            ) : null}
          </div>
        );

      case 'pdf':
        return (
          <iframe
            ref={iframeRef}
            src={pdfUrlWithPage}
            className="w-full h-full border-0"
            onLoad={handleIframeLoad}
            onError={handleIframeError}
            title={documentName || 'Document'}
          />
        );

      default:
        return (
          <iframe
            ref={iframeRef}
            src={documentUrl}
            className="w-full h-full border-0"
            onLoad={handleIframeLoad}
            onError={handleIframeError}
            title={documentName || 'Document'}
          />
        );
    }
  };

  return ReactDOM.createPortal(
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[9999]">
      <div className="bg-white rounded-lg w-full max-w-5xl h-[90vh] flex flex-col border border-light-200 shadow-2xl mx-4">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-light-200 bg-light-50 rounded-t-lg">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-owl-blue-100 rounded-lg">
              <IconComponent className="w-5 h-5 text-owl-blue-700" />
            </div>
            <div>
              <h2 className="font-semibold text-owl-blue-900 text-lg">
                {documentName || 'Document Viewer'}
              </h2>
              <p className="text-xs text-light-600">
                {fileType === 'image' ? 'Image' : fileType === 'audio' ? 'Audio' : fileType === 'video' ? 'Video' : fileType === 'text' ? 'Text' : 'Document'}
                {isPdf && initialPage > 1 && ` • Opened at page ${initialPage}`}
                {highlightText && ` • Searching for: "${highlightText}"`}
              </p>
            </div>
          </div>
          
          <div className="flex items-center gap-2">
            {isPdf && (
              <div className="flex items-center gap-1 bg-white border border-light-200 rounded-lg px-2 py-1">
                <button
                  onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                  className="p-1 hover:bg-light-100 rounded transition-colors"
                  title="Previous page"
                >
                  <ChevronLeft className="w-4 h-4 text-light-600" />
                </button>
                <span className="text-sm text-light-700 min-w-[60px] text-center">
                  Page {currentPage}
                </span>
                <button
                  onClick={() => setCurrentPage(currentPage + 1)}
                  className="p-1 hover:bg-light-100 rounded transition-colors"
                  title="Next page"
                >
                  <ChevronRight className="w-4 h-4 text-light-600" />
                </button>
              </div>
            )}

            <button
              onClick={handleOpenInNewTab}
              className="p-2 hover:bg-light-100 rounded-lg transition-colors"
              title="Open in new tab"
            >
              <ExternalLink className="w-5 h-5 text-light-600" />
            </button>

            <button
              onClick={onClose}
              className="p-2 hover:bg-light-100 rounded-lg transition-colors"
              title="Close"
            >
              <X className="w-5 h-5 text-light-600" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 relative bg-light-100 overflow-hidden">
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center bg-light-50 z-10">
              <div className="flex flex-col items-center gap-3">
                <Loader2 className="w-8 h-8 text-owl-blue-500 animate-spin" />
                <p className="text-sm text-light-600">Loading {fileType}...</p>
              </div>
            </div>
          )}

          {error && (
            <div className="absolute inset-0 flex items-center justify-center bg-light-50 z-10">
              <div className="flex flex-col items-center gap-3 text-center p-6">
                <div className="p-3 bg-red-100 rounded-full">
                  <FileText className="w-8 h-8 text-red-500" />
                </div>
                <p className="text-lg font-medium text-light-800">Failed to load {fileType}</p>
                <p className="text-sm text-light-600 max-w-md">
                  The file could not be loaded. It may not exist or the format may not be supported.
                </p>
                <button
                  onClick={handleOpenInNewTab}
                  className="mt-2 flex items-center gap-2 px-4 py-2 bg-owl-blue-500 hover:bg-owl-blue-600 text-white rounded-lg transition-colors"
                >
                  <ExternalLink className="w-4 h-4" />
                  Try opening in new tab
                </button>
              </div>
            </div>
          )}

          {renderContent()}
        </div>

        {/* Footer */}
        <div className="px-4 py-2 border-t border-light-200 bg-light-50 rounded-b-lg">
          <div className="flex items-center justify-between text-xs text-light-600">
            <span>
              {isPdf ? 'Use scroll or browser controls to navigate within the document' : `Viewing source ${fileType} file`}
            </span>
            <span>
              Press <kbd className="px-1.5 py-0.5 bg-light-200 rounded text-light-700">Esc</kbd> to close
            </span>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
