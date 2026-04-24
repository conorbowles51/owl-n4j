import React, { useState } from 'react';
import { X, Pin, CheckCircle2, Download, Sparkles, FileText, ExternalLink } from 'lucide-react';
import DocumentViewer from '../../DocumentViewer';
import { evidenceAPI, workspaceAPI } from '../../../services/api';
import { evidenceUrl, formatSize, categoryColor } from './filesUtils';
import FileTagEditor from './FileTagEditor';
import FileEntityLinker from './FileEntityLinker';

/**
 * Right-pane detail panel for a selected Cellebrite file.
 *
 * Props:
 *   caseId
 *   file                    — full file record (with parent info)
 *   caseTags                — case-wide tag cloud
 *   onClose
 *   onFileChanged(file)     — called when local changes happen so parent can update
 */
export default function FileDetailPanel({ caseId, file, caseTags = [], onClose, onFileChanged }) {
  const [showViewer, setShowViewer] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [processingResult, setProcessingResult] = useState(null);
  const [error, setError] = useState(null);

  if (!file) {
    return (
      <div className="w-96 flex-shrink-0 border-l border-light-200 bg-light-50 flex items-center justify-center text-sm text-light-500 italic p-4 text-center">
        Click a file to see details.
      </div>
    );
  }

  const url = file.id ? evidenceUrl(file.id) : null;
  const cat = file.cellebrite_category || 'Other';
  const color = categoryColor(cat);

  const toggleRelevant = async () => {
    try {
      await evidenceAPI.setRelevance([file.id], !file.is_relevant);
      onFileChanged?.({ ...file, is_relevant: !file.is_relevant });
    } catch (e) {
      setError(e.message || 'Failed to update relevance');
    }
  };

  const pin = async () => {
    try {
      await workspaceAPI.pinItem(caseId, 'evidence', file.id);
      setProcessingResult('Pinned to case');
    } catch (e) {
      setError(e.message || 'Failed to pin');
    }
  };

  const runLLM = async () => {
    setProcessing(true);
    setError(null);
    setProcessingResult(null);
    try {
      const res = await evidenceAPI.process(caseId, [file.id]);
      setProcessingResult(res?.message || 'LLM processing started');
    } catch (e) {
      setError(e.message || 'Failed to start processing');
    } finally {
      setProcessing(false);
    }
  };

  return (
    <div className="w-96 flex-shrink-0 border-l border-light-200 bg-white flex flex-col min-h-0">
      {/* Header */}
      <div
        className="flex items-center gap-2 px-3 py-2 border-b border-light-200"
        style={{ background: color + '15' }}
      >
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-owl-blue-900 truncate">
            {file.original_filename || file.id}
          </div>
          <div className="text-[11px] text-light-600">
            {cat} · {formatSize(file.size)}
          </div>
        </div>
        <button onClick={onClose} className="p-1 text-light-500 hover:text-light-800">
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto">
        {/* Preview */}
        <div className="p-3 border-b border-light-200">
          <FilePreview file={file} onOpenViewer={() => setShowViewer(true)} />
        </div>

        {/* Parent breadcrumb */}
        {file.parent && (
          <div className="px-3 py-2 border-b border-light-200 text-xs">
            <div className="text-[11px] text-light-500 font-medium uppercase tracking-wide mb-1">
              Parent
            </div>
            <div className="flex items-center gap-1 text-light-900">
              <ExternalLink className="w-3 h-3 text-light-500" />
              <span className="font-medium">{file.parent.label}</span>
              {file.parent.source_app && (
                <span className="text-light-500">({file.parent.source_app})</span>
              )}
            </div>
            {file.parent.name && (
              <div className="text-light-600 text-[11px] truncate mt-0.5">
                {file.parent.name}
              </div>
            )}
            {file.parent.timestamp && (
              <div className="text-light-500 text-[10px] mt-0.5">
                {file.parent.timestamp.slice(0, 19)}
              </div>
            )}
          </div>
        )}

        {/* Tags */}
        <div className="px-3 py-2 border-b border-light-200">
          <div className="text-[11px] text-light-500 font-medium uppercase tracking-wide mb-1">
            Tags
          </div>
          <FileTagEditor
            caseId={caseId}
            evidenceId={file.id}
            tags={file.tags || []}
            caseTags={caseTags}
            onChange={(next) => onFileChanged?.({ ...file, tags: next })}
          />
        </div>

        {/* Linked entities */}
        <div className="px-3 py-2 border-b border-light-200">
          <div className="text-[11px] text-light-500 font-medium uppercase tracking-wide mb-1">
            Linked entities
          </div>
          <FileEntityLinker
            caseId={caseId}
            evidenceId={file.id}
            entityIds={file.linked_entity_ids || []}
            onChange={(next) => onFileChanged?.({ ...file, linked_entity_ids: next })}
          />
        </div>

        {/* Metadata */}
        <div className="px-3 py-2 border-b border-light-200 text-[11px]">
          <div className="text-light-500 font-medium uppercase tracking-wide mb-1">Metadata</div>
          <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 text-light-700">
            <dt className="text-light-500">Category</dt>
            <dd>{cat}</dd>
            <dt className="text-light-500">Size</dt>
            <dd>{formatSize(file.size)}</dd>
            <dt className="text-light-500">SHA256</dt>
            <dd className="break-all font-mono text-[10px]">{file.sha256}</dd>
            <dt className="text-light-500">Status</dt>
            <dd>{file.status}</dd>
            {file.cellebrite_file_id && (
              <>
                <dt className="text-light-500">File ID</dt>
                <dd className="break-all font-mono text-[10px]">{file.cellebrite_file_id}</dd>
              </>
            )}
            {file.device_path_segments?.length > 0 && (
              <>
                <dt className="text-light-500">Path</dt>
                <dd className="break-all text-[11px]">{file.device_path_segments.join('/')}</dd>
              </>
            )}
          </dl>
        </div>

        {/* Actions */}
        <div className="px-3 py-2">
          <div className="text-[11px] text-light-500 font-medium uppercase tracking-wide mb-1.5">
            Actions
          </div>
          <div className="grid grid-cols-2 gap-1.5">
            <ActionButton
              onClick={toggleRelevant}
              active={file.is_relevant}
              icon={CheckCircle2}
              label={file.is_relevant ? 'Relevant ✓' : 'Mark relevant'}
            />
            <ActionButton onClick={pin} icon={Pin} label="Pin" />
            <ActionButton
              onClick={runLLM}
              icon={Sparkles}
              label={processing ? 'Running…' : 'LLM summarize'}
              disabled={processing}
            />
            {url && (
              <a
                href={url}
                download={file.original_filename}
                className="flex items-center gap-1 px-2 py-1 text-xs border border-light-300 rounded hover:bg-light-50 text-light-700"
              >
                <Download className="w-3 h-3" /> Download
              </a>
            )}
          </div>
          {processingResult && (
            <div className="mt-2 text-[11px] text-emerald-700">{processingResult}</div>
          )}
          {error && <div className="mt-2 text-[11px] text-red-600">{error}</div>}
        </div>
      </div>

      {showViewer && url && (
        <DocumentViewer
          isOpen
          onClose={() => setShowViewer(false)}
          documentUrl={url}
          documentName={file.original_filename || 'file'}
        />
      )}
    </div>
  );
}

function ActionButton({ onClick, icon: Icon, label, active = false, disabled = false }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`flex items-center gap-1 px-2 py-1 text-xs border rounded ${
        active
          ? 'border-emerald-400 bg-emerald-50 text-emerald-800'
          : 'border-light-300 hover:bg-light-50 text-light-700'
      } disabled:opacity-50`}
    >
      <Icon className="w-3 h-3" />
      {label}
    </button>
  );
}

function FilePreview({ file, onOpenViewer }) {
  const url = file.id ? evidenceUrl(file.id) : null;
  const cat = file.cellebrite_category || 'Other';
  if (!url) return null;

  if (cat === 'Image') {
    return (
      <button
        onClick={onOpenViewer}
        className="w-full border border-light-200 rounded overflow-hidden bg-light-100 flex items-center justify-center"
        style={{ maxHeight: 320 }}
      >
        <img
          src={url}
          alt={file.original_filename}
          className="w-full h-auto object-contain"
          style={{ maxHeight: 320 }}
        />
      </button>
    );
  }
  if (cat === 'Audio') {
    return <audio src={url} controls preload="metadata" className="w-full" />;
  }
  if (cat === 'Video') {
    return <video src={url} controls preload="metadata" className="w-full max-h-[320px] bg-black" />;
  }
  if (cat === 'Text') {
    return (
      <button
        onClick={onOpenViewer}
        className="flex items-center gap-1.5 px-2 py-1.5 border border-light-300 rounded hover:bg-light-50 w-full text-left"
      >
        <FileText className="w-4 h-4 text-light-600" />
        <span className="text-xs text-light-800 truncate">Open text preview</span>
      </button>
    );
  }
  return (
    <div className="text-xs text-light-500 italic">No preview for this file type.</div>
  );
}
