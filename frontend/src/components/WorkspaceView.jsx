import React, { useState, useEffect, useCallback } from 'react';
import { X, Users, Search, Download, Settings } from 'lucide-react';
import { workspaceAPI, casesAPI, graphAPI } from '../services/api';
import CaseContextPanel from './workspace/CaseContextPanel';
import WorkspaceGraphView from './workspace/WorkspaceGraphView';
import CaseHeaderBar from './workspace/CaseHeaderBar';
import SectionContentPanel from './workspace/SectionContentPanel';
import CaseOverviewView from './workspace/CaseOverviewView';
import VisualInvestigationTimeline from './workspace/VisualInvestigationTimeline';

/**
 * WorkspaceView Component
 * 
 * Main workspace view for case investigation with:
 * - Case header bar
 * - Three-panel layout (Case Context, Graph, Investigation)
 * - Activity timeline at bottom
 */
export default function WorkspaceView({
  caseId,
  caseName,
  onBack,
  authUsername,
}) {
  const [caseData, setCaseData] = useState(null);
  const [caseContext, setCaseContext] = useState(null);
  const [onlineUsers, setOnlineUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [fullGraphData, setFullGraphData] = useState({ nodes: [], links: [] }); // Store full graph for reset
  const [theoryGraphKeys, setTheoryGraphKeys] = useState(null); // Entity keys for theory graph filter
  const [selectedNode, setSelectedNode] = useState(null);
  const [viewMode, setViewMode] = useState('graph'); // 'graph', 'timeline', or 'map'
  const [selectedSection, setSelectedSection] = useState(null);
  const [witnesses, setWitnesses] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [deadlines, setDeadlines] = useState([]);
  const [pinnedItems, setPinnedItems] = useState([]);

  // Load case data and context
  useEffect(() => {
    const loadData = async () => {
      if (!caseId) return;
      
      setLoading(true);
      try {
        // Load case metadata
        const caseInfo = await casesAPI.get(caseId);
        setCaseData(caseInfo);

        // Load case context
        const context = await workspaceAPI.getCaseContext(caseId);
        setCaseContext(context);

        // Load graph data
        const graph = await graphAPI.getGraph({ case_id: caseId });
        setGraphData(graph);
        setFullGraphData(graph); // Store full graph
        setTheoryGraphKeys(null); // Reset theory graph filter when case changes

        // Load presence
        const presence = await workspaceAPI.getPresence(caseId);
        setOnlineUsers(presence.online_users || []);

        // Load workspace data
        const [witnessesData, tasksData, deadlinesData, pinnedData] = await Promise.all([
          workspaceAPI.getWitnesses(caseId).catch(() => ({ witnesses: [] })),
          workspaceAPI.getTasks(caseId).catch(() => ({ tasks: [] })),
          workspaceAPI.getDeadlines(caseId).catch(() => ({ deadlines: [] })),
          workspaceAPI.getPinnedItems(caseId).catch(() => ({ pinned_items: [] })),
        ]);

        setWitnesses(witnessesData.witnesses || []);
        setTasks(tasksData.tasks || []);
        setDeadlines(deadlinesData.deadlines || []);
        setPinnedItems(pinnedData.pinned_items || []);
      } catch (err) {
        console.error('Failed to load workspace data:', err);
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [caseId]);

  // Refresh handlers
  const handleRefreshPinned = useCallback(async () => {
    try {
      const pinnedData = await workspaceAPI.getPinnedItems(caseId);
      setPinnedItems(pinnedData.pinned_items || []);
    } catch (err) {
      console.error('Failed to refresh pinned items:', err);
    }
  }, [caseId]);

  // Update case context
  const handleUpdateContext = useCallback(async (updates) => {
    try {
      const updated = await workspaceAPI.updateCaseContext(caseId, updates);
      setCaseContext(updated);
    } catch (err) {
      console.error('Failed to update case context:', err);
      throw err;
    }
  }, [caseId]);

  // Listen for theory graph built event
  useEffect(() => {
    const handleTheoryGraphBuilt = (event) => {
      const { entity_keys } = event.detail;
      if (entity_keys && entity_keys.length > 0) {
        setTheoryGraphKeys(entity_keys);
      }
    };

    window.addEventListener('theory-graph-built', handleTheoryGraphBuilt);
    return () => {
      window.removeEventListener('theory-graph-built', handleTheoryGraphBuilt);
    };
  }, []);

  // Filter graph when theory keys are set
  useEffect(() => {
    if (theoryGraphKeys && theoryGraphKeys.length > 0 && fullGraphData.nodes.length > 0) {
      const keysSet = new Set(theoryGraphKeys);
      const filteredNodes = fullGraphData.nodes.filter(node => keysSet.has(node.key));
      const filteredLinks = fullGraphData.links.filter(link => {
        const sourceKey = typeof link.source === 'object' ? link.source?.key : link.source;
        const targetKey = typeof link.target === 'object' ? link.target?.key : link.target;
        return keysSet.has(sourceKey) && keysSet.has(targetKey);
      });
      
      setGraphData({
        nodes: filteredNodes,
        links: filteredLinks,
      });
    } else if (!theoryGraphKeys && fullGraphData.nodes.length > 0) {
      // Reset to full graph when filter is cleared
      setGraphData(fullGraphData);
    }
  }, [theoryGraphKeys, fullGraphData]);

  // Reset graph when theory filter is cleared
  const handleClearTheoryFilter = useCallback(() => {
    setTheoryGraphKeys(null);
    setGraphData(fullGraphData);
  }, [fullGraphData]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-owl-blue-600 mx-auto mb-4"></div>
          <p className="text-light-600">Loading workspace...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-light-50">
      {/* Case Header Bar */}
      <CaseHeaderBar
        caseName={caseName || caseData?.name || 'Untitled Case'}
        caseId={caseId}
        caseType={caseData?.case_type}
        trialDate={caseContext?.trial_date}
        onlineUsers={onlineUsers}
        onBack={onBack}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Panel: Case Context */}
        <div className="w-80 border-r border-light-200 bg-white overflow-y-auto">
          <CaseContextPanel
            caseId={caseId}
            caseName={caseName || caseData?.name || 'Untitled Case'}
            caseContext={caseContext}
            onUpdateContext={handleUpdateContext}
            authUsername={authUsername}
            selectedSection={selectedSection}
            onSectionSelect={setSelectedSection}
            pinnedItems={pinnedItems}
            onRefreshPinned={async () => {
              const data = await workspaceAPI.getPinnedItems(caseId);
              setPinnedItems(data.pinned_items || []);
            }}
          />
        </div>

        {/* Center/Right Panels */}
        {selectedSection === 'case-overview' ? (
          /* Case Overview Mode: Full width with horizontal scroll */
          <div className="flex-1 overflow-x-auto bg-white">
            <CaseOverviewView
              caseId={caseId}
              caseContext={caseContext}
              onUpdateContext={handleUpdateContext}
              authUsername={authUsername}
              witnesses={witnesses}
              tasks={tasks}
              deadlines={deadlines}
              pinnedItems={pinnedItems}
            />
          </div>
        ) : selectedSection === 'investigation-timeline' ? (
          /* Investigation Timeline Mode: Full width timeline */
          <div className="flex-1 overflow-hidden bg-white">
            <VisualInvestigationTimeline
              caseId={caseId}
              width={null}
              height={null}
            />
          </div>
        ) : (
          /* Normal Mode: 45/55 split (Graph 45%, Content 55%) - favoring text area */
          <>
            {/* Center Panel: Graph View (45%) */}
            <div className="flex-[0.45] overflow-hidden border-r border-light-200">
              <WorkspaceGraphView
                caseId={caseId}
                graphData={graphData}
                onNodeSelect={setSelectedNode}
                selectedNode={selectedNode}
                theoryGraphKeys={theoryGraphKeys}
                onClearTheoryFilter={handleClearTheoryFilter}
                viewMode={viewMode}
                onViewModeChange={setViewMode}
              />
            </div>

            {/* Right Panel: Section Content (55%) */}
            <div className="flex-[0.55] border-l border-light-200 bg-white overflow-y-auto">
              <SectionContentPanel
                selectedSection={selectedSection}
                caseId={caseId}
                caseContext={caseContext}
                onUpdateContext={handleUpdateContext}
                authUsername={authUsername}
                witnesses={witnesses}
                tasks={tasks}
                deadlines={deadlines}
                pinnedItems={pinnedItems}
                onRefreshWitnesses={async () => {
                  const data = await workspaceAPI.getWitnesses(caseId);
                  setWitnesses(data.witnesses || []);
                }}
                onRefreshTasks={async () => {
                  const data = await workspaceAPI.getTasks(caseId);
                  setTasks(data.tasks || []);
                }}
                onRefreshDeadlines={async () => {
                  const data = await workspaceAPI.getDeadlines(caseId);
                  setDeadlines(data.deadlines || []);
                }}
                onRefreshPinned={async () => {
                  const data = await workspaceAPI.getPinnedItems(caseId);
                  setPinnedItems(data.pinned_items || []);
                }}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
