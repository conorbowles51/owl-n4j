import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { cellebriteEventsAPI } from '../../services/api';
import PhoneSelector from './shared/PhoneSelector';
import NoPhonesSelectedEmptyState from './shared/NoPhonesSelectedEmptyState';
import TabLoadingIndicator from './shared/TabLoadingIndicator';
import { usePhoneReports } from '../../context/PhoneReportsContext';
import EventTypeFilter from './events/EventTypeFilter';
import { useCellebriteSelection } from './shared/CellebriteSelectionContext';
import PhoneIdentityChip from './shared/PhoneIdentityChip';
import CellebriteSearchInput from './shared/CellebriteSearchInput';
import TimelineScrubber from './shared/TimelineScrubber';
import HighlightedText from './shared/HighlightedText';
import { parseQuery, matchItem } from '../../utils/cellebriteSearch';
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
  // Scrubber window — Date objects, both null = show everything.
  // Tracked alongside string forms passed to the API so we can keep the
  // server-side coarse filter without re-deriving strings everywhere.
  const [windowStart, setWindowStart] = useState(null);
  const [windowEnd, setWindowEnd] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');

  // --- Data state ---
  const [eventTypes, setEventTypes] = useState([]);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadingProgress, setLoadingProgress] = useState(0);
  const [loadingStage, setLoadingStage] = useState('');

  // --- Selection ---
  // Selection drives the universal selection flyout via the
  // CellebriteSelectionContext — replaces the legacy slide-over
  // EventDetailDrawer that used to mount here. Avoids double-call
  // (drawer + flyout) on every row click.
  const { selectEntity } = useCellebriteSelection();
  const [selectedEvent, setSelectedEvent] = useState(null);

  // ISO yyyy-mm-dd derived from the scrubber window, sent to the
  // server-side filter so we don't pull data we'll never display.
  const startDate = windowStart ? toISODate(windowStart) : '';
  const endDate = windowEnd ? toISODate(windowEnd) : '';

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

  // Fetch events whenever the *server-side* filters change. Search is
  // applied in-memory in a useMemo below, so adding it here would
  // pointlessly re-run the Cypher round-trip on every keystroke.
  //
  // Phased fetch: one call per active event type so we can show real
  // progress as each Neo4j query resolves. Per-type LIMIT keeps each
  // call to a manageable size (the previous single call asked for
  // limit=500000 which routinely never completed on busy cases).
  useEffect(() => {
    if (!caseId) return;
    if (activeEventTypes.size === 0) {
      setEvents([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setLoadingProgress(0);
    setLoadingStage('');
    setEvents([]);
    const reportKeysArr = selectedReportKeys.size > 0 ? [...selectedReportKeys] : null;
    const stages = [...activeEventTypes];

    const t = setTimeout(() => {
      (async () => {
        const aggregated = [];
        // A Neo4j node can carry multiple event-type labels (e.g. a
        // cell-tower ping that's also a location), so the same event
        // can come back from more than one per-type stage. Dedupe by
        // id so React keys stay unique and counts aren't inflated.
        const seen = new Set();
        for (let i = 0; i < stages.length; i += 1) {
          if (cancelled) return;
          const etype = stages[i];
          setLoadingStage(`Loading ${etype.replace('_', ' ')} events`);
          try {
            // eslint-disable-next-line no-await-in-loop
            const data = await cellebriteEventsAPI.getEvents(caseId, {
              reportKeys: reportKeysArr,
              eventTypes: [etype],
              startDate: startDate || null,
              endDate: endDate || null,
              onlyGeolocated: false,
              limit: 5000,
            });
            if (cancelled) return;
            for (const ev of (data.events || [])) {
              const key = ev.id || ev.node_key;
              if (key) {
                if (seen.has(key)) continue;
                seen.add(key);
              }
              aggregated.push(ev);
            }
          } catch {
            // Skip failed stages so a single broken type doesn't
            // blank out the whole timeline.
          }
          setLoadingProgress(Math.round(((i + 1) / stages.length) * 100));
        }
        if (cancelled) return;
        setEvents(aggregated);
        setLoading(false);
        setLoadingStage('');
      })();
    }, 250);

    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [caseId, selectedReportKeys, activeEventTypes, startDate, endDate]);

  // Parsed query is shared by the matcher + the row highlighter.
  const parsedQuery = useMemo(() => parseQuery(searchQuery), [searchQuery]);

  // Pure in-memory filter — runs synchronously on every keystroke
  // because the events array is already loaded. No network calls.
  const { filteredEvents, highlights } = useMemo(() => {
    if (!searchQuery) {
      return { filteredEvents: events, highlights: [] };
    }
    const out = [];
    const allHighlights = new Set();
    for (const ev of events) {
      const m = matchItem(ev, parsedQuery, 'event', reports);
      if (m.matches) {
        out.push(ev);
        m.highlights.forEach((h) => allHighlights.add(h));
      }
    }
    return { filteredEvents: out, highlights: Array.from(allHighlights) };
  }, [events, searchQuery, parsedQuery, reports]);

  // Sort newest-first by default; group by date for visual rhythm
  const groupedByDay = useMemo(() => {
    const sorted = [...filteredEvents].sort((a, b) => {
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
  }, [filteredEvents]);

  // Scroll-to-bucket from scrubber bar clicks. Each day header carries
  // data-day so we can find it cheaply.
  const bodyRef = useRef(null);
  const scrollToDate = useCallback((bucketStart) => {
    const day = toISODate(bucketStart);
    const root = bodyRef.current;
    if (!root) return;
    // Find the first day header whose ISO is <= the bucket date (lists
    // are newest-first so an exact match isn't always present).
    const headers = root.querySelectorAll('[data-day]');
    let target = null;
    for (const h of headers) {
      const d = h.getAttribute('data-day');
      if (!d || d === '—') continue;
      if (d <= day) { target = h; break; }
    }
    if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, []);

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

      {/* Type filter row */}
      <div className="flex items-center gap-3 px-3 py-2 border-b border-light-200 bg-light-50 flex-shrink-0 overflow-x-auto">
        <EventTypeFilter
          types={eventTypes}
          active={activeEventTypes}
          onChange={setActiveEventTypes}
          onlyGeolocated={false}
          onOnlyGeolocatedChange={() => {}}
        />
        <div className="flex-1" />
      </div>

      {/* Histogram scrubber — replaces the old date-picker pair */}
      <TimelineScrubber
        items={events}
        windowStart={windowStart}
        windowEnd={windowEnd}
        onWindowChange={(s, e) => { setWindowStart(s); setWindowEnd(e); }}
        onBarClick={(bucketStart) => scrollToDate(bucketStart)}
      />

      {/* Wide search bar */}
      <div className="px-3 py-2 border-b border-light-200 bg-white flex-shrink-0">
        <CellebriteSearchInput
          value={searchQuery}
          onChange={setSearchQuery}
          placeholder='Search events — try type:call from:John app:WhatsApp before:2023-01-15'
          matchCount={filteredEvents.length}
          totalCount={events.length}
          itemNoun="event"
          focusOnSlash
        />
      </div>

      {/* Body — grouped chronological list */}
      <div ref={bodyRef} className="flex-1 min-h-0 overflow-y-auto">
        {loading && events.length === 0 ? (
          <TabLoadingIndicator
            label="Loading timeline events"
            progress={loadingProgress}
            stage={loadingStage}
          />
        ) : filteredEvents.length === 0 && !loading ? (
          <div className="flex items-center justify-center h-full text-sm text-light-500 italic">
            {events.length === 0
              ? 'No phone events match the current filters.'
              : `No events match "${searchQuery}".`}
          </div>
        ) : (
          <div className="px-4 py-3">
            {groupedByDay.map((group) => (
              <div key={group.day} data-day={group.day} className="mb-4">
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
                      highlights={highlights}
                      onClick={() => {
                        setSelectedEvent(ev);
                        selectEntity({
                          type: ev.event_type || 'event',
                          id: ev.id || ev.node_key,
                          caseId,
                          reportKey: ev.device_report_key,
                          payload: { ...ev, node_key: ev.node_key || ev.id },
                          source: 'timeline',
                        });
                      }}
                    />
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Selection flyout is rendered globally by CellebriteView —
          we just publish via selectEntity(). No local drawer mount. */}
    </div>
  );
}

function TimelineRow({ ev, reports, onClick, showPhoneChip = false, highlights = [] }) {
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
  const hasHighlights = highlights && highlights.length > 0;

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
            <span className="text-[10px] text-light-500">
              · {hasHighlights
                ? <HighlightedText text={ev.source_app} highlights={highlights} />
                : ev.source_app}
            </span>
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
          <div className="text-xs text-light-700 truncate">
            {hasHighlights
              ? <HighlightedText text={direction} highlights={highlights} />
              : direction}
          </div>
        )}
        {ev.summary && (
          <div
            className="text-xs text-light-600 truncate"
            title={ev.summary}
          >
            {hasHighlights
              ? <HighlightedText text={ev.summary} highlights={highlights} />
              : ev.summary}
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

/**
 * yyyy-mm-dd in *local* time (so the bar-click → day-header lookup
 * matches the way `groupedByDay` derives its key from
 * `(ev.timestamp || '').slice(0, 10)`).
 */
function toISODate(d) {
  if (!(d instanceof Date) || isNaN(d.getTime())) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
