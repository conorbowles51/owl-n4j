import React, { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { Search, Loader2 } from 'lucide-react';
import { cellebriteFilesAPI, evidenceTagsAPI } from '../../services/api';
import PhoneSelector from './shared/PhoneSelector';
import NoPhonesSelectedEmptyState from './shared/NoPhonesSelectedEmptyState';
import { usePhoneReports } from '../../context/PhoneReportsContext';
import FilesTree from './files/FilesTree';
import FilesList from './files/FilesList';
import FileDetailPanel from './files/FileDetailPanel';
import FileBulkActionsBar from './files/FileBulkActionsBar';
import { useChatContext } from '../../contexts/ChatContext';
import { buildFilesContext } from '../../utils/chatContextSummary';

/**
 * Cellebrite Files Explorer — 7th tab in CellebriteView.
 * Shows the 20,876+ registered Cellebrite media files in a browseable tree
 * with a group-by switcher, plus a list + detail panel for viewing and tagging.
 */
export default function CellebriteFilesExplorer({ caseId, reports: reportsProp = [] }) {
  const phoneCtx = usePhoneReports();
  const fallbackReports = useMemo(() => reportsProp || [], [reportsProp]);
  const fallbackSelection = useMemo(
    () => new Set(fallbackReports.map((r) => r.report_key)),
    [fallbackReports],
  );
  const reports = phoneCtx?.reports?.length ? phoneCtx.reports : fallbackReports;
  const selectedReportKeys = phoneCtx ? phoneCtx.selectedReportKeys : fallbackSelection;

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
  // EXIF date + has-geotag filters (Cellebrite TaggedFile metadata).
  // `null` = no filter; date strings are YYYY-MM-DD. `hasGeotag` is
  // tri-state (null / true / false) for show-all / only-geotagged /
  // only-non-geotagged. All three are nullable so the server omits
  // the param when no filter is set.
  const [captureAfter, setCaptureAfter] = useState('');
  const [captureBefore, setCaptureBefore] = useState('');
  const [hasGeotag, setHasGeotag] = useState(null);
  const [layout, setLayout] = useState('grid');

  const [selectedIds, setSelectedIds] = useState(new Set());
  const [activeFile, setActiveFile] = useState(null);

  const [caseTags, setCaseTags] = useState([]);

  // View-aware AI context
  const rootRef = useRef(null);
  const { publish, clear } = useChatContext();

  // Publish view context for the AI assistant
  useEffect(() => {
    publish({
      ...buildFilesContext({
        reports,
        selectedReportKeys,
        groupBy,
        activeNode,
        searchQuery: debouncedSearch,
        onlyRelevant,
        files,
        totalMatching: filesTotal,
        selectedIds,
      }),
      anchorRef: rootRef,
    });
  }, [
    publish,
    reports,
    selectedReportKeys,
    groupBy,
    activeNode,
    debouncedSearch,
    onlyRelevant,
    files,
    filesTotal,
    selectedIds,
  ]);

  useEffect(() => () => clear(), [clear]);

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
        captureAfter: captureAfter || null,
        captureBefore: captureBefore || null,
        hasGeotag,
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
  }, [caseId, reportKeysArr, activeNode, debouncedSearch, onlyRelevant, captureAfter, captureBefore, hasGeotag]);

  useEffect(() => {
    loadFiles();
  }, [loadFiles]);

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

  if (phoneCtx?.noneSelected) {
    return (
      <div ref={rootRef} className="flex flex-col h-full min-h-0 bg-white">
        <PhoneSelector />
        <NoPhonesSelectedEmptyState />
      </div>
    );
  }

  return (
    <div ref={rootRef} className="flex flex-col h-full min-h-0 bg-white">
      <PhoneSelector />

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

        {/* EXIF date range — capture time first, falls back to
            creation time on the backend. Inputs use the browser-
            native date picker; empty string = no bound. */}
        <div className="flex items-center gap-1 text-xs text-light-700">
          <span className="text-light-500">Taken</span>
          <input
            type="date"
            value={captureAfter}
            onChange={(e) => setCaptureAfter(e.target.value)}
            className="px-1 py-0.5 border border-light-300 rounded text-xs"
            title="Show files captured on or after this date"
          />
          <span className="text-light-400">–</span>
          <input
            type="date"
            value={captureBefore}
            onChange={(e) => setCaptureBefore(e.target.value)}
            className="px-1 py-0.5 border border-light-300 rounded text-xs"
            title="Show files captured on or before this date"
          />
          {(captureAfter || captureBefore) && (
            <button
              type="button"
              onClick={() => { setCaptureAfter(''); setCaptureBefore(''); }}
              className="text-[10px] text-light-500 hover:text-red-700 px-1"
              title="Clear date range"
            >
              ×
            </button>
          )}
        </div>

        {/* Tri-state geotag pill — All / Geotagged / No geotag.
            Cycles on click; visual state mirrors active filter. */}
        <button
          type="button"
          onClick={() => {
            // null → true → false → null
            setHasGeotag((v) => (v === null ? true : v === true ? false : null));
          }}
          className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 border rounded transition-colors ${
            hasGeotag === true
              ? 'bg-cyan-50 border-cyan-300 text-cyan-800'
              : hasGeotag === false
                ? 'bg-light-100 border-light-300 text-light-600 line-through'
                : 'bg-white border-light-300 text-light-700 hover:bg-light-100'
          }`}
          title={
            hasGeotag === true
              ? 'Showing only geotagged files (click for non-geotagged only)'
              : hasGeotag === false
                ? 'Showing only non-geotagged files (click to clear filter)'
                : 'Click to filter to geotagged files only'
          }
        >
          {hasGeotag === true ? 'Geotagged' : hasGeotag === false ? 'No geotag' : 'Any geotag'}
        </button>

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
