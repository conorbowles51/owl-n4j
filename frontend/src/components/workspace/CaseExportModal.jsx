import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  X,
  Download,
  Check,
  Loader2,
  Network,
  Calendar,
  MapPin,
  Clock,
  ListChecks,
} from 'lucide-react';
import {
  casesAPI,
  evidenceAPI,
  workspaceAPI,
  graphAPI,
  systemLogsAPI,
} from '../../services/api';
import GraphView from '../GraphView';
import TimelineView from '../timeline/TimelineView';
import MapView from '../MapView';
import VisualInvestigationTimeline from './VisualInvestigationTimeline';
import { exportCaseToHTML } from '../../utils/theoryHtmlExport';
import html2canvas from 'html2canvas';
import {
  convertGraphNodesToTimelineEvents,
  convertGraphNodesToMapLocations,
  hasTimelineData,
  hasMapData,
} from '../../utils/graphDataConverter';

const SECTION_KEYS = [
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
  'timeline',
  'evidence',
  'documents',
  'audit-log',
  'snapshots',
];

const SECTION_LABELS = {
  'client-profile': 'Client Profile',
  theories: 'Theories',
  'pinned-evidence': 'Pinned Evidence',
  witnesses: 'Witnesses',
  deadlines: 'Deadlines',
  notes: 'Notes',
  tasks: 'Tasks',
  graph: 'Graph',
  'graph-timeline': 'Graph Timeline',
  'graph-map': 'Graph Map',
  timeline: 'Timeline',
  evidence: 'Evidence',
  documents: 'Documents',
  'audit-log': 'Audit Log',
  snapshots: 'Snapshots',
};

/**
 * Case Export Modal
 *
 * Exports all selected Case Overview sections to an HTML report.
 * Each section has a checkbox to include/exclude. Works like Theory Attached Items export.
 */
export default function CaseExportModal({
  isOpen,
  onClose,
  caseId,
  caseName,
  graphData: initialGraphData,
  includeBySection = {},
}) {
  const [caseItems, setCaseItems] = useState({
    evidence: [],
    documents: [],
    witnesses: [],
    notes: [],
    tasks: [],
    deadlines: [],
    pinned: [],
    theories: [],
    auditLog: [],
    snapshots: [],
  });
  const [caseContext, setCaseContext] = useState(null);
  const [fullGraphData, setFullGraphData] = useState(initialGraphData || null);
  const [timelineEvents, setTimelineEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('sections');
  const [exporting, setExporting] = useState(false);
  const [exportProgress, setExportProgress] = useState(0);

  /** Include flags for export: from Case Overview panel checkboxes, with defaults for timeline/snapshots */
  const includeInExport = useMemo(() => {
    const o = {};
    SECTION_KEYS.forEach((k) => {
      o[k] = includeBySection[k] !== false;
    });
    return o;
  }, [includeBySection]);

  const graphCanvasRef = useRef(null);
  const graphTimelineCanvasRef = useRef(null);
  const mapCanvasRef = useRef(null);
  const timelineCanvasRef = useRef(null);

  const hasTimeline = fullGraphData && hasTimelineData(fullGraphData.nodes);
  const hasMap = fullGraphData && hasMapData(fullGraphData.nodes);
  const timelineEventsFromGraph =
    fullGraphData && hasTimeline
      ? convertGraphNodesToTimelineEvents(fullGraphData.nodes, fullGraphData.links)
      : [];
  const mapLocationsFromGraph =
    fullGraphData && hasMap
      ? convertGraphNodesToMapLocations(fullGraphData.nodes, fullGraphData.links)
      : [];

  const setProgress = (p) => {
    setExportProgress(Math.min(100, Math.max(0, p)));
  };

  useEffect(() => {
    if (!isOpen || !caseId) return;

    const load = async () => {
      setLoading(true);
      try {
        const [
          contextRes,
          witnessesRes,
          notesRes,
          tasksRes,
          deadlinesRes,
          pinnedRes,
          theoriesRes,
          evidenceRes,
          timelineRes,
          graphRes,
          logsRes,
          caseRes,
        ] = await Promise.all([
          workspaceAPI.getCaseContext(caseId),
          workspaceAPI.getWitnesses(caseId).catch(() => ({ witnesses: [] })),
          workspaceAPI.getNotes(caseId).catch(() => ({ notes: [] })),
          workspaceAPI.getTasks(caseId).catch(() => ({ tasks: [] })),
          workspaceAPI.getDeadlines(caseId).catch(() => ({ deadlines: [] })),
          workspaceAPI.getPinnedItems(caseId).catch(() => ({ pinned_items: [] })),
          workspaceAPI.getTheories(caseId).catch(() => ({ theories: [] })),
          evidenceAPI.list(caseId).catch(() => ({ files: [] })),
          workspaceAPI.getInvestigationTimeline(caseId).catch(() => ({ events: [] })),
          graphAPI.getGraph({ case_id: caseId }).catch(() => ({ nodes: [], links: [] })),
          systemLogsAPI.getLogs({ case_id: caseId, limit: 200 }).catch(() => ({ logs: [] })),
          casesAPI.get(caseId).catch(() => null),
        ]);

        setCaseContext(contextRes || null);
        const evidenceList = evidenceRes?.files || [];
        const versions = caseRes?.versions || [];
        const latest = [...versions].sort((a, b) => (b.version ?? 0) - (a.version ?? 0))[0];
        const versionSnapshots = latest?.snapshots || [];
        setCaseItems({
          evidence: evidenceList,
          documents: filterDocuments(evidenceList),
          witnesses: witnessesRes?.witnesses || [],
          notes: notesRes?.notes || [],
          tasks: tasksRes?.tasks || [],
          deadlines: deadlinesRes?.deadlines || [],
          pinned: pinnedRes?.pinned_items || [],
          theories: theoriesRes?.theories || [],
          auditLog: logsRes?.logs || [],
          snapshots: versionSnapshots,
        });
        setTimelineEvents(timelineRes?.events || []);
        setFullGraphData(graphRes?.nodes?.length ? graphRes : null);
      } catch (err) {
        console.error('Failed to load case data for export:', err);
      } finally {
        setLoading(false);
      }
    };

    load();
  }, [isOpen, caseId]);

  function filterDocuments(files) {
    return (files || []).filter((f) => {
      const n = (f.original_filename || f.filename || '').toLowerCase();
      if (n.startsWith('note_') && n.endsWith('.txt')) return true;
      if (n.startsWith('link_') || n.endsWith('_link.txt')) return true;
      const img = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'];
      if (img.some((e) => n.endsWith(e))) return true;
      const doc = ['.pdf', '.doc', '.docx', '.txt', '.rtf'];
      if (doc.some((e) => n.endsWith(e))) {
        const simple = n.split('.').length === 2;
        const qa = n.startsWith('note_') || n.startsWith('link_');
        return qa || simple;
      }
      return false;
    });
  }

  const getSectionCount = (key) => {
    switch (key) {
      case 'client-profile':
        return caseContext ? 1 : 0;
      case 'theories':
        return caseItems.theories.length;
      case 'pinned-evidence':
        return caseItems.pinned.length;
      case 'witnesses':
        return caseItems.witnesses.length;
      case 'deadlines':
        return caseItems.deadlines.length;
      case 'notes':
        return caseItems.notes.length;
      case 'tasks':
        return caseItems.tasks.length;
      case 'graph':
        return fullGraphData?.nodes?.length ? 1 : 0;
      case 'graph-timeline':
        return hasTimeline ? 1 : 0;
      case 'graph-map':
        return hasMap ? 1 : 0;
      case 'timeline':
        return timelineEvents.length;
      case 'evidence':
        return caseItems.evidence.length;
      case 'documents':
        return caseItems.documents.length;
      case 'audit-log':
        return caseItems.auditLog.length;
      case 'snapshots':
        return caseItems.snapshots.length;
      default:
        return 0;
    }
  };

  const handleExport = async () => {
    setExporting(true);
    setProgress(0);
    const originalTab = activeTab;

    try {
      setProgress(5);

      let graphCanvasDataUrl = null;
      let graphTimelineCanvasDataUrl = null;
      let mapCanvasDataUrl = null;
      let theoryTimelineCanvasDataUrl = null;

      const captureTab = async (tab, ref, extraWait = 0) => {
        if (activeTab !== tab) {
          setActiveTab(tab);
          await new Promise((r) => setTimeout(r, 1500));
        } else {
          await new Promise((r) => setTimeout(r, 500));
        }
        await new Promise((r) => setTimeout(r, 1500 + extraWait));
        const el = ref?.current;
        if (!el) return null;
        try {
          const canvas = await html2canvas(el, {
            backgroundColor: '#ffffff',
            scale: 2,
            useCORS: true,
            logging: false,
            width: el.scrollWidth || el.offsetWidth,
            height: el.scrollHeight || el.offsetHeight,
          });
          return canvas.toDataURL('image/png', 1.0);
        } catch (err) {
          console.warn(`Failed to capture ${tab}:`, err);
          return null;
        }
      };

      if (includeInExport.graph && fullGraphData?.nodes?.length > 0) {
        setProgress(25);
        const u = await captureTab('graph', graphCanvasRef);
        if (u) graphCanvasDataUrl = u;
        else {
          const c = graphCanvasRef.current?.querySelector?.('canvas');
          if (c) graphCanvasDataUrl = c.toDataURL('image/png', 1.0);
        }
      }
      if (includeInExport['graph-timeline'] && hasTimeline) {
        setProgress(42);
        const u = await captureTab('graph-timeline', graphTimelineCanvasRef, 800);
        if (u) graphTimelineCanvasDataUrl = u;
      }
      if (includeInExport['graph-map'] && hasMap) {
        setProgress(58);
        const u = await captureTab('graph-map', mapCanvasRef, 1000);
        if (u) mapCanvasDataUrl = u;
      }
      if (includeInExport.timeline && timelineEvents.length > 0) {
        setProgress(72);
        const u = await captureTab('timeline', timelineCanvasRef);
        if (u) theoryTimelineCanvasDataUrl = u;
      }

      setProgress(85);

      if (activeTab !== originalTab) {
        setActiveTab(originalTab);
      }

      await exportCaseToHTML(
        {
          caseContext,
          caseItems,
          graphData: fullGraphData,
          timelineEvents,
          timelineEventsFromGraph: timelineEventsFromGraph || [],
          mapLocationsFromGraph: mapLocationsFromGraph || [],
          graphCanvasDataUrl,
          graphTimelineCanvasDataUrl,
          mapCanvasDataUrl,
          theoryTimelineCanvasDataUrl,
          caseId,
          caseName,
          includeTabs: includeInExport,
        }
      );
      setProgress(100);
    } catch (err) {
      console.error('Failed to export case:', err);
      alert(`Failed to export: ${err.message}`);
    } finally {
      setExporting(false);
      setExportProgress(0);
    }
  };

  if (!isOpen) return null;

  const tabs = [
    { key: 'sections', label: 'Sections', icon: ListChecks },
    { key: 'graph', label: 'Graph', icon: Network, count: getSectionCount('graph') },
    { key: 'graph-timeline', label: 'Graph Timeline', icon: Calendar, count: getSectionCount('graph-timeline') },
    { key: 'graph-map', label: 'Graph Map', icon: MapPin, count: getSectionCount('graph-map') },
    { key: 'timeline', label: 'Timeline', icon: Clock, count: getSectionCount('timeline') },
  ];

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-4xl mx-4 max-h-[85vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-light-200">
          <h3 className="text-lg font-semibold text-owl-blue-900">Export Case Report</h3>
          <div className="flex items-center gap-2">
            <button
              onClick={handleExport}
              disabled={exporting}
              className="px-3 py-1.5 text-sm font-medium text-owl-blue-700 bg-owl-blue-50 rounded-lg hover:bg-owl-blue-100 transition-colors flex items-center gap-2 disabled:opacity-60 disabled:cursor-not-allowed"
              title="Export case to HTML report"
            >
              {exporting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Download className="w-4 h-4" />
              )}
              <span>Export Report</span>
            </button>
            <button
              onClick={onClose}
              disabled={exporting}
              className="p-1 hover:bg-light-100 rounded disabled:opacity-60 disabled:cursor-not-allowed"
            >
              <X className="w-5 h-5 text-light-600" />
            </button>
          </div>
        </div>

        {exporting && (
          <div className="flex-shrink-0 px-4 py-3 bg-owl-blue-50 border-b border-owl-blue-100 flex flex-col gap-2">
            <div className="flex items-center gap-2 text-sm text-owl-blue-900">
              <Loader2 className="w-4 h-4 animate-spin flex-shrink-0" />
              <span className="font-medium">Generating report…</span>
              <span className="text-owl-blue-700 ml-auto">{exportProgress}%</span>
            </div>
            <div className="h-2 bg-owl-blue-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-owl-blue-600 rounded-full transition-all duration-300 ease-out"
                style={{ width: `${exportProgress}%` }}
              />
            </div>
          </div>
        )}

        <div className="flex border-b border-light-200 bg-light-50 overflow-x-auto">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`flex items-center gap-2 px-3 py-3 text-sm font-medium transition-colors border-b-2 flex-shrink-0 ${
                  activeTab === tab.key
                    ? 'border-owl-blue-600 text-owl-blue-900 bg-white'
                    : 'border-transparent text-light-600 hover:text-owl-blue-900 hover:bg-light-100'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span>{tab.label}</span>
                {tab.count != null && tab.count > 0 && (
                  <span
                    className={`px-2 py-0.5 rounded-full text-xs ${
                      activeTab === tab.key ? 'bg-owl-blue-100 text-owl-blue-700' : 'bg-light-200 text-light-600'
                    }`}
                  >
                    {tab.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        <div className="flex-1 overflow-hidden flex flex-col">
          {activeTab === 'sections' ? (
            <div className="flex-1 overflow-y-auto p-4">
              {loading ? (
                <p className="text-sm text-light-500 text-center py-8">Loading case data…</p>
              ) : (
                <div className="space-y-2">
                  <p className="text-sm text-light-600 mb-4">
                    Included sections are determined by the include/exclude checkboxes in each Case Overview panel. Toggle them there, then export.
                  </p>
                  {SECTION_KEYS.map((key) => {
                    const included = includeInExport[key] !== false;
                    const count = getSectionCount(key);
                    return (
                      <div
                        key={key}
                        className="flex items-center justify-between py-2 px-3 rounded-lg border border-light-200 bg-white"
                      >
                        <span className={`w-5 h-5 rounded border flex items-center justify-center flex-shrink-0 ${
                          included ? 'bg-owl-blue-100 border-owl-blue-300 text-owl-blue-700' : 'bg-light-100 border-light-300 text-light-400'
                        }`}>
                          {included && <Check className="w-3 h-3" strokeWidth={3} />}
                        </span>
                        <span className="flex-1 text-sm font-medium text-owl-blue-900 ml-3">
                          {SECTION_LABELS[key]}
                        </span>
                        <span className="text-xs text-light-500">
                          {count} {count === 1 ? 'item' : 'items'}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ) : activeTab === 'graph' ? (
            <div className="flex-1 min-h-0">
              {loading ? (
                <div className="flex items-center justify-center h-full">
                  <p className="text-sm text-light-500">Loading…</p>
                </div>
              ) : !fullGraphData?.nodes?.length ? (
                <div className="flex items-center justify-center h-full">
                  <p className="text-sm text-light-500">No graph data</p>
                </div>
              ) : (
                <div ref={graphCanvasRef} className="h-full min-h-[320px]">
                  <GraphView
                    graphData={fullGraphData || { nodes: [], links: [] }}
                    caseId={caseId}
                    onNodeClick={() => {}}
                    selectedNodes={[]}
                  />
                </div>
              )}
            </div>
          ) : activeTab === 'graph-timeline' ? (
            <div className="flex-1 min-h-0">
              {loading ? (
                <div className="flex items-center justify-center h-full">
                  <p className="text-sm text-light-500">Loading…</p>
                </div>
              ) : !hasTimeline ? (
                <div className="flex items-center justify-center h-full">
                  <p className="text-sm text-light-500">No timeline data in case graph</p>
                </div>
              ) : (
                <div ref={graphTimelineCanvasRef} className="h-full">
                  <TimelineView
                    timelineData={timelineEventsFromGraph}
                    onSelectEvent={() => {}}
                    expandAllOnMount
                  />
                </div>
              )}
            </div>
          ) : activeTab === 'graph-map' ? (
            <div className="flex-1 min-h-0 flex flex-col">
              {loading ? (
                <div className="flex items-center justify-center flex-1 min-h-[280px]">
                  <p className="text-sm text-light-500">Loading…</p>
                </div>
              ) : !hasMap ? (
                <div className="flex items-center justify-center flex-1 min-h-[280px]">
                  <p className="text-sm text-light-500">No map data in case graph</p>
                </div>
              ) : (
                <div ref={mapCanvasRef} className="flex-1 min-h-[320px] w-full h-full">
                  <MapView
                    locations={mapLocationsFromGraph}
                    caseId={caseId}
                    onNodeClick={() => {}}
                    containerStyle={{ minHeight: 320 }}
                  />
                </div>
              )}
            </div>
          ) : activeTab === 'timeline' ? (
            <div className="flex-1 min-h-0">
              {loading ? (
                <div className="flex items-center justify-center h-full">
                  <p className="text-sm text-light-500">Loading…</p>
                </div>
              ) : timelineEvents.length === 0 ? (
                <div className="flex items-center justify-center h-full">
                  <p className="text-sm text-light-500">No timeline events for this case</p>
                </div>
              ) : (
                <div ref={timelineCanvasRef} className="h-full">
                  <VisualInvestigationTimeline caseId={caseId} events={timelineEvents} />
                </div>
              )}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
