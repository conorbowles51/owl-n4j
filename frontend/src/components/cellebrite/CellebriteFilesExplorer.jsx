import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { Search, Loader2 } from 'lucide-react';
import { cellebriteFilesAPI, evidenceTagsAPI } from '../../services/api';
import CommsDeviceSelector from './comms/CommsDeviceSelector';
import FilesTree from './files/FilesTree';
import FilesList from './files/FilesList';
import FileDetailPanel from './files/FileDetailPanel';
import FileBulkActionsBar from './files/FileBulkActionsBar';

/**
 * Cellebrite Files Explorer — 7th tab in CellebriteView.
 * Shows the 20,876+ registered Cellebrite media files in a browseable tree
 * with a group-by switcher, plus a list + detail panel for viewing and tagging.
 */
export default function CellebriteFilesExplorer({ caseId, reports = [] }) {
  const [selectedReportKeys, setSelectedReportKeys] = useState(
    () => new Set(reports.map((r) => r.report_key))
  );

  const [groupBy, setGroupBy] = useState('category');
  const [tree, setTree] = useState(null);
  const [treeLoading, setTreeLoading] = useState(false);

  const [activeNode, setActiveNode] = useState(null); // { key, label, filter }

  const [files, setFiles] = useState([]);
  const [filesTotal, setFilesTotal] = useState(0);
  const [filesLoading, setFilesLoading] = useState(false);

  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [onlyRelevant, setOnlyRelevant] = useState(false);
  const [layout, setLayout] = useState('grid');

  const [selectedIds, setSelectedIds] = useState(new Set());
  const [activeFile, setActiveFile] = useState(null);

  const [caseTags, setCaseTags] = useState([]);

  // Reset device selection when reports change
  useEffect(() => {
    setSelectedReportKeys(new Set(reports.map((r) => r.report_key)));
  }, [reports]);

  // Debounce search
  useEffect(() => {
    const id = setTimeout(() => setDebouncedSearch(searchQuery), 300);
    return () => clearTimeout(id);
  }, [searchQuery]);

  const reportKeysArr = useMemo(
    () => (selectedReportKeys.size > 0 ? [...selectedReportKeys] : null),
    [selectedReportKeys]
  );

  // Fetch tree when groupBy or devices change
  useEffect(() => {
    if (!caseId) return;
    let cancelled = false;
    setTreeLoading(true);
    cellebriteFilesAPI
      .tree(caseId, { groupBy, reportKeys: reportKeysArr })
      .then((data) => {
        if (cancelled) return;
        setTree(data);
        setTreeLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setTree(null);
        setTreeLoading(false);
      });
    return () => { cancelled = true; };
  }, [caseId, groupBy, reportKeysArr]);

  // Fetch case tags (for autocomplete)
  const loadCaseTags = useCallback(async () => {
    if (!caseId) return;
    try {
      const data = await evidenceTagsAPI.getCaseTags(caseId);
      setCaseTags(data.tags || []);
    } catch {
      setCaseTags([]);
    }
  }, [caseId]);

  useEffect(() => {
    loadCaseTags();
  }, [loadCaseTags]);

  // Fetch files when filters change
  const loadFiles = useCallback(() => {
    if (!caseId) return;
    setFilesLoading(true);
    const filter = activeNode?.filter || {};
    cellebriteFilesAPI
      .list(caseId, {
        reportKeys: reportKeysArr,
        category: filter.category || null,
        parentLabel: filter.parent_label || null,
        sourceApp: filter.source_app || null,
        devicePath: filter.device_path || null,
        search: debouncedSearch || null,
        onlyRelevant,
        limit: 500,
      })
      .then((data) => {
        setFiles(data.files || []);
        setFilesTotal(data.total || 0);
        setFilesLoading(false);
      })
      .catch(() => {
        setFiles([]);
        setFilesTotal(0);
        setFilesLoading(false);
      });
  }, [caseId, reportKeysArr, activeNode, debouncedSearch, onlyRelevant]);

  useEffect(() => {
    loadFiles();
  }, [loadFiles]);

  // Device helpers
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

  // Selection helpers
  const toggleSelect = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const selectRange = (startIdx, endIdx) => {
    const [a, b] = startIdx < endIdx ? [startIdx, endIdx] : [endIdx, startIdx];
    setSelectedIds((prev) => {
      const next = new Set(prev);
      for (let i = a; i <= b; i++) {
        if (files[i]?.id) next.add(files[i].id);
      }
      return next;
    });
  };
  const clearSelection = () => setSelectedIds(new Set());

  const handleFileChanged = (updated) => {
    setFiles((prev) => prev.map((f) => (f.id === updated.id ? updated : f)));
    if (activeFile?.id === updated.id) setActiveFile(updated);
    loadCaseTags();
  };

  return (
    <div className="flex flex-col h-full min-h-0 bg-white">
      <CommsDeviceSelector
        reports={reports}
        selectedReportKeys={selectedReportKeys}
        onToggle={toggleDevice}
        onSelectAll={selectAllDevices}
        onClear={clearDevices}
      />

      {/* Top filters */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-light-200 bg-light-50 flex-shrink-0">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-light-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search filename…"
            className="w-full pl-7 pr-2 py-1 text-xs border border-light-300 rounded focus:outline-none focus:border-owl-blue-400"
          />
        </div>
        <label className="flex items-center gap-1 text-xs text-light-700 cursor-pointer">
          <input
            type="checkbox"
            checked={onlyRelevant}
            onChange={(e) => setOnlyRelevant(e.target.checked)}
            className="w-3 h-3"
          />
          Only relevant
        </label>
        <div className="flex-1" />
        {filesLoading && <Loader2 className="w-4 h-4 animate-spin text-light-400" />}
        <span className="text-xs text-light-500">
          {filesTotal.toLocaleString()} files
        </span>
      </div>

      <FileBulkActionsBar
        caseId={caseId}
        selectedIds={selectedIds}
        caseTags={caseTags}
        onClear={clearSelection}
        onChanged={() => {
          loadFiles();
          loadCaseTags();
        }}
      />

      {/* Main: tree | list | detail */}
      <div className="flex flex-1 min-h-0">
        <FilesTree
          tree={tree}
          groupBy={groupBy}
          onGroupByChange={setGroupBy}
          selectedKey={activeNode?.key}
          onSelect={setActiveNode}
          loading={treeLoading}
          total={tree?.root?.count || 0}
        />

        <FilesList
          files={files}
          total={filesTotal}
          loading={filesLoading}
          selectedIds={selectedIds}
          onToggleSelect={toggleSelect}
          onRangeSelect={selectRange}
          onOpen={(file) => setActiveFile(file)}
          layout={layout}
          onLayoutChange={setLayout}
        />

        <FileDetailPanel
          caseId={caseId}
          file={activeFile}
          caseTags={caseTags}
          onClose={() => setActiveFile(null)}
          onFileChanged={handleFileChanged}
        />
      </div>
    </div>
  );
}
