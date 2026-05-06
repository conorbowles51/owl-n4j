import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { Loader2, Search, Calendar } from 'lucide-react';
import { cellebriteEventsAPI } from '../../services/api';
import PhoneSelector from './shared/PhoneSelector';
import NoPhonesSelectedEmptyState from './shared/NoPhonesSelectedEmptyState';
import { usePhoneReports } from '../../context/PhoneReportsContext';
import EventTypeFilter from './events/EventTypeFilter';
import EventDetailDrawer from './events/EventDetailDrawer';
import PhoneIdentityChip from './shared/PhoneIdentityChip';
import {
  EVENT_COLORS,
  EVENT_ICONS,
  EVENT_LABELS,
  formatTs,
  parseTs,
  deviceColor as deviceColorOf,
} from './events/eventUtils';

/**
 * Cellebrite Timeline tab — phone-activity feed.
 *
 * Vertical, chronological list of every phone event we ingest: calls,
 * messages, emails, locations, cell-tower pings, WiFi associations, power
 * events, app sessions, page visits, searches, meetings. Built on the
 * unified /api/cellebrite/events feed so it stays consistent with the
 * Location & Events tab.
 *
 * Differs from the Events Center by being purely chronological and by
 * focusing on day-by-day behavioural patterns — no map, no playback, just
 * a clean activity log the investigator can scan and search.
 */
export default function CellebriteTimeline({ caseId, reports: reportsProp }) {
  // --- Phone selection: sourced from PhoneReportsContext when available so
  // the selection persists across tabs and refreshes. ---
  const phoneCtx = usePhoneReports();
  const fallbackReports = useMemo(() => reportsProp || [], [reportsProp]);
  const fallbackSelection = useMemo(
    () => new Set(fallbackReports.map((r) => r.report_key)),
    [fallbackReports],
  );
  const reports = phoneCtx?.reports?.length ? phoneCtx.reports : fallbackReports;
  const selectedReportKeys = phoneCtx ? phoneCtx.selectedReportKeys : fallbackSelection;

  const [activeEventTypes, setActiveEventTypes] = useState(new Set());
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');

  // --- Data state ---
  const [eventTypes, setEventTypes] = useState([]);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(false);

  // --- Selection ---
  const [selectedEvent, setSelectedEvent] = useState(null);

  // Debounce search
  useEffect(() => {
    const id = setTimeout(() => setDebouncedSearch(searchQuery), 300);
    return () => clearTimeout(id);
  }, [searchQuery]);

  // Fetch event types when device set changes (powers the type filter chips)
  useEffect(() => {
    if (!caseId) return;
    let cancelled = false;
    const keys = selectedReportKeys.size > 0 ? [...selectedReportKeys] : null;
    cellebriteEventsAPI
      .getEventTypes(caseId, keys)
      .then((data) => {
        if (cancelled) return;
        const types = data.types || [];
        setEventTypes(types);
        // First time: enable everything
        setActiveEventTypes((prev) =>
          prev.size > 0 ? prev : new Set(types.map((t) => t.event_type))
        );
      })
      .catch(() => {
        if (!cancelled) setEventTypes([]);
      });
    return () => {
      cancelled = true;
    };
  }, [caseId, selectedReportKeys]);

  // Fetch events whenever filters change (debounced)
  useEffect(() => {
    if (!caseId) return;
    if (activeEventTypes.size === 0) {
      setEvents([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const reportKeysArr = selectedReportKeys.size > 0 ? [...selectedReportKeys] : null;
    const t = setTimeout(() => {
      cellebriteEventsAPI
        .getEvents(caseId, {
          reportKeys: reportKeysArr,
          eventTypes: [...activeEventTypes],
          startDate: startDate || null,
          endDate: endDate || null,
          onlyGeolocated: false,
          limit: 500000,
        })
        .then((data) => {
          if (cancelled) return;
          let evs = data.events || [];
          if (debouncedSearch) {
            const q = debouncedSearch.toLowerCase();
            evs = evs.filter((e) => {
              const haystack =
                (e.label || '') + ' ' +
                (e.summary || '') + ' ' +
                (e.source_app || '') + ' ' +
                (e.sender?.name || '') + ' ' +
                (e.counterpart?.name || '');
              return haystack.toLowerCase().includes(q);
            });
          }
          setEvents(evs);
          setLoading(false);
        })
        .catch(() => {
          if (cancelled) return;
          setEvents([]);
          setLoading(false);
        });
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [caseId, selectedReportKeys, activeEventTypes, startDate, endDate, debouncedSearch]);

  // Sort newest-first by default; group by date for visual rhythm
  const groupedByDay = useMemo(() => {
    const sorted = [...events].sort((a, b) => {
      const ta = a.timestamp ? new Date(a.timestamp).getTime() : 0;
      const tb = b.timestamp ? new Date(b.timestamp).getTime() : 0;
      return tb - ta;
    });
    const groups = [];
    let current = null;
    for (const ev of sorted) {
      const day = (ev.timestamp || '').slice(0, 10) || '—';
      if (!current || current.day !== day) {
        current = { day, events: [] };
        groups.push(current);
      }
      current.events.push(ev);
    }
    return groups;
  }, [events]);

  if (phoneCtx?.noneSelected) {
    return (
      <div className="flex flex-col h-full min-h-0 bg-white">
        <PhoneSelector />
        <NoPhonesSelectedEmptyState />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full min-h-0 bg-white">
      {/* Device selector — global across Cellebrite tabs */}
      <PhoneSelector />

      {/* Type filter + date + search */}
      <div className="flex items-center gap-3 px-3 py-2 border-b border-light-200 bg-light-50 flex-shrink-0 overflow-x-auto">
        <EventTypeFilter
          types={eventTypes}
          active={activeEventTypes}
          onChange={setActiveEventTypes}
          onlyGeolocated={false}
          onOnlyGeolocatedChange={() => {}}
        />
        <div className="h-4 w-px bg-light-300 flex-shrink-0" />
        <div className="flex items-center gap-1 text-xs flex-shrink-0">
          <Calendar className="w-3.5 h-3.5 text-light-500" />
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="px-1.5 py-0.5 text-xs border border-light-300 rounded focus:outline-none focus:border-owl-blue-400"
          />
          <span className="text-light-400">→</span>
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="px-1.5 py-0.5 text-xs border border-light-300 rounded focus:outline-none focus:border-owl-blue-400"
          />
        </div>
        <div className="relative flex-1 max-w-sm flex-shrink-0">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-light-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search events…"
            className="w-full pl-7 pr-2 py-1 text-xs border border-light-300 rounded focus:outline-none focus:border-owl-blue-400"
          />
        </div>
        <div className="flex-1" />
        {loading && <Loader2 className="w-4 h-4 animate-spin text-light-400" />}
        <span className="text-xs text-light-500 flex-shrink-0">
          {events.length.toLocaleString()} events
        </span>
      </div>

      {/* Body — grouped chronological list */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {events.length === 0 && !loading ? (
          <div className="flex items-center justify-center h-full text-sm text-light-500 italic">
            No phone events match the current filters.
          </div>
        ) : (
          <div className="px-4 py-3">
            {groupedByDay.map((group) => (
              <div key={group.day} className="mb-4">
                <div className="sticky top-0 z-10 bg-white border-b border-light-200 mb-2 pb-1 flex items-center gap-2">
                  <span className="text-[11px] font-semibold uppercase tracking-wide text-light-700">
                    {formatDayHeader(group.day)}
                  </span>
                  <span className="text-[10px] text-light-400">
                    {group.events.length} event{group.events.length === 1 ? '' : 's'}
                  </span>
                </div>
                <ul className="space-y-1">
                  {group.events.map((ev, idx) => (
                    <TimelineRow
                      key={ev.id || ev.node_key || idx}
                      ev={ev}
                      reports={reports}
                      showPhoneChip={reports.length > 1}
                      onClick={() => setSelectedEvent(ev)}
                    />
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Drawer */}
      {selectedEvent && (
        <EventDetailDrawer
          caseId={caseId}
          event={selectedEvent}
          onClose={() => setSelectedEvent(null)}
        />
      )}
    </div>
  );
}

function TimelineRow({ ev, reports, onClick, showPhoneChip = false }) {
  const Icon = EVENT_ICONS[ev.event_type] || EVENT_ICONS.location;
  const color = EVENT_COLORS[ev.event_type] || '#64748b';
  const dColor = deviceColorOf(ev.device_report_key, reports);
  const time = formatTs(ev.timestamp).slice(11) || '—';
  const sender = ev.sender?.name;
  const recipient =
    ev.counterpart?.name ||
    (Array.isArray(ev.recipients) && ev.recipients[0]?.name) ||
    null;
  let direction = '';
  if (sender && recipient) direction = `${sender} → ${recipient}`;
  else if (sender) direction = sender;
  else if (recipient) direction = `→ ${recipient}`;

  // Phone accent stripe — 4px coloured left border when there are
  // multiple phones in the case. Replaces the previous 2px ring around
  // the event-type dot, which was nearly invisible.
  const stripeStyle = showPhoneChip && ev.device_report_key
    ? {
        borderLeftWidth: '4px',
        borderLeftStyle: 'solid',
        borderLeftColor: dColor,
      }
    : undefined;

  return (
    <li
      onClick={onClick}
      style={stripeStyle}
      className="grid grid-cols-[80px_18px_1fr] items-start gap-2 py-1.5 pl-2 pr-2 rounded hover:bg-light-50 cursor-pointer"
    >
      <span className="text-[11px] tabular-nums text-light-500 pt-0.5">{time}</span>
      <span
        className="w-3 h-3 rounded-full mt-1 flex-shrink-0"
        style={{ background: color }}
      />
      <div className="min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          <Icon className="w-3 h-3 flex-shrink-0" style={{ color }} />
          <span className="text-[11px] font-medium text-light-800">
            {EVENT_LABELS[ev.event_type] || ev.event_type}
          </span>
          {ev.source_app && (
            <span className="text-[10px] text-light-500">· {ev.source_app}</span>
          )}
          {ev.direction && (
            <span className="text-[10px] text-light-500">· {ev.direction}</span>
          )}
          {ev.duration && (
            <span className="text-[10px] text-light-500">· {ev.duration}</span>
          )}
          {showPhoneChip && ev.device_report_key && (
            <PhoneIdentityChip
              reportKey={ev.device_report_key}
              variant="dense"
              className="ml-auto flex-shrink-0"
            />
          )}
        </div>
        {direction && (
          <div className="text-xs text-light-700 truncate">{direction}</div>
        )}
        {ev.summary && (
          <div
            className="text-xs text-light-600 truncate"
            title={ev.summary}
          >
            {ev.summary}
          </div>
        )}
      </div>
    </li>
  );
}

function formatDayHeader(day) {
  if (!day || day === '—') return '(no date)';
  try {
    const d = new Date(day + 'T00:00:00');
    if (isNaN(d.getTime())) return day;
    return d.toLocaleDateString([], {
      weekday: 'short',
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return day;
  }
}
