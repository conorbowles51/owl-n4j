# Swim-lane Timeline — wire-up patch for `CellebriteTimeline.jsx`

This patch wires the new swim-lane component into the existing
chronological Timeline tab. It is intentionally small — all the new
behaviour lives in the three new files committed alongside this plan:

- `frontend/src/utils/crossPhoneResolver.js` — cross-phone counterpart resolver
- `frontend/src/utils/commsHandoff.js` — Comms Center handoff bridge
- `frontend/src/components/cellebrite/CellebriteTimelineSwimLane.jsx` — swim-lane UI

Apply the four hunks below to `frontend/src/components/cellebrite/CellebriteTimeline.jsx`.

---

## Hunk 1 — add imports

```diff
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
+import { List, LayoutPanelTop, LayoutPanelLeft } from 'lucide-react';
+import CellebriteTimelineSwimLane from './CellebriteTimelineSwimLane';
 import { parseQuery, matchItem } from '../../utils/cellebriteSearch';
```

---

## Hunk 2 — add view-mode state next to other timeline state

Add immediately after the `const [searchQuery, setSearchQuery] = useState('');`
declaration:

```jsx
  // View-mode toggle. The classic chronological list stays as the
  // default ('list'). The two swim-lane orientations share data with
  // the list — only the renderer changes, no extra fetches.
  const [viewMode, setViewMode] = useState('list'); // 'list' | 'swim-v' | 'swim-h'
```

---

## Hunk 3 — add the toggle chip into the filter row

Replace this block:

```jsx
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
```

with:

```jsx
      <div className="flex items-center gap-3 px-3 py-2 border-b border-light-200 bg-light-50 flex-shrink-0 overflow-x-auto">
        <EventTypeFilter
          types={eventTypes}
          active={activeEventTypes}
          onChange={setActiveEventTypes}
          onlyGeolocated={false}
          onOnlyGeolocatedChange={() => {}}
        />
        <div className="flex-1" />
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
```

---

## Hunk 4 — branch the body on view mode

Replace the `{/* Body — grouped chronological list */}` block (the
`<div ref={bodyRef} ...>` and its children) with:

```jsx
      {/* Body — grouped chronological list OR swim-lane */}
      <div ref={bodyRef} className="flex-1 min-h-0 overflow-y-auto flex flex-col">
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
```

---

## Optional follow-up — Comms Center handoff consumer

To pick up the swim-lane → Comms handoff, add this to
`frontend/src/components/cellebrite/CellebriteCommsCenter.jsx`
(near the top of the component body):

```jsx
import { useEffect } from 'react';
import { consumeCommsHandoff } from '../../utils/commsHandoff';

// inside the component:
useEffect(() => {
  const payload = consumeCommsHandoff();
  if (!payload) return;
  // Apply the time window + phone subset to whatever filter state the
  // Comms Center already owns. Wire to the existing setters here.
  // Example:
  //   setStartDate(payload.startTs);
  //   setEndDate(payload.endTs);
  //   if (phoneCtx) phoneCtx.setSelection(payload.reportKeys);
}, []);
```

And in `frontend/src/components/cellebrite/CellebriteView.jsx` (the
tab host), listen for the tab-switch event:

```jsx
import { onCellebriteTabSwitch } from '../../utils/commsHandoff';

useEffect(() => {
  return onCellebriteTabSwitch((tabId) => {
    if (tabId) setActiveTab(tabId);
  });
}, []);
```

---

## Verification

1. `npx vite build` — should pass (the new files already build clean
   on their own).
2. Open Timeline → toggle to "Lanes ↓" / "Lanes →". With one phone
   ingested today you'll see a single lane; ingest a second phone to
   see real cross-phone arcs.
3. Drag a box on the lane surface → action bar appears with
   "Apply as filter" / "Open in Comms".
