import React, { useState, useEffect, useRef } from 'react';
import { X, FileText, User, Archive, Trash2, CheckCircle2, Calendar, ChevronDown, ChevronUp, Clock, Network, Download, MapPin, Check, Loader2 } from 'lucide-react';
import { evidenceAPI, casesAPI, workspaceAPI, snapshotsAPI, graphAPI } from '../../services/api';
import FilePreview from '../FilePreview';
import ReactMarkdown from 'react-markdown';
import VisualInvestigationTimeline from './VisualInvestigationTimeline';
import GraphView from '../GraphView';
import TimelineView from '../timeline/TimelineView';
import MapView from '../MapView';
import { exportTheoryToHTML } from '../../utils/theoryHtmlExport';
import html2canvas from 'html2canvas';
import { convertGraphNodesToTimelineEvents, convertGraphNodesToMapLocations, hasTimelineData, hasMapData } from '../../utils/graphDataConverter';

const TAB_KEYS = ['evidence', 'witnesses', 'notes', 'snapshots', 'documents', 'tasks', 'graph', 'graph-timeline', 'graph-map', 'timeline'];

/**
 * Attached Items Modal
 * 
 * Displays all items attached to a theory in tabs:
 * - Evidence files (with preview)
 * - Witness interviews (with details)
 * - Investigative notes
 * - Snapshots (expandable)
 * - Case documents (with preview)
 */
export default function AttachedItemsModal({
  isOpen,
  onClose,
  theory,
  caseId,
  caseName,
  onDetach,
}) {
  const [attachedItems, setAttachedItems] = useState({
    evidence: [],
    witnesses: [],
    notes: [],
    snapshots: [],
    documents: [],
    tasks: [],
  });
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('evidence');
  const [timelineEvents, setTimelineEvents] = useState([]);
  const [loadingTimeline, setLoadingTimeline] = useState(false);
  const [theoryGraphData, setTheoryGraphData] = useState(null);
  const [fullGraphData, setFullGraphData] = useState(null);
  const [loadingGraph, setLoadingGraph] = useState(false);
  const [expandedEvidenceId, setExpandedEvidenceId] = useState(null);
  const [expandedDocumentId, setExpandedDocumentId] = useState(null);
  const [expandedSnapshotId, setExpandedSnapshotId] = useState(null);
  const [expandedWitnessId, setExpandedWitnessId] = useState(null);
  const [loadedSnapshotDetails, setLoadedSnapshotDetails] = useState({});
  const graphCanvasRef = useRef(null);
  const timelineCanvasRef = useRef(null);
  const graphTimelineCanvasRef = useRef(null);
  const mapCanvasRef = useRef(null);

  const [includeInExport, setIncludeInExport] = useState(() => {
    const o = {};
    TAB_KEYS.forEach(k => { o[k] = true; });
    return o;
  });
  const [exporting, setExporting] = useState(false);
  const [exportProgress, setExportProgress] = useState(0);
  const toggleIncludeInExport = (key, e) => {
    e?.stopPropagation();
    setIncludeInExport(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const setProgress = (p) => {
    setExportProgress(Math.min(100, Math.max(0, p)));
  };

  // Load timeline events when modal opens (to show count) and when timeline tab is active
  useEffect(() => {
    if (!isOpen || !theory || !caseId || !theory.theory_id) return;

    const loadTimeline = async () => {
      // Only show loading state if we're on the timeline tab
      if (activeTab === 'timeline') {
        setLoadingTimeline(true);
      }
      try {
        const data = await workspaceAPI.getTheoryTimeline(caseId, theory.theory_id);
        setTimelineEvents(data.events || []);
      } catch (err) {
        console.error('Failed to load theory timeline:', err);
        setTimelineEvents([]);
      } finally {
        if (activeTab === 'timeline') {
          setLoadingTimeline(false);
        }
      }
    };

    loadTimeline();
  }, [isOpen, theory, caseId]);


  // Preload full case graph when modal opens (if theory has attached graph). Use full graph for
  // Graph Timeline / Graph Map; use filtered theory subgraph for Graph tab only.
  useEffect(() => {
    if (!isOpen || !theory || !caseId) return;
    if (!theory.attached_graph_data) {
      setTheoryGraphData(null);
      setFullGraphData(null);
      return;
    }

    const loadGraph = async () => {
      setLoadingGraph(true);
      try {
        const fullGraph = await graphAPI.getGraph({ case_id: caseId });
        setFullGraphData(fullGraph);

        const entityKeys = theory.attached_graph_data.entity_keys || [];
        if (entityKeys.length === 0) {
          setTheoryGraphData({ nodes: [], links: [] });
          return;
        }
        const nodeKeysSet = new Set(entityKeys);
        const filteredNodes = fullGraph.nodes.filter(node => nodeKeysSet.has(node.key));
        const filteredNodeKeys = new Set(filteredNodes.map(n => n.key));
        const filteredLinks = fullGraph.links.filter(link => {
          const sourceKey = typeof link.source === 'object' ? link.source.key : link.source;
          const targetKey = typeof link.target === 'object' ? link.target.key : link.target;
          return filteredNodeKeys.has(sourceKey) && filteredNodeKeys.has(targetKey);
        });
        setTheoryGraphData({ nodes: filteredNodes, links: filteredLinks });
      } catch (err) {
        console.error('Failed to load theory graph:', err);
        setTheoryGraphData({ nodes: [], links: [] });
        setFullGraphData(null);
      } finally {
        setLoadingGraph(false);
      }
    };

    loadGraph();
  }, [isOpen, theory, caseId]);

  useEffect(() => {
    if (!isOpen) return;
    setIncludeInExport(prev => {
      const next = { ...prev };
      TAB_KEYS.forEach(k => { if (next[k] === undefined) next[k] = true; });
      return next;
    });
  }, [isOpen]);

  // Use full case graph for timeline/map (same as workspace) so Graph Timeline & Graph Map have data.
  // Graph tab uses filtered theory subgraph only.
  const hasTimeline = fullGraphData ? hasTimelineData(fullGraphData.nodes) : false;
  const hasMap = fullGraphData ? hasMapData(fullGraphData.nodes) : false;
  const timelineEventsFromGraph = fullGraphData && hasTimeline
    ? convertGraphNodesToTimelineEvents(fullGraphData.nodes, fullGraphData.links)
    : [];
  const mapLocationsFromGraph = fullGraphData && hasMap
    ? convertGraphNodesToMapLocations(fullGraphData.nodes, fullGraphData.links)
    : [];

  useEffect(() => {
    if (!isOpen || !theory || !caseId) return;

    const loadAttachedItems = async () => {
      setLoading(true);
      try {
        const items = {
          evidence: [],
          witnesses: [],
          notes: [],
          snapshots: [],
          documents: [],
          tasks: [],
        };
        
        // Reset expanded states when tab changes
        setExpandedEvidenceId(null);
        setExpandedDocumentId(null);
        setExpandedSnapshotId(null);
        setExpandedWitnessId(null);

        // Load evidence
        if (theory.attached_evidence_ids?.length > 0) {
          try {
            const evidenceData = await evidenceAPI.list(caseId);
            const allFiles = evidenceData?.files || (Array.isArray(evidenceData) ? evidenceData : []);
            items.evidence = allFiles.filter((f) => theory.attached_evidence_ids.includes(f.id));
          } catch (err) {
            console.error('Failed to load attached evidence:', err);
          }
        }

        // Load witnesses
        if (theory.attached_witness_ids?.length > 0) {
          try {
            const witnessesData = await workspaceAPI.getWitnesses(caseId);
            const allWitnesses = witnessesData?.witnesses || [];
            items.witnesses = allWitnesses.filter((w) => theory.attached_witness_ids.includes(w.witness_id));
          } catch (err) {
            console.error('Failed to load attached witnesses:', err);
          }
        }

        // Load snapshots
        if (theory.attached_snapshot_ids?.length > 0) {
          try {
            const caseData = await casesAPI.get(caseId);
            const versions = caseData?.versions || [];
            const sorted = [...versions].sort((a, b) => (b.version ?? 0) - (a.version ?? 0));
            const latest = sorted[0];
            const allSnapshots = latest?.snapshots || [];
            items.snapshots = allSnapshots.filter((s) => theory.attached_snapshot_ids.includes(s.id));
          } catch (err) {
            console.error('Failed to load attached snapshots:', err);
          }
        }

        // Load documents (same as evidence, filtered by attached_document_ids)
        if (theory.attached_document_ids?.length > 0) {
          try {
            const evidenceData = await evidenceAPI.list(caseId);
            const allFiles = evidenceData?.files || (Array.isArray(evidenceData) ? evidenceData : []);
            items.documents = allFiles.filter((f) => theory.attached_document_ids.includes(f.id));
          } catch (err) {
            console.error('Failed to load attached documents:', err);
          }
        }

        // Load notes
        if (theory.attached_note_ids?.length > 0) {
          try {
            const notesData = await workspaceAPI.getNotes(caseId);
            const allNotes = notesData?.notes || [];
            items.notes = allNotes.filter((n) => theory.attached_note_ids.includes(n.note_id || n.id));
          } catch (err) {
            console.error('Failed to load attached notes:', err);
            // Fallback to placeholder
            items.notes = theory.attached_note_ids.map((id, idx) => ({
              id,
              note_id: id,
              content: `Note ${idx + 1}`,
            }));
          }
        }

        // Load tasks
        if (theory.attached_task_ids?.length > 0) {
          try {
            const tasksData = await workspaceAPI.getTasks(caseId);
            const allTasks = tasksData?.tasks || [];
            items.tasks = allTasks.filter((t) => theory.attached_task_ids.includes(t.task_id));
          } catch (err) {
            console.error('Failed to load attached tasks:', err);
          }
        }

        setAttachedItems(items);
        
        // Set first tab with items
        const tabs = ['evidence', 'witnesses', 'notes', 'snapshots', 'documents', 'tasks'];
        const firstTabWithItems = tabs.find(tab => items[tab]?.length > 0);
        if (firstTabWithItems) {
          setActiveTab(firstTabWithItems);
        }
      } catch (err) {
        console.error('Failed to load attached items:', err);
      } finally {
        setLoading(false);
      }
    };

    loadAttachedItems();
  }, [isOpen, theory, caseId]);

  const handleDetach = async (type, itemId) => {
    if (!theory || !onDetach) return;
    onDetach(type, itemId);
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    try {
      return new Date(dateString).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateString;
    }
  };

  const humanSize = (bytes) => {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
  };

  const getCredibilityColor = (rating) => {
    if (!rating) return 'text-light-600';
    if (rating >= 4) return 'text-green-600';
    if (rating >= 3) return 'text-yellow-600';
    return 'text-red-600';
  };

  const getCredibilityStars = (rating) => {
    if (!rating) return '';
    return '⭐'.repeat(rating);
  };

  const getRiskEmoji = (risk) => {
    if (!risk) return '';
    if (risk.toLowerCase().includes('high') || risk.toLowerCase().includes('critical')) return '🔴';
    if (risk.toLowerCase().includes('medium') || risk.toLowerCase().includes('moderate')) return '🟡';
    if (risk.toLowerCase().includes('low')) return '🟢';
    return '🟡'; // Default to yellow
  };

  const loadSnapshotDetails = async (snapshot) => {
    if (loadedSnapshotDetails[snapshot.id]) return;
    
    try {
      const full = await snapshotsAPI.get(snapshot.id);
      setLoadedSnapshotDetails(prev => ({ ...prev, [snapshot.id]: full }));
    } catch (err) {
      if (err?.status !== 404) {
        console.error('Failed to load snapshot details:', err);
      }
      // If 404, snapshot only exists in case version, use case data
      setLoadedSnapshotDetails(prev => ({ ...prev, [snapshot.id]: null }));
    }
  };

  const mergeSnapshot = (caseSnap, apiSnap) => {
    if (!apiSnap) return caseSnap;
    const hasContent = (v, pred) => v != null && pred(v);
    return {
      ...caseSnap,
      subgraph: hasContent(apiSnap.subgraph, (s) => (s?.nodes?.length || s?.links?.length)) ? apiSnap.subgraph : caseSnap.subgraph,
      overview: hasContent(apiSnap.overview, (o) => (o?.nodes?.length || (typeof o === 'object' && Object.keys(o || {}).length))) ? apiSnap.overview : caseSnap.overview,
      timeline: hasContent(apiSnap.timeline, (t) => Array.isArray(t) && t.length) ? apiSnap.timeline : caseSnap.timeline,
      citations: hasContent(apiSnap.citations, (c) => typeof c === 'object' && Object.keys(c || {}).length) ? apiSnap.citations : caseSnap.citations,
      chat_history: hasContent(apiSnap.chat_history, (h) => Array.isArray(h) && h.length) ? apiSnap.chat_history : caseSnap.chat_history,
      ai_overview: apiSnap.ai_overview && String(apiSnap.ai_overview).trim() ? apiSnap.ai_overview : caseSnap.ai_overview,
    };
  };

  const handleExportPDF = async () => {
    setExporting(true);
    setProgress(0);
    try {
      const originalTab = activeTab;

      setProgress(5);
      // Load full snapshot details for export
      const snapshotsWithDetails = [];
      if (attachedItems.snapshots && attachedItems.snapshots.length > 0) {
        for (const snapshot of attachedItems.snapshots) {
          try {
            let fullSnapshot = snapshot;
            // Try to load full details if not already loaded
            if (!loadedSnapshotDetails[snapshot.id]) {
              try {
                const full = await snapshotsAPI.get(snapshot.id);
                fullSnapshot = mergeSnapshot(snapshot, full);
              } catch (err) {
                if (err?.status !== 404) {
                  console.warn(`Failed to load snapshot ${snapshot.id}:`, err);
                }
                // Use snapshot as-is if load fails
              }
            } else {
              fullSnapshot = mergeSnapshot(snapshot, loadedSnapshotDetails[snapshot.id]);
            }
            snapshotsWithDetails.push(fullSnapshot);
          } catch (err) {
            console.warn(`Failed to process snapshot ${snapshot.id}:`, err);
            snapshotsWithDetails.push(snapshot);
          }
        }
      }
      setProgress(15);

      let graphDataForExport = theoryGraphData;
      let fullGraphForExport = fullGraphData;
      if (theory?.attached_graph_data) {
        try {
          const fullGraph = await graphAPI.getGraph({ case_id: caseId });
          fullGraphForExport = fullGraph;
          if (!fullGraphData) setFullGraphData(fullGraph);
          const entityKeys = theory.attached_graph_data.entity_keys || [];
          if (entityKeys.length > 0 && (!graphDataForExport || graphDataForExport.nodes.length === 0)) {
            const nodeKeysSet = new Set(entityKeys);
            const filteredNodes = fullGraph.nodes.filter(node => nodeKeysSet.has(node.key));
            const filteredNodeKeys = new Set(filteredNodes.map(n => n.key));
            const filteredLinks = fullGraph.links.filter(link => {
              const sourceKey = typeof link.source === 'object' ? link.source.key : link.source;
              const targetKey = typeof link.target === 'object' ? link.target.key : link.target;
              return filteredNodeKeys.has(sourceKey) && filteredNodeKeys.has(targetKey);
            });
            graphDataForExport = { nodes: filteredNodes, links: filteredLinks };
            if (!theoryGraphData?.nodes?.length) setTheoryGraphData(graphDataForExport);
          }
        } catch (err) {
          console.error('Failed to load graph data for export:', err);
        }
      }
      setProgress(25);

      let graphCanvasDataUrl = null;
      let graphTimelineCanvasDataUrl = null;
      let mapCanvasDataUrl = null;
      let theoryTimelineCanvasDataUrl = null;

      const exportHasTimeline = fullGraphForExport && hasTimelineData(fullGraphForExport.nodes);
      const exportHasMap = fullGraphForExport && hasMapData(fullGraphForExport.nodes);

      const captureTab = async (tab, ref, extraWait = 0) => {
        if (activeTab !== tab) {
          setActiveTab(tab);
          await new Promise(resolve => setTimeout(resolve, 1500));
        } else {
          await new Promise(resolve => setTimeout(resolve, 500));
        }
        await new Promise(resolve => setTimeout(resolve, 1500 + extraWait));
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

      if (includeInExport.graph && theory?.attached_graph_data && graphDataForExport?.nodes?.length > 0) {
        setProgress(35);
        const dataUrl = await captureTab('graph', graphCanvasRef);
        if (dataUrl) graphCanvasDataUrl = dataUrl;
        else {
          const canvasEl = graphCanvasRef.current?.querySelector?.('canvas');
          if (canvasEl) graphCanvasDataUrl = canvasEl.toDataURL('image/png', 1.0);
        }
      }
      if (includeInExport['graph-timeline'] && theory?.attached_graph_data && exportHasTimeline) {
        setProgress(48);
        const dataUrl = await captureTab('graph-timeline', graphTimelineCanvasRef, 800);
        if (dataUrl) graphTimelineCanvasDataUrl = dataUrl;
      }
      if (includeInExport['graph-map'] && theory?.attached_graph_data && exportHasMap) {
        setProgress(62);
        const dataUrl = await captureTab('graph-map', mapCanvasRef, 1000);
        if (dataUrl) mapCanvasDataUrl = dataUrl;
      }
      if (includeInExport.timeline && timelineEvents.length > 0) {
        setProgress(75);
        const dataUrl = await captureTab('timeline', timelineCanvasRef);
        if (dataUrl) theoryTimelineCanvasDataUrl = dataUrl;
      }
      setProgress(88);

      if (activeTab !== originalTab) {
        setActiveTab(originalTab);
      }

      // Create enhanced attached items with full snapshot details
      const enhancedAttachedItems = {
        ...attachedItems,
        snapshots: snapshotsWithDetails,
      };

      setProgress(92);
      console.log('Exporting theory - caseName prop:', caseName, 'caseId:', caseId);
      await exportTheoryToHTML(
        theory,
        enhancedAttachedItems,
        graphDataForExport || theoryGraphData,
        timelineEvents,
        graphCanvasDataUrl,
        graphTimelineCanvasDataUrl,
        mapCanvasDataUrl,
        theoryTimelineCanvasDataUrl,
        caseId,
        caseName,
        includeInExport
      );
      setProgress(100);
    } catch (err) {
      console.error('Failed to export theory:', err);
      alert(`Failed to export: ${err.message}`);
    } finally {
      setExporting(false);
      setExportProgress(0);
    }
  };

  if (!isOpen) return null;

  const tabs = [
    { key: 'evidence', label: 'Evidence', icon: FileText, count: attachedItems.evidence.length },
    { key: 'witnesses', label: 'Witnesses', icon: User, count: attachedItems.witnesses.length },
    { key: 'notes', label: 'Notes', icon: FileText, count: attachedItems.notes.length },
    { key: 'snapshots', label: 'Snapshots', icon: Archive, count: attachedItems.snapshots.length },
    { key: 'documents', label: 'Documents', icon: FileText, count: attachedItems.documents.length },
    { key: 'tasks', label: 'Tasks', icon: FileText, count: attachedItems.tasks.length },
    { key: 'graph', label: 'Graph', icon: Network, count: theory?.attached_graph_data ? 1 : 0 },
    { key: 'graph-timeline', label: 'Graph Timeline', icon: Calendar, count: fullGraphData && hasTimeline ? 1 : 0 },
    { key: 'graph-map', label: 'Graph Map', icon: MapPin, count: fullGraphData && hasMap ? 1 : 0 },
    { key: 'timeline', label: 'Timeline', icon: Clock, count: timelineEvents.length },
  ];

  const activeItems = attachedItems[activeTab] || [];

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-4xl mx-4 max-h-[85vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-light-200">
          <h3 className="text-lg font-semibold text-owl-blue-900">
            Attached Items: {theory?.title || 'Theory'}
          </h3>
          <div className="flex items-center gap-2">
            <button
              onClick={handleExportPDF}
              disabled={exporting}
              className="px-3 py-1.5 text-sm font-medium text-owl-blue-700 bg-owl-blue-50 rounded-lg hover:bg-owl-blue-100 transition-colors flex items-center gap-2 disabled:opacity-60 disabled:cursor-not-allowed disabled:hover:bg-owl-blue-50"
              title="Export theory to HTML (can be printed to PDF)"
            >
              {exporting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Download className="w-4 h-4" />
              )}
              <span>Export Report</span>
            </button>
            <button onClick={onClose} disabled={exporting} className="p-1 hover:bg-light-100 rounded disabled:opacity-60 disabled:cursor-not-allowed">
              <X className="w-5 h-5 text-light-600" />
            </button>
          </div>
        </div>

        {/* Export progress overlay */}
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

        {/* Tabs */}
        <div className="flex border-b border-light-200 bg-light-50 overflow-x-auto">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const included = includeInExport[tab.key] !== false;
            return (
              <button
                key={tab.key}
                onClick={() => {
                  setActiveTab(tab.key);
                  setExpandedEvidenceId(null);
                  setExpandedDocumentId(null);
                  setExpandedSnapshotId(null);
                  setExpandedWitnessId(null);
                }}
                className={`flex items-center gap-2 px-3 py-3 text-sm font-medium transition-colors border-b-2 flex-shrink-0 ${
                  activeTab === tab.key
                    ? 'border-owl-blue-600 text-owl-blue-900 bg-white'
                    : 'border-transparent text-light-600 hover:text-owl-blue-900 hover:bg-light-100'
                }`}
              >
                <button
                  type="button"
                  onClick={(e) => toggleIncludeInExport(tab.key, e)}
                  className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 ${included ? 'bg-owl-blue-100 border-owl-blue-300 text-owl-blue-700' : 'bg-white border-light-300 text-light-400'}`}
                  title={included ? 'Include in export (click to exclude)' : 'Exclude from export (click to include)'}
                >
                  {included && <Check className="w-3 h-3" strokeWidth={3} />}
                </button>
                <Icon className="w-4 h-4" />
                <span>{tab.label}</span>
                {tab.count > 0 && (
                  <span className={`px-2 py-0.5 rounded-full text-xs ${
                    activeTab === tab.key ? 'bg-owl-blue-100 text-owl-blue-700' : 'bg-light-200 text-light-600'
                  }`}>
                    {tab.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Tab Content */}
        <div className="flex-1 overflow-hidden flex flex-col">
          {activeTab === 'timeline' ? (
            <div className="flex-1 min-h-0">
              {loadingTimeline ? (
                <div className="flex items-center justify-center h-full">
                  <p className="text-sm text-light-500">Loading timeline...</p>
                </div>
              ) : timelineEvents.length === 0 ? (
                <div className="flex items-center justify-center h-full">
                  <p className="text-sm text-light-500">No timeline events for this theory</p>
                </div>
              ) : (
                <div ref={timelineCanvasRef} className="h-full">
                  <VisualInvestigationTimeline
                    caseId={caseId}
                    events={timelineEvents}
                  />
                </div>
              )}
            </div>
          ) : activeTab === 'graph' ? (
            <div className="flex-1 min-h-0">
              {loadingGraph ? (
                <div className="flex items-center justify-center h-full">
                  <p className="text-sm text-light-500">Loading graph...</p>
                </div>
              ) : !theory?.attached_graph_data ? (
                <div className="flex items-center justify-center h-full">
                  <div className="text-center">
                    <Network className="w-12 h-12 mx-auto mb-3 text-light-400" />
                    <p className="text-sm text-light-500">No graph built for this theory yet</p>
                    <p className="text-xs text-light-400 mt-1">Use "Build Theory Graph" to create a graph</p>
                  </div>
                </div>
              ) : theoryGraphData && theoryGraphData.nodes.length === 0 ? (
                <div className="flex items-center justify-center h-full">
                  <p className="text-sm text-light-500">Graph is empty</p>
                </div>
              ) : (
                <div ref={graphCanvasRef} className="h-full">
                  <GraphView
                    graphData={theoryGraphData || { nodes: [], links: [] }}
                    onNodeClick={() => {}}
                    selectedNodes={[]}
                  />
                </div>
              )}
            </div>
          ) : activeTab === 'graph-timeline' ? (
            <div className="flex-1 min-h-0">
              {loadingGraph ? (
                <div className="flex items-center justify-center h-full">
                  <p className="text-sm text-light-500">Loading...</p>
                </div>
              ) : !theory?.attached_graph_data ? (
                <div className="flex items-center justify-center h-full">
                  <p className="text-sm text-light-500">Build a theory graph first</p>
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
              {loadingGraph ? (
                <div className="flex items-center justify-center flex-1 min-h-[280px]">
                  <p className="text-sm text-light-500">Loading...</p>
                </div>
              ) : !theory?.attached_graph_data ? (
                <div className="flex items-center justify-center flex-1 min-h-[280px]">
                  <p className="text-sm text-light-500">Build a theory graph first</p>
                </div>
              ) : !hasMap ? (
                <div className="flex items-center justify-center flex-1 min-h-[280px]">
                  <p className="text-sm text-light-500">No map data in case graph</p>
                </div>
              ) : (
                <div
                  ref={mapCanvasRef}
                  className="flex-1 min-h-[320px] w-full h-full"
                >
                  <MapView
                    locations={mapLocationsFromGraph}
                    caseId={caseId}
                    onNodeClick={() => {}}
                    containerStyle={{ minHeight: 320 }}
                  />
                </div>
              )}
            </div>
          ) : (
            <div className="flex-1 overflow-y-auto p-4">
              {loading ? (
                <p className="text-sm text-light-500 text-center py-8">Loading attached items...</p>
              ) : activeItems.length === 0 ? (
                <p className="text-sm text-light-500 text-center py-8">No {tabs.find(t => t.key === activeTab)?.label.toLowerCase()} attached to this theory</p>
              ) : (
                <div className="space-y-3">
              {/* Evidence Tab */}
              {activeTab === 'evidence' && attachedItems.evidence.map((file) => {
                const isExpanded = expandedEvidenceId === file.id;
                return (
                  <div
                    key={file.id}
                    className="border border-light-200 rounded-lg bg-light-50 hover:bg-light-100 transition-colors"
                  >
                    <div className="p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-start gap-2 flex-1 min-w-0">
                          <FileText className="w-4 h-4 text-owl-blue-600 mt-0.5 flex-shrink-0" />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <p className="text-sm font-medium text-owl-blue-900 truncate">
                                {file.original_filename || file.filename || `Evidence ${file.id}`}
                              </p>
                              {file.status === 'processed' && (
                                <CheckCircle2 className="w-3.5 h-3.5 text-green-600 flex-shrink-0" title="Processed" />
                              )}
                              {file.status === 'unprocessed' && (
                                <span className="text-xs text-orange-600 bg-orange-100 px-1.5 py-0.5 rounded" title="Unprocessed">
                                  Unprocessed
                                </span>
                              )}
                            </div>
                            <div className="flex items-center gap-2 mt-1 text-xs text-light-600">
                              {file.size && (
                                <>
                                  <span>{humanSize(file.size)}</span>
                                  <span>•</span>
                                </>
                              )}
                              {file.processed_at && (
                                <>
                                  <Calendar className="w-3 h-3" />
                                  <span>{formatDate(file.processed_at)}</span>
                                </>
                              )}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-1 flex-shrink-0">
                          <button
                            onClick={() => setExpandedEvidenceId(isExpanded ? null : file.id)}
                            className="p-1.5 hover:bg-light-200 rounded transition-colors text-light-600"
                            title={isExpanded ? 'Collapse' : 'Expand'}
                          >
                            {isExpanded ? (
                              <ChevronUp className="w-4 h-4" />
                            ) : (
                              <ChevronDown className="w-4 h-4" />
                            )}
                          </button>
                          <button
                            onClick={() => handleDetach('evidence', file.id)}
                            className="p-1.5 hover:bg-red-100 rounded text-red-600 transition-colors"
                            title="Detach"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    </div>
                    {isExpanded && (
                      <div className="px-3 pb-3 border-t border-light-200 pt-3">
                        <FilePreview
                          caseId={caseId}
                          filePath={file.stored_path || ''}
                          fileName={file.original_filename || file.filename}
                          fileType="file"
                          onClose={() => setExpandedEvidenceId(null)}
                        />
                      </div>
                    )}
                  </div>
                );
              })}

              {/* Witnesses Tab */}
              {activeTab === 'witnesses' && attachedItems.witnesses.map((witness) => {
                const isExpanded = expandedWitnessId === witness.witness_id;
                const interviews = witness.interviews || [];
                const latestInterview = interviews.length > 0 
                  ? interviews.sort((a, b) => new Date(b.date || 0) - new Date(a.date || 0))[0]
                  : null;

                return (
                  <div
                    key={witness.witness_id}
                    className="border border-light-200 rounded-lg bg-light-50 hover:bg-light-100 transition-colors"
                  >
                    <div className="p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <User className="w-4 h-4 text-owl-blue-600 flex-shrink-0" />
                            <span className="text-sm font-medium text-owl-blue-900">
                              {witness.name}
                              {witness.role && witness.organization && (
                                <span className="text-light-600 font-normal">
                                  {' '}({witness.role}, {witness.organization})
                                </span>
                              )}
                              {witness.role && !witness.organization && (
                                <span className="text-light-600 font-normal">
                                  {' '}({witness.role})
                                </span>
                              )}
                            </span>
                            {witness.credibility_rating && (
                              <span className={`text-xs font-medium ${getCredibilityColor(witness.credibility_rating)}`}>
                                {witness.credibility_rating}/5
                              </span>
                            )}
                          </div>
                          {witness.status && (
                            <p className="text-xs text-light-600">Status: {witness.status}</p>
                          )}
                          {witness.category && (
                            <p className="text-xs text-light-600">Category: {witness.category}</p>
                          )}
                          
                          {/* Latest Interview Summary */}
                          {latestInterview && (
                            <div className="mt-2 text-xs space-y-1">
                              <div className="flex items-center gap-2 flex-wrap">
                                {latestInterview.status && (
                                  <span className="text-owl-blue-900 font-medium">
                                    Status: {latestInterview.status}
                                  </span>
                                )}
                                {latestInterview.credibility_rating && (
                                  <span className={`${getCredibilityColor(latestInterview.credibility_rating)}`}>
                                    Credibility: {getCredibilityStars(latestInterview.credibility_rating)} ({latestInterview.credibility_rating >= 4 ? 'High' : latestInterview.credibility_rating >= 3 ? 'Medium' : 'Low'})
                                  </span>
                                )}
                              </div>
                              {latestInterview.statement && (
                                <p className="text-light-700">
                                  Statement: {latestInterview.statement}
                                </p>
                              )}
                              {latestInterview.risk_assessment && (
                                <p className="text-red-600">
                                  Risk: {getRiskEmoji(latestInterview.risk_assessment)} {latestInterview.risk_assessment}
                                </p>
                              )}
                            </div>
                          )}

                          {/* No interviews message */}
                          {interviews.length === 0 && (
                            <p className="text-xs text-light-500 italic mt-1">No interviews recorded</p>
                          )}
                        </div>
                        <div className="flex items-center gap-1 flex-shrink-0">
                          {interviews.length > 0 && (
                            <button
                              onClick={() => setExpandedWitnessId(isExpanded ? null : witness.witness_id)}
                              className="p-1.5 hover:bg-light-200 rounded transition-colors text-light-600"
                              title={isExpanded ? 'Collapse interviews' : 'Expand interviews'}
                            >
                              {isExpanded ? (
                                <ChevronUp className="w-4 h-4" />
                              ) : (
                                <ChevronDown className="w-4 h-4" />
                              )}
                            </button>
                          )}
                          <button
                            onClick={() => handleDetach('witness', witness.witness_id)}
                            className="p-1.5 hover:bg-red-100 rounded text-red-600 transition-colors"
                            title="Detach"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    </div>

                    {/* Expanded Interviews List */}
                    {isExpanded && interviews.length > 0 && (
                      <div className="px-3 pb-3 border-t border-light-200 pt-3 space-y-3">
                        <h5 className="text-xs font-semibold text-owl-blue-900 mb-2">
                          Interviews ({interviews.length})
                        </h5>
                        {interviews
                          .sort((a, b) => new Date(b.date || 0) - new Date(a.date || 0))
                          .map((interview) => (
                            <div
                              key={interview.interview_id}
                              className="bg-white rounded-lg border border-light-200 p-3"
                            >
                              <div className="flex items-start justify-between gap-2">
                                <div className="flex-1">
                                  <div className="flex items-center gap-2 flex-wrap text-xs mb-1">
                                    {interview.date && (
                                      <span className="text-light-600">
                                        {formatDate(interview.date)}
                                      </span>
                                    )}
                                    {interview.duration && (
                                      <>
                                        <span className="text-light-400">•</span>
                                        <span className="text-light-600">{interview.duration}</span>
                                      </>
                                    )}
                                  </div>
                                  {interview.status && (
                                    <p className="text-xs text-owl-blue-900 font-medium mb-1">
                                      Status: {interview.status}
                                    </p>
                                  )}
                                  {interview.credibility_rating && (
                                    <p className={`text-xs ${getCredibilityColor(interview.credibility_rating)} mb-1`}>
                                      Credibility: {getCredibilityStars(interview.credibility_rating)} ({interview.credibility_rating >= 4 ? 'High' : interview.credibility_rating >= 3 ? 'Medium' : 'Low'})
                                    </p>
                                  )}
                                  {interview.statement && (
                                    <p className="text-xs text-light-700 mb-1">
                                      Statement: {interview.statement}
                                    </p>
                                  )}
                                  {interview.risk_assessment && (
                                    <p className="text-xs text-red-600">
                                      Risk: {getRiskEmoji(interview.risk_assessment)} {interview.risk_assessment}
                                    </p>
                                  )}
                                </div>
                              </div>
                            </div>
                          ))}
                      </div>
                    )}
                  </div>
                );
              })}

              {/* Notes Tab */}
              {activeTab === 'notes' && attachedItems.notes.map((note) => {
                const noteId = note.note_id || note.id;
                const noteContent = note.content || 'Note';
                return (
                  <div
                    key={noteId}
                    className="p-3 bg-light-50 rounded-lg border border-light-200 hover:bg-light-100 transition-colors"
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <FileText className="w-4 h-4 text-owl-blue-600 flex-shrink-0" />
                          {note.created_at && (
                            <span className="text-xs text-light-500 flex items-center gap-1">
                              <Calendar className="w-3 h-3" />
                              {formatDate(note.created_at)}
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-owl-blue-900 whitespace-pre-wrap">{noteContent}</p>
                      </div>
                      <button
                        onClick={() => handleDetach('note', noteId)}
                        className="p-1.5 hover:bg-red-100 rounded text-red-600 transition-colors flex-shrink-0 ml-2"
                        title="Detach"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                );
              })}

              {/* Snapshots Tab */}
              {activeTab === 'snapshots' && attachedItems.snapshots.map((snapshot) => {
                const isExpanded = expandedSnapshotId === snapshot.id;
                const full = loadedSnapshotDetails[snapshot.id] !== undefined
                  ? mergeSnapshot(snapshot, loadedSnapshotDetails[snapshot.id])
                  : snapshot;
                const overviewNodes = full.overview?.nodes ?? (Array.isArray(full.overview) ? full.overview : null);
                const subgraphNodes = full.subgraph?.nodes;
                const nodes = overviewNodes && overviewNodes.length ? overviewNodes : (subgraphNodes && subgraphNodes.length ? subgraphNodes : []);
                const timeline = Array.isArray(full.timeline) ? full.timeline : [];
                const citations = full.citations && typeof full.citations === 'object' ? full.citations : {};
                // Filter out non-citation objects (like node objects) from citations
                const citationValues = Object.values(citations).filter(cite => {
                  // If it's a string, it's a citation
                  if (typeof cite === 'string') return true;
                  // If it's an object, check if it has citation-like properties
          if (cite && typeof cite === 'object') {
            // If it has node properties, it's probably a node, not a citation
            if ('node_key' in cite || 'node_name' in cite || 'node_type' in cite) return false;
            // Otherwise, treat it as a citation object
            return true;
          }
          return false;
        });
                const chatHistory = Array.isArray(full.chat_history) ? full.chat_history : [];

                return (
                  <div
                    key={snapshot.id}
                    className="border border-light-200 rounded-lg bg-light-50"
                  >
                    <div className="p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <Archive className="w-4 h-4 text-owl-blue-600 flex-shrink-0" />
                            <span className="text-sm font-medium text-owl-blue-900">
                              {snapshot.name || 'Unnamed snapshot'}
                            </span>
                          </div>
                          <div className="flex items-center gap-3 text-xs text-light-600 mt-1">
                            {snapshot.timestamp && (
                              <span>{formatDate(snapshot.timestamp)}</span>
                            )}
                            {nodes.length > 0 && (
                              <span>• {nodes.length} nodes</span>
                            )}
                            {timeline.length > 0 && (
                              <span>• {timeline.length} timeline events</span>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-1 flex-shrink-0">
                          <button
                            onClick={() => {
                              if (!isExpanded) {
                                loadSnapshotDetails(snapshot);
                                setExpandedSnapshotId(snapshot.id);
                              } else {
                                setExpandedSnapshotId(null);
                              }
                            }}
                            className="p-1.5 hover:bg-light-200 rounded transition-colors text-light-600"
                            title={isExpanded ? 'Collapse' : 'Expand'}
                          >
                            {isExpanded ? (
                              <ChevronUp className="w-4 h-4" />
                            ) : (
                              <ChevronDown className="w-4 h-4" />
                            )}
                          </button>
                          <button
                            onClick={() => handleDetach('snapshot', snapshot.id)}
                            className="p-1.5 hover:bg-red-100 rounded text-red-600 transition-colors"
                            title="Detach"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    </div>
                    {isExpanded && (
                      <div className="px-3 pb-3 border-t border-light-200 pt-3 space-y-4">
                        {full.ai_overview && (
                          <div>
                            <h5 className="text-sm font-semibold text-owl-blue-900 mb-2">AI Overview</h5>
                            <p className="text-xs text-light-700">{full.ai_overview}</p>
                          </div>
                        )}
                        {nodes.length > 0 && (
                          <div>
                            <h5 className="text-sm font-semibold text-owl-blue-900 mb-2">Node Overview ({nodes.length} nodes)</h5>
                            <div className="space-y-2">
                              {nodes.slice(0, 10).map((node, i) => {
                                const nodeName = node?.name || node?.node_name || node?.id || node?.node_key || 'Unnamed node';
                                const nodeSummary = node?.summary || node?.notes || '';
                                return (
                                  <div key={i} className="bg-light-100 rounded p-2 text-xs">
                                    <p className="font-medium text-owl-blue-900">{nodeName}</p>
                                    {nodeSummary && <p className="text-light-600 mt-1">{nodeSummary}</p>}
                                  </div>
                                );
                              })}
                              {nodes.length > 10 && <p className="text-xs text-light-500">+{nodes.length - 10} more nodes</p>}
                            </div>
                          </div>
                        )}
                        {citationValues.length > 0 && (
                          <div>
                            <h5 className="text-sm font-semibold text-owl-blue-900 mb-2">Source Citations ({citationValues.length})</h5>
                            <div className="space-y-1">
                              {citationValues.slice(0, 5).map((cite, i) => {
                                let citationText = '';
                                if (typeof cite === 'string') {
                                  citationText = cite;
                                } else if (cite && typeof cite === 'object') {
                                  citationText = cite.fact_text || cite.text || cite.summary || cite.description || JSON.stringify(cite);
                                }
                                return (
                                  <p key={i} className="text-xs text-light-600">{citationText}</p>
                                );
                              })}
                              {citationValues.length > 5 && <p className="text-xs text-light-500">+{citationValues.length - 5} more citations</p>}
                            </div>
                          </div>
                        )}
                        {timeline.length > 0 && (
                          <div>
                            <h5 className="text-sm font-semibold text-owl-blue-900 mb-2">Timeline Events ({timeline.length})</h5>
                            <div className="space-y-1">
                              {timeline.slice(0, 5).map((event, i) => {
                                let eventText = '';
                                if (typeof event === 'string') {
                                  eventText = event;
                                } else if (event && typeof event === 'object') {
                                  eventText = event.summary || event.description || event.text || JSON.stringify(event);
                                }
                                return (
                                  <p key={i} className="text-xs text-light-600">{eventText}</p>
                                );
                              })}
                              {timeline.length > 5 && <p className="text-xs text-light-500">+{timeline.length - 5} more events</p>}
                            </div>
                          </div>
                        )}
                        {chatHistory.length > 0 && (
                          <div>
                            <h5 className="text-sm font-semibold text-owl-blue-900 mb-2">Chat History ({chatHistory.length} messages)</h5>
                            <div className="space-y-2">
                              {chatHistory.slice(0, 3).map((msg, i) => (
                                <div key={i} className="bg-light-100 rounded p-2 text-xs">
                                  <p className="font-medium text-owl-blue-900 mb-1">{msg.role === 'user' ? 'User' : 'Assistant'}</p>
                                  <div className="text-light-700">
                                    {msg.role === 'user' ? (
                                      <p className="whitespace-pre-wrap">{msg.content}</p>
                                    ) : (
                                      <ReactMarkdown>{msg.content || ''}</ReactMarkdown>
                                    )}
                                  </div>
                                </div>
                              ))}
                              {chatHistory.length > 3 && <p className="text-xs text-light-500">+{chatHistory.length - 3} more messages</p>}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}

              {/* Documents Tab */}
              {activeTab === 'documents' && attachedItems.documents.map((doc) => {
                const isExpanded = expandedDocumentId === doc.id;
                return (
                  <div
                    key={doc.id}
                    className="border border-light-200 rounded-lg bg-light-50 hover:bg-light-100 transition-colors"
                  >
                    <div className="p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-start gap-2 flex-1 min-w-0">
                          <FileText className="w-4 h-4 text-owl-blue-600 mt-0.5 flex-shrink-0" />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-owl-blue-900 truncate">
                              {doc.original_filename || doc.filename || `Document ${doc.id}`}
                            </p>
                            {doc.summary && (
                              <p className="text-xs text-light-600 mt-1 line-clamp-2">
                                {doc.summary}
                              </p>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-1 flex-shrink-0">
                          <button
                            onClick={() => setExpandedDocumentId(isExpanded ? null : doc.id)}
                            className="p-1.5 hover:bg-light-200 rounded transition-colors text-light-600"
                            title={isExpanded ? 'Collapse' : 'Expand'}
                          >
                            {isExpanded ? (
                              <ChevronUp className="w-4 h-4" />
                            ) : (
                              <ChevronDown className="w-4 h-4" />
                            )}
                          </button>
                          <button
                            onClick={() => handleDetach('document', doc.id)}
                            className="p-1.5 hover:bg-red-100 rounded text-red-600 transition-colors"
                            title="Detach"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    </div>
                    {isExpanded && (
                      <div className="px-3 pb-3 border-t border-light-200 pt-3">
                        <FilePreview
                          caseId={caseId}
                          filePath={doc.stored_path || ''}
                          fileName={doc.original_filename || doc.filename}
                          fileType="file"
                          onClose={() => setExpandedDocumentId(null)}
                        />
                      </div>
                    )}
                  </div>
                );
              })}

              {/* Tasks Tab */}
              {activeTab === 'tasks' && attachedItems.tasks.map((task) => {
                const getPriorityEmoji = (priority) => {
                  switch (priority) {
                    case 'URGENT': return '🔴';
                    case 'HIGH': return '🟡';
                    default: return '🟢';
                  }
                };
                const getPriorityLabel = (priority) => {
                  switch (priority) {
                    case 'URGENT': return 'URGENT';
                    case 'HIGH': return 'HIGH';
                    default: return 'STANDARD';
                  }
                };
                const getPriorityColor = (priority) => {
                  switch (priority) {
                    case 'URGENT': return 'bg-red-50 border-red-200 text-red-600';
                    case 'HIGH': return 'bg-yellow-50 border-yellow-200 text-yellow-600';
                    default: return 'bg-green-50 border-green-200 text-green-600';
                  }
                };
                const formatShortDate = (dateString) => {
                  if (!dateString) return null;
                  try {
                    return new Date(dateString).toLocaleDateString('en-US', {
                      month: 'short',
                      day: 'numeric',
                    });
                  } catch {
                    return dateString;
                  }
                };
                const getStatusText = (task) => {
                  if (task.status_text) {
                    return task.status_text;
                  }
                  if (task.completion_percentage > 0 && task.completion_percentage < 100) {
                    return `${task.completion_percentage}% Complete`;
                  }
                  if (task.status === 'COMPLETED') {
                    return 'Completed';
                  }
                  if (task.status === 'IN_PROGRESS') {
                    return 'In Progress';
                  }
                  return 'Not Started';
                };

                const priorityEmoji = getPriorityEmoji(task.priority);
                const priorityLabel = getPriorityLabel(task.priority);
                const priorityColor = getPriorityColor(task.priority);
                const dueDate = formatShortDate(task.due_date);
                const statusText = getStatusText(task);

                return (
                  <div
                    key={task.task_id}
                    className={`p-3 rounded-lg border ${priorityColor}`}
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="text-xs font-semibold">
                        {priorityEmoji} {priorityLabel}
                        {dueDate && ` - Due ${dueDate}`}
                      </div>
                      <button
                        onClick={() => handleDetach('task', task.task_id)}
                        className="p-1 hover:bg-white hover:bg-opacity-50 rounded transition-colors text-red-600"
                        title="Detach"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                    <div className="text-sm font-medium mb-1">
                      {task.title}
                    </div>
                    {task.description && (
                      <div className="text-xs mb-2 opacity-90">
                        {task.description}
                      </div>
                    )}
                    <div className="text-xs opacity-80">
                      {task.assigned_to && (
                        <span>
                          Assigned: {task.assigned_to}
                        </span>
                      )}
                      {task.assigned_to && statusText && ' | '}
                      {statusText && (
                        <span>
                          Status: {statusText}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="p-4 border-t border-light-200">
          <button
            onClick={onClose}
            className="w-full px-4 py-2 bg-light-200 text-light-700 rounded-lg hover:bg-light-300"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
