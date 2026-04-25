import React from 'react';
import { Trash2, Smartphone } from 'lucide-react';
import CommsAttachment from './CommsAttachment';
import { formatShortTime, paletteForSenderKey, senderInitials } from './commsUtils';

/**
 * Chat-style message bubble with clear sender attribution.
 *
 * Visual rules:
 *   • Right-align bubbles from the **phone owner**, left-align everyone else.
 *   • Each unique sender gets a deterministic colour from a palette so it's
 *     instantly obvious who's who, even in 1:1 chats.
 *   • An avatar circle with the sender's initials sits on the bubble's
 *     outside edge so the eye latches on to the speaker.
 *   • The sender's name renders above the bubble for the first message in
 *     a run from that speaker (consecutive messages from the same person
 *     collapse — like iMessage / WhatsApp).
 *
 * Props:
 *   item                  — message item (must include sender.key and sender.name)
 *   palette               — optional precomputed sender palette (Map<key, palette>)
 *                           passed by the parent so colours stay stable per thread.
 *   showSenderName        — show the sender name + avatar on the first message
 *                           of a run. Default true.
 *   isFirstInRun          — true for the first bubble of a consecutive run
 *                           from the same sender. Avatar + name only show on the
 *                           first; subsequent ones get a hidden avatar slot to
 *                           keep alignment.
 */
export default function CommsMessageBubble({
  item,
  palette,
  showSenderName = true,
  isFirstInRun = true,
}) {
  const sender = item.sender || null;
  const isOwner = !!(sender && sender.is_owner);
  const senderKey = sender?.key || 'unknown';
  const senderName = sender?.name || sender?.key || 'Unknown';

  // Resolve the palette for this sender.
  const resolved =
    (palette && typeof palette.get === 'function' && palette.get(senderKey)) ||
    paletteForSenderKey(senderKey, isOwner);

  const attachments = item.attachments || [];
  const isDeleted =
    (item.deleted_state || '').toLowerCase() !== 'intact' && item.deleted_state;
  const initials = senderInitials(senderName);

  // Owner bubbles flow right-to-left so the avatar lands on the right edge.
  const rowDir = isOwner ? 'flex-row-reverse' : 'flex-row';
  const colAlign = isOwner ? 'items-end' : 'items-start';
  const showHeader = showSenderName && isFirstInRun;

  return (
    <div className={`flex ${isOwner ? 'justify-end' : 'justify-start'} px-3 py-0.5`}>
      <div className={`max-w-[75%] flex ${rowDir} items-end gap-1.5`}>
        {/* Avatar — only on first bubble of a run; reserve space on others
            so consecutive bubbles stay aligned with the run leader. */}
        <div className="flex-shrink-0 w-7" aria-hidden={!isFirstInRun}>
          {isFirstInRun && (
            <div
              className={`w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-semibold shadow-sm ring-2 ring-white ${resolved.avatar} ${resolved.avatarText}`}
              title={`${senderName}${isOwner ? ' (phone owner)' : ''}`}
            >
              {initials}
            </div>
          )}
        </div>

        {/* Bubble column */}
        <div className={`flex flex-col ${colAlign} min-w-0`}>
          {showHeader && (
            <div
              className={`flex items-center gap-1 mb-0.5 px-1 ${
                isOwner ? 'flex-row-reverse' : ''
              }`}
            >
              <span className="text-[11px] font-semibold text-light-900 truncate max-w-[200px]">
                {senderName}
              </span>
              {isOwner && (
                <span
                  className="inline-flex items-center gap-0.5 text-[9px] uppercase tracking-wide text-emerald-700 bg-emerald-50 border border-emerald-200 px-1 py-px rounded"
                  title="Phone owner"
                >
                  <Smartphone className="w-2.5 h-2.5" />
                  You
                </span>
              )}
            </div>
          )}
          <div
            className={`relative rounded-2xl px-3 py-1.5 shadow-sm border border-black/5 ${
              resolved.bubble
            } ${resolved.text} ${
              isOwner ? 'rounded-br-sm' : 'rounded-bl-sm'
            } ${isDeleted ? 'opacity-60 italic' : ''}`}
          >
            {isDeleted && (
              <div className="flex items-center gap-1 text-[10px] text-red-700 mb-1">
                <Trash2 className="w-2.5 h-2.5" />
                {item.deleted_state}
              </div>
            )}
            {item.body && (
              <div className="text-sm whitespace-pre-wrap break-words">
                {item.body}
              </div>
            )}
            {attachments.length > 0 && (
              <div
                className={`mt-1.5 flex flex-wrap gap-1.5 ${
                  attachments.length === 1 ? '' : 'max-w-[480px]'
                }`}
              >
                {attachments.map((att) => (
                  <CommsAttachment key={att.file_id} attachment={att} />
                ))}
              </div>
            )}
          </div>
          <div
            className={`text-[10px] text-light-400 mt-0.5 px-1 ${
              isOwner ? 'text-right' : ''
            }`}
          >
            {formatShortTime(item.timestamp)}
            {item.source_app ? ` · ${item.source_app}` : ''}
          </div>
        </div>
      </div>
    </div>
  );
}
