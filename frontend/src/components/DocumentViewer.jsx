import React, { useState, useEffect, useRef } from 'react';
import ReactDOM from 'react-dom';
import { X, ExternalLink, FileText, ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';

/**
 * DocumentViewer Component
 * 
 * Modal for viewing source documents (PDFs) with page navigation.
 * Supports jumping to specific pages when viewing citations.
 */
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
  const iframeRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      setLoading(true);
      setError(null);
      setCurrentPage(initialPage);
    }
  }, [isOpen, documentUrl, initialPage]);

  useEffect(() => {
    // Handle escape key to close modal
    const handleEscape = (e) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  // Build the PDF URL with page parameter
  // Most PDF viewers support #page=N fragment
  const pdfUrlWithPage = documentUrl 
    ? `${documentUrl}#page=${currentPage}`
    : null;

  const handleIframeLoad = () => {
    setLoading(false);
  };

  const handleIframeError = () => {
    setLoading(false);
    setError('Failed to load document');
  };

  const handleOpenInNewTab = () => {
    if (documentUrl) {
      window.open(pdfUrlWithPage, '_blank');
    }
  };

  return ReactDOM.createPortal(
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[9999]">
      <div className="bg-white rounded-lg w-full max-w-5xl h-[90vh] flex flex-col border border-light-200 shadow-2xl mx-4">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-light-200 bg-light-50 rounded-t-lg">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-owl-blue-100 rounded-lg">
              <FileText className="w-5 h-5 text-owl-blue-700" />
            </div>
            <div>
              <h2 className="font-semibold text-owl-blue-900 text-lg">
                {documentName || 'Document Viewer'}
              </h2>
              {initialPage > 1 && (
                <p className="text-xs text-light-600">
                  Opened at page {initialPage}
                  {highlightText && ` • Searching for: "${highlightText}"`}
                </p>
              )}
            </div>
          </div>
          
          <div className="flex items-center gap-2">
            {/* Page navigation */}
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

            {/* Open in new tab */}
            <button
              onClick={handleOpenInNewTab}
              className="p-2 hover:bg-light-100 rounded-lg transition-colors"
              title="Open in new tab"
            >
              <ExternalLink className="w-5 h-5 text-light-600" />
            </button>

            {/* Close button */}
            <button
              onClick={onClose}
              className="p-2 hover:bg-light-100 rounded-lg transition-colors"
              title="Close"
            >
              <X className="w-5 h-5 text-light-600" />
            </button>
          </div>
        </div>

        {/* Document content */}
        <div className="flex-1 relative bg-light-100 overflow-hidden">
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center bg-light-50">
              <div className="flex flex-col items-center gap-3">
                <Loader2 className="w-8 h-8 text-owl-blue-500 animate-spin" />
                <p className="text-sm text-light-600">Loading document...</p>
              </div>
            </div>
          )}

          {error && (
            <div className="absolute inset-0 flex items-center justify-center bg-light-50">
              <div className="flex flex-col items-center gap-3 text-center p-6">
                <div className="p-3 bg-red-100 rounded-full">
                  <FileText className="w-8 h-8 text-red-500" />
                </div>
                <p className="text-lg font-medium text-light-800">Failed to load document</p>
                <p className="text-sm text-light-600 max-w-md">
                  The document could not be loaded. It may not exist or you may not have permission to view it.
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

          {documentUrl && (
            <iframe
              ref={iframeRef}
              src={pdfUrlWithPage}
              className="w-full h-full border-0"
              onLoad={handleIframeLoad}
              onError={handleIframeError}
              title={documentName || 'Document'}
            />
          )}

          {!documentUrl && !error && (
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
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-2 border-t border-light-200 bg-light-50 rounded-b-lg">
          <div className="flex items-center justify-between text-xs text-light-600">
            <span>
              Use scroll or browser controls to navigate within the document
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

