import React from 'react';
import { PhoneIncoming, PhoneOutgoing, PhoneMissed, Phone, Video } from 'lucide-react';
import CommsAttachment from './CommsAttachment';
import PhoneIdentityChip from '../shared/PhoneIdentityChip';
import HighlightedText from '../shared/HighlightedText';
import LinkNodeToEntityButton from '../../entities/LinkNodeToEntityButton';
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
export default function CommsCallRow({
  item,
  reportKey,
  showPhoneChip = false,
  highlights = [],
  caseId = null,
  // Optional rail-aware select handler. When set, the row becomes
  // clickable and publishes the call to the universal rail.
  onSelect = null,
  selected = false,
}) {
  const hasHighlights = highlights && highlights.length > 0;
  const Icon = iconForCall(item.direction, item.call_type);
  const isOwnerFrom = !!(item.sender && item.sender.is_owner);
  const isMissed = (item.call_type || '').toLowerCase() === 'missed';
  const color = isMissed ? 'text-red-600' : isOwnerFrom ? 'text-emerald-600' : 'text-owl-blue-600';
  const attachments = item.attachments || [];

  const fromName = item.sender?.name || 'Unknown';
  const toName = item.recipient?.name || 'Unknown';
  const effectiveReportKey = reportKey || item.report_key || item.cellebrite_report_key;
  const nodeKey = item.id || item.key;

  const interactive = typeof onSelect === 'function';
  const rowProps = interactive
    ? {
        role: 'button',
        tabIndex: 0,
        onClick: (e) => {
          if (e.defaultPrevented) return;
          onSelect(item);
        },
        onKeyDown: (e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onSelect(item);
          }
        },
        className: `flex items-center gap-3 px-4 py-2 border-b border-light-100 cursor-pointer ${
          selected ? 'bg-emerald-50/60 ring-1 ring-emerald-300/60' : 'hover:bg-light-50'
        }`,
      }
    : {
        className: 'flex items-center gap-3 px-4 py-2 border-b border-light-100 hover:bg-light-50',
      };

  return (
    <div {...rowProps}>
      <Icon className={`w-4 h-4 flex-shrink-0 ${color}`} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 text-sm text-light-900">
          <span className="font-medium truncate">
            {hasHighlights ? <HighlightedText text={fromName} highlights={highlights} /> : fromName}
          </span>
          <span className="text-light-400">→</span>
          <span className="font-medium truncate">
            {hasHighlights ? <HighlightedText text={toName} highlights={highlights} /> : toName}
          </span>
          {item.video_call && <Video className="w-3 h-3 text-light-500 flex-shrink-0" title="Video call" />}
          {isMissed && <span className="text-[10px] text-red-700 bg-red-50 px-1 rounded">Missed</span>}
          {showPhoneChip && effectiveReportKey && (
            <PhoneIdentityChip
              reportKey={effectiveReportKey}
              variant="dense"
              className="flex-shrink-0 ml-auto"
            />
          )}
          {caseId && nodeKey && (
            <LinkNodeToEntityButton
              caseId={caseId}
              nodeKey={nodeKey}
              compact
            />
          )}
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
