import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Loader2, DollarSign, RefreshCw, AlertCircle, Download, Search, X, Upload, Wand2, MessageSquare, ChevronDown, ChevronRight, BarChart3 } from 'lucide-react';
import { financialAPI } from '../../services/api';
import FinancialSummaryCards from './FinancialSummaryCards';
import FinancialCharts from './FinancialCharts';
import FinancialTable from './FinancialTable';
import FinancialFilterPanel from './FinancialFilterPanel';
import EntityFlowTables from './EntityFlowTables';
import AddCategoryModal from './AddCategoryModal';
import BulkCorrectionModal from './BulkCorrectionModal';
import AutoExtractPreviewModal from './AutoExtractPreviewModal';
import NotesUploadModal from './NotesUploadModal';

export default function FinancialView({ caseId, onNodeSelect }) {
  // ── Server-driven query result ──
  const [queryResult, setQueryResult] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isQuerying, setIsQuerying] = useState(false);
  const [error, setError] = useState(null);

  // ── Init data (transaction types + categories) ──
  const [transactionTypes, setTransactionTypes] = useState([]);
  const [categories, setCategories] = useState([]); // {name, color, builtin}[]

  // ── Filter state ──
  const [selectedTypes, setSelectedTypes] = useState(new Set());
  const [selectedCategories, setSelectedCategories] = useState(new Set());
  const [startDate, setStartDate] = useState(null);
  const [endDate, setEndDate] = useState(null);
  const [selectedFromEntities, setSelectedFromEntities] = useState(new Set());
  const [selectedToEntities, setSelectedToEntities] = useState(new Set());
  const [searchQuery, setSearchQuery] = useState(''); // Filter panel search
  const [filterExpanded, setFilterExpanded] = useState(false);
  const [chartsExpanded, setChartsExpanded] = useState(true);

  // ── Sort + Pagination (lifted from FinancialTable) ──
  const [sortField, setSortField] = useState('date');
  const [sortDir, setSortDir] = useState('asc');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(100);

  // ── Resizable charts section ──
  const [chartsSectionHeight, setChartsSectionHeight] = useState(null);
  const containerRef = useRef(null);
  const chartsSectionRef = useRef(null);
  const isDraggingRef = useRef(false);

  const handleDragStart = useCallback((e) => {
    e.preventDefault();
    isDraggingRef.current = true;
    const startY = e.clientY;
    const startHeight = chartsSectionRef.current?.getBoundingClientRect().height || 200;

    const onMouseMove = (moveEvent) => {
      if (!isDraggingRef.current) return;
      const containerRect = containerRef.current?.getBoundingClientRect();
      if (!containerRect) return;
      const delta = startY - moveEvent.clientY;
      const newHeight = Math.max(60, Math.min(startHeight - delta, containerRect.height * 0.6));
      setChartsSectionHeight(newHeight);
    };

    const onMouseUp = () => {
      isDraggingRef.current = false;
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';
  }, []);

  // ── Selection state for batch operations ──
  const [selectedKeys, setSelectedKeys] = useState([]);

  // ── Search state — inputs update immediately, API calls use debounced values ──
  const [searchTerm, setSearchTerm] = useState('');
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState('');
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState('');

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearchTerm(searchTerm), 300);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearchQuery(searchQuery), 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // ── Modal state ──
  const [showAddCategoryModal, setShowAddCategoryModal] = useState(false);
  const [showBulkCorrectionModal, setShowBulkCorrectionModal] = useState(false);
  const [showNotesUploadModal, setShowNotesUploadModal] = useState(false);
  const [showAutoExtractModal, setShowAutoExtractModal] = useState(false);
  const [autoExtractLoading, setAutoExtractLoading] = useState(false);
  const [autoExtractApplying, setAutoExtractApplying] = useState(false);
  const [autoExtractPreview, setAutoExtractPreview] = useState(null);
  const [autoExtractError, setAutoExtractError] = useState(null);

  // ── Derived from categories ──
  const categoryNames = useMemo(() => categories.map(c => c.name), [categories]);
  const categoryColorMap = useMemo(() => {
    const map = {};
    categories.forEach(c => { map[c.name] = c.color; });
    return map;
  }, [categories]);

  // ── Track whether initial load is complete (so we don't show "no data" flash) ──
  const initDoneRef = useRef(false);

  // ═══════════════════════════════════════════════════════════════════════
  // Initial load: fetch transaction types + categories, then first page
  // ═══════════════════════════════════════════════════════════════════════
  const loadInit = useCallback(async () => {
    if (!caseId) return;
    setIsLoading(true);
    setError(null);
    try {
      const [typesRes, catRes] = await Promise.all([
        financialAPI.getTransactionTypes(caseId),
        financialAPI.getCategories(caseId),
      ]);

      const types = typesRes.types || [];
      const cats = catRes.categories || [];
      setTransactionTypes(types);
      setCategories(cats);

      // Initialize filters with all types and categories selected
      setSelectedTypes(new Set(types));
      setSelectedCategories(new Set(cats.map(c => c.name)));

      initDoneRef.current = true;
    } catch (err) {
      console.error('Failed to load financial init data:', err);
      setError(err.message || 'Failed to load financial data');
    }
    setIsLoading(false);
  }, [caseId]);

  useEffect(() => {
    loadInit();
  }, [loadInit]);

  // ═══════════════════════════════════════════════════════════════════════
  // fetchPage: main data-fetching function — called whenever filters,
  // sort, or pagination change
  // ═══════════════════════════════════════════════════════════════════════
  const fetchPage = useCallback(async () => {
    if (!caseId || !initDoneRef.current) return;
    setIsQuerying(true);
    try {
      const result = await financialAPI.queryTransactions({
        caseId,
        types: selectedTypes.size > 0 ? [...selectedTypes].join(',') : undefined,
        categories: selectedCategories.size > 0 ? [...selectedCategories].join(',') : undefined,
        startDate: startDate || undefined,
        endDate: endDate || undefined,
        search: debouncedSearchQuery || undefined,
        searchHeader: debouncedSearchTerm || undefined,
        fromEntities: selectedFromEntities.size > 0 ? [...selectedFromEntities].join(',') : undefined,
        toEntities: selectedToEntities.size > 0 ? [...selectedToEntities].join(',') : undefined,
        sortField,
        sortDir,
        page,
        pageSize,
      });
      setQueryResult(result);
    } catch (err) {
      console.error('Failed to query transactions:', err);
      // Don't clobber existing data on transient errors — just log
    }
    setIsQuerying(false);
  }, [
    caseId, selectedTypes, selectedCategories, startDate, endDate,
    debouncedSearchQuery, debouncedSearchTerm,
    selectedFromEntities, selectedToEntities,
    sortField, sortDir, page, pageSize,
  ]);

  // Trigger fetchPage whenever any dependency changes
  useEffect(() => {
    fetchPage();
  }, [fetchPage]);

  // Reset to page 1 when any filter (not sort/page) changes
  useEffect(() => {
    setPage(1);
  }, [
    selectedTypes, selectedCategories, startDate, endDate,
    debouncedSearchQuery, debouncedSearchTerm,
    selectedFromEntities, selectedToEntities,
  ]);

  // Refresh financial data when entities are merged/changed elsewhere
  useEffect(() => {
    const handleEntitiesRefresh = () => {
      loadInit().then(() => fetchPage());
    };
    window.addEventListener('entities-refresh', handleEntitiesRefresh);
    return () => window.removeEventListener('entities-refresh', handleEntitiesRefresh);
  }, [loadInit, fetchPage]);

  // ═══════════════════════════════════════════════════════════════════════
  // Derived from queryResult
  // ═══════════════════════════════════════════════════════════════════════
  const transactions = queryResult?.transactions || [];
  const totalCount = queryResult?.total || 0;
  const totalPages = queryResult?.total_pages || 0;
  const summary = queryResult?.summary || null;
  const fromEntities = queryResult?.from_entities || [];
  const toEntities = queryResult?.to_entities || [];
  const volumeData = queryResult?.volume_data || [];
  const categoryBreakdown = queryResult?.category_breakdown || {};

  const hasEntitySelection = selectedFromEntities.size > 0 || selectedToEntities.size > 0;

  // ═══════════════════════════════════════════════════════════════════════
  // Inline edit handlers — optimistic updates on queryResult.transactions
  // ═══════════════════════════════════════════════════════════════════════
  const updateTransaction = useCallback((key, updater) => {
    setQueryResult(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        transactions: prev.transactions.map(t =>
          t.key === key ? updater(t) : t
        ),
      };
    });
  }, []);

  const updateTransactionsBatch = useCallback((keys, updater) => {
    setQueryResult(prev => {
      if (!prev) return prev;
      const keySet = new Set(keys);
      return {
        ...prev,
        transactions: prev.transactions.map(t =>
          keySet.has(t.key) ? updater(t) : t
        ),
      };
    });
  }, []);

  // Handle category change on a single transaction
  const handleCategoryChange = useCallback(async (nodeKey, category) => {
    try {
      await financialAPI.categorize(nodeKey, category, caseId);
      updateTransaction(nodeKey, t => ({ ...t, category }));
    } catch (err) {
      console.error('Failed to categorize:', err);
      alert('Failed to save category. Please try selecting the category again.\n\n' + err.message);
    }
  }, [caseId, updateTransaction]);

  // Handle batch categorize
  const handleBatchCategorize = useCallback(async (nodeKeys, category) => {
    try {
      await financialAPI.batchCategorize(nodeKeys, category, caseId);
      updateTransactionsBatch(nodeKeys, t => ({ ...t, category }));
    } catch (err) {
      console.error('Failed to batch categorize:', err);
      alert('Failed to save category for ' + nodeKeys.length + ' transactions. Please try again.\n\n' + err.message);
    }
  }, [caseId, updateTransactionsBatch]);

  // Handle from/to change
  const handleFromToChange = useCallback(async (nodeKey, side, entity) => {
    try {
      const payload = { caseId };
      if (side === 'from') {
        payload.fromKey = entity.key;
        payload.fromName = entity.name;
      } else {
        payload.toKey = entity.key;
        payload.toName = entity.name;
      }
      await financialAPI.setFromTo(nodeKey, payload);
      updateTransaction(nodeKey, t => {
        if (side === 'from') {
          return { ...t, from_entity: entity, has_manual_from: true };
        }
        return { ...t, to_entity: entity, has_manual_to: true };
      });
    } catch (err) {
      console.error('Failed to update from/to:', err);
      alert('Failed to save sender/beneficiary. Please click the edit icon and try again.\n\n' + err.message);
    }
  }, [caseId, updateTransaction]);

  // Handle swap from/to
  const handleSwapFromTo = useCallback(async (nodeKey, fromEntity, toEntity) => {
    try {
      await financialAPI.setFromTo(nodeKey, {
        caseId,
        fromKey: toEntity?.key,
        fromName: toEntity?.name,
        toKey: fromEntity?.key,
        toName: fromEntity?.name,
      });
      updateTransaction(nodeKey, t => ({
        ...t,
        from_entity: toEntity,
        to_entity: fromEntity,
        has_manual_from: true,
        has_manual_to: true,
      }));
    } catch (err) {
      console.error('Failed to swap from/to:', err);
      alert('Failed to swap sender/beneficiary. Please try again.\n\n' + err.message);
    }
  }, [caseId, updateTransaction]);

  // Handle details change (purpose, counterparty_details, notes)
  const handleDetailsChange = useCallback(async (nodeKey, details) => {
    try {
      await financialAPI.updateDetails(nodeKey, {
        caseId,
        purpose: details.purpose,
        counterpartyDetails: details.counterpartyDetails,
        notes: details.notes,
      });
      updateTransaction(nodeKey, t => {
        const updated = { ...t };
        if (details.purpose !== undefined) updated.purpose = details.purpose;
        if (details.counterpartyDetails !== undefined) updated.counterparty_details = details.counterpartyDetails;
        if (details.notes !== undefined) updated.notes = details.notes;
        return updated;
      });
    } catch (err) {
      console.error('Failed to update details:', err);
      alert('Failed to save transaction details. Please click into the field and try again.\n\n' + err.message);
    }
  }, [caseId, updateTransaction]);

  const handleAmountChange = useCallback(async (nodeKey, newAmount, correctionReason) => {
    try {
      await financialAPI.updateAmount(nodeKey, {
        caseId: caseId,
        newAmount,
        correctionReason,
      });
      updateTransaction(nodeKey, t => ({
        ...t,
        amount: newAmount,
        amount_corrected: true,
        original_amount: t.original_amount ?? t.amount,
        correction_reason: correctionReason,
      }));
    } catch (err) {
      console.error('Failed to update amount:', err);
      alert('Failed to save amount correction. Please click the amount and try again.\n\n' + err.message);
    }
  }, [caseId, updateTransaction]);

  // Handle batch from/to change
  const handleBatchFromTo = useCallback(async (nodeKeys, side, entity) => {
    try {
      const payload = { caseId };
      if (side === 'from') {
        payload.fromKey = entity.key;
        payload.fromName = entity.name;
      } else {
        payload.toKey = entity.key;
        payload.toName = entity.name;
      }
      await financialAPI.batchSetFromTo(nodeKeys, payload);
      updateTransactionsBatch(nodeKeys, t => {
        if (side === 'from') {
          return { ...t, from_entity: entity, has_manual_from: true };
        }
        return { ...t, to_entity: entity, has_manual_to: true };
      });
    } catch (err) {
      console.error('Failed to batch update from/to:', err);
      alert('Failed to save sender/beneficiary for ' + nodeKeys.length + ' transactions. Please try again.\n\n' + err.message);
    }
  }, [caseId, updateTransactionsBatch]);

  // Handle creating a new custom category
  const handleCreateCategory = useCallback(async (name, color) => {
    await financialAPI.createCategory(name, color, caseId);
    // Refresh categories from backend to get accurate state
    const catRes = await financialAPI.getCategories(caseId);
    const cats = catRes.categories || [];
    setCategories(cats);
    // Auto-select the new category in filters
    setSelectedCategories(prev => {
      const next = new Set(prev);
      next.add(name);
      return next;
    });
  }, [caseId]);

  const handleExportPDF = () => {
    const params = new URLSearchParams();
    params.append('case_id', caseId);
    params.append('case_name', caseId);
    if (selectedCategories.size > 0) {
      params.append('categories', [...selectedCategories].join(','));
    }
    if (selectedTypes.size > 0) {
      params.append('types', [...selectedTypes].join(','));
    }
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    if (selectedFromEntities.size > 0) {
      params.append('from_entities', [...selectedFromEntities].join(','));
    }
    if (selectedToEntities.size > 0) {
      params.append('to_entities', [...selectedToEntities].join(','));
    }
    if (searchQuery && searchQuery.trim()) {
      params.append('search', searchQuery.trim());
    }
    if (searchTerm.trim()) {
      params.append('search_header', searchTerm.trim());
    }
    params.append('include_entity_notes', 'true');
    window.open(`/api/financial/export/pdf?${params.toString()}`, '_blank');
  };

  // Auto-extract from/to: preview (dry run)
  const handleAutoExtractPreview = useCallback(async () => {
    setShowAutoExtractModal(true);
    setAutoExtractLoading(true);
    setAutoExtractPreview(null);
    setAutoExtractError(null);
    try {
      const result = await financialAPI.autoExtractFromTo(caseId, { dryRun: true });
      setAutoExtractPreview(result);
    } catch (err) {
      console.error('Auto-extract preview failed:', err);
      setAutoExtractError(err.message || 'Failed to analyze transactions');
    }
    setAutoExtractLoading(false);
  }, [caseId]);

  // Auto-extract from/to: apply
  const handleAutoExtractApply = useCallback(async () => {
    setAutoExtractApplying(true);
    setAutoExtractError(null);
    try {
      await financialAPI.autoExtractFromTo(caseId, { dryRun: false });
      setShowAutoExtractModal(false);
      setAutoExtractPreview(null);
      await fetchPage();
    } catch (err) {
      console.error('Auto-extract apply failed:', err);
      setAutoExtractError(err.message || 'Failed to apply extractions');
    }
    setAutoExtractApplying(false);
  }, [caseId, fetchPage]);

  // Sort change handler (passed to FinancialTable)
  const handleSortChange = useCallback((field, dir) => {
    setSortField(field);
    setSortDir(dir);
  }, []);

  // Page change handler
  const handlePageChange = useCallback((newPage) => {
    setPage(newPage);
  }, []);

  // Page size change handler
  const handlePageSizeChange = useCallback((newSize) => {
    setPageSize(newSize);
    setPage(1);
  }, []);

  // Filter handlers
  const toggleType = (type) => {
    setSelectedTypes(prev => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  const toggleCategory = (cat) => {
    setSelectedCategories(prev => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  };

  // Full refresh (re-init + re-fetch)
  const handleFullRefresh = useCallback(async () => {
    await loadInit();
    // fetchPage will be triggered by the state changes from loadInit
  }, [loadInit]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex items-center gap-2 text-light-500">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span className="text-sm">Loading financial data...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <AlertCircle className="w-8 h-8 text-red-400 mx-auto mb-2" />
          <p className="text-sm text-light-600">{error}</p>
          <button onClick={handleFullRefresh} className="mt-2 text-sm text-owl-blue-600 hover:underline flex items-center gap-1 mx-auto">
            <RefreshCw className="w-3.5 h-3.5" /> Retry
          </button>
        </div>
      </div>
    );
  }

  if (!queryResult && !isQuerying) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <DollarSign className="w-8 h-8 text-light-300 mx-auto mb-2" />
          <p className="text-sm text-light-500">No financial data available</p>
          <p className="text-xs text-light-400 mt-1">This case has no entities with amount properties</p>
        </div>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex-shrink-0 px-4 py-2 border-b border-light-200 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <DollarSign className="w-4 h-4 text-owl-blue-600" />
          <span className="text-sm font-medium text-light-800">Financial Analysis</span>
          <span className="text-xs text-light-500">
            {totalCount > 0
              ? `${transactions.length} of ${totalCount.toLocaleString()} transactions (page ${page})`
              : '0 transactions'}
          </span>
          {isQuerying && <Loader2 className="w-3 h-3 animate-spin text-owl-blue-500" />}
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-light-400" />
            <input
              type="text"
              placeholder="Search transactions..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-48 text-xs pl-7 pr-7 py-1.5 border border-light-200 rounded focus:outline-none focus:border-owl-blue-400"
            />
            {searchTerm && (
              <button
                onClick={() => { setSearchTerm(''); setDebouncedSearchTerm(''); }}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-light-400 hover:text-light-600"
              >
                <X className="w-3 h-3" />
              </button>
            )}
          </div>
          <div className="flex items-center gap-1">
          <button
            onClick={handleAutoExtractPreview}
            className="flex items-center gap-1 px-2 py-1 text-xs text-owl-blue-600 border border-owl-blue-200 rounded hover:bg-owl-blue-50"
            title="Auto-extract Senders & Beneficiaries from transaction names"
          >
            <Wand2 className="w-3.5 h-3.5" />
            <span>Auto-Extract</span>
          </button>
          <button
            onClick={() => setShowNotesUploadModal(true)}
            className="flex items-center gap-1 px-2 py-1 text-xs text-light-600 border border-light-200 rounded hover:bg-light-50"
            title="Upload investigator notes CSV"
          >
            <MessageSquare className="w-3.5 h-3.5" />
            <span>Notes CSV</span>
          </button>
          <button
            onClick={() => setShowBulkCorrectionModal(true)}
            className="p-1 text-light-500 hover:text-owl-blue-600 rounded hover:bg-light-50"
            title="Import Bulk Corrections"
          >
            <Upload className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleExportPDF}
            className="p-1 text-light-500 hover:text-owl-blue-600 rounded hover:bg-light-50"
            title="Export PDF"
          >
            <Download className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleFullRefresh}
            className="p-1 text-light-500 hover:text-owl-blue-600 rounded hover:bg-light-50"
            title="Refresh"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
          </div>
        </div>
      </div>

      {/* Top: Filters + Summary Cards */}
      <div className="flex-shrink-0 px-4 py-2 space-y-2">
        <FinancialFilterPanel
          transactionTypes={transactionTypes}
          selectedTypes={selectedTypes}
          onToggleType={toggleType}
          onSelectAllTypes={() => setSelectedTypes(new Set(transactionTypes))}
          onClearAllTypes={() => setSelectedTypes(new Set())}
          categories={categoryNames}
          selectedCategories={selectedCategories}
          onToggleCategory={toggleCategory}
          onSelectAllCategories={() => setSelectedCategories(new Set(categoryNames))}
          onClearAllCategories={() => setSelectedCategories(new Set())}
          startDate={startDate}
          endDate={endDate}
          onStartDateChange={setStartDate}
          onEndDateChange={setEndDate}
          isExpanded={filterExpanded}
          onToggleExpand={() => setFilterExpanded(!filterExpanded)}
          categoryColorMap={categoryColorMap}
          onAddCategory={() => setShowAddCategoryModal(true)}
          searchQuery={searchQuery}
          onSearchChange={(val) => { setSearchQuery(val); if (!val) setDebouncedSearchQuery(''); }}
        />
        <FinancialSummaryCards
          summary={summary}
          hasEntitySelection={hasEntitySelection}
          entitySelectionLabel={
            [
              selectedFromEntities.size > 0 ? `${selectedFromEntities.size} sender(s)` : '',
              selectedToEntities.size > 0 ? `${selectedToEntities.size} recipient(s)` : '',
            ].filter(Boolean).join(' and ')
          }
        />
      </div>

      {/* Charts & Entity Flow — full width, collapsible, resizable */}
      <div
        ref={chartsSectionRef}
        className="border-t border-light-200 flex flex-col min-h-0"
        style={chartsExpanded && chartsSectionHeight != null ? { height: chartsSectionHeight, flexShrink: 0 } : chartsExpanded ? { maxHeight: '30vh', flexShrink: 0 } : {}}
      >
        <div
          className="flex-shrink-0 flex items-center gap-2 px-4 py-2 cursor-pointer hover:bg-light-50 select-none"
          onClick={() => setChartsExpanded(!chartsExpanded)}
        >
          {chartsExpanded ? <ChevronDown className="w-4 h-4 text-light-500" /> : <ChevronRight className="w-4 h-4 text-light-500" />}
          <BarChart3 className="w-4 h-4 text-light-600" />
          <span className="text-sm font-medium text-light-700">Charts & Entity Flow</span>
          {hasEntitySelection && (
            <span className="text-xs text-owl-blue-600">
              ({[
                selectedFromEntities.size > 0 ? `${selectedFromEntities.size} senders` : '',
                selectedToEntities.size > 0 ? `${selectedToEntities.size} recipients` : '',
              ].filter(Boolean).join(', ')} selected)
            </span>
          )}
        </div>

        {chartsExpanded && (
          <div className="flex-1 min-h-0 overflow-y-auto px-4 pb-3 space-y-3">
            <FinancialCharts
              volumeData={volumeData}
              categoryBreakdown={categoryBreakdown}
              categoryColorMap={categoryColorMap}
            />
            <EntityFlowTables
              fromEntities={fromEntities}
              toEntities={toEntities}
              selectedFromEntities={selectedFromEntities}
              selectedToEntities={selectedToEntities}
              onFromSelectionChange={setSelectedFromEntities}
              onToSelectionChange={setSelectedToEntities}
            />
          </div>
        )}
      </div>

      {/* Drag handle to resize charts vs table */}
      {chartsExpanded && (
        <div
          onMouseDown={handleDragStart}
          className="flex-shrink-0 h-1.5 border-t border-b border-light-200 cursor-row-resize hover:bg-owl-blue-100 active:bg-owl-blue-200 transition-colors group relative"
          title="Drag to resize"
        >
          <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 flex justify-center">
            <div className="w-8 h-0.5 rounded-full bg-light-300 group-hover:bg-owl-blue-400 transition-colors" />
          </div>
        </div>
      )}

      {/* Transaction Table — full width, takes all remaining space */}
      <div className="flex-1 min-h-0 border-t border-light-200">
        <FinancialTable
          transactions={transactions}
          categories={categoryNames}
          categoryColorMap={categoryColorMap}
          caseId={caseId}
          onNodeSelect={onNodeSelect}
          onCategoryChange={handleCategoryChange}
          onFromToChange={handleFromToChange}
          onDetailsChange={handleDetailsChange}
          onAmountChange={handleAmountChange}
          onBatchFromTo={handleBatchFromTo}
          selectedKeys={selectedKeys}
          onSelectionChange={setSelectedKeys}
          onBatchCategorize={handleBatchCategorize}
          onTransactionsRefresh={fetchPage}
          onSwapFromTo={handleSwapFromTo}
          /* Server-driven sort/pagination */
          sortField={sortField}
          sortDir={sortDir}
          onSortChange={handleSortChange}
          page={page}
          pageSize={pageSize}
          totalCount={totalCount}
          totalPages={totalPages}
          onPageChange={handlePageChange}
          onPageSizeChange={handlePageSizeChange}
        />
      </div>

      {/* Add Category Modal */}
      <AddCategoryModal
        isOpen={showAddCategoryModal}
        onClose={() => setShowAddCategoryModal(false)}
        onSubmit={handleCreateCategory}
        existingNames={categoryNames}
      />

      {/* Bulk Correction Modal */}
      <BulkCorrectionModal
        isOpen={showBulkCorrectionModal}
        onClose={() => setShowBulkCorrectionModal(false)}
        caseId={caseId}
        transactions={transactions}
        onComplete={fetchPage}
      />

      {/* Notes Upload Modal */}
      <NotesUploadModal
        isOpen={showNotesUploadModal}
        onClose={() => setShowNotesUploadModal(false)}
        caseId={caseId}
        transactions={transactions}
        onComplete={fetchPage}
      />

      {/* Auto-Extract From/To Modal */}
      <AutoExtractPreviewModal
        isOpen={showAutoExtractModal}
        onClose={() => {
          if (!autoExtractApplying) {
            setShowAutoExtractModal(false);
            setAutoExtractPreview(null);
            setAutoExtractError(null);
          }
        }}
        preview={autoExtractPreview}
        loading={autoExtractLoading}
        applying={autoExtractApplying}
        onApply={handleAutoExtractApply}
        error={autoExtractError}
      />
    </div>
  );
}
