import React, { useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, Loader2, Phone, MessageSquare, Mail, Activity } from 'lucide-react';
import { cellebriteCommsAPI } from '../../../services/api';
import { formatShortTime, previewBody, appIconEmoji } from './commsUtils';

/**
 * Bottom panel showing a chronological cross-type feed of all comms matching
 * the current filters (devices / entities / types / apps / date / search).
 *
 * Always renders. When no entity filter is active it shows the overall feed
 * for the current device set. When From/To entities are selected it narrows
 * to interactions between them.
 */
export default function CommsCrossTypeTimeline({
  caseId,
  fromKeys,
  toKeys,
  reportKeys,
  types,
  sourceApps,
  startDate,
  endDate,
  onJumpToThread,
}) {
  const [expanded, setExpanded] = useState(true);
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);

  const hasEntitySelection = fromKeys.size > 0 || toKeys.size > 0;

  useEffect(() => {
    if (!caseId || !expanded) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    cellebriteCommsAPI.getBetween(caseId, {
      fromKeys: fromKeys.size > 0 ? [...fromKeys] : null,
      toKeys: toKeys.size > 0 ? [...toKeys] : null,
      types: [...types],
      reportKeys: reportKeys.size > 0 ? [...reportKeys] : null,
      sourceApps: sourceApps && sourceApps.size > 0 ? [...sourceApps] : null,
      startDate,
      endDate,
      limit: 300,
    }).then((data) => {
      if (!cancelled) {
        setItems(data.items || []);
        setTotal(data.total || 0);
        setLoading(false);
      }
    }).catch(() => {
      if (!cancelled) {
        setItems([]);
        setTotal(0);
        setLoading(false);
      }
    });
    return () => { cancelled = true; };
  }, [caseId, fromKeys, toKeys, reportKeys, types, sourceApps, startDate, endDate, expanded]);

  const contextLabel = hasEntitySelection
    ? 'between selected entities'
    : 'across all selected devices';

  return (
    <div
      className="border-t-2 border-owl-blue-200 bg-white flex-shrink-0 flex flex-col"
      style={{ height: expanded ? '33vh' : 'auto', minHeight: expanded ? '200px' : '32px' }}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-4 py-1.5 text-xs text-light-700 hover:bg-light-50 transition-colors border-b border-light-100 flex-shrink-0"
      >
        {expanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        <Activity className="w-3.5 h-3.5 text-owl-blue-600" />
        <span className="font-semibold">Conversation timeline</span>
        <span className="text-light-500">{contextLabel}</span>
        <span className="text-light-400">·</span>
        <span className="text-light-500">{total.toLocaleString()} items</span>
        {loading && <Loader2 className="w-3 h-3 animate-spin text-light-400 ml-1" />}
      </button>
      {expanded && (
        <div className="flex-1 overflow-y-auto">
          {loading && items.length === 0 ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-5 h-5 animate-spin text-light-400" />
            </div>
          ) : items.length === 0 ? (
            <div className="text-xs text-light-500 italic text-center py-6">
              No comms match the current filters
            </div>
          ) : (
            items.map((item, idx) => (
              <TimelineRow
                key={`${item.id || 'x'}-${idx}`}
                item={item}
                onClick={onJumpToThread ? () => onJumpToThread(item) : null}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}

function TimelineRow({ item, onClick }) {
  const Icon = item.type === 'call' ? Phone : item.type === 'email' ? Mail : MessageSquare;
  const color =
    item.type === 'call'
      ? 'text-emerald-600'
      : item.type === 'email'
      ? 'text-amber-600'
      : 'text-owl-blue-600';
  const from = item.sender?.name || '?';
  const to = (item.recipients && item.recipients[0]?.name) || '?';
  const body = item.type === 'email' ? (item.subject || '') : (item.body || '');
  const typeLabel =
    item.type === 'call' ? `${item.call_type || 'call'} ${item.duration || ''}`.trim() : '';

  return (
    <button
      onClick={onClick}
      className="w-full text-left flex items-center gap-2 px-4 py-1.5 border-b border-light-100 hover:bg-light-50"
    >
      <Icon className={`w-3 h-3 flex-shrink-0 ${color}`} />
      <span className="text-[10px] text-light-500 w-32 flex-shrink-0 tabular-nums">
        {formatShortTime(item.timestamp)}
      </span>
      <span className="text-xs flex-shrink-0" title={item.source_app}>
        {appIconEmoji(item.source_app || item.type)}
      </span>
      <span className="text-xs text-light-900 font-medium truncate max-w-[140px]" title={from}>
        {from}
      </span>
      <span className="text-light-400 flex-shrink-0">→</span>
      <span className="text-xs text-light-900 font-medium truncate max-w-[140px]" title={to}>
        {to}
      </span>
      <span className="flex-1 text-xs text-light-600 truncate">{previewBody(body, 100)}</span>
      {typeLabel && (
        <span className="text-[10px] text-light-500 italic flex-shrink-0">{typeLabel}</span>
      )}
    </button>
  );
}
