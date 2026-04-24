import React, { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { Calendar, Loader2 } from 'lucide-react';
import { cellebriteEventsAPI } from '../../services/api';
import CommsDeviceSelector from './comms/CommsDeviceSelector';
import EventTypeFilter from './events/EventTypeFilter';
import EventPlaybackBar from './events/EventPlaybackBar';
import EventMapPanel from './events/EventMapPanel';
import EventTimelinePanel from './events/EventTimelinePanel';
import EventDetailDrawer from './events/EventDetailDrawer';
import IntersectionPanel from './events/IntersectionPanel';
import { deviceColor } from './events/eventUtils';
import { useChatContext } from '../../contexts/ChatContext';
import { buildEventsContext } from '../../utils/chatContextSummary';

/**
 * Cellebrite Location & Event Center — orchestrates map + timeline + playback
 * + intersection detection across devices.
 */
export default function CellebriteEventCenter({ caseId, reports = [] }) {
  // --- Filter state ---
  const [selectedReportKeys, setSelectedReportKeys] = useState(
    () => new Set(reports.map((r) => r.report_key))
  );
  const [activeEventTypes, setActiveEventTypes] = useState(new Set());
  const [onlyGeolocated, setOnlyGeolocated] = useState(false);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  // --- Data state ---
  const [eventTypes, setEventTypes] = useState([]);
  const [events, setEvents] = useState([]);
  const [tracks, setTracks] = useState([]);
  const [loading, setLoading] = useState(false);

  // --- Playback ---
  const [playheadTime, setPlayheadTime] = useState(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(60); // 60x = 1h real per sec wall
  const trailWindowMs = 30 * 60 * 1000; // 30 min

  // --- Selection / drawer / intersections ---
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [intersectionResults, setIntersectionResults] = useState({});
  const [intersectionCollapsed, setIntersectionCollapsed] = useState(false);

  // View-aware AI context
  const rootRef = useRef(null);
  const { publish, clear } = useChatContext();

  // Reset device selection when reports change
  useEffect(() => {
    setSelectedReportKeys(new Set(reports.map((r) => r.report_key)));
  }, [reports]);

  // Publish view context for the assistant
  useEffect(() => {
    publish({
      ...buildEventsContext({
        reports,
        selectedReportKeys,
        activeEventTypes,
        onlyGeolocated,
        startDate,
        endDate,
        playheadTime,
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
    playheadTime,
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

  // Fetch events + tracks when filters change (debounced)
  useEffect(() => {
    if (!caseId) return;
    if (activeEventTypes.size === 0) {
      setEvents([]);
      setTracks([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const reportKeysArr = selectedReportKeys.size > 0 ? [...selectedReportKeys] : null;
    const typesArr = [...activeEventTypes];

    const t = setTimeout(() => {
      Promise.all([
        cellebriteEventsAPI.getEvents(caseId, {
          reportKeys: reportKeysArr,
          eventTypes: typesArr,
          startDate: startDate || null,
          endDate: endDate || null,
          onlyGeolocated,
          limit: 5000,
        }),
        cellebriteEventsAPI.getTracks(caseId, {
          reportKeys: reportKeysArr,
          startDate: startDate || null,
          endDate: endDate || null,
        }),
      ])
        .then(([evData, trData]) => {
          if (cancelled) return;
          setEvents(evData.events || []);
          setTracks(trData.tracks || []);
          setLoading(false);
        })
        .catch(() => {
          if (cancelled) return;
          setEvents([]);
          setTracks([]);
          setLoading(false);
        });
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

  // Device toggle helpers
  const toggleDevice = (key) => {
    setSelectedReportKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };
  const selectAllDevices = () =>
    setSelectedReportKeys(new Set(reports.map((r) => r.report_key)));
  const clearDevices = () => setSelectedReportKeys(new Set());

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

  return (
    <div ref={rootRef} className="flex flex-col h-full min-h-0 bg-white">
      {/* Device selector */}
      <CommsDeviceSelector
        reports={reports}
        selectedReportKeys={selectedReportKeys}
        onToggle={toggleDevice}
        onSelectAll={selectAllDevices}
        onClear={clearDevices}
      />

      {/* Type filter + date */}
      <div className="flex items-center gap-3 px-3 py-2 border-b border-light-200 bg-light-50 flex-shrink-0 overflow-x-auto">
        <EventTypeFilter
          types={eventTypes}
          active={activeEventTypes}
          onChange={setActiveEventTypes}
          onlyGeolocated={onlyGeolocated}
          onOnlyGeolocatedChange={setOnlyGeolocated}
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
        <div className="flex-1" />
        {loading && <Loader2 className="w-4 h-4 animate-spin text-light-400" />}
        <span className="text-xs text-light-500 flex-shrink-0">
          {events.length.toLocaleString()} events
        </span>
      </div>

      {/* Main: map + intersection panel */}
      <div className="flex flex-1 min-h-0">
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
        />
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

      {/* Playback bar */}
      <EventPlaybackBar
        events={events}
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
          events={events}
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
