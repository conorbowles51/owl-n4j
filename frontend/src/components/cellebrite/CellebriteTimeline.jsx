import React, {
  useState,
  useEffect,
  useMemo,
  useRef,
  useCallback,
  forwardRef,
  useImperativeHandle,
} from 'react';
import { cellebriteEventsAPI } from '../../services/api';
import PhoneSelector from './shared/PhoneSelector';
import NoPhonesSelectedEmptyState from './shared/NoPhonesSelectedEmptyState';
import TabLoadingIndicator from './shared/TabLoadingIndicator';
import { usePhoneReports } from '../../context/PhoneReportsContext';
import EventTypeFilter from './events/EventTypeFilter';
import { useCellebriteSelection } from './shared/CellebriteSelectionContext';
import PhoneIdentityChip from './shared/PhoneIdentityChip';
import CellebriteSearchInput from './shared/CellebriteSearchInput';
import CollapsibleScrubber from './shared/CollapsibleScrubber';
import CommsMediaStrip from './comms/CommsMediaStrip';
import AttachmentFilterToggle from './shared/AttachmentFilterToggle';
import HighlightedText from './shared/HighlightedText';
import { phoneFromKey } from './shared/PersonName';
import { useCellebriteTime } from './shared/CellebriteTimezone';
import { List, LayoutPanelTop, LayoutPanelLeft, AlertTriangle, Loader2, ArrowDown, ArrowUp } from 'lucide-react';
import CellebriteTimelineSwimLane from './CellebriteTimelineSwimLane';
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
// Per-type body-fetch window. "Load more" grows the shared cap by this step
// (see pageLimit) so the feed reaches progressively further toward the full
// envelope total without switching to keyset/cursor pagination (S3-03).
const PAGE_STEP = 5000;

export default function CellebriteTimeline({ caseId, reports: reportsProp }) {
  // Day grouping + headers follow the view's selected timezone so a day is the
  // local calendar day, not the UTC day (which made days look like they end at
  // 8 PM). Consuming the hook re-groups live when the analyst flips the zone.
  const { dayKey: tzDayKey, tzId, offsetLabel: tzOffsetLabel } = useCellebriteTime();
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
  // "Has attachment" filter — applied via the shared search matcher
  // (injected into the parsed query so it composes with text search).
  const [hasAttachmentOnly, setHasAttachmentOnly] = useState(false);

  // View-mode toggle. The classic chronological list stays as the
  // default ('list'). The two swim-lane orientations share data with
  // the list — only the renderer changes, no extra fetches.
  const [viewMode, setViewMode] = useState('list'); // 'list' | 'swim-v' | 'swim-h'

  // Sort direction for the chronological list. 'desc' (default) shows
  // newest events first; 'asc' shows oldest first. Drives BOTH the
  // day-group order and the intra-day row order. Persisted per-case in
  // localStorage (mirrors the cb.* per-case key style used elsewhere).
  const sortDirKey = `cb.timeline.sortDir.${caseId || 'unknown'}`;
  const [sortDir, setSortDir] = useState(() => {
    if (typeof window === 'undefined') return 'desc';
    try {
      return window.localStorage.getItem(sortDirKey) === 'asc' ? 'asc' : 'desc';
    } catch { return 'desc'; }
  });
  useEffect(() => {
    if (typeof window === 'undefined') return;
    try { window.localStorage.setItem(sortDirKey, sortDir); }
    catch { /* ignore */ }
  }, [sortDir, sortDirKey]);

  // --- Data state ---
  const [eventTypes, setEventTypes] = useState([]);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadingProgress, setLoadingProgress] = useState(0);
  const [loadingStage, setLoadingStage] = useState('');
  // Which event types hit the per-type body cap (so we can tell the user,
  // honestly, that older events of those types aren't loaded — never silently
  // truncate an investigative view).
  const [truncatedTypes, setTruncatedTypes] = useState([]);
  // True when the body fetch came back empty BECAUSE requests failed (e.g. a
  // backend/connection timeout), not because there genuinely are no matches —
  // so we can show a retryable error instead of the misleading "no events".
  const [loadFailed, setLoadFailed] = useState(false);
  // Bump to force a re-fetch (Retry button).
  const [reloadKey, setReloadKey] = useState(0);
  // Progressive loading window. The body fetch is per-event-type, so a single
  // global offset is awkward (each type paginates independently). Instead we
  // grow a shared per-type cap by PAGE_STEP on each "Load more" and re-fetch —
  // this widens every type's window at once while leaving the existing dedupe,
  // truncation notice, scrubber, and search completely untouched. `loadingMore`
  // keeps the button in a pending state during the re-fetch.
  const [pageLimit, setPageLimit] = useState(PAGE_STEP);
  const [loadingMore, setLoadingMore] = useState(false);
  // Cheap server-side aggregation (true total + full min/max date + per-day
  // histogram) so the scrubber shows the honest full range/density even though
  // the body feed is capped per type. Loads async, independent of the body.
  const [envelope, setEnvelope] = useState(null);

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

  // Reset the progressive window to the first page whenever a server-side
  // filter changes — a new filter set means the previous "Load more" depth no
  // longer applies. Kept separate from the body-fetch effect so growing
  // pageLimit (via "Load more") doesn't reset itself.
  useEffect(() => {
    setPageLimit(PAGE_STEP);
  }, [caseId, selectedReportKeys, activeEventTypes, startDate, endDate, hasAttachmentOnly]);

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
    // A "Load more" re-fetch (pageLimit grown past the first page) keeps the
    // already-rendered events on screen and only flags the button as pending —
    // blanking the list + showing the full-screen spinner on every page would
    // be jarring. The first page (and any filter change, which resets pageLimit)
    // takes the normal loading path.
    const isLoadMore = pageLimit > PAGE_STEP;
    if (isLoadMore) {
      setLoadingMore(true);
    } else {
      setLoading(true);
      setLoadingProgress(0);
      setLoadingStage('');
      setLoadFailed(false);
      setEvents([]);
    }
    const reportKeysArr = selectedReportKeys.size > 0 ? [...selectedReportKeys] : null;
    const stages = [...activeEventTypes];

    const t = setTimeout(() => {
      (async () => {
        const aggregated = [];
        let errorCount = 0;
        // A Neo4j node can carry multiple event-type labels (e.g. a
        // cell-tower ping that's also a location), so the same event
        // can come back from more than one per-type stage. Dedupe by
        // id so React keys stay unique and counts aren't inflated.
        const seen = new Set();
        // Types whose body fetch hit the per-type cap — surfaced to the user
        // so the capped slice is never mistaken for the whole dataset.
        const truncated = new Set();
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
              hasAttachment: hasAttachmentOnly,
              limit: pageLimit,
            });
            if (cancelled) return;
            if (data.truncated) {
              for (const tt of (data.truncated_types || [etype])) truncated.add(tt);
            }
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
            // blank out the whole timeline — but remember it failed so an
            // all-empty result from errors reads as an error, not "no data".
            errorCount += 1;
          }
          setLoadingProgress(Math.round(((i + 1) / stages.length) * 100));
        }
        if (cancelled) return;
        setEvents(aggregated);
        setTruncatedTypes([...truncated]);
        setLoadFailed(aggregated.length === 0 && errorCount > 0);
        setLoading(false);
        setLoadingMore(false);
        setLoadingStage('');
      })();
    }, 250);

    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [caseId, selectedReportKeys, activeEventTypes, startDate, endDate, hasAttachmentOnly, reloadKey, pageLimit]);

  // Envelope fetch — true total + full min/max date + per-day histogram for
  // the scrubber. Deliberately NOT scoped to the scrubber window (startDate/
  // endDate): it must describe the WHOLE available range so the scrubber can
  // show what's outside the current window. Re-runs only when the device set
  // or active types change.
  useEffect(() => {
    if (!caseId || activeEventTypes.size === 0) {
      setEnvelope(null);
      return undefined;
    }
    let cancelled = false;
    const reportKeysArr = selectedReportKeys.size > 0 ? [...selectedReportKeys] : null;
    setEnvelope((e) => (e ? { ...e, loading: true } : { loading: true }));
    cellebriteEventsAPI
      .getEventsEnvelope(caseId, {
        reportKeys: reportKeysArr,
        eventTypes: [...activeEventTypes],
        hasAttachment: hasAttachmentOnly,
      })
      .then((data) => {
        if (cancelled) return;
        setEnvelope({
          minDate: data.min_date || undefined,
          maxDate: data.max_date || undefined,
          histogram: data.histogram || [],
          total: data.total || 0,
          loading: false,
        });
      })
      .catch(() => { if (!cancelled) setEnvelope(null); });
    return () => { cancelled = true; };
  }, [caseId, selectedReportKeys, activeEventTypes, hasAttachmentOnly]);

  // "Load more" availability + counts. More events exist when the envelope's
  // true total (for the active filters) exceeds what we've loaded AND at least
  // one type actually hit the cap (truncated) — without a truncated type the
  // envelope/body gap is just dedupe/rounding noise, not unloaded rows.
  const loadedCount = events.length;
  const totalCount = typeof envelope?.total === 'number' ? envelope.total : null;
  const hasMore =
    truncatedTypes.length > 0 &&
    totalCount != null &&
    totalCount > loadedCount;
  const handleLoadMore = useCallback(() => {
    setPageLimit((n) => n + PAGE_STEP);
  }, []);

  // The scrubber shows more than the loaded body slice whenever a type was
  // capped — flag it so the "All time" summary becomes honest.
  const scrubberEnvelope = useMemo(() => {
    if (!envelope) return null;
    return { ...envelope, hasMoreThanItems: truncatedTypes.length > 0 };
  }, [envelope, truncatedTypes]);

  // Parsed query is shared by the matcher + the row highlighter. The
  // "Has attachment" toggle is folded in as a has:attachment operator so it
  // composes with whatever the user typed.
  const parsedQuery = useMemo(() => {
    const q = parseQuery(searchQuery);
    if (hasAttachmentOnly) q.operators = { ...q.operators, has: 'attachment' };
    return q;
  }, [searchQuery, hasAttachmentOnly]);

  // Pure in-memory filter — runs synchronously on every keystroke
  // because the events array is already loaded. No network calls.
  const { filteredEvents, highlights } = useMemo(() => {
    if (!searchQuery && !hasAttachmentOnly) {
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
  }, [events, searchQuery, hasAttachmentOnly, parsedQuery, reports]);

  // Sort by the chosen direction; group by date for visual rhythm. Because
  // groups are emitted in encounter order, sorting the events ascending also
  // makes the day groups come out oldest-first (and vice-versa for desc).
  const groupedByDay = useMemo(() => {
    const sorted = [...filteredEvents].sort((a, b) => {
      const ta = a.timestamp ? new Date(a.timestamp).getTime() : 0;
      const tb = b.timestamp ? new Date(b.timestamp).getTime() : 0;
      return sortDir === 'asc' ? ta - tb : tb - ta;
    });
    const groups = [];
    let current = null;
    for (const ev of sorted) {
      // Bucket by the calendar day in the SELECTED zone (not the raw UTC
      // string), so an evening event near local midnight stays in its local
      // day instead of jumping a UTC day and looking out of order.
      const day = ev.timestamp ? tzDayKey(ev.timestamp) : '—';
      if (!current || current.day !== day) {
        current = { day, events: [] };
        groups.push(current);
      }
      current.events.push(ev);
    }
    return groups;
  }, [filteredEvents, tzDayKey, tzId, sortDir]);

  // Scroll-to-bucket from scrubber bar clicks. The list is windowed, so the
  // target day header may not be in the DOM — TimelineList exposes an
  // imperative scrollToDay() that scrolls by computed offset instead.
  const listRef = useRef(null);
  const scrollToDate = useCallback((bucketStart) => {
    // Guard like the old toISODate did: a bucket with a NaN start yields an
    // Invalid Date whose .toISOString() THROWS (RangeError) — that crash was
    // taking down the whole tab when narrowing/clicking the scrubber.
    if (!(bucketStart instanceof Date) || isNaN(bucketStart.getTime())) return;
    // Match the day-headers, which are keyed by the selected-zone calendar day.
    const day = tzDayKey(bucketStart.toISOString());
    listRef.current?.scrollToDay(day);
  }, [tzDayKey]);

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
        {/* Sort-direction toggle — flips both the day-group order and the
            intra-day row order. Default 'desc' = newest first. */}
        <button
          type="button"
          onClick={() => setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'))}
          title={sortDir === 'desc' ? 'Newest first (click for oldest first)' : 'Oldest first (click for newest first)'}
          className="inline-flex items-center gap-1 px-2 py-1 bg-white border border-light-300 rounded-md text-[11px] text-light-700 hover:bg-light-100 flex-shrink-0"
        >
          {sortDir === 'desc'
            ? <ArrowDown className="w-3 h-3" />
            : <ArrowUp className="w-3 h-3" />}
          {sortDir === 'desc' ? 'Newest first' : 'Oldest first'}
        </button>
        {/* View-mode toggle — same data, different rendering. */}
        <div className="inline-flex items-center bg-white border border-light-300 rounded-md overflow-hidden text-[11px] flex-shrink-0">
          <button
            type="button"
            title="List view"
            onClick={() => setViewMode('list')}
            className={`px-2 py-1 inline-flex items-center gap-1 ${viewMode === 'list' ? 'bg-owl-blue-100 text-owl-blue-900' : 'text-light-700 hover:bg-light-100'}`}
          >
            <List className="w-3 h-3" /> List
          </button>
          <button
            type="button"
            title="Swim-lane (vertical)"
            onClick={() => setViewMode('swim-v')}
            className={`px-2 py-1 inline-flex items-center gap-1 border-l border-light-200 ${viewMode === 'swim-v' ? 'bg-owl-blue-100 text-owl-blue-900' : 'text-light-700 hover:bg-light-100'}`}
          >
            <LayoutPanelTop className="w-3 h-3" /> Lanes ↓
          </button>
          <button
            type="button"
            title="Swim-lane (horizontal)"
            onClick={() => setViewMode('swim-h')}
            className={`px-2 py-1 inline-flex items-center gap-1 border-l border-light-200 ${viewMode === 'swim-h' ? 'bg-owl-blue-100 text-owl-blue-900' : 'text-light-700 hover:bg-light-100'}`}
          >
            <LayoutPanelLeft className="w-3 h-3" /> Lanes →
          </button>
        </div>
      </div>

      {/* Histogram scrubber — replaces the old date-picker pair. The
          envelope gives it the honest full range/density/total even though
          the body feed below is capped per type. */}
      <CollapsibleScrubber
        items={events}
        envelope={scrubberEnvelope}
        windowStart={windowStart}
        windowEnd={windowEnd}
        onWindowChange={(s, e) => { setWindowStart(s); setWindowEnd(e); }}
        onBarClick={(bucketStart) => scrollToDate(bucketStart)}
      />

      {/* Honest truncation notice — the body feed caps each event type at
          5,000 rows for responsiveness, so older events of capped types
          aren't loaded. Never let the capped slice pass as the whole set. */}
      {truncatedTypes.length > 0 && (
        <div className="px-3 py-1.5 border-b border-amber-200 bg-amber-50 text-[11px] text-amber-800 flex items-start gap-1.5 flex-shrink-0">
          <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
          <span>
            Showing the most recent <span className="font-semibold">{pageLimit.toLocaleString()}</span> per type for{' '}
            <span className="font-medium">{truncatedTypes.map((t) => EVENT_LABELS[t] || t).join(', ')}</span>
            {typeof envelope?.total === 'number' && envelope.total > events.length && (
              <> — <span className="font-semibold">{envelope.total.toLocaleString()}</span> events exist in total</>
            )}
            . Narrow the date range (drag the scrubber or use “Pick dates”) to load older events in that window.
          </span>
        </div>
      )}

      {/* Wide search bar + Has-attachment toggle */}
      <div className="px-3 py-2 border-b border-light-200 bg-white flex-shrink-0 flex items-center gap-2">
        <div className="flex-1 min-w-0">
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
        <AttachmentFilterToggle
          value={hasAttachmentOnly}
          onChange={setHasAttachmentOnly}
          className="flex-shrink-0"
        />
      </div>

      {/* Body — grouped chronological list OR swim-lane */}
      <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
        {loading && events.length === 0 ? (
          <TabLoadingIndicator
            label="Loading timeline events"
            progress={loadingProgress}
            stage={loadingStage}
          />
        ) : loadFailed && !loading ? (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-sm text-light-600">
            <AlertTriangle className="w-6 h-6 text-amber-500" />
            <span>Couldn’t load events — the request timed out or the connection dropped.</span>
            <button
              type="button"
              onClick={() => setReloadKey((k) => k + 1)}
              className="mt-1 px-3 py-1 rounded bg-owl-blue-600 text-white text-xs font-medium hover:bg-owl-blue-700"
            >
              Retry
            </button>
          </div>
        ) : filteredEvents.length === 0 && !loading ? (
          <div className="flex items-center justify-center h-full text-sm text-light-500 italic">
            {events.length === 0
              ? 'No phone events match the current filters.'
              : `No events match "${searchQuery}".`}
          </div>
        ) : viewMode !== 'list' ? (
          <CellebriteTimelineSwimLane
            caseId={caseId}
            events={filteredEvents}
            reports={reports}
            selectedReportKeys={selectedReportKeys}
            orientation={viewMode === 'swim-h' ? 'horizontal' : 'vertical'}
            onEventSelect={(ev) => {
              setSelectedEvent(ev);
              selectEntity({
                type: ev.event_type || 'event',
                id: ev.id || ev.node_key,
                caseId,
                reportKey: ev.device_report_key,
                payload: { ...ev, node_key: ev.node_key || ev.id },
                source: 'timeline-swim',
              });
            }}
            onApplyWindow={({ startTs, endTs }) => {
              setWindowStart(startTs ? new Date(startTs) : null);
              setWindowEnd(endTs ? new Date(endTs) : null);
            }}
          />
        ) : (
          <TimelineList
            ref={listRef}
            groups={groupedByDay}
            sortDir={sortDir}
            reports={reports}
            showPhoneChip={reports.length > 1}
            highlights={highlights}
            offsetLabel={tzOffsetLabel}
            hasMore={hasMore}
            loadingMore={loadingMore}
            loadedCount={loadedCount}
            totalCount={totalCount}
            onLoadMore={handleLoadMore}
            onRowClick={(ev) => {
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
        )}
      </div>

      {/* Selection flyout is rendered globally by CellebriteView —
          we just publish via selectEntity(). No local drawer mount. */}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Windowed list
//
// The feed can hold 60K+ events. Rendering one <li> per event mounted ~67K
// DOM rows and froze the tab for ~40s on load (and re-froze for ~12s every
// time a scrubber drag committed and the parent re-rendered the whole
// subtree). We window it like LocationsTable/EventsTable do.
//
// Rows are variable height (1–3 lines), so a single fixed ROW_PX would
// mis-position. We precompute each item's height deterministically from its
// fields, build a cumulative-offset array, and binary-search the visible
// slice. Day headers are flattened inline as their own items. Heights are
// set explicitly on each rendered item (with overflow hidden) so the
// measured layout matches the offsets exactly — no drift, no blank gaps.
// ---------------------------------------------------------------------------
const TL_HEADER_PX = 30;
const TL_ROW_BASE_PX = 34; // type line + vertical padding
const TL_ROW_LINE_PX = 18; // each extra line (direction / summary)
const TL_ROW_MEDIA_PX = 36; // compact media strip (28px thumb + margins), one line
const TL_OVERSCAN_PX = 600;

function timelineRowHeight(ev) {
  const sender = ev.sender?.name;
  const recipient =
    ev.counterpart?.name ||
    (Array.isArray(ev.recipients) && ev.recipients[0]?.name) ||
    null;
  const hasDirection = !!(sender || recipient);
  const hasSummary = !!ev.summary;
  const hasMedia = Array.isArray(ev.attachments) && ev.attachments.length > 0;
  return (
    TL_ROW_BASE_PX +
    (hasDirection ? TL_ROW_LINE_PX : 0) +
    (hasSummary ? TL_ROW_LINE_PX : 0) +
    (hasMedia ? TL_ROW_MEDIA_PX : 0)
  );
}

// First index i such that arr[i] >= x (arr ascending). O(log n).
function firstGE(arr, x) {
  let lo = 0;
  let hi = arr.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (arr[mid] < x) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

const TimelineList = forwardRef(function TimelineList(
  {
    groups,
    sortDir = 'desc',
    reports,
    showPhoneChip,
    highlights,
    onRowClick,
    offsetLabel,
    hasMore = false,
    loadingMore = false,
    loadedCount = 0,
    totalCount = null,
    onLoadMore,
  },
  ref,
) {
  const scrollRef = useRef(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportH, setViewportH] = useState(600);

  // Flatten the day groups into a single list of render items and precompute
  // the pixel offset where each one starts (offsets[i]). dayOffset maps a day
  // key → its header's offset for imperative scroll-to-day.
  const { items, offsets, total, dayOffset } = useMemo(() => {
    const it = [];
    const off = [];
    const dayMap = new Map();
    let acc = 0;
    for (const g of groups) {
      dayMap.set(g.day, acc);
      it.push({ kind: 'header', day: g.day, n: g.events.length });
      off.push(acc);
      acc += TL_HEADER_PX;
      for (const ev of g.events) {
        it.push({ kind: 'row', ev });
        off.push(acc);
        acc += timelineRowHeight(ev);
      }
    }
    return { items: it, offsets: off, total: acc, dayOffset: dayMap };
  }, [groups]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return undefined;
    setViewportH(el.clientHeight || 600);
    const onScroll = () => setScrollTop(el.scrollTop);
    el.addEventListener('scroll', onScroll, { passive: true });
    let ro;
    if (typeof ResizeObserver !== 'undefined') {
      ro = new ResizeObserver(() => setViewportH(el.clientHeight || 600));
      ro.observe(el);
    }
    return () => {
      el.removeEventListener('scroll', onScroll);
      if (ro) ro.disconnect();
    };
  }, []);

  useImperativeHandle(
    ref,
    () => ({
      scrollToDay(day) {
        const el = scrollRef.current;
        if (!el) return;
        // An exact match isn't guaranteed — jump to the nearest day in the
        // current sort direction. Desc (newest-first): first day at or BEFORE
        // the target. Asc (oldest-first): first day at or AFTER the target.
        // Either way offsets come from the same group order, so scroll stays
        // correct when sortDir flips.
        let targetDay = null;
        for (const g of groups) {
          if (!g.day || g.day === '—') continue;
          if (sortDir === 'asc' ? g.day >= day : g.day <= day) {
            targetDay = g.day;
            break;
          }
        }
        const off = targetDay != null ? dayOffset.get(targetDay) : 0;
        if (off != null) el.scrollTo({ top: off, behavior: 'smooth' });
      },
    }),
    [groups, dayOffset, sortDir],
  );

  const top = scrollTop - TL_OVERSCAN_PX;
  const bottom = scrollTop + viewportH + TL_OVERSCAN_PX;
  const startIdx = Math.max(0, firstGE(offsets, top) - 1);
  const endIdx = firstGE(offsets, bottom); // exclusive
  const topPad = offsets[startIdx] || 0;
  const bottomPad = Math.max(0, total - (endIdx < offsets.length ? offsets[endIdx] : total));
  const visible = items.slice(startIdx, endIdx);

  return (
    <div ref={scrollRef} className="h-full overflow-y-auto px-4 py-3">
      {topPad > 0 && <div style={{ height: topPad }} />}
      {visible.map((it, i) => {
        const idx = startIdx + i;
        if (it.kind === 'header') {
          return (
            <div
              key={`h:${it.day}`}
              data-day={it.day}
              style={{ height: TL_HEADER_PX }}
              className="bg-white border-b border-light-200 flex items-center gap-2 overflow-hidden"
            >
              <span className="text-[11px] font-semibold uppercase tracking-wide text-light-700">
                {formatDayHeader(it.day)}
              </span>
              {offsetLabel && it.day && it.day !== '—' && (
                <span className="text-[10px] font-normal text-light-400 normal-case">
                  · {offsetLabel(`${it.day}T00:00:00Z`)}
                </span>
              )}
              <span className="text-[10px] text-light-400">
                {it.n} event{it.n === 1 ? '' : 's'}
              </span>
            </div>
          );
        }
        const ev = it.ev;
        return (
          <div
            key={ev.id || ev.node_key || idx}
            style={{ height: timelineRowHeight(ev) }}
            className="overflow-hidden"
          >
            <TimelineRow
              ev={ev}
              reports={reports}
              showPhoneChip={showPhoneChip}
              highlights={highlights}
              onClick={() => onRowClick(ev)}
            />
          </div>
        );
      })}
      {bottomPad > 0 && <div style={{ height: bottomPad }} />}
      {hasMore && (
        <div className="flex flex-col items-center gap-1 py-4 border-t border-light-200 mt-2">
          <button
            type="button"
            onClick={onLoadMore}
            disabled={loadingMore}
            className="px-4 py-1.5 rounded bg-owl-blue-600 text-white text-xs font-medium hover:bg-owl-blue-700 disabled:opacity-60 disabled:cursor-default inline-flex items-center gap-1.5"
          >
            {loadingMore && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            {loadingMore ? 'Loading…' : 'Load more'}
          </button>
          {totalCount != null && (
            <span className="text-[11px] text-light-500">
              Showing {loadedCount.toLocaleString()} of {totalCount.toLocaleString()}
            </span>
          )}
        </div>
      )}
    </div>
  );
});

function TimelineRow({ ev, reports, onClick, showPhoneChip = false, highlights = [] }) {
  const Icon = EVENT_ICONS[ev.event_type] || EVENT_ICONS.location;
  const color = EVENT_COLORS[ev.event_type] || '#64748b';
  const dColor = deviceColorOf(ev.device_report_key, reports);
  const time = formatTs(ev.timestamp).slice(11) || '—';
  const fmtParty = (party) => {
    if (!party) return null;
    const num = phoneFromKey(party.key) || (Array.isArray(party.phone_numbers) && party.phone_numbers[0]) || null;
    const name = party.name || party.key;
    if (!name) return null;
    return num ? `${name} · ${num}` : name;
  };
  const sender = fmtParty(ev.sender);
  const recipient =
    fmtParty(ev.counterpart) ||
    (Array.isArray(ev.recipients) && fmtParty(ev.recipients[0])) ||
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
    <div
      onClick={onClick}
      style={stripeStyle}
      className="grid grid-cols-[80px_18px_1fr] items-start gap-2 py-1.5 pl-2 pr-2 rounded hover:bg-light-50 cursor-pointer"
    >
      <span className="text-[11px] tabular-nums text-light-500 pt-0.5" title={formatTs(ev.timestamp)}>{time}</span>
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
          <div className="text-xs text-light-700 truncate" title={direction}>
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
        {Array.isArray(ev.attachments) && ev.attachments.length > 0 && (
          // Compact preview only — the windowed row's fixed height +
          // overflow-hidden can't grow for inline expansion, so clicking the
          // strip bubbles to the row click and opens the detail flyout (which
          // renders the full media). Height budgeted in timelineRowHeight.
          <CommsMediaStrip attachments={ev.attachments} expandable={false} />
        )}
      </div>
    </div>
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
