import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, ChevronRight, Loader2, Phone, MessageSquare, Mail, Activity, ArrowDownWideNarrow, ArrowUpWideNarrow, Layers, List, LayoutPanelTop, LayoutPanelLeft } from 'lucide-react';
import { cellebriteCommsAPI } from '../../../services/api';
import { formatShortTime, previewBody, appIconEmoji } from './commsUtils';
import PhoneIdentityChip from '../shared/PhoneIdentityChip';
import { usePhoneReports } from '../../../context/PhoneReportsContext';
import CommsCrossTypeSwimLane from './CommsCrossTypeSwimLane';

// Two-line row layout (per user feedback):
//   line 1: [phone] [time] [type icon] [app] [body preview]
//   line 2: [sender → recipient] [type meta e.g. "missed 0:12"]
// Phone chip is leftmost so the user can scan the device column at a
// glance; sender→recipient sits on its own line so it's never truncated
// out by a long body. Height bumped so the windowed renderer math
// stays accurate.
const ROW_HEIGHT = 46;

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
  // Direction-agnostic involvement filter. When non-empty, takes
  // priority over from/to (which the parent leaves empty in Any
  // mode). Routes through the backend's `participant_keys` OR
  // semantics — see CellebriteCommsCenter for context.
  participantKeys = new Set(),
  reportKeys,
  types,
  sourceApps,
  startDate,
  endDate,
  onJumpToThread,
  // Optional rail-aware select handler. Fires alongside onJumpToThread
  // so a single row click both navigates to the parent thread (if the
  // caller wants that) and publishes the item to the universal rail.
  onItemSelect = null,
  // Optional callback fired when the user drags a selection box in
  // swim-lane mode and clicks "Apply as filter". The parent Comms
  // Center wires this into its scrubber so the picked window narrows
  // the rest of the page (threads + thread view) too.
  onApplyWindow = null,
}) {
  const [expanded, setExpanded] = useState(true);
  // List | Lanes ↓ | Lanes → renderer selector. Same data either
  // way — only the visual layout differs.
  const [viewMode, setViewMode] = useState('list'); // 'list' | 'swim-v' | 'swim-h'
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);

  // Sort: 'desc' (newest first), 'asc' (oldest first), or 'type' (group
  // by message/call/email then by timestamp DESC within group).
  const [sortMode, setSortMode] = useState('desc');
  const [sortOpen, setSortOpen] = useState(false);

  // Windowed rendering — track scroll position so only the visible
  // rows + a small overscan are mounted. Lets us bump limit from 300
  // to 2000 without DOM cost.
  const scrollRef = useRef(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportH, setViewportH] = useState(0);

  const hasEntitySelection =
    fromKeys.size > 0 || toKeys.size > 0 || participantKeys.size > 0;

  // Show per-row phone chip only when the case has more than one phone
  // — chip would just add noise on a single-phone case.
  const phoneCtx = usePhoneReports();
  const hasMultiplePhones = !!phoneCtx?.hasMultiple;

  useEffect(() => {
    if (!caseId || !expanded) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    // Server-side sort goes through for asc/desc; 'type' is sorted
    // client-side after fetch (the backend has no per-type bucket
    // ordering, and the row cap is the same in either case).
    const apiSort = sortMode === 'asc' ? 'asc' : 'desc';
    cellebriteCommsAPI.getBetween(caseId, {
      fromKeys: fromKeys.size > 0 ? [...fromKeys] : null,
      toKeys: toKeys.size > 0 ? [...toKeys] : null,
      participantKeys: participantKeys.size > 0 ? [...participantKeys] : null,
      types: [...types],
      reportKeys: reportKeys.size > 0 ? [...reportKeys] : null,
      sourceApps: sourceApps && sourceApps.size > 0 ? [...sourceApps] : null,
      startDate,
      endDate,
      limit: 2000,
      sort: apiSort,
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
  }, [caseId, fromKeys, toKeys, participantKeys, reportKeys, types, sourceApps, startDate, endDate, expanded, sortMode]);

  // Apply sort=type client-side (the backend doesn't bucket by type).
  // For asc/desc the backend already returns the correct order.
  const orderedItems = useMemo(() => {
    if (sortMode !== 'type') return items;
    const typeRank = { message: 0, call: 1, email: 2 };
    const arr = [...items];
    arr.sort((a, b) => {
      const r = (typeRank[a.type] ?? 99) - (typeRank[b.type] ?? 99);
      if (r !== 0) return r;
      // Within a type, newest first.
      const ta = a.timestamp || '';
      const tb = b.timestamp || '';
      return tb.localeCompare(ta);
    });
    return arr;
  }, [items, sortMode]);

  // Window calculation
  const overscan = 8;
  const totalHeight = orderedItems.length * ROW_HEIGHT;
  const startIdx = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - overscan);
  const endIdx = Math.min(
    orderedItems.length,
    Math.ceil((scrollTop + viewportH) / ROW_HEIGHT) + overscan,
  );
  const visibleItems = orderedItems.slice(startIdx, endIdx);
  const topPad = startIdx * ROW_HEIGHT;
  const bottomPad = Math.max(0, totalHeight - endIdx * ROW_HEIGHT);

  // Re-measure viewport on expand / data change
  useEffect(() => {
    if (!expanded) return;
    const el = scrollRef.current;
    if (!el) return;
    const measure = () => setViewportH(el.clientHeight || 0);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [expanded]);

  const contextLabel = hasEntitySelection
    ? 'between selected entities'
    : 'across all selected devices';

  return (
    <div
      className="border-t-2 border-owl-blue-200 bg-white flex-shrink-0 flex flex-col"
      style={{ height: expanded ? '33vh' : 'auto', minHeight: expanded ? '200px' : '32px' }}
    >
      <div className="flex items-center gap-2 px-4 py-1.5 text-xs text-light-700 border-b border-light-100 flex-shrink-0">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-2 flex-1 text-left hover:bg-light-50 -mx-1 px-1 rounded"
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
          <div className="inline-flex items-center bg-white border border-light-300 rounded overflow-hidden text-[11px] flex-shrink-0 mr-1">
            <button
              type="button"
              title="List view"
              onClick={() => setViewMode('list')}
              className={`px-1.5 py-0.5 inline-flex items-center gap-1 ${viewMode === 'list' ? 'bg-owl-blue-100 text-owl-blue-900' : 'text-light-700 hover:bg-light-100'}`}
            >
              <List className="w-3 h-3" /> List
            </button>
            <button
              type="button"
              title="Swim-lane (vertical)"
              onClick={() => setViewMode('swim-v')}
              className={`px-1.5 py-0.5 inline-flex items-center gap-1 border-l border-light-200 ${viewMode === 'swim-v' ? 'bg-owl-blue-100 text-owl-blue-900' : 'text-light-700 hover:bg-light-100'}`}
            >
              <LayoutPanelTop className="w-3 h-3" /> Lanes ↓
            </button>
            <button
              type="button"
              title="Swim-lane (horizontal)"
              onClick={() => setViewMode('swim-h')}
              className={`px-1.5 py-0.5 inline-flex items-center gap-1 border-l border-light-200 ${viewMode === 'swim-h' ? 'bg-owl-blue-100 text-owl-blue-900' : 'text-light-700 hover:bg-light-100'}`}
            >
              <LayoutPanelLeft className="w-3 h-3" /> Lanes →
            </button>
          </div>
        )}
        {expanded && viewMode === 'list' && (
          <div className="relative flex-shrink-0">
            <button
              onClick={() => setSortOpen((v) => !v)}
              className="flex items-center gap-1 px-2 py-0.5 text-[11px] text-light-700 border border-light-300 rounded hover:bg-light-50"
              title="Sort order"
            >
              {sortMode === 'asc' ? (
                <><ArrowUpWideNarrow className="w-3 h-3" /> Oldest first</>
              ) : sortMode === 'type' ? (
                <><Layers className="w-3 h-3" /> By type</>
              ) : (
                <><ArrowDownWideNarrow className="w-3 h-3" /> Newest first</>
              )}
              <ChevronDown className="w-3 h-3" />
            </button>
            {sortOpen && (
              <>
                <div
                  className="fixed inset-0 z-10"
                  onClick={() => setSortOpen(false)}
                />
                <div className="absolute right-0 mt-1 z-20 bg-white border border-light-200 rounded shadow-lg py-1 min-w-[160px] text-[11px]">
                  {[
                    { key: 'desc', label: 'Newest first', icon: ArrowDownWideNarrow },
                    { key: 'asc', label: 'Oldest first', icon: ArrowUpWideNarrow },
                    { key: 'type', label: 'By type', icon: Layers },
                  ].map((opt) => {
                    const OptIcon = opt.icon;
                    const active = sortMode === opt.key;
                    return (
                      <button
                        key={opt.key}
                        onClick={() => { setSortMode(opt.key); setSortOpen(false); }}
                        className={`w-full flex items-center gap-1.5 px-2.5 py-1 text-left ${
                          active ? 'bg-owl-blue-50 text-owl-blue-800 font-medium' : 'hover:bg-light-50 text-light-700'
                        }`}
                      >
                        <OptIcon className="w-3 h-3" />
                        {opt.label}
                      </button>
                    );
                  })}
                </div>
              </>
            )}
          </div>
        )}
      </div>
      {expanded && (
        <div
          ref={scrollRef}
          className={`flex-1 min-h-0 ${viewMode === 'list' ? 'overflow-y-auto' : 'flex flex-col overflow-hidden'}`}
          onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
        >
          {loading && items.length === 0 ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-5 h-5 animate-spin text-light-400" />
            </div>
          ) : orderedItems.length === 0 ? (
            <div className="text-xs text-light-500 italic text-center py-6">
              No comms match the current filters
            </div>
          ) : viewMode !== 'list' ? (
            <CommsCrossTypeSwimLane
              items={orderedItems}
              orientation={viewMode === 'swim-h' ? 'horizontal' : 'vertical'}
              onItemSelect={(item) => {
                if (onJumpToThread) onJumpToThread(item);
                if (onItemSelect) onItemSelect(item);
              }}
              onApplyWindow={(win) => {
                if (onApplyWindow) onApplyWindow(win);
              }}
            />
          ) : (
            <div style={{ height: totalHeight, position: 'relative' }}>
              <div style={{ height: topPad }} />
              {visibleItems.map((item, i) => {
                // Compose row click: jump-to-thread (if caller provided it)
                // AND publish to the rail (if a rail-aware caller is wired).
                // Using a single click handler keeps the row affordance
                // unambiguous and avoids two rapid state updates fighting
                // each other when both are wired.
                const handleRowClick = (onJumpToThread || onItemSelect)
                  ? () => {
                      if (onJumpToThread) onJumpToThread(item);
                      if (onItemSelect) onItemSelect(item);
                    }
                  : null;
                return (
                  <TimelineRow
                    key={`${item.id || 'x'}-${startIdx + i}`}
                    item={item}
                    showPhoneChip={hasMultiplePhones}
                    onClick={handleRowClick}
                  />
                );
              })}
              <div style={{ height: bottomPad }} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function TimelineRow({ item, onClick, showPhoneChip = false }) {
  const Icon = item.type === 'call' ? Phone : item.type === 'email' ? Mail : MessageSquare;
  const color =
    item.type === 'call'
      ? 'text-emerald-600'
      : item.type === 'email'
      ? 'text-amber-600'
      : 'text-owl-blue-600';
  const from = item.sender?.name || '?';
  const to = (item.recipients && item.recipients[0]?.name) || '?';
  const extraTo = (item.recipients?.length || 0) > 1
    ? ` +${item.recipients.length - 1}`
    : '';
  const body = item.type === 'email' ? (item.subject || '') : (item.body || '');
  const typeLabel =
    item.type === 'call' ? `${item.call_type || 'call'} ${item.duration || ''}`.trim()
    : item.type === 'email' ? 'email'
    : 'message';

  // Two-line layout. Phone chip on the FAR LEFT (user feedback: easier
  // to scan device column). Sender → recipient lives on line 2 so a
  // long body never elbows it off-screen.
  return (
    <button
      onClick={onClick}
      style={{ height: ROW_HEIGHT }}
      className="w-full text-left flex flex-col justify-center gap-0.5 px-4 border-b border-light-100 hover:bg-light-50"
    >
      <div className="flex items-center gap-2 min-w-0">
        {showPhoneChip && item.report_key ? (
          <PhoneIdentityChip
            reportKey={item.report_key}
            variant="dense"
            className="flex-shrink-0"
          />
        ) : null}
        <Icon className={`w-3 h-3 flex-shrink-0 ${color}`} />
        <span className="text-[10px] text-light-500 w-28 flex-shrink-0 tabular-nums">
          {formatShortTime(item.timestamp)}
        </span>
        <span className="text-xs flex-shrink-0" title={item.source_app}>
          {appIconEmoji(item.source_app || item.type)}
        </span>
        <span className="flex-1 text-xs text-light-700 truncate">
          {previewBody(body, 120) || <span className="italic text-light-400">(no preview)</span>}
        </span>
      </div>
      <div className="flex items-center gap-1 min-w-0 pl-[18px]">
        <span className="text-[10px] text-light-500 truncate" title={`${from} → ${to}${extraTo} (${typeLabel})`}>
          <span className="text-light-700 font-medium">{from}</span>
          <span className="mx-1 text-light-400">→</span>
          <span className="text-light-700 font-medium">{to}{extraTo}</span>
          <span className="mx-1 text-light-400">·</span>
          <span className="italic">{typeLabel}</span>
        </span>
      </div>
    </button>
  );
}
