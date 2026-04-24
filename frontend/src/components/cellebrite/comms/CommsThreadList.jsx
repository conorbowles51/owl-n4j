import React from 'react';
import { MessageSquare, Phone, Mail, Paperclip, Smartphone, Loader2 } from 'lucide-react';
import { formatRelative, appIconEmoji } from './commsUtils';

/**
 * Left-pane scrollable list of threads (chats + synthetic call/email threads).
 * Clicking a row selects the thread for display in CommsThreadView.
 */
export default function CommsThreadList({
  threads = [],
  loading = false,
  selectedThreadId,
  onSelect,
  deviceById = {}, // map report_key → device label for badges
}) {
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
          deviceLabel={deviceById[t.report_key]}
        />
      ))}
    </div>
  );
}

function ThreadRow({ thread, isSelected, onSelect, deviceLabel }) {
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

  return (
    <button
      onClick={onSelect}
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
          </div>
          <div className="flex items-center gap-1.5 text-[10px] text-light-500">
            <span className="truncate">{thread.source_app || '—'}</span>
            {deviceLabel && (
              <>
                <span>·</span>
                <span className="flex items-center gap-0.5 flex-shrink-0" title={deviceLabel}>
                  <Smartphone className="w-2.5 h-2.5" />
                  {deviceLabel.length > 18 ? deviceLabel.slice(0, 18) + '…' : deviceLabel}
                </span>
              </>
            )}
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
