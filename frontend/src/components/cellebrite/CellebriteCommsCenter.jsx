import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, Calendar, Search } from 'lucide-react';
import { cellebriteCommsAPI } from '../../services/api';
import CommsDeviceSelector from './comms/CommsDeviceSelector';
import CommsEntityFilter from './comms/CommsEntityFilter';
import CommsTypeFilter from './comms/CommsTypeFilter';
import CommsAppFilter from './comms/CommsAppFilter';
import CommsThreadList from './comms/CommsThreadList';
import CommsThreadView from './comms/CommsThreadView';
import CommsCrossTypeTimeline from './comms/CommsCrossTypeTimeline';
import { useChatContext } from '../../contexts/ChatContext';
import { buildCommsContext } from '../../utils/chatContextSummary';

/**
 * Cellebrite Communication Center — the hybrid dashboard orchestrator.
 */
export default function CellebriteCommsCenter({ caseId, reports = [] }) {
  // --- Filter state ---
  const [selectedReportKeys, setSelectedReportKeys] = useState(
    () => new Set(reports.map(r => r.report_key))
  );
  const [fromKeys, setFromKeys] = useState(new Set());
  const [toKeys, setToKeys] = useState(new Set());
  const [activeTypes, setActiveTypes] = useState(new Set(['message', 'call', 'email']));
  const [activeApps, setActiveApps] = useState(new Set()); // empty = all apps
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');

  // --- Data state ---
  const [entities, setEntities] = useState([]);
  const [entitiesLoading, setEntitiesLoading] = useState(false);

  const [sourceApps, setSourceApps] = useState([]);

  const [threads, setThreads] = useState([]);
  const [threadsTotal, setThreadsTotal] = useState(0);
  const [threadsLoading, setThreadsLoading] = useState(false);

  const [selectedThread, setSelectedThread] = useState(null);

  // View-aware AI context
  const rootRef = useRef(null);
  const { publish, clear } = useChatContext();

  // If reports list changes (new ingestion), reset device selection to all
  useEffect(() => {
    setSelectedReportKeys(new Set(reports.map(r => r.report_key)));
  }, [reports]);

  // Publish view context to ChatContext (debounced). Runs whenever the filters
  // or the threads list change.
  useEffect(() => {
    publish({
      ...buildCommsContext({
        reports,
        selectedReportKeys,
        fromKeys,
        toKeys,
        activeTypes,
        activeApps,
        startDate,
        endDate,
        searchQuery: debouncedSearch,
        threads,
        selectedThread,
      }),
      anchorRef: rootRef,
    });
    return () => {
      // Don't clear aggressively — other unmount paths handle the full clear.
    };
  }, [
    publish,
    reports,
    selectedReportKeys,
    fromKeys,
    toKeys,
    activeTypes,
    activeApps,
    startDate,
    endDate,
    debouncedSearch,
    threads,
    selectedThread,
  ]);

  // On unmount, clear the context so the chips disappear when the user leaves.
  useEffect(() => () => clear(), [clear]);

  // Debounce search
  useEffect(() => {
    const id = setTimeout(() => setDebouncedSearch(searchQuery), 300);
    return () => clearTimeout(id);
  }, [searchQuery]);

  // Device map for thread row badges
  const deviceById = useMemo(() => {
    const map = {};
    reports.forEach(r => {
      map[r.report_key] = `${r.device_model || '?'}${r.phone_owner_name ? ` · ${r.phone_owner_name}` : ''}`;
    });
    return map;
  }, [reports]);

  const threadTypesParam = useMemo(() => {
    const map = { message: 'chat', call: 'calls', email: 'emails' };
    return [...activeTypes].map(t => map[t]).filter(Boolean);
  }, [activeTypes]);

  // Load entities + source apps when report set changes
  useEffect(() => {
    if (!caseId) return;
    let cancelled = false;
    setEntitiesLoading(true);
    const keys = selectedReportKeys.size > 0 ? [...selectedReportKeys] : null;
    Promise.all([
      cellebriteCommsAPI.getEntities(caseId, keys).catch(() => ({ entities: [] })),
      cellebriteCommsAPI.getSourceApps(caseId, keys).catch(() => ({ apps: [] })),
    ]).then(([entitiesData, appsData]) => {
      if (!cancelled) {
        setEntities(entitiesData.entities || []);
        setSourceApps(appsData.apps || []);
        setEntitiesLoading(false);
        // Prune any selected apps that no longer exist
        setActiveApps(prev => {
          if (prev.size === 0) return prev;
          const available = new Set((appsData.apps || []).map(a => a.source_app));
          const next = new Set([...prev].filter(a => available.has(a)));
          return next.size === prev.size ? prev : next;
        });
      }
    });
    return () => { cancelled = true; };
  }, [caseId, selectedReportKeys]);

  // Load threads when filters change
  useEffect(() => {
    if (!caseId) return;
    let cancelled = false;
    setThreadsLoading(true);
    const reportKeysArr = selectedReportKeys.size > 0 ? [...selectedReportKeys] : null;
    cellebriteCommsAPI.getThreads(caseId, {
      reportKeys: reportKeysArr,
      fromKeys: fromKeys.size > 0 ? [...fromKeys] : null,
      toKeys: toKeys.size > 0 ? [...toKeys] : null,
      threadTypes: threadTypesParam,
      sourceApps: activeApps.size > 0 ? [...activeApps] : null,
      startDate: startDate || null,
      endDate: endDate || null,
      search: debouncedSearch || null,
      limit: 300,
    }).then((data) => {
      if (!cancelled) {
        setThreads(data.threads || []);
        setThreadsTotal(data.total || 0);
        setThreadsLoading(false);
      }
    }).catch(() => {
      if (!cancelled) {
        setThreads([]);
        setThreadsLoading(false);
      }
    });
    return () => { cancelled = true; };
  }, [caseId, selectedReportKeys, fromKeys, toKeys, threadTypesParam, activeApps, startDate, endDate, debouncedSearch]);

  // Clear selected thread when it no longer matches filters
  useEffect(() => {
    if (!selectedThread) return;
    const stillPresent = threads.some(t => t.thread_id === selectedThread.thread_id);
    if (!stillPresent) setSelectedThread(null);
  }, [threads, selectedThread]);

  // Device toggle helpers
  const toggleDevice = (key) => {
    setSelectedReportKeys(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };
  const selectAllDevices = () => setSelectedReportKeys(new Set(reports.map(r => r.report_key)));
  const clearDevices = () => setSelectedReportKeys(new Set());

  return (
    <div ref={rootRef} className="flex flex-col h-full min-h-0 bg-white">
      {/* Device selector strip */}
      <CommsDeviceSelector
        reports={reports}
        selectedReportKeys={selectedReportKeys}
        onToggle={toggleDevice}
        onSelectAll={selectAllDevices}
        onClear={clearDevices}
      />

      {/* Entity filter */}
      <CommsEntityFilter
        entities={entities}
        fromKeys={fromKeys}
        toKeys={toKeys}
        onFromChange={setFromKeys}
        onToChange={setToKeys}
      />

      {/* Source-app filter row */}
      <div className="flex items-center gap-2 px-4 py-1.5 border-b border-light-200 bg-white flex-shrink-0 overflow-x-auto">
        <span className="text-xs text-light-600 font-medium flex-shrink-0">Source:</span>
        <CommsAppFilter apps={sourceApps} active={activeApps} onChange={setActiveApps} />
      </div>

      {/* Secondary filters */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-light-200 bg-light-50 flex-shrink-0">
        <CommsTypeFilter active={activeTypes} onChange={setActiveTypes} />
        <div className="h-4 w-px bg-light-300" />
        <div className="flex items-center gap-1.5 text-xs">
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
        <div className="h-4 w-px bg-light-300" />
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-light-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search thread name / app..."
            className="w-full pl-7 pr-2 py-1 text-xs border border-light-300 rounded focus:outline-none focus:border-owl-blue-400"
          />
        </div>
        <span className="text-xs text-light-500">
          {threadsTotal.toLocaleString()} threads
        </span>
      </div>

      {/* Main split: thread list | thread view */}
      <div className="flex flex-1 min-h-0">
        <div className="w-80 border-r border-light-200 flex flex-col min-h-0 flex-shrink-0">
          <CommsThreadList
            threads={threads}
            loading={threadsLoading || entitiesLoading}
            selectedThreadId={selectedThread?.thread_id}
            onSelect={setSelectedThread}
            deviceById={deviceById}
          />
        </div>
        <div className="flex-1 flex flex-col min-h-0">
          <CommsThreadView caseId={caseId} selectedThread={selectedThread} />
        </div>
      </div>

      {/* Bottom cross-type timeline */}
      <CommsCrossTypeTimeline
        caseId={caseId}
        fromKeys={fromKeys}
        toKeys={toKeys}
        reportKeys={selectedReportKeys}
        types={activeTypes}
        sourceApps={activeApps}
        startDate={startDate || null}
        endDate={endDate || null}
      />
    </div>
  );
}
