import React, { useMemo, useRef, useEffect, useState } from 'react';
import { Network, Calendar, MapPin, Download, Check } from 'lucide-react';
import PinnedEvidenceSection from './PinnedEvidenceSection';
import ClientProfileSection from './ClientProfileSection';
import WitnessMatrixSection from './WitnessMatrixSection';
import CaseDeadlinesSection from './CaseDeadlinesSection';
import TasksSection from './TasksSection';
import DocumentsSection from './DocumentsSection';
import AuditLogSection from './AuditLogSection';
import SnapshotsSection from './SnapshotsSection';
import TheoriesSection from './TheoriesSection';
import InvestigativeNotesSection from './InvestigativeNotesSection';
import AllEvidenceSection from './AllEvidenceSection';
import GraphView from '../GraphView';
import TimelineView from '../timeline/TimelineView';
import MapView from '../MapView';
import CaseExportModal from './CaseExportModal';
import { convertGraphNodesToTimelineEvents, convertGraphNodesToMapLocations, hasTimelineData, hasMapData } from '../../utils/graphDataConverter';

/** Width for Graph/Timeline/Map viz cards */
const VIZ_CARD_WIDTH = 480;

/** Section keys for include-in-export (match CaseExportModal) */
const OVERVIEW_SECTION_KEYS = [
  'client-profile',
  'theories',
  'pinned-evidence',
  'witnesses',
  'deadlines',
  'notes',
  'tasks',
  'graph',
  'graph-timeline',
  'graph-map',
  'evidence',
  'documents',
  'audit-log',
  'snapshots',
];

/**
 * Case Overview View
 * 
 * Displays all sections side by side in a horizontal scrollable layout.
 * Includes Graph, Timeline, and Map visualization cards.
 */
export default function CaseOverviewView({
  caseId,
  caseName,
  caseContext,
  onUpdateContext,
  authUsername,
  witnesses,
  tasks,
  deadlines,
  pinnedItems,
  graphData = { nodes: [], links: [] },
}) {
  const [exportModalOpen, setExportModalOpen] = useState(false);
  const [includeBySection, setIncludeBySection] = useState(() => {
    const o = {};
    OVERVIEW_SECTION_KEYS.forEach((k) => { o[k] = true; });
    return o;
  });

  const toggleInclude = (key, e) => {
    e?.stopPropagation();
    setIncludeBySection((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const commonProps = {
    caseId,
    isCollapsed: false,
    onToggle: () => {},
  };

  const hasTimeline = useMemo(() => hasTimelineData(graphData.nodes), [graphData.nodes]);
  const hasMap = useMemo(() => hasMapData(graphData.nodes), [graphData.nodes]);
  const timelineEvents = useMemo(
    () => (hasTimeline ? convertGraphNodesToTimelineEvents(graphData.nodes, graphData.links) : []),
    [hasTimeline, graphData.nodes, graphData.links]
  );
  const mapLocations = useMemo(
    () => (hasMap ? convertGraphNodesToMapLocations(graphData.nodes, graphData.links) : []),
    [hasMap, graphData.nodes, graphData.links]
  );

  const graphContainerRef = useRef(null);
  const [graphDimensions, setGraphDimensions] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const el = graphContainerRef.current;
    if (!el) return;
    const update = () => {
      const rect = el.getBoundingClientRect();
      setGraphDimensions({ width: rect.width || el.offsetWidth, height: rect.height || el.offsetHeight });
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  function IncludeBar({ sectionKey }) {
    const included = includeBySection[sectionKey] !== false;
    return (
      <div className="flex-shrink-0 flex items-center gap-2 px-3 py-1.5 border-b border-light-200 bg-light-50">
        <button
          type="button"
          onClick={(e) => toggleInclude(sectionKey, e)}
          className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 transition-colors ${included ? 'bg-owl-blue-100 border-owl-blue-300 text-owl-blue-700' : 'bg-white border-light-300 text-light-400'}`}
          title={included ? 'Include in export (click to exclude)' : 'Exclude from export (click to include)'}
        >
          {included && <Check className="w-2.5 h-2.5" strokeWidth={3} />}
        </button>
        <span className="text-xs text-light-600">Include in export</span>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-light-50 min-h-0">
      {/* Toolbar: fixed at top, does not scroll */}
      <div className="flex-shrink-0 flex items-center justify-between px-4 py-3 border-b border-light-200 bg-white">
        <h2 className="text-base font-semibold text-owl-blue-900">Case Overview</h2>
        <button
          onClick={() => setExportModalOpen(true)}
          className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-owl-blue-700 bg-owl-blue-50 rounded-lg hover:bg-owl-blue-100 transition-colors"
          title="Export case report (select sections to include)"
        >
          <Download className="w-4 h-4" />
          Export Case
        </button>
      </div>
      {/* Scrollable area: only this part scrolls horizontally */}
      <div className="flex-1 min-h-0 overflow-x-auto overflow-y-hidden">
        <div className="flex flex-nowrap gap-4 p-4 pb-4 h-full" style={{ minWidth: 'max-content' }}>
        {/* Each section in its own card with include checkbox */}
        <div className="flex-shrink-0 w-96 flex flex-col" style={{ height: '100%' }}>
          <div className="bg-white border border-light-200 rounded-lg flex flex-col overflow-hidden shadow-sm h-full">
            <IncludeBar sectionKey="client-profile" />
            <div className="flex-1 min-h-0 overflow-auto">
              <ClientProfileSection
                caseContext={caseContext}
                onUpdate={onUpdateContext}
                {...commonProps}
              />
            </div>
          </div>
        </div>

        <div className="flex-shrink-0 w-96 flex flex-col" style={{ height: '100%' }}>
          <div className="bg-white border border-light-200 rounded-lg flex flex-col overflow-hidden shadow-sm h-full">
            <IncludeBar sectionKey="theories" />
            <div className="flex-1 min-h-0 overflow-auto">
              <TheoriesSection
                caseId={caseId}
                authUsername={authUsername}
                fullHeight={true}
                {...commonProps}
              />
            </div>
          </div>
        </div>

        <div className="flex-shrink-0 w-96 flex flex-col" style={{ height: '100%' }}>
          <div className="bg-white border border-light-200 rounded-lg flex flex-col overflow-hidden shadow-sm h-full">
            <IncludeBar sectionKey="pinned-evidence" />
            <div className="flex-1 min-h-0 overflow-auto">
              <PinnedEvidenceSection
                caseId={caseId}
                pinnedItems={pinnedItems}
                onRefresh={() => {}}
                fullHeight={true}
                {...commonProps}
              />
            </div>
          </div>
        </div>

        <div className="flex-shrink-0 w-96 flex flex-col" style={{ height: '100%' }}>
          <div className="bg-white border border-light-200 rounded-lg flex flex-col overflow-hidden shadow-sm h-full">
            <IncludeBar sectionKey="witnesses" />
            <div className="flex-1 min-h-0 overflow-auto">
              <WitnessMatrixSection
                caseId={caseId}
                witnesses={witnesses}
                onRefresh={() => {}}
                {...commonProps}
              />
            </div>
          </div>
        </div>

        <div className="flex-shrink-0 w-96 flex flex-col" style={{ height: '100%' }}>
          <div className="bg-white border border-light-200 rounded-lg flex flex-col overflow-hidden shadow-sm h-full">
            <IncludeBar sectionKey="deadlines" />
            <div className="flex-1 min-h-0 overflow-auto">
              <CaseDeadlinesSection
                caseId={caseId}
                deadlines={deadlines}
                onRefresh={() => {}}
                {...commonProps}
              />
            </div>
          </div>
        </div>

        <div className="flex-shrink-0 w-96 flex flex-col" style={{ height: '100%' }}>
          <div className="bg-white border border-light-200 rounded-lg flex flex-col overflow-hidden shadow-sm h-full">
            <IncludeBar sectionKey="notes" />
            <div className="flex-1 min-h-0 overflow-auto">
              <InvestigativeNotesSection
                caseId={caseId}
                {...commonProps}
              />
            </div>
          </div>
        </div>

        <div className="flex-shrink-0 w-96 flex flex-col" style={{ height: '100%' }}>
          <div className="bg-white border border-light-200 rounded-lg flex flex-col overflow-hidden shadow-sm h-full">
            <IncludeBar sectionKey="tasks" />
            <div className="flex-1 min-h-0 overflow-auto">
              <TasksSection
                caseId={caseId}
                tasks={tasks}
                onRefresh={() => {}}
                {...commonProps}
              />
            </div>
          </div>
        </div>

        {/* Graph */}
        <div className="flex-shrink-0 flex flex-col" style={{ width: VIZ_CARD_WIDTH, height: '100%' }}>
          <div className="bg-white border border-light-200 rounded-lg flex flex-col overflow-hidden shadow-sm h-full">
            <IncludeBar sectionKey="graph" />
            <div className="flex-shrink-0 px-4 py-2 border-b border-light-200 flex items-center gap-2">
              <Network className="w-4 h-4 text-owl-blue-600" />
              <h3 className="text-sm font-semibold text-owl-blue-900">Graph</h3>
            </div>
            <div ref={graphContainerRef} className="flex-1 min-h-0 w-full">
              {graphData.nodes.length > 0 && graphDimensions.width > 0 && graphDimensions.height > 0 ? (
                <GraphView
                  graphData={graphData}
                  caseId={caseId}
                  width={graphDimensions.width}
                  height={graphDimensions.height}
                  showCenterButton={false}
                  isSubgraph={true}
                />
              ) : graphData.nodes.length === 0 ? (
                <div className="flex items-center justify-center w-full h-full text-sm text-light-500 bg-light-50 rounded-b-lg">
                  No graph data
                </div>
              ) : null}
            </div>
          </div>
        </div>

        {/* Timeline */}
        <div className="flex-shrink-0 flex flex-col" style={{ width: VIZ_CARD_WIDTH, height: '100%' }}>
          <div className="bg-white border border-light-200 rounded-lg flex flex-col overflow-hidden shadow-sm h-full">
            <IncludeBar sectionKey="graph-timeline" />
            <div className="flex-shrink-0 px-4 py-2 border-b border-light-200 flex items-center gap-2">
              <Calendar className="w-4 h-4 text-owl-blue-600" />
              <h3 className="text-sm font-semibold text-owl-blue-900">Timeline</h3>
            </div>
            <div className="flex-1 min-h-0 overflow-hidden w-full">
              {hasTimeline && timelineEvents.length > 0 ? (
                <div className="h-full w-full">
                  <TimelineView timelineData={timelineEvents} />
                </div>
              ) : (
                <div className="flex items-center justify-center w-full h-full text-sm text-light-500 bg-light-50 rounded-b-lg">
                  No timeline data
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Map */}
        <div className="flex-shrink-0 flex flex-col" style={{ width: VIZ_CARD_WIDTH, height: '100%' }}>
          <div className="bg-white border border-light-200 rounded-lg flex flex-col overflow-hidden shadow-sm h-full">
            <IncludeBar sectionKey="graph-map" />
            <div className="flex-shrink-0 px-4 py-2 border-b border-light-200 flex items-center gap-2">
              <MapPin className="w-4 h-4 text-owl-blue-600" />
              <h3 className="text-sm font-semibold text-owl-blue-900">Map</h3>
            </div>
            <div className="flex-1 min-h-0 overflow-hidden w-full">
              {hasMap && mapLocations.length > 0 ? (
                <div className="h-full w-full">
                  <MapView locations={mapLocations} caseId={caseId} />
                </div>
              ) : (
                <div className="flex items-center justify-center w-full h-full text-sm text-light-500 bg-light-50 rounded-b-lg">
                  No map data
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="flex-shrink-0 w-96 flex flex-col" style={{ height: '100%' }}>
          <div className="bg-white border border-light-200 rounded-lg flex flex-col overflow-hidden shadow-sm h-full">
            <IncludeBar sectionKey="evidence" />
            <div className="flex-1 min-h-0 overflow-auto">
              <AllEvidenceSection
                caseId={caseId}
                fullHeight={true}
                {...commonProps}
              />
            </div>
          </div>
        </div>

        <div className="flex-shrink-0 w-96 flex flex-col" style={{ height: '100%' }}>
          <div className="bg-white border border-light-200 rounded-lg flex flex-col overflow-hidden shadow-sm h-full">
            <IncludeBar sectionKey="documents" />
            <div className="flex-1 min-h-0 overflow-auto">
              <DocumentsSection
                caseId={caseId}
                {...commonProps}
              />
            </div>
          </div>
        </div>

        <div className="flex-shrink-0 w-96 flex flex-col" style={{ height: '100%' }}>
          <div className="bg-white border border-light-200 rounded-lg flex flex-col overflow-hidden shadow-sm h-full">
            <IncludeBar sectionKey="audit-log" />
            <div className="flex-1 min-h-0 overflow-auto">
              <AuditLogSection
                caseId={caseId}
                fullHeight={true}
                {...commonProps}
              />
            </div>
          </div>
        </div>

        <div className="flex-shrink-0 w-96 flex flex-col" style={{ height: '100%' }}>
          <div className="bg-white border border-light-200 rounded-lg flex flex-col overflow-hidden shadow-sm h-full">
            <IncludeBar sectionKey="snapshots" />
            <div className="flex-1 min-h-0 overflow-auto">
              <SnapshotsSection
                caseId={caseId}
                fullHeight={true}
                {...commonProps}
              />
            </div>
          </div>
        </div>
        </div>
      </div>
      <CaseExportModal
        isOpen={exportModalOpen}
        onClose={() => setExportModalOpen(false)}
        caseId={caseId}
        caseName={caseName}
        graphData={graphData}
        includeBySection={includeBySection}
      />
    </div>
  );
}
