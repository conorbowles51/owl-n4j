import React, { useState, useEffect, useCallback } from 'react';
import {
  Smartphone, Network, Clock, Users, MessageSquare, MapPin, FolderTree, Loader2,
  Globe, UserCheck,
} from 'lucide-react';
import { cellebriteAPI } from '../../services/api';
import CellebriteOverview from './CellebriteOverview';
import CellebriteCrossPhoneGraph from './CellebriteCrossPhoneGraph';
import CellebriteTimeline from './CellebriteTimeline';
import CellebriteCommunicationView from './CellebriteCommunicationView';
import CellebriteCommsCenter from './CellebriteCommsCenter';
import CellebriteEventCenter from './CellebriteEventCenter';
import CellebriteLocations from './CellebriteLocations';
import CellebriteFilesExplorer from './CellebriteFilesExplorer';
import CellebriteUnifiedContacts from './CellebriteUnifiedContacts';
import CellebriteStatusBar, { CellebriteStatusProvider } from './shared/CellebriteStatusBar';
import { CellebriteSelectionProvider, useCellebriteSelection } from './shared/CellebriteSelectionContext';
import CellebriteSelectionRail from './shared/CellebriteSelectionRail';

const TABS = [
  { key: 'overview', label: 'Overview', icon: Smartphone },
  { key: 'comms', label: 'Comms Center', icon: MessageSquare },
  // Unified contacts: rolls Persons up by canonical phone number so
  // the same human across multiple phones (different alias names)
  // shows as one row. Direct response to user feedback that
  // investigators couldn't see "everyone who's texting +1-202-805-2817".
  { key: 'unified', label: 'Contacts (unified)', icon: UserCheck },
  // Locations gets its own tab — promoted out of Events Center to
  // match Cellebrite Reader's "Device Locations" surface and so the
  // map-centric workflow doesn't compete with the wider event feed.
  { key: 'locations', label: 'Locations', icon: Globe },
  { key: 'events', label: 'Location & Events', icon: MapPin },
  { key: 'files', label: 'Files', icon: FolderTree },
  { key: 'graph', label: 'Cross-Phone Graph', icon: Network },
  { key: 'timeline', label: 'Timeline', icon: Clock },
  { key: 'communications', label: 'Communications', icon: Users },
];

/**
 * Main Cellebrite Multi-Phone View container.
 * Renders a tab bar and every previously-visited tab's content.
 *
 * Tabs are *kept mounted* once visited (display:none when inactive)
 * so flipping between tabs doesn't trigger a full reload of their
 * fetched data. The first visit to a tab pays the load cost; every
 * subsequent visit is instant.
 */
export default function CellebriteView({ caseId }) {
  const [activeTab, setActiveTab] = useState('overview');
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  // Tabs that have been activated at least once. We render only these
  // (so we don't pay the load cost for tabs the user never opens) and
  // keep them rendered for the rest of the session.
  const [mountedTabs, setMountedTabs] = useState(() => new Set(['overview']));

  // Reset mounted set when the case changes — different case means
  // different data; we want the load cost to be paid per case.
  useEffect(() => {
    setMountedTabs(new Set(['overview']));
    setActiveTab('overview');
  }, [caseId]);

  // Whenever the user activates a new tab, add it to the mounted set.
  const handleTabClick = (key) => {
    setActiveTab(key);
    setMountedTabs((prev) => {
      if (prev.has(key)) return prev;
      const next = new Set(prev);
      next.add(key);
      return next;
    });
  };

  const refreshReports = useCallback(async () => {
    if (!caseId) return;
    try {
      const data = await cellebriteAPI.getReports(caseId);
      setReports(data.reports || []);
    } catch {
      setReports([]);
    }
  }, [caseId]);

  useEffect(() => {
    if (!caseId) return;
    let cancelled = false;
    setLoading(true);
    cellebriteAPI.getReports(caseId).then(data => {
      if (!cancelled) {
        setReports(data.reports || []);
        setLoading(false);
      }
    }).catch(() => {
      if (!cancelled) {
        setReports([]);
        setLoading(false);
      }
    });
    return () => { cancelled = true; };
  }, [caseId]);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-light-400" />
      </div>
    );
  }

  if (reports.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center px-8">
        <Smartphone className="w-12 h-12 text-light-300 mb-4" />
        <h3 className="text-lg font-semibold text-owl-blue-900 mb-2">No Phone Reports</h3>
        <p className="text-sm text-light-600 max-w-md">
          No phone reports have been ingested yet. Upload a Cellebrite UFED report folder
          through the evidence panel and process it to get started.
        </p>
      </div>
    );
  }

  return (
    <CellebriteStatusProvider>
    <CellebriteSelectionProvider>
    {/* Cross-tab intent listener — when a tab publishes a selection
        with `_filter_intent: 'comms'` (e.g. the unified-contacts
        "Filter Comms" button), switch the active tab to Comms so the
        user sees the just-applied filter take effect. */}
    <FilterIntentTabSwitcher onSwitchToComms={() => handleTabClick('comms')} />
    <div className="flex flex-col h-full min-h-0">
      {/* Tab Bar */}
      <div className="flex items-center border-b border-light-200 bg-light-50 px-4 flex-shrink-0">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => handleTabClick(key)}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              activeTab === key
                ? 'border-emerald-500 text-emerald-700'
                : 'border-transparent text-light-600 hover:text-owl-blue-900 hover:border-light-300'
            }`}
          >
            <Icon className="w-4 h-4" />
            {label}
          </button>
        ))}
        <div className="flex-1" />
        <span className="text-xs text-light-500">
          {reports.length} device{reports.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Tab Content — every visited tab stays mounted (display:none
          when inactive) so re-selecting it skips the reload entirely.
          The `isActive` prop lets descendants react to becoming
          visible (e.g. Leaflet needs invalidateSize() after being
          un-hidden, otherwise it draws at the wrong size).

          The selection flyout (CellebriteSelectionRail) used to live
          here as a persistent right-dock; it's now a slide-in flyout
          that's mounted at the bottom of this component (overlays via
          fixed positioning) so it pays zero layout cost when no
          selection is active. */}
      <div className="flex-1 min-h-0 overflow-hidden relative">
        {mountedTabs.has('overview') && (
          <TabPane active={activeTab === 'overview'}>
            <CellebriteOverview caseId={caseId} reports={reports} onReportsChanged={refreshReports} isActive={activeTab === 'overview'} />
          </TabPane>
        )}
        {mountedTabs.has('comms') && (
          <TabPane active={activeTab === 'comms'}>
            <CellebriteCommsCenter caseId={caseId} reports={reports} isActive={activeTab === 'comms'} />
          </TabPane>
        )}
        {mountedTabs.has('unified') && (
          <TabPane active={activeTab === 'unified'}>
            <CellebriteUnifiedContacts caseId={caseId} isActive={activeTab === 'unified'} />
          </TabPane>
        )}
        {mountedTabs.has('locations') && (
          <TabPane active={activeTab === 'locations'}>
            <CellebriteLocations caseId={caseId} reports={reports} isActive={activeTab === 'locations'} />
          </TabPane>
        )}
        {mountedTabs.has('events') && (
          <TabPane active={activeTab === 'events'}>
            <CellebriteEventCenter caseId={caseId} reports={reports} isActive={activeTab === 'events'} />
          </TabPane>
        )}
        {mountedTabs.has('files') && (
          <TabPane active={activeTab === 'files'}>
            <CellebriteFilesExplorer caseId={caseId} reports={reports} isActive={activeTab === 'files'} />
          </TabPane>
        )}
        {mountedTabs.has('graph') && (
          <TabPane active={activeTab === 'graph'}>
            <CellebriteCrossPhoneGraph caseId={caseId} isActive={activeTab === 'graph'} />
          </TabPane>
        )}
        {mountedTabs.has('timeline') && (
          <TabPane active={activeTab === 'timeline'}>
            <CellebriteTimeline caseId={caseId} reports={reports} isActive={activeTab === 'timeline'} />
          </TabPane>
        )}
        {mountedTabs.has('communications') && (
          <TabPane active={activeTab === 'communications'}>
            <CellebriteCommunicationView caseId={caseId} isActive={activeTab === 'communications'} />
          </TabPane>
        )}
      </div>

      {/* Universal selection flyout — overlays the page (fixed
          position) when something is selected, returns nothing when
          nothing is. No layout cost, no permanent dock. */}
      <CellebriteSelectionRail caseId={caseId} />

      {/* Persistent Reader-style status bar — every tab feeds counts via
          useCellebriteStatus(); shell renders them in one place so the
          investigator never has to ask "is this all of it?". */}
      <CellebriteStatusBar />
    </div>
    </CellebriteSelectionProvider>
    </CellebriteStatusProvider>
  );
}

/**
 * Wrapper that keeps a tab's DOM in the document but hides it via
 * `display:none` when inactive. Cheaper than unmount/remount and
 * preserves the child's React state and scroll position.
 *
 * `display:none` is preferred over `visibility:hidden` so layout-
 * sensitive children (Leaflet maps, virtualised lists) don't get
 * sized at zero while inactive.
 */
function TabPane({ active, children }) {
  return (
    <div
      className="absolute inset-0"
      style={{ display: active ? 'block' : 'none' }}
    >
      {children}
    </div>
  );
}

/**
 * Subscribes to selection changes inside the rail provider so the
 * surrounding CellebriteView shell can react to cross-tab intents.
 * Currently the only intent we honour is `_filter_intent: 'comms'`
 * from the unified-contacts tab — fired when the user clicks the
 * "Filter Comms" button on a row, expecting both the filter to be
 * applied AND the active tab to switch to Comms.
 *
 * Implemented as its own component because useCellebriteSelection()
 * needs to live inside the provider; CellebriteView itself wraps it.
 */
function FilterIntentTabSwitcher({ onSwitchToComms }) {
  const { selection } = useCellebriteSelection();
  const lastConsumedRef = React.useRef(null);
  React.useEffect(() => {
    if (!selection) return;
    if (selection.payload?._filter_intent !== 'comms') return;
    if (lastConsumedRef.current === selection.id) return;
    lastConsumedRef.current = selection.id;
    onSwitchToComms?.();
  }, [selection, onSwitchToComms]);
  return null;
}
