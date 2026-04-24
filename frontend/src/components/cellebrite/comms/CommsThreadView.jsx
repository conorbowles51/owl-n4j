import React, { useEffect, useState, useRef } from 'react';
import { Loader2, MessageSquare } from 'lucide-react';
import { cellebriteCommsAPI } from '../../../services/api';
import CommsMessageBubble from './CommsMessageBubble';
import CommsCallRow from './CommsCallRow';
import CommsEmailCard from './CommsEmailCard';
import LinkNodeToEntityButton from '../../entities/LinkNodeToEntityButton';
import { appIconEmoji } from './commsUtils';

/**
 * Right-pane thread viewer. Fetches thread detail for the selected thread and
 * renders messages as bubbles, calls as rows, emails as cards (chronologically).
 */
export default function CommsThreadView({ caseId, selectedThread }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (!caseId || !selectedThread) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    cellebriteCommsAPI
      .getThreadDetail(caseId, selectedThread.thread_id, selectedThread.thread_type, { limit: 500 })
      .then((data) => {
        if (!cancelled) {
          setDetail(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message || 'Failed to load thread');
          setDetail(null);
          setLoading(false);
        }
      });
    return () => { cancelled = true; };
  }, [caseId, selectedThread]);

  // Auto-scroll to bottom on load
  useEffect(() => {
    if (scrollRef.current && detail?.items?.length) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [detail]);

  if (!selectedThread) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-light-500 bg-light-50">
        <MessageSquare className="w-10 h-10 mb-2 text-light-300" />
        <div className="text-sm">Select a thread to view messages</div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-5 h-5 animate-spin text-light-400" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-red-600 text-sm p-4">
        Error: {error}
      </div>
    );
  }

  if (!detail || !detail.items?.length) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-light-500 text-sm">
        Empty thread
      </div>
    );
  }

  const participants = detail.thread?.participants || [];
  const nonOwnerNames = participants.filter(p => !p.is_owner).map(p => p.name).join(', ');
  const ownerName = participants.find(p => p.is_owner)?.name || 'You';
  const isGroupChat = participants.length > 2;

  // Date separators
  const itemsByDate = [];
  let currentDate = null;
  for (const item of detail.items) {
    const d = (item.timestamp || '').slice(0, 10);
    if (d !== currentDate) {
      itemsByDate.push({ type: 'date-sep', date: d });
      currentDate = d;
    }
    itemsByDate.push({ type: 'item', item });
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-gradient-to-b from-light-50 to-light-100">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-light-200 bg-white flex-shrink-0">
        <span className="text-xl">{appIconEmoji(detail.thread?.source_app || detail.thread?.thread_type)}</span>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-owl-blue-900 truncate">
            {nonOwnerNames || detail.thread?.name}
          </div>
          <div className="text-[10px] text-light-500 truncate">
            {detail.thread?.source_app || '—'} · {detail.total.toLocaleString()} items
            {ownerName && ` · You = ${ownerName}`}
          </div>
        </div>
        {caseId && detail.thread?.thread_id && (
          <LinkNodeToEntityButton caseId={caseId} nodeKey={detail.thread.thread_id} />
        )}
      </div>

      {/* Body */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto py-2">
        {itemsByDate.map((row, idx) => {
          if (row.type === 'date-sep') {
            return (
              <div key={`sep-${idx}`} className="flex items-center justify-center my-2">
                <span className="text-[10px] bg-light-200 text-light-600 px-2 py-0.5 rounded-full">
                  {formatDateSep(row.date)}
                </span>
              </div>
            );
          }
          const item = row.item;
          if (item.type === 'call') return <CommsCallRow key={item.id || idx} item={item} />;
          if (item.type === 'email') return <CommsEmailCard key={item.id || idx} item={item} />;
          // message
          return (
            <CommsMessageBubble
              key={item.id || idx}
              item={item}
              showSenderName={isGroupChat}
            />
          );
        })}
      </div>
    </div>
  );
}

function formatDateSep(d) {
  if (!d) return '';
  try {
    const dt = new Date(d);
    if (isNaN(dt.getTime())) return d;
    return dt.toLocaleDateString([], { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' });
  } catch {
    return d;
  }
}
