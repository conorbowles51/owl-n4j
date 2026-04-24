import React from 'react';
import { Trash2 } from 'lucide-react';
import CommsAttachment from './CommsAttachment';
import { formatShortTime } from './commsUtils';

/**
 * WhatsApp-style message bubble. When the sender is the phone owner the bubble
 * renders right-aligned with a light-blue fill; otherwise left-aligned with
 * white fill.
 */
export default function CommsMessageBubble({ item, showSenderName = true }) {
  const isOwner = !!(item.sender && item.sender.is_owner);
  const senderName = item.sender?.name || 'Unknown';
  const attachments = item.attachments || [];
  const isDeleted = (item.deleted_state || '').toLowerCase() !== 'intact' && item.deleted_state;

  return (
    <div className={`flex ${isOwner ? 'justify-end' : 'justify-start'} px-4 py-1`}>
      <div className={`max-w-[68%] ${isOwner ? 'items-end' : 'items-start'} flex flex-col`}>
        {showSenderName && !isOwner && (
          <div className="text-[10px] text-light-500 font-medium mb-0.5 px-1">
            {senderName}
          </div>
        )}
        <div
          className={`rounded-2xl px-3 py-1.5 shadow-sm ${
            isOwner
              ? 'bg-owl-blue-100 text-owl-blue-950 rounded-br-sm'
              : 'bg-white border border-light-200 text-light-900 rounded-bl-sm'
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
            <div className={`mt-1.5 flex flex-wrap gap-1.5 ${attachments.length === 1 ? '' : 'max-w-[480px]'}`}>
              {attachments.map((att) => (
                <CommsAttachment key={att.file_id} attachment={att} />
              ))}
            </div>
          )}
        </div>
        <div className={`text-[10px] text-light-400 mt-0.5 px-1 ${isOwner ? 'text-right' : ''}`}>
          {formatShortTime(item.timestamp)}
          {item.source_app ? ` · ${item.source_app}` : ''}
        </div>
      </div>
    </div>
  );
}
