import React, { useState } from 'react';
import { Mail, ChevronDown, ChevronRight, Folder } from 'lucide-react';
import CommsAttachment from './CommsAttachment';
import { formatShortTime, previewBody } from './commsUtils';

/**
 * Email card: collapsed shows subject + first line + metadata.
 * Expanded shows the full body rendered as sanitized HTML.
 */
export default function CommsEmailCard({ item, defaultExpanded = false }) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  const fromName = item.sender?.name || 'Unknown';
  const toName = item.recipient?.name || 'Unknown';
  const subject = item.subject || '(no subject)';
  const bodyHtml = item.body || '';
  // Heuristic: treat as HTML if it contains tags, else wrap as <pre>
  const hasHtml = /<[a-z][\s\S]*>/i.test(bodyHtml);
  const attachments = item.attachments || [];

  return (
    <div className="border-b border-light-100 bg-white">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-start gap-2 px-4 py-2 text-left hover:bg-light-50 transition-colors"
      >
        <Mail className="w-4 h-4 mt-0.5 flex-shrink-0 text-amber-600" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 text-sm text-light-900">
            {expanded ? <ChevronDown className="w-3 h-3 flex-shrink-0" /> : <ChevronRight className="w-3 h-3 flex-shrink-0" />}
            <span className="font-medium truncate">{subject}</span>
          </div>
          <div className="text-[10px] text-light-500 mt-0.5 flex items-center gap-2">
            <span className="truncate">{fromName} → {toName}</span>
            <span>·</span>
            <span className="flex-shrink-0">{formatShortTime(item.timestamp)}</span>
            {item.folder && (
              <span className="flex items-center gap-0.5 flex-shrink-0 px-1 rounded bg-light-100 text-light-600">
                <Folder className="w-2.5 h-2.5" />
                {item.folder}
              </span>
            )}
            {item.email_status && (
              <span className="flex-shrink-0">· {item.email_status}</span>
            )}
          </div>
          {!expanded && bodyHtml && (
            <div className="text-xs text-light-600 truncate mt-0.5">
              {previewBody(hasHtml ? bodyHtml.replace(/<[^>]*>/g, ' ') : bodyHtml, 120)}
            </div>
          )}
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-3 ml-6">
          {hasHtml ? (
            <iframe
              title="email-body"
              className="w-full min-h-[200px] max-h-[500px] border border-light-200 rounded bg-white"
              srcDoc={`<html><head><meta charset="utf-8"><style>body{font-family:sans-serif;font-size:13px;padding:8px;color:#1e293b;margin:0}img{max-width:100%;height:auto}a{color:#2563eb}</style></head><body>${bodyHtml}</body></html>`}
              sandbox=""
            />
          ) : (
            <pre className="text-xs text-light-800 whitespace-pre-wrap font-sans bg-light-50 p-2 rounded border border-light-200">
              {bodyHtml}
            </pre>
          )}
          {attachments.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {attachments.map((att) => (
                <CommsAttachment key={att.file_id} attachment={att} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
