import React, { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { Loader2, Map as MapIcon, Rows3, Columns2 } from 'lucide-react';
import { cellebriteEventsAPI } from '../../services/api';
import PhoneSelector from './shared/PhoneSelector';
import NoPhonesSelectedEmptyState from './shared/NoPhonesSelectedEmptyState';
import TabLoadingIndicator from './shared/TabLoadingIndicator';
import { usePhoneReports } from '../../context/PhoneReportsContext';
import EventTypeFilter from './events/EventTypeFilter';
import EventPlaybackBar from './events/EventPlaybackBar';
import EventMapPanel from './events/EventMapPanel';
import EventsTable from './events/EventsTable';
import EventTimelinePanel from './events/EventTimelinePanel';
import EventDetailDrawer from './events/EventDetailDrawer';
import IntersectionPanel from './events/IntersectionPanel';
import CellebriteSearchInput from './shared/CellebriteSearchInput';
import TimelineScrubber from './shared/TimelineScrubber';
import { deviceColor } from './events/eventUtils';
import { useChatContext } from '../../contexts/ChatContext';
import { buildEventsContext } from '../../utils/chatContextSummary';
import { parseQuery, matchItem } from '../../utils/cellebriteSearch';
import { useCellebriteStatus } from './shared/CellebriteStatusBar';

/**
 * Cellebrite Location & Event Center — orchestrates map + timeline + playback
 * + intersection detection across devices.
 */
export default function CellebriteEventCenter({ caseId, reports: reportsProp = [], isActive = true }) {
  // --- Phone selection: sourced from PhoneReportsContext when available so
  // the user's choice persists across tabs and refreshes. Falls back to the
  // prop-supplied reports when no provider is mounted (e.g. unit tests).
  const phoneCtx = usePhoneReports();
  const fallbackReports = useMemo(() => reportsProp || [], [reportsProp]);
  const fallbackSelection = useMemo(
    () => new Set(fallbackReports.map((r) => r.report_key)),
    [fallbackReports],
  );
  const reports = phoneCtx?.reports?.length ? phoneCtx.reports : fallbackReports;
  const selectedReportKeys = phoneCtx ? phoneCtx.selectedReportKeys : fallbackSelection;

  // --- Filter state ---
  const [activeEventTypes, setActiveEventTypes] = useState(new Set());
  const [onlyGeolocated, setOnlyGeolocated] = useState(false);
  // Scrubber-driven coarse window (Date | null). The string forms feed
  // the existing server-side filter and the IntersectionPanel.
  const [windowStart, setWindowStart] = useState(null);
  const [windowEnd, setWindowEnd] = useState(null);
  const startDate = windowStart ? toISODate(windowStart) : '';
  const endDate = windowEnd ? toISODate(windowEnd) : '';
  const [searchQuery, setSearchQuery] = useState('');

  // --- Data state ---
  const [eventTypes, setEventTypes] = useState([]);
  const [events, setEvents] = useState([]);
  const [tracks, setTracks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadingProgress, setLoadingProgress] = useState(0);
  const [loadingStage, setLoadingStage] = useState('');

  // --- Playback ---
  const [playheadTime, setPlayheadTime] = useState(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(60); // 60x = 1h real per sec wall
  const trailWindowMs = 30 * 60 * 1000; // 30 min

  // --- Selection / drawer / intersections ---
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [intersectionResults, setIntersectionResults] = useState({});
  const [intersectionCollapsed, setIntersectionCollapsed] = useState(false);

  // --- Phase 7: view mode (map | split | table) ---
  const [viewMode, setViewMode] = useState('map');

  // Pure in-memory search filter — synchronous per keystroke. The
  // server-side fetch is unaffected (it's gated on selectedReportKeys,
  // event types, and the scrubber window via startDate/endDate).
  const parsedQuery = useMemo(() => parseQuery(searchQuery), [searchQuery]);
  const filteredEvents = useMemo(() => {
    if (!searchQuery) return events;
    return events.filter((ev) => matchItem(ev, parsedQuery, 'event', reports).matches);
  }, [events, searchQuery, parsedQuery, reports]);

  // Derived: how many events have direct or nearest geolocation
  const geolocatedCount = useMemo(() => {
    let n = 0;
    for (const e of filteredEvents) {
      if (e.latitude != null && e.longitude != null) n += 1;
    }
    return n;
  }, [filteredEvents]);

  // Publish counts to the persistent status bar. The "geolocated" hint
  // makes it obvious how much of the displayed pool is map-renderable
  // without forcing the user to read the page header.
  useCellebriteStatus({
    isActive,
    total: events.length,
    displayed: filteredEvents.length,
    selected: selectedEvent ? 1 : 0,
    label: 'events',
    hint: loading
      ? (loadingStage || 'Loading…')
      : (events.length > 0
          ? `${geolocatedCount.toLocaleString()} geolocated`
          : null),
  });

  // View-aware AI context
  const rootRef = useRef(null);
  const { publish, clear } = useChatContext();

  // Publish view context for the assistant.
  // NOTE: `playheadTime` is deliberately excluded from the effect deps so
  // animation frames do not trigger a ChatContext publish on every tick
  // (which was starving the playback loop). The AI still sees the latest
  // playhead because it is read on send via a ref below.
  const playheadRef = useRef(playheadTime);
  useEffect(() => { playheadRef.current = playheadTime; }, [playheadTime]);

  useEffect(() => {
    publish({
      ...buildEventsContext({
        reports,
        selectedReportKeys,
        activeEventTypes,
        onlyGeolocated,
        startDate,
        endDate,
        playheadTime: playheadRef.current,
        events,
        selectedEvent,
      }),
      anchorRef: rootRef,
    });
  }, [
    publish,
    reports,
    selectedReportKeys,
    activeEventTypes,
    onlyGeolocated,
    startDate,
    endDate,
    events,
    selectedEvent,
  ]);

  useEffect(() => () => clear(), [clear]);

  const deviceColorOf = useCallback(
    (key) => deviceColor(key, reports),
    [reports]
  );

  // Fetch event types when report set changes
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
        // On first load, enable everything
        setActiveEventTypes((prev) => {
          if (prev.size > 0) return prev;
          return new Set(types.map((t) => t.event_type));
        });
      })
      .catch(() => {
        if (!cancelled) setEventTypes([]);
      });
    return () => {
      cancelled = true;
    };
  }, [caseId, selectedReportKeys]);

  // Fetch events + tracks when filters change (debounced).
  //
  // Phased fetch: one events call per active event type, plus one
  // tracks call. The progress bar advances as each Neo4j round-trip
  // resolves so the user can see real movement on slow loads. Per-type
  // limit stays at 5000.
  useEffect(() => {
    if (!caseId) return;
    if (activeEventTypes.size === 0) {
      setEvents([]);
      setTracks([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setLoadingProgress(0);
    setLoadingStage('');
    setEvents([]);
    const reportKeysArr = selectedReportKeys.size > 0 ? [...selectedReportKeys] : null;
    const typesArr = [...activeEventTypes];
    const totalSteps = typesArr.length + 1; // +1 for tracks

    const t = setTimeout(() => {
      (async () => {
        const aggregated = [];
        for (let i = 0; i < typesArr.length; i += 1) {
          if (cancelled) return;
          const etype = typesArr[i];
          setLoadingStage(`Loading ${etype.replace('_', ' ')} events`);
          try {
            // eslint-disable-next-line no-await-in-loop
            const data = await cellebriteEventsAPI.getEvents(caseId, {
              reportKeys: reportKeysArr,
              eventTypes: [etype],
              startDate: startDate || null,
              endDate: endDate || null,
              onlyGeolocated,
              limit: 5000,
            });
            if (cancelled) return;
            aggregated.push(...(data.events || []));
          } catch {
            // Skip failed stages so a single broken type doesn't
            // blank the map.
          }
          setLoadingProgress(Math.round(((i + 1) / totalSteps) * 100));
        }

        if (cancelled) return;
        setEvents(aggregated);

        setLoadingStage('Loading device tracks');
        try {
          const trData = await cellebriteEventsAPI.getTracks(caseId, {
            reportKeys: reportKeysArr,
            startDate: startDate || null,
            endDate: endDate || null,
          });
          if (cancelled) return;
          setTracks(trData.tracks || []);
        } catch {
          if (!cancelled) setTracks([]);
        }

        if (cancelled) return;
        setLoadingProgress(100);
        setLoading(false);
        setLoadingStage('');
      })();
    }, 300);

    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [caseId, selectedReportKeys, activeEventTypes, onlyGeolocated, startDate, endDate]);

  // Derive list of active intersection match centres (for map flagging)
  const activeIntersectionMatches = useMemo(() => {
    const out = [];
    for (const r of Object.values(intersectionResults)) {
      for (const m of r?.matches || []) {
        out.push({ ...m, method: r.method });
      }
    }
    return out;
  }, [intersectionResults]);

  // Jump to an intersection match
  const handleJumpToMatch = useCallback(
    (match) => {
      if (match.start_time) {
        const t = new Date(match.start_time);
        if (!isNaN(t.getTime())) setPlayheadTime(t);
      }
      if (match.evidence && match.evidence.length > 0) {
        // Open drawer for the first evidence event
        setSelectedEvent({
          id: match.evidence[0].event_id,
          node_key: match.evidence[0].event_id,
          label: match.evidence[0].label,
          timestamp: match.evidence[0].timestamp,
          latitude: match.evidence[0].latitude,
          longitude: match.evidence[0].longitude,
          event_type:
            match.method === 'spatial'
              ? 'location'
              : match.method === 'cell_tower'
              ? 'cell_tower'
              : match.method === 'wifi'
              ? 'wifi'
              : 'message',
        });
      }
    },
    []
  );

  if (phoneCtx?.noneSelected) {
    return (
      <div ref={rootRef} className="flex flex-col h-full min-h-0 bg-white">
        <PhoneSelector />
        <NoPhonesSelectedEmptyState />
      </div>
    );
  }

  return (
    <div ref={rootRef} className="flex flex-col h-full min-h-0 bg-white">
      {/* Device selector — global across Cellebrite tabs */}
      <PhoneSelector />

      {/* Type filter + view mode */}
      <div className="flex items-center gap-3 px-3 py-2 border-b border-light-200 bg-light-50 flex-shrink-0 overflow-x-auto">
        <EventTypeFilter
          types={eventTypes}
          active={activeEventTypes}
          onChange={setActiveEventTypes}
          onlyGeolocated={onlyGeolocated}
          onOnlyGeolocatedChange={setOnlyGeolocated}
        />
        <div className="flex-1" />
        {loading && <Loader2 className="w-4 h-4 animate-spin text-light-400" />}
        <span className="text-xs text-light-500 flex-shrink-0">
          {searchQuery
            ? `${filteredEvents.length.toLocaleString()} of ${events.length.toLocaleString()}`
            : `${events.length.toLocaleString()}`} event{events.length === 1 ? '' : 's'}
          {geolocatedCount < filteredEvents.length && (
            <>
              {' '}
              · <span className="text-light-400">{geolocatedCount.toLocaleString()} geolocated</span>
            </>
          )}
        </span>
        {/* View mode toggle */}
        <div className="flex items-center rounded border border-light-300 overflow-hidden flex-shrink-0">
          <ViewModeButton mode="map" current={viewMode} onClick={setViewMode} icon={MapIcon} label="Map" />
          <ViewModeButton mode="split" current={viewMode} onClick={setViewMode} icon={Columns2} label="Split" />
          <ViewModeButton mode="table" current={viewMode} onClick={setViewMode} icon={Rows3} label="Table" />
        </div>
      </div>

      {/* Histogram scrubber — replaces the old date-picker pair. Drives
          the server-side coarse filter via startDate/endDate. */}
      <TimelineScrubber
        items={events}
        windowStart={windowStart}
        windowEnd={windowEnd}
        onWindowChange={(s, e) => { setWindowStart(s); setWindowEnd(e); }}
      />

      {/* Wide search bar */}
      <div className="px-3 py-2 border-b border-light-200 bg-white flex-shrink-0">
        <CellebriteSearchInput
          value={searchQuery}
          onChange={setSearchQuery}
          placeholder='Search events — try type:location app:WhatsApp from:John before:2023-01-15'
          matchCount={filteredEvents.length}
          totalCount={events.length}
          itemNoun="event"
          focusOnSlash
        />
      </div>

      {/* Main: map / split / table + intersection panel.
          During the initial load (no events yet) render a prominent
          progress indicator instead of an empty map — Neo4j event queries
          can take long enough on first load that a small corner spinner
          is easy to miss. */}
      {loading && events.length === 0 ? (
        <div className="flex-1 min-h-0">
          <TabLoadingIndicator
            label="Loading phone events"
            progress={loadingProgress}
            stage={loadingStage}
          />
        </div>
      ) : (
      <div className="flex flex-1 min-h-0">
        <div className="flex-1 flex flex-col min-h-0">
          {viewMode === 'map' && (
            <EventMapPanel
              events={filteredEvents}
              tracks={tracks}
              playheadTime={playheadTime}
              trailWindowMs={trailWindowMs}
              isPlaying={isPlaying}
              selectedEventId={selectedEvent?.id || selectedEvent?.node_key}
              onEventClick={setSelectedEvent}
              intersectionMatches={activeIntersectionMatches}
              deviceColorOf={deviceColorOf}
              isActive={isActive}
            />
          )}
          {viewMode === 'split' && (
            <>
              <div className="flex-1 min-h-0 border-b border-light-200">
                <EventMapPanel
                  events={events}
                  tracks={tracks}
                  playheadTime={playheadTime}
                  trailWindowMs={trailWindowMs}
                  isPlaying={isPlaying}
                  selectedEventId={selectedEvent?.id || selectedEvent?.node_key}
                  onEventClick={setSelectedEvent}
                  intersectionMatches={activeIntersectionMatches}
                  deviceColorOf={deviceColorOf}
                  isActive={isActive}
                />
              </div>
              <div className="flex-1 min-h-0">
                <EventsTable
                  events={filteredEvents}
                  reports={reports}
                  playheadTime={playheadTime}
                  isPlaying={isPlaying}
                  selectedEventId={selectedEvent?.id || selectedEvent?.node_key}
                  onEventClick={setSelectedEvent}
                />
              </div>
            </>
          )}
          {viewMode === 'table' && (
            <EventsTable
              events={filteredEvents}
              reports={reports}
              playheadTime={playheadTime}
              isPlaying={isPlaying}
              selectedEventId={selectedEvent?.id || selectedEvent?.node_key}
              onEventClick={setSelectedEvent}
            />
          )}
        </div>
        <IntersectionPanel
          caseId={caseId}
          reportKeys={selectedReportKeys.size > 0 ? [...selectedReportKeys] : null}
          startDate={startDate || null}
          endDate={endDate || null}
          results={intersectionResults}
          onResult={(method, result) =>
            setIntersectionResults((prev) => ({ ...prev, [method]: result }))
          }
          onJumpToMatch={handleJumpToMatch}
          collapsed={intersectionCollapsed}
          onToggleCollapsed={setIntersectionCollapsed}
        />
      </div>
      )}

      {/* Playback bar */}
      <EventPlaybackBar
        events={filteredEvents}
        playheadTime={playheadTime}
        setPlayheadTime={setPlayheadTime}
        isPlaying={isPlaying}
        setIsPlaying={setIsPlaying}
        playbackSpeed={playbackSpeed}
        setPlaybackSpeed={setPlaybackSpeed}
      />

      {/* Timeline (bottom third) */}
      <div className="flex-shrink-0" style={{ height: '30vh', minHeight: 180 }}>
        <EventTimelinePanel
          events={filteredEvents}
          reports={reports}
          selectedReportKeys={selectedReportKeys}
          playheadTime={playheadTime}
          setPlayheadTime={setPlayheadTime}
          onEventClick={setSelectedEvent}
          deviceColorOf={deviceColorOf}
        />
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

function ViewModeButton({ mode, current, onClick, icon: Icon, label }) {
  const active = current === mode;
  return (
    <button
      onClick={() => onClick(mode)}
      className={`flex items-center gap-1 px-2 py-1 text-[11px] transition-colors ${
        active
          ? 'bg-owl-blue-100 text-owl-blue-800'
          : 'bg-white text-light-600 hover:bg-light-50'
      }`}
      title={label}
    >
      <Icon className="w-3 h-3" />
      <span>{label}</span>
    </button>
  );
}

/** yyyy-mm-dd in local time — feeds the existing server-side date filter. */
function toISODate(d) {
  if (!(d instanceof Date) || isNaN(d.getTime())) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
