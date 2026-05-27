import React, { useState } from 'react';
import { FileText, AlertCircle, Film } from 'lucide-react';
import { attachmentKind, attachmentUrl, videoThumbUrl } from './commsUtils';
import DocumentViewer from '../../DocumentViewer';
import MediaAnalysisPanel from '../files/MediaAnalysisPanel';

/**
 * Render a single attachment. Images render inline thumbnails that open the
 * DocumentViewer modal on click. Audio renders an inline <audio>. Video shows
 * a poster/thumbnail + click-to-open. Documents show a file chip.
 *
 * Media attachments (image / audio / video) that resolved to an evidence row
 * also get a "send to AI processing" action (transcription for audio/video,
 * image recognition for images) via the shared MediaAnalysisPanel. The panel
 * is lazy (no cache fetch until the investigator clicks) so a thread with
 * hundreds of media messages doesn't fan out a request per attachment.
 */
export default function CommsAttachment({ attachment }) {
  const [viewerOpen, setViewerOpen] = useState(false);

  if (!attachment) return null;
  if (attachment.missing) {
    return (
      <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-amber-50 border border-amber-200 text-amber-700 text-xs">
        <AlertCircle className="w-3 h-3" />
        <span>Attachment unavailable</span>
      </div>
    );
  }

  const kind = attachmentKind(attachment);
  const url = attachmentUrl(attachment);
  const name = attachment.original_filename || 'attachment';

  if (!url) return null;

  // AI action that applies to this attachment: image → recognition,
  // audio/video → transcription. Needs a resolved evidence_id to process.
  const aiKind = kind === 'image' ? 'image'
    : (kind === 'audio' || kind === 'video') ? 'transcription'
    : null;
  const evidenceId = attachment.evidence_id;

  let media;
  if (kind === 'image') {
    media = (
      <button
        onClick={() => setViewerOpen(true)}
        className="block overflow-hidden rounded border border-light-200 hover:border-owl-blue-400 transition-colors"
      >
        <img src={url} alt={name} className="max-w-[240px] max-h-[240px] object-cover" loading="lazy" />
      </button>
    );
  } else if (kind === 'audio') {
    media = <audio controls preload="metadata" src={url} className="max-w-[300px]" />;
  } else if (kind === 'video') {
    const thumb = videoThumbUrl(attachment);
    media = (
      <button
        onClick={() => setViewerOpen(true)}
        className="relative block overflow-hidden rounded border border-light-200 hover:border-owl-blue-400 transition-colors"
        title={name}
      >
        {thumb ? (
          <img src={thumb} alt={name} className="max-w-[240px] max-h-[240px] object-cover" loading="lazy" />
        ) : (
          <div className="w-60 h-32 bg-light-100 flex items-center justify-center text-light-400">
            <Film className="w-8 h-8" />
          </div>
        )}
        <div className="absolute inset-0 flex items-center justify-center bg-black/20">
          <div className="w-10 h-10 rounded-full bg-white/90 flex items-center justify-center">
            <div className="w-0 h-0 border-t-[6px] border-t-transparent border-b-[6px] border-b-transparent border-l-[10px] border-l-owl-blue-600 ml-0.5" />
          </div>
        </div>
      </button>
    );
  } else {
    media = (
      <button
        onClick={() => setViewerOpen(true)}
        className="flex items-center gap-1.5 px-2 py-1 rounded border border-light-200 bg-light-50 hover:bg-light-100 text-xs text-light-700"
      >
        <FileText className="w-3 h-3" />
        <span className="truncate max-w-[200px]">{name}</span>
      </button>
    );
  }

  const canOpenViewer = kind !== 'audio';

  return (
    <div className="inline-block align-top">
      {media}
      {aiKind && evidenceId && (
        <MediaAnalysisPanel evidenceId={evidenceId} kind={aiKind} compact />
      )}
      {viewerOpen && canOpenViewer && (
        <DocumentViewer
          isOpen
          onClose={() => setViewerOpen(false)}
          documentUrl={url}
          documentName={name}
        />
      )}
    </div>
  );
}
