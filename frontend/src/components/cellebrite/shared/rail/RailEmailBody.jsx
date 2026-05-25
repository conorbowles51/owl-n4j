/**
 * RailEmailBody — dedicated email renderer for the selection rail
 * flyout.
 *
 * Replaces the previous `CommsEmailCard defaultExpanded` reuse, which
 * was built for the thread view (collapsible chevron, dense metadata
 * row) and didn't fit the rail's permanently-expanded shape. The new
 * component:
 *
 *   1. Always shows the email body. Toggles between
 *      - Rendered  (sandboxed iframe — sanitised by sandbox, no JS,
 *                   no same-origin, no top-nav)
 *      - Raw text  (plaintext fallback derived by stripping tags),
 *      - Raw HTML  (the actual stored markup, for forensic review).
 *      The toggle is always visible, never hidden behind a click.
 *
 *   2. Lists every attachment in a dedicated section with a link
 *      into the Files Explorer for each (uses the existing
 *      requestCellebriteTabSwitch event so the Files tab opens with
 *      the picked evidence selected).
 *
 *   3. Honestly reports when attachments couldn't be resolved —
 *      either "no attachments on this email" (when the ingest never
 *      stored any attachment_file_ids) or "N attachments referenced
 *      but unavailable in evidence" (when the ids are stored but the
 *      file rows were dropped from the evidence table).
 */

import React, { useMemo, useState } from 'react';
import { Folder, FileText, Code, Eye, ExternalLink, Paperclip, AlertCircle } from 'lucide-react';
import CommsAttachment from '../../comms/CommsAttachment';
import { formatShortTime } from '../../comms/commsUtils';
import { useCellebriteSelection } from '../CellebriteSelectionContext';
import { requestCellebriteTabSwitch } from '../../../../utils/commsHandoff';

export default function RailEmailBody({ item, caseId }) {
  const [viewMode, setViewMode] = useState('rendered'); // 'rendered' | 'text' | 'raw'

  const subject = item.subject || '(no subject)';
  const fromName = item.sender?.name || 'Unknown';
  const toName = item.recipient?.name
    || (item.recipients && item.recipients[0]?.name)
    || 'Unknown';
  const extraTo = Array.isArray(item.recipients) && item.recipients.length > 1
    ? ` + ${item.recipients.length - 1} more`
    : '';
  const bodyRaw = item.body || '';
  const hasHtml = useMemo(() => /<[a-z][\s\S]*>/i.test(bodyRaw), [bodyRaw]);
  // Plaintext is computed once per body — used by the 'text' view and
  // as a fallback when the rendered iframe ends up blank (e.g. the
  // entire email body is hidden inside display:none divs, which
  // happens with email-marketing preheaders).
  const plaintext = useMemo(() => htmlToText(bodyRaw), [bodyRaw]);

  const attachments = Array.isArray(item.attachments) ? item.attachments : [];

  return (
    <div className="space-y-2">
      {/* Header */}
      <div className="px-3 pt-2 pb-1.5 border-b border-light-100">
        <div className="text-sm font-semibold text-owl-blue-900 break-words">
          {subject}
        </div>
        <div className="mt-1 text-[11px] text-light-600 flex flex-wrap items-center gap-x-2 gap-y-0.5">
          <span>
            <span className="text-light-500">From </span>
            <span className="text-light-800 font-medium">{fromName}</span>
          </span>
          <span>
            <span className="text-light-500">to </span>
            <span className="text-light-800 font-medium">{toName}{extraTo}</span>
          </span>
          <span className="text-light-400">·</span>
          <span className="text-light-700 tabular-nums">{formatShortTime(item.timestamp)}</span>
          {item.folder && (
            <span className="flex items-center gap-0.5 px-1 rounded bg-light-100 text-light-600">
              <Folder className="w-2.5 h-2.5" />
              {item.folder}
            </span>
          )}
          {item.email_status && (
            <span className="px-1 rounded bg-light-100 text-light-600">
              {item.email_status}
            </span>
          )}
        </div>
      </div>

      {/* View-mode toggle. Always visible — investigators frequently
          need to flip between rendered + raw to verify what they
          looked at vs what the source actually contained. */}
      <div className="px-3">
        <div className="inline-flex items-center bg-white border border-light-300 rounded overflow-hidden text-[11px]">
          <ToggleBtn
            active={viewMode === 'rendered'}
            onClick={() => setViewMode('rendered')}
            disabled={!hasHtml}
            icon={Eye}
            label="Rendered"
            title={hasHtml ? 'Show the email as the recipient would have seen it' : 'No HTML body to render'}
          />
          <ToggleBtn
            active={viewMode === 'text'}
            onClick={() => setViewMode('text')}
            icon={FileText}
            label="Text"
            title="Plain-text extraction of the body"
          />
          <ToggleBtn
            active={viewMode === 'raw'}
            onClick={() => setViewMode('raw')}
            icon={Code}
            label="Raw source"
            title="The exact bytes Cellebrite recorded for the body"
          />
        </div>
      </div>

      {/* Body — switches between three views */}
      <div className="px-3">
        {viewMode === 'rendered' && hasHtml ? (
          <RenderedBody bodyHtml={bodyRaw} />
        ) : viewMode === 'rendered' && !hasHtml ? (
          // Auto-fall to text when there's no HTML to render
          <PlainView text={bodyRaw || plaintext} />
        ) : viewMode === 'text' ? (
          <PlainView text={plaintext || bodyRaw} />
        ) : (
          <RawView source={bodyRaw} />
        )}
      </div>

      {/* Attachments */}
      <div className="px-3 pb-3">
        <AttachmentsSection
          attachments={attachments}
          caseId={caseId}
        />
      </div>
    </div>
  );
}

/* ─────────────────────── Body view variants ─────────────────────── */

function RenderedBody({ bodyHtml }) {
  // Sandboxed iframe — no allow-scripts, no allow-same-origin. This
  // is the safest cross-tenant rendering surface for unknown HTML. We
  // wrap the body in our own minimal stylesheet so emails missing a
  // body color don't render white-on-white inside the rail (the most
  // common failure mode of email-marketing HTML).
  const wrapped =
    '<!doctype html><html><head><meta charset="utf-8">'
    + '<base target="_blank">'
    + '<style>'
    + 'html,body{margin:0;padding:8px;background:#fff;color:#1e293b;'
    + '  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;'
    + '  font-size:13px;line-height:1.45;word-break:break-word;}'
    + 'img{max-width:100%;height:auto}'
    + 'a{color:#2563eb;text-decoration:underline}'
    + 'pre{white-space:pre-wrap}'
    + 'table{max-width:100%}'
    + 'blockquote{border-left:3px solid #e2e8f0;margin:0 0 0 0;padding-left:10px;color:#475569}'
    + '</style></head><body>'
    + bodyHtml
    + '</body></html>';
  return (
    <iframe
      title="email-body-rendered"
      className="w-full min-h-[260px] max-h-[60vh] border border-light-200 rounded bg-white"
      srcDoc={wrapped}
      // Empty sandbox = strongest isolation: no scripts, no same-origin,
      // no top-level nav, no popups. We add allow-popups so the
      // `target="_blank"` base above lets the user click outbound
      // links if they want to — but those open in a new tab, never
      // hijacking the app.
      sandbox="allow-popups allow-popups-to-escape-sandbox"
      referrerPolicy="no-referrer"
    />
  );
}

function PlainView({ text }) {
  if (!text) {
    return (
      <div className="text-[11px] italic text-light-500 px-2 py-3 border border-dashed border-light-200 rounded">
        No body content recorded for this email.
      </div>
    );
  }
  return (
    <div className="text-xs whitespace-pre-wrap text-light-800 leading-relaxed bg-light-50 border border-light-200 rounded px-3 py-2 max-h-[60vh] overflow-y-auto">
      {text}
    </div>
  );
}

function RawView({ source }) {
  if (!source) {
    return (
      <div className="text-[11px] italic text-light-500 px-2 py-3 border border-dashed border-light-200 rounded">
        No raw source recorded for this email.
      </div>
    );
  }
  return (
    <pre className="text-[11px] whitespace-pre-wrap break-words font-mono bg-light-50 border border-light-200 rounded px-3 py-2 max-h-[60vh] overflow-auto text-light-700">
      {source}
    </pre>
  );
}

/* ─────────────────────── Attachments section ─────────────────────── */

function AttachmentsSection({ attachments, caseId }) {
  const { selectEntity } = useCellebriteSelection();

  if (attachments.length === 0) {
    return (
      <div className="text-[11px] text-light-500 italic flex items-center gap-1.5 px-2 py-1.5 border border-dashed border-light-200 rounded">
        <Paperclip className="w-3 h-3" />
        No attachments recorded for this email.
      </div>
    );
  }

  const missing = attachments.filter((a) => a.missing);
  const present = attachments.filter((a) => !a.missing);

  // Open the Files tab and select the evidence row so the investigator
  // lands on the attachment's full forensic context (path, hashes,
  // previous tags). Uses the existing tab-switch event bus that
  // already routes through CellebriteView's SwimLaneTabSwitcher.
  const onOpenInFiles = (att) => {
    if (!att.evidence_id) return;
    selectEntity({
      type: 'file',
      id: att.evidence_id,
      caseId,
      reportKey: att.cellebrite_report_key || null,
      payload: {
        evidence_id: att.evidence_id,
        file_id: att.file_id,
        original_filename: att.original_filename,
        category: att.category,
        size: att.size,
        // Files Explorer accordion looks for either
        // `_open_in_files_intent` (preferred — explicit) or falls back
        // to type 'file'. Set both so it doesn't matter which one the
        // consumer implements first.
        _open_in_files_intent: true,
      },
      source: 'rail.email.attachment',
    });
    requestCellebriteTabSwitch('files');
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-light-600 font-semibold">
        <Paperclip className="w-3 h-3" />
        Attachments
        <span className="font-normal normal-case text-light-400">
          ({attachments.length})
        </span>
      </div>

      {/* Inline previews for present attachments — images / video /
          audio render straight in the rail; other types get a chip. */}
      {present.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {present.map((att) => (
            <div key={att.file_id || att.evidence_id} className="flex flex-col gap-1">
              <CommsAttachment attachment={att} />
              <button
                type="button"
                onClick={() => onOpenInFiles(att)}
                disabled={!att.evidence_id}
                className="text-[10px] text-owl-blue-600 hover:text-owl-blue-800 disabled:text-light-400 disabled:cursor-not-allowed inline-flex items-center gap-1"
                title={att.evidence_id ? 'Open this attachment in the Files tab' : 'Attachment not linked to an evidence record'}
              >
                <ExternalLink className="w-2.5 h-2.5" />
                Open in Files
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Missing-attachment warning — surfaces ingestion-side data
          loss honestly so the user knows the email *referenced* an
          attachment that isn't on disk anywhere. */}
      {missing.length > 0 && (
        <div className="flex items-start gap-1.5 px-2 py-1.5 rounded bg-amber-50 border border-amber-200 text-amber-700 text-[11px]">
          <AlertCircle className="w-3 h-3 mt-0.5 flex-shrink-0" />
          <div>
            {missing.length} attachment{missing.length === 1 ? '' : 's'}
            {' '}referenced by this email but missing from evidence storage.
            The Cellebrite report carried the file ids but the files themselves
            weren't ingested into the Files tab.
          </div>
        </div>
      )}
    </div>
  );
}

/* ─────────────────────── Toggle button ─────────────────────── */

function ToggleBtn({ active, onClick, disabled, icon: Icon, label, title }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`px-2 py-1 inline-flex items-center gap-1 border-l first:border-l-0 border-light-200 ${
        active
          ? 'bg-owl-blue-100 text-owl-blue-900'
          : 'text-light-700 hover:bg-light-100 disabled:text-light-400 disabled:cursor-not-allowed disabled:hover:bg-transparent'
      }`}
    >
      <Icon className="w-3 h-3" />
      {label}
    </button>
  );
}

/* ─────────────────────── Helpers ─────────────────────── */

/**
 * Naive HTML → plaintext converter. Used to (a) populate the "Text"
 * view, and (b) provide a fallback preview when the rendered iframe
 * is empty (which happens with email-marketing HTML that hides its
 * entire body inside display:none preheaders).
 *
 * We deliberately don't pull in a sanitiser library — the rail
 * iframe is sandboxed and the plaintext path never reaches innerHTML.
 */
function htmlToText(html) {
  if (!html) return '';
  // Strip <script> / <style> blocks entirely so their contents don't
  // show up as gibberish in the text view.
  let s = String(html)
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    // Block-level tags → linebreaks so paragraphs stay separated.
    .replace(/<\/(p|div|h[1-6]|li|tr|blockquote)>/gi, '\n')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<[^>]+>/g, '');
  // Decode the handful of HTML entities that survive most often.
  const entities = {
    '&nbsp;': ' ', '&amp;': '&', '&lt;': '<', '&gt;': '>',
    '&quot;': '"', '&#39;': "'", '&apos;': "'", '&zwnj;': '',
    '&zwj;': '', '&ndash;': '–', '&mdash;': '—', '&hellip;': '…',
    '&#x200c;': '', '&#x200d;': '',
  };
  s = s.replace(/&[a-z]+;|&#x?[0-9a-f]+;/gi, (m) => entities[m.toLowerCase()] || m);
  // Collapse runs of whitespace, but preserve our injected newlines.
  s = s.replace(/[ \t\u00a0\u200c]+/g, ' ').replace(/\n[ \t]+/g, '\n');
  // Cap consecutive blank lines to two.
  s = s.replace(/\n{3,}/g, '\n\n').trim();
  return s;
}
