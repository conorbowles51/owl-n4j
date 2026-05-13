import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, MapPin } from 'lucide-react';
import { cellebriteEventsAPI } from '../../services/api';
import { usePhoneReports } from '../../context/PhoneReportsContext';
import PhoneSelector from './shared/PhoneSelector';
import NoPhonesSelectedEmptyState from './shared/NoPhonesSelectedEmptyState';
import EventMapPanel from './events/EventMapPanel';
import TimelineScrubber from './shared/TimelineScrubber';
import CellebriteSearchInput from './shared/CellebriteSearchInput';
import LocationsTable from './locations/LocationsTable';
import { useCellebriteStatus } from './shared/CellebriteStatusBar';
import { useCellebriteSelection } from './shared/CellebriteSelectionContext';
import { parseQuery, matchItem } from '../../utils/cellebriteSearch';
import { deviceColor } from './events/eventUtils';

/**
 * Dedicated Locations tab.
 *
 * Promotes locations from a buried Events Center filter to a top-level
 * tab so investigators can work with them as their own surface — same
 * pattern as Cellebrite Reader's Device Locations view (map + table +
 * detail rail). Defers heavy spatial intelligence to follow-ups (tile
 * aggregation, place: search, geofence intersection).
 */
export default function CellebriteLocations({ caseId, reports: reportsProp = [], isActive = true }) {
  const phoneCtx = usePhoneReports();
  const fallbackReports = useMemo(() => reportsProp || [], [reportsProp]);
  const fallbackSelection = useMemo(
    () => new Set(fallbackReports.map(r => r.report_key)),
    [fallbackReports],
  );
  const reports = phoneCtx?.reports?.length ? phoneCtx.reports : fallbackReports;
  const selectedReportKeys = phoneCtx ? phoneCtx.selectedReportKeys : fallbackSelection;

  // --- Filter state ---
  const [windowStart, setWindowStart] = useState(null);
  const [windowEnd, setWindowEnd] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const startDate = windowStart ? toISODate(windowStart) : '';
  const endDate = windowEnd ? toISODate(windowEnd) : '';

  // --- Data state ---
  const [locations, setLocations] = useState([]);
  const [tracks, setTracks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Fetch locations across the selected phones. We pull only the
  // `location` event_type and only geolocated rows — the tab is
  // purpose-built around points on the map.
  useEffect(() => {
    if (!caseId) return undefined;
    if (selectedReportKeys.size === 0) {
      setLocations([]);
      setTracks([]);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    const reportKeysArr = [...selectedReportKeys];

    Promise.all([
      cellebriteEventsAPI.getEvents(caseId, {
        reportKeys: reportKeysArr,
        eventTypes: ['location'],
        onlyGeolocated: true,
        startDate: startDate || null,
        endDate: endDate || null,
        limit: 5000,
      }),
      cellebriteEventsAPI.getTracks(caseId, {
        reportKeys: reportKeysArr,
        startDate: startDate || null,
        endDate: endDate || null,
      }),
    ])
      .then(([eventsRes, tracksRes]) => {
        if (cancelled) return;
        setLocations(eventsRes?.events || []);
        setTracks(tracksRes?.tracks || []);
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e?.message || 'Failed to load locations');
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [caseId, selectedReportKeys, startDate, endDate]);

  // Client-side search across the loaded slice. Mirrors the operator
  // language the rest of the platform uses so muscle memory carries.
  const parsedQuery = useMemo(() => parseQuery(searchQuery), [searchQuery]);
  const filteredLocations = useMemo(() => {
    if (!searchQuery) return locations;
    return locations.filter((loc) => matchItem(loc, parsedQuery, 'event', reports).matches);
  }, [locations, searchQuery, parsedQuery, reports]);

  // Status bar — `total` is what the server returned for the active
  // filters; `displayed` is what survives the client-side search.
  useCellebriteStatus({
    isActive,
    total: locations.length,
    displayed: filteredLocations.length,
    selected: 0,
    label: 'locations',
    hint: loading ? 'Loading…' : (
      tracks.length > 0 ? `${tracks.length} device track${tracks.length === 1 ? '' : 's'}` : null
    ),
  });

  // Per-device colour for markers / track polylines — reuses the same
  // palette as the Events Center so a phone's colour is consistent
  // across tabs.
  const deviceColorOf = useCallback(
    (key) => deviceColor(key, reports),
    [reports],
  );

  // Selection bridge — clicking a marker or table row publishes to the
  // universal rail. Type 'location' routes to EventAccordion which
  // renders the same body as the Events Center detail.
  const { selectEntity } = useCellebriteSelection();
  const [selectedId, setSelectedId] = useState(null);

  const handleSelect = useCallback((row) => {
    if (!row) {
      setSelectedId(null);
      return;
    }
    setSelectedId(row.id || row.node_key || null);
    selectEntity({
      type: 'location',
      id: row.id || row.node_key,
      caseId,
      reportKey: row.device_report_key,
      payload: { ...row, event_type: 'location' },
      source: 'locations',
    });
  }, [caseId, selectEntity]);

  // ------------------------------------------------------------------
  // Layout
  // ------------------------------------------------------------------

  if (!caseId) return null;

  if (selectedReportKeys.size === 0) {
    return (
      <div className="h-full flex flex-col bg-white">
        <PhoneSelector />
        <NoPhonesSelectedEmptyState message="Select one or more phones to see their locations." />
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-white min-h-0">
      <PhoneSelector />

      {/* Histogram scrubber over the loaded locations. Items-driven
          here (no server envelope endpoint for locations yet — that's
          a follow-up under G2). */}
      <TimelineScrubber
        items={filteredLocations}
        windowStart={windowStart}
        windowEnd={windowEnd}
        onWindowChange={(s, e) => { setWindowStart(s); setWindowEnd(e); }}
      />

      {/* Search */}
      <div className="px-4 py-2 border-b border-light-200 bg-white flex-shrink-0">
        <CellebriteSearchInput
          value={searchQuery}
          onChange={setSearchQuery}
          placeholder="Search locations — try app:GoogleMaps after:2024-01-01"
          matchCount={filteredLocations.length}
          totalCount={locations.length}
          itemNoun="location"
          focusOnSlash
        />
      </div>

      {/* Map / table split. Map gets the larger share — table scrolls
          underneath. Reader's Device Locations view uses the same
          horizontal banner-then-table layout. */}
      <div className="flex-1 min-h-0 flex flex-col">
        <div className="flex-1 min-h-0 relative">
          {error && (
            <div className="absolute inset-0 flex items-center justify-center text-sm text-red-700 bg-white/80 z-10">
              {error}
            </div>
          )}
          {loading && filteredLocations.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center text-sm text-light-500 bg-white/80 z-10">
              <Loader2 className="w-4 h-4 animate-spin mr-2" />
              Loading locations…
            </div>
          )}
          <EventMapPanel
            events={filteredLocations}
            tracks={tracks}
            playheadTime={null}
            trailWindowMs={30 * 60 * 1000}
            isPlaying={false}
            selectedEventId={selectedId}
            onEventClick={handleSelect}
            intersectionMatches={[]}
            deviceColorOf={deviceColorOf}
            isActive={isActive}
          />
        </div>
        <div className="h-64 border-t border-light-200 flex-shrink-0 overflow-hidden">
          <LocationsTable
            locations={filteredLocations}
            selectedId={selectedId}
            onRowClick={handleSelect}
            reports={reports}
          />
        </div>
      </div>
    </div>
  );
}

function toISODate(d) {
  if (!(d instanceof Date) || isNaN(d.getTime())) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

// Default export with no other side effects.
export { CellebriteLocations as RawLocations };

// Small leading icon so import sites don't have to repeat the import.
export const LocationsTabIcon = MapPin;
