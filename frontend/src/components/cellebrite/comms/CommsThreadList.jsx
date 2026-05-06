import React from 'react';
import { MessageSquare, Phone, Mail, Paperclip, Loader2 } from 'lucide-react';
import { formatRelative, appIconEmoji } from './commsUtils';
import PhoneIdentityChip from '../shared/PhoneIdentityChip';
import { usePhoneReports } from '../../../context/PhoneReportsContext';

/**
 * Left-pane scrollable list of threads (chats + synthetic call/email threads).
 * Clicking a row selects the thread for display in CommsThreadView.
 *
 * Each row gets a 4px coloured accent stripe on the left + a small phone
 * chip in the meta row, so investigators can identify the source phone
 * without reading the device-name text.
 */
export default function CommsThreadList({
  threads = [],
  loading = false,
  selectedThreadId,
  onSelect,
  // deviceById left for backwards compatibility but no longer used —
  // the PhoneIdentityChip pulls everything it needs from context.
  deviceById = {},
}) {
  const phoneCtx = usePhoneReports();
  const hasMultiple = !!phoneCtx?.hasMultiple;
  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-5 h-5 animate-spin text-light-400" />
      </div>
    );
  }

  if (!threads.length) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-light-500 text-xs p-4">
        <MessageSquare className="w-8 h-8 mb-2 text-light-300" />
        <div className="text-center">No threads match current filters</div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {threads.map((t) => (
        <ThreadRow
          key={t.thread_id}
          thread={t}
          isSelected={selectedThreadId === t.thread_id}
          onSelect={() => onSelect(t)}
          phoneCtx={phoneCtx}
          showPhoneChip={hasMultiple}
        />
      ))}
    </div>
  );
}

function ThreadRow({ thread, isSelected, onSelect, phoneCtx, showPhoneChip }) {
  const Icon = thread.thread_type === 'chat'
    ? MessageSquare
    : thread.thread_type === 'calls'
      ? Phone
      : Mail;

  // Participant summary: show up to 2 names + count
  const participants = thread.participants || [];
  const nonOwnerParticipants = participants.filter(p => !p.is_owner);
  const displayNames = (nonOwnerParticipants.length ? nonOwnerParticipants : participants)
    .slice(0, 2)
    .map(p => p.name)
    .join(', ');
  const extraCount = Math.max(0, participants.length - 2);

  // Phone accent stripe — only show when there are multiple phones.
  // When the thread is selected we keep the existing blue selection
  // marker (a 4px owl-blue stripe) so selection state stays obvious;
  // otherwise we show the phone's identity colour as a 4px stripe.
  const identity = showPhoneChip && phoneCtx
    ? phoneCtx.getIdentityByKey(thread.report_key)
    : null;

  const stripeStyle = !isSelected && identity
    ? {
        borderLeftWidth: '4px',
        borderLeftStyle: 'solid',
        borderLeftColor: identity.hex,
      }
    : undefined;

  return (
    <button
      onClick={onSelect}
      style={stripeStyle}
      className={`w-full text-left border-b border-light-100 px-3 py-2 hover:bg-light-50 transition-colors ${
        isSelected ? 'bg-owl-blue-50 border-l-4 border-l-owl-blue-500' : ''
      }`}
    >
      <div className="flex items-start gap-2">
        <div className="flex-shrink-0 mt-0.5 text-sm">
          {appIconEmoji(thread.source_app || thread.thread_type)}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-0.5">
            <Icon className="w-3 h-3 text-light-500 flex-shrink-0" />
            <span className="text-xs font-semibold text-owl-blue-900 truncate">
              {displayNames || thread.name}
              {extraCount > 0 && <span className="text-light-500"> +{extraCount}</span>}
            </span>
            {showPhoneChip && thread.report_key && (
              <PhoneIdentityChip
                reportKey={thread.report_key}
                variant="dense"
                className="flex-shrink-0 ml-auto"
              />
            )}
          </div>
          <div className="flex items-center gap-1.5 text-[10px] text-light-500">
            <span className="truncate">{thread.source_app || '—'}</span>
            <div className="flex-1" />
            {thread.has_attachments && (
              <Paperclip className="w-2.5 h-2.5 text-amber-600 flex-shrink-0" title={`${thread.attachment_count} attachments`} />
            )}
            <span className="flex-shrink-0">{formatRelative(thread.last_activity)}</span>
          </div>
          <div className="flex items-center gap-2 mt-0.5 text-[10px] text-light-500">
            <span>{thread.message_count.toLocaleString()} items</span>
          </div>
        </div>
      </div>
    </button>
  );
}
