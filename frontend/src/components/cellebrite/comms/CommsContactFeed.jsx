/**
 * CommsContactFeed
 *
 * Inline (non-drawer) version of CommsContactDrawer's body. Renders
 * every call/message/email involving one contact across all phones.
 *
 * Two view modes, toggled at the top:
 *   - Chat   : interleaved bubble / row / card layout (the original)
 *   - Table  : flat row-per-event spreadsheet (CommsContactTable)
 *
 * Search:
 *   A CellebriteSearchInput sits above the body and applies the same
 *   parseQuery / matchItem engine used by Timeline + Comms-Center
 *   thread list, so `type:call from:John app:WhatsApp before:2023-01-15`
 *   etc. all work consistently. The matcher operates on the loaded
 *   items in memory — instant per-keystroke filtering with highlights.
 *
 * In-table filters (table mode only):
 *   Cells like App, Type, Date, Direction are clickable to narrow the
 *   table without leaving the drill. Filter state lives here so it
 *   survives toggling between Chat and Table modes.
 *
 * Used by:
 *   - CellebriteCommunicationView's breadcrumb drill pane (page-level)
 *   - CommsContactDrawer (legacy slide-in flyover) — still works,
 *     just with no onDrillName passed in (names are static there).
 */

import React, { useEffect, useMemo, useState } from 'react';
import { Loader2, Phone, MessageSquare, Mail, MessageCircle, Table2 } from 'lucide-react';
import { cellebriteCommsAPI } from '../../../services/api';
import CommsTypeFilter from './CommsTypeFilter';
import CommsMessageBubble from './CommsMessageBubble';
import CommsCallRow from './CommsCallRow';
import CommsEmailCard from './CommsEmailCard';
import CommsContactTable from './CommsContactTable';
import CellebriteSearchInput from '../shared/CellebriteSearchInput';
import AttachmentFilterToggle from '../shared/AttachmentFilterToggle';
import { useCellebriteTime } from '../shared/CellebriteTimezone';
import { usePhoneReports } from '../../../context/PhoneReportsContext';
import { buildSenderPalette } from './commsUtils';
import { parseQuery, matchItem } from '../../../utils/cellebriteSearch';

const DEFAULT_TYPES = ['message', 'call', 'email'];

export default function CommsContactFeed({
  caseId,
  contact,
  initialTypes = DEFAULT_TYPES,
  // Push a new drill frame in the parent breadcrumb stack.
  onDrillName = null,
}) {
  useCellebriteTime(); // re-render feed times when the zone toggles
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTypes, setActiveTypes] = useState(new Set(initialTypes));

  // Chat | Table view-mode toggle. Per-case localStorage so the
  // investigator's preference persists.
  const viewKey = `cb.communications.feedView.${caseId || 'unknown'}`;
  const [viewMode, setViewMode] = useState(() => {
    if (typeof window === 'undefined') return 'chat';
    try {
      const stored = window.localStorage.getItem(viewKey);
      return stored === 'table' ? 'table' : 'chat';
    } catch { return 'chat'; }
  });
  useEffect(() => {
    if (typeof window === 'undefined') return;
    try { window.localStorage.setItem(viewKey, viewMode); }
    catch { /* ignore */ }
  }, [viewKey, viewMode]);

  // In-table filter state lives here so toggling between Chat and
  // Table doesn't lose narrowing the user already applied.
  const [cellFilters, setCellFilters] = useState({});

  // Full search input — uses the shared parseQuery engine so the
  // syntax matches Timeline + Comms-Center thread search exactly.
  const [searchQuery, setSearchQuery] = useState('');
  const [hasAttachmentOnly, setHasAttachmentOnly] = useState(false);

  // Reset per-contact state when the contact changes (drilling into a
  // new person should start with a clean lens).
  useEffect(() => {
    setCellFilters({});
    setSearchQuery('');
    setHasAttachmentOnly(false);
  }, [contact?.person_key]);

  useEffect(() => {
    if (!caseId || !contact?.person_key) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    cellebriteCommsAPI
      .getContactFeed(caseId, contact.person_key, {
        types: [...activeTypes],
        hasAttachment: hasAttachmentOnly,
        limit: 2000,
      })
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.message || 'Failed to load contact comms');
        setData(null);
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, [caseId, contact?.person_key, activeTypes, hasAttachmentOnly]);

  const phoneCtx = usePhoneReports();
  const hasMultiplePhones = !!phoneCtx?.hasMultiple;
  const reports = phoneCtx?.reports || [];

  // Stable colour palette across the contact's feed.
  const palette = useMemo(() => {
    const seen = new Map();
    for (const it of data?.items || []) {
      const s = it.sender;
      if (s?.key && !seen.has(s.key)) {
        seen.set(s.key, { key: s.key, name: s.name || s.key, is_owner: !!s.is_owner });
      }
    }
    return buildSenderPalette([...seen.values()]);
  }, [data]);

  // -----------------------------------------------------------------
  // Filter pipeline.
  //
  // The raw `data.items` array gets passed through three stages:
  //   1. Full-text search (parseQuery + matchItem)
  //   2. In-table cell filters (app=, type=, date=, direction=)
  //   3. (Render stage decides chat vs table)
  //
  // We compute highlights from the search stage so both views can
  // render <mark>'d substrings.
  // -----------------------------------------------------------------
  const parsedQuery = useMemo(() => {
    const q = parseQuery(searchQuery);
    if (hasAttachmentOnly) q.operators = { ...q.operators, has: 'attachment' };
    return q;
  }, [searchQuery, hasAttachmentOnly]);

  const { searchFiltered, highlights } = useMemo(() => {
    if (!searchQuery && !hasAttachmentOnly) {
      return { searchFiltered: data?.items || [], highlights: [] };
    }
    const out = [];
    const allHighlights = new Set();
    for (const it of data?.items || []) {
      const m = matchItem(it, parsedQuery, 'event', reports);
      if (m.matches) {
        out.push(it);
        m.highlights.forEach((h) => allHighlights.add(h));
      }
    }
    return { searchFiltered: out, highlights: [...allHighlights] };
  }, [data, searchQuery, hasAttachmentOnly, parsedQuery, reports]);

  const cellFiltered = useMemo(() => {
    const filters = cellFilters || {};
    const keys = Object.keys(filters);
    if (keys.length === 0) return searchFiltered;
    return searchFiltered.filter((it) => {
      for (const k of keys) {
        const want = filters[k];
        if (!want) continue;
        if (k === 'app') {
          if ((it.source_app || '').toLowerCase() !== String(want).toLowerCase()) return false;
        } else if (k === 'type') {
          if ((it.type || '').toLowerCase() !== String(want).toLowerCase()) return false;
        } else if (k === 'date') {
          if ((it.timestamp || '').slice(0, 10) !== want) return false;
        } else if (k === 'direction') {
          if ((it.direction || '').toLowerCase() !== String(want).toLowerCase()) return false;
        }
      }
      return true;
    });
  }, [searchFiltered, cellFilters]);

  // Group by day + speaker runs (chat view only)
  const grouped = useMemo(() => {
    const out = [];
    let currentDay = null;
    let lastSenderKey = null;
    for (const item of cellFiltered) {
      const day = (item.timestamp || '').slice(0, 10) || '—';
      if (currentDay !== day) {
        out.push({ type: 'date-sep', day });
        currentDay = day;
        lastSenderKey = null;
      }
      if (item.type === 'message') {
        const senderKey = item.sender?.key || 'unknown';
        const isFirstInRun = senderKey !== lastSenderKey;
        out.push({ type: 'item', item, isFirstInRun });
        lastSenderKey = senderKey;
      } else {
        out.push({ type: 'item', item, isFirstInRun: true });
        lastSenderKey = null;
      }
    }
    return out;
  }, [cellFiltered]);

  // Counts (post-search, pre-cell-filter so the user sees how the
  // search itself affected the type distribution).
  const counts = useMemo(() => {
    return (searchFiltered || []).reduce((acc, it) => {
      acc[it.type] = (acc[it.type] || 0) + 1;
      return acc;
    }, {});
  }, [searchFiltered]);

  const totalRaw = data?.total ?? (data?.items?.length || 0);
  const totalMatched = cellFiltered.length;

  if (!contact?.person_key) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-light-500 italic">
        No contact selected.
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Filter row + view toggle + counts */}
      <div className="flex items-center gap-3 px-3 py-2 border-b border-light-200 bg-light-50 flex-shrink-0 flex-wrap">
        <CommsTypeFilter active={activeTypes} onChange={setActiveTypes} />

        {/* Chat | Table toggle */}
        <div className="inline-flex items-center bg-white border border-light-300 rounded overflow-hidden text-[11px]">
          <button
            type="button"
            onClick={() => setViewMode('chat')}
            className={`px-2 py-1 inline-flex items-center gap-1 ${
              viewMode === 'chat'
                ? 'bg-owl-blue-100 text-owl-blue-900'
                : 'text-light-700 hover:bg-light-100'
            }`}
            title="Chat view (bubbles + speaker runs)"
          >
            <MessageCircle className="w-3 h-3" />
            Chat
          </button>
          <button
            type="button"
            onClick={() => setViewMode('table')}
            className={`px-2 py-1 inline-flex items-center gap-1 border-l border-light-200 ${
              viewMode === 'table'
                ? 'bg-owl-blue-100 text-owl-blue-900'
                : 'text-light-700 hover:bg-light-100'
            }`}
            title="Table view (sortable row per event, clickable cells)"
          >
            <Table2 className="w-3 h-3" />
            Table
          </button>
        </div>

        <div className="flex-1" />
        {loading && <Loader2 className="w-4 h-4 animate-spin text-light-400" />}
        <div className="flex items-center gap-2 text-[11px] text-light-600">
          <span className="flex items-center gap-1">
            <Phone className="w-3 h-3 text-emerald-600" />
            {(counts.call || 0).toLocaleString()}
          </span>
          <span className="flex items-center gap-1">
            <MessageSquare className="w-3 h-3 text-blue-600" />
            {(counts.message || 0).toLocaleString()}
          </span>
          <span className="flex items-center gap-1">
            <Mail className="w-3 h-3 text-amber-600" />
            {(counts.email || 0).toLocaleString()}
          </span>
          <span className="text-light-500">·</span>
          <span className="text-light-700 font-medium">
            {totalMatched.toLocaleString()}
          </span>
          <span className="text-light-500">of {totalRaw.toLocaleString()}</span>
        </div>
      </div>

      {/* Full search input — same engine as Timeline / threads. */}
      <div className="px-3 py-2 border-b border-light-200 bg-white flex-shrink-0 flex items-center gap-2">
        <div className="flex-1 min-w-0">
          <CellebriteSearchInput
            value={searchQuery}
            onChange={setSearchQuery}
            placeholder='Search this contact — try type:call before:2023-01-15 app:WhatsApp "exact phrase"'
            matchCount={totalMatched}
            totalCount={data?.items?.length || 0}
            itemNoun="comm"
            focusOnSlash
          />
        </div>
        <AttachmentFilterToggle
          value={hasAttachmentOnly}
          onChange={setHasAttachmentOnly}
          className="flex-shrink-0"
        />
      </div>

      {/* Body — chat OR table */}
      {viewMode === 'table' ? (
        <CommsContactTable
          items={cellFiltered}
          caseId={caseId}
          onDrillName={onDrillName}
          highlights={highlights}
          cellFilters={cellFilters}
          onCellFiltersChange={setCellFilters}
        />
      ) : (
        <div className="flex-1 overflow-y-auto bg-gradient-to-b from-light-50 to-light-100 py-2">
          {error && <div className="p-4 text-xs text-red-600">{error}</div>}
          {!loading && !error && cellFiltered.length === 0 && (
            <div className="flex items-center justify-center h-full text-sm text-light-500 italic">
              No comms match the current filters.
            </div>
          )}
          {grouped.map((row, idx) => {
            if (row.type === 'date-sep') {
              return (
                <div key={`sep-${idx}`} className="flex items-center justify-center my-2">
                  <span className="text-[10px] bg-light-200 text-light-600 px-2 py-0.5 rounded-full">
                    {formatDay(row.day)}
                  </span>
                </div>
              );
            }
            const item = row.item;
            if (item.type === 'call') {
              return (
                <CommsCallRow
                  key={item.id ?? `${item.type}-${item.report_key ?? ''}-${item.timestamp ?? ''}-${idx}`}
                  item={item}
                  reportKey={item.report_key}
                  showPhoneChip={hasMultiplePhones}
                  caseId={caseId}
                />
              );
            }
            if (item.type === 'email') {
              return (
                <CommsEmailCard
                  key={item.id ?? `${item.type}-${item.report_key ?? ''}-${item.timestamp ?? ''}-${idx}`}
                  item={item}
                  reportKey={item.report_key}
                  showPhoneChip={hasMultiplePhones}
                  caseId={caseId}
                />
              );
            }
            return (
              <CommsMessageBubble
                key={item.id ?? `${item.type}-${item.report_key ?? ''}-${item.timestamp ?? ''}-${idx}`}
                item={item}
                palette={palette}
                showSenderName
                isFirstInRun={row.isFirstInRun}
                reportKey={item.report_key}
                showPhoneChip={hasMultiplePhones}
                caseId={caseId}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

function formatDay(d) {
  if (!d || d === '—') return '(no date)';
  try {
    const dt = new Date(d + 'T00:00:00');
    if (isNaN(dt.getTime())) return d;
    return dt.toLocaleDateString([], {
      weekday: 'short',
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return d;
  }
}
