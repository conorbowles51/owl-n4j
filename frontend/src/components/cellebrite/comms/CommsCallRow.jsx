import React from 'react';
import { PhoneIncoming, PhoneOutgoing, PhoneMissed, Phone, Video } from 'lucide-react';
import CommsAttachment from './CommsAttachment';
import { formatShortTime, formatDuration } from './commsUtils';

function iconForCall(direction, callType) {
  const d = (direction || '').toLowerCase();
  const t = (callType || '').toLowerCase();
  if (t === 'missed' || d.includes('miss')) return PhoneMissed;
  if (d.includes('incoming')) return PhoneIncoming;
  if (d.includes('outgoing') || d.includes('outgoing')) return PhoneOutgoing;
  return Phone;
}

/**
 * Compact row for a single call. Voicemail audio (if attached) renders inline.
 */
export default function CommsCallRow({ item }) {
  const Icon = iconForCall(item.direction, item.call_type);
  const isOwnerFrom = !!(item.sender && item.sender.is_owner);
  const isMissed = (item.call_type || '').toLowerCase() === 'missed';
  const color = isMissed ? 'text-red-600' : isOwnerFrom ? 'text-emerald-600' : 'text-owl-blue-600';
  const attachments = item.attachments || [];

  const fromName = item.sender?.name || 'Unknown';
  const toName = item.recipient?.name || 'Unknown';

  return (
    <div className="flex items-center gap-3 px-4 py-2 border-b border-light-100 hover:bg-light-50">
      <Icon className={`w-4 h-4 flex-shrink-0 ${color}`} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 text-sm text-light-900">
          <span className="font-medium truncate">{fromName}</span>
          <span className="text-light-400">→</span>
          <span className="font-medium truncate">{toName}</span>
          {item.video_call && <Video className="w-3 h-3 text-light-500 flex-shrink-0" title="Video call" />}
          {isMissed && <span className="text-[10px] text-red-700 bg-red-50 px-1 rounded">Missed</span>}
        </div>
        <div className="text-[10px] text-light-500 flex items-center gap-2">
          <span>{formatShortTime(item.timestamp)}</span>
          {item.duration && <span>· {formatDuration(item.duration)}</span>}
          {item.source_app && <span>· {item.source_app}</span>}
          {item.call_type && !isMissed && <span>· {item.call_type}</span>}
        </div>
        {attachments.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1.5">
            {attachments.map((att) => (
              <CommsAttachment key={att.file_id} attachment={att} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
