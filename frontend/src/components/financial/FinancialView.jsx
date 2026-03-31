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
  const [transactions, setTransactions] = useState([]);
  const [volumeData, setVolumeData] = useState([]);
  const [categories, setCategories] = useState([]); // {name, color, builtin}[]
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filter state
  const [selectedTypes, setSelectedTypes] = useState(new Set());
  const [selectedCategories, setSelectedCategories] = useState(new Set());
  const [startDate, setStartDate] = useState(null);
  const [endDate, setEndDate] = useState(null);
  const [selectedFromEntities, setSelectedFromEntities] = useState(new Set()); // Set of entity keys
  const [selectedToEntities, setSelectedToEntities] = useState(new Set());     // Set of entity keys
  const [searchQuery, setSearchQuery] = useState(''); // Free-text search across names
  const [filterExpanded, setFilterExpanded] = useState(false);
  const [chartsExpanded, setChartsExpanded] = useState(true);

  // Resizable charts section — user drags the divider to control height
  const [chartsSectionHeight, setChartsSectionHeight] = useState(null); // null = auto (use default)
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

  // Selection state for batch operations
  const [selectedKeys, setSelectedKeys] = useState([]);

  // Search state
  const [searchTerm, setSearchTerm] = useState('');

  // Add category modal
  const [showAddCategoryModal, setShowAddCategoryModal] = useState(false);

  // Bulk correction modal
  const [showBulkCorrectionModal, setShowBulkCorrectionModal] = useState(false);

  // Notes upload modal
  const [showNotesUploadModal, setShowNotesUploadModal] = useState(false);

  // Auto-extract from/to modal
  const [showAutoExtractModal, setShowAutoExtractModal] = useState(false);
  const [autoExtractLoading, setAutoExtractLoading] = useState(false);
  const [autoExtractApplying, setAutoExtractApplying] = useState(false);
  const [autoExtractPreview, setAutoExtractPreview] = useState(null);
  const [autoExtractError, setAutoExtractError] = useState(null);

  // Derived helpers from category objects
  const categoryNames = useMemo(() => categories.map(c => c.name), [categories]);
  const categoryColorMap = useMemo(() => {
    const map = {};
    categories.forEach(c => { map[c.name] = c.color; });
    return map;
  }, [categories]);

  // Load all financial data
  const loadData = useCallback(async () => {
    if (!caseId) return;
    setIsLoading(true);
    setError(null);
    try {
      const [txnRes, volumeRes, catRes] = await Promise.all([
        financialAPI.getTransactions({ caseId }),
        financialAPI.getVolume(caseId),
        financialAPI.getCategories(caseId),
      ]);
      setTransactions(txnRes.transactions || []);
      setVolumeData(volumeRes.data || []);
      const cats = catRes.categories || [];
      setCategories(cats);

      // Initialize filters with all types and categories selected
      const types = new Set((txnRes.transactions || []).map(t => t.type));
      setSelectedTypes(types);
      setSelectedCategories(new Set(cats.map(c => c.name)));
    } catch (err) {
      console.error('Failed to load financial data:', err);
      setError(err.message || 'Failed to load financial data');
    }
    setIsLoading(false);
  }, [caseId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Derive available transaction types from data
  const transactionTypes = useMemo(() => {
    const types = new Set(transactions.map(t => t.type));
    return [...types].sort();
  }, [transactions]);

  // Stage 1: Filter transactions by type/category/date/search (before entity selection)
  // This feeds the entity flow tables so they reflect non-entity filters
  const baseFilteredTransactions = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    return transactions.filter(t => {
      if (selectedTypes.size > 0 && !selectedTypes.has(t.type)) return false;
      if (selectedCategories.size > 0 && !selectedCategories.has(t.category || 'Unknown')) return false;
      if (startDate && t.date && t.date < startDate) return false;
      if (endDate && t.date && t.date > endDate) return false;
      if (q) {
        const fields = [
          t.name, t.purpose, t.notes, t.counterparty_details,
          t.from_entity?.name, t.to_entity?.name,
          t.category,
        ].filter(Boolean).map(f => f.toLowerCase());
        if (!fields.some(f => f.includes(q))) return false;
      }
      if (searchTerm.trim()) {
        const st = searchTerm.toLowerCase();
        const nameMatch = (t.name || '').toLowerCase().includes(st);
        const fromMatch = (t.from_entity?.name || '').toLowerCase().includes(st);
        const toMatch = (t.to_entity?.name || '').toLowerCase().includes(st);
        const purposeMatch = (t.purpose || '').toLowerCase().includes(st);
        const notesMatch = (t.notes || '').toLowerCase().includes(st);
        if (!nameMatch && !fromMatch && !toMatch && !purposeMatch && !notesMatch) return false;
      }
      return true;
    });
  }, [transactions, selectedTypes, selectedCategories, startDate, endDate, searchQuery, searchTerm]);

  // Compute From entities (senders), constrained by To selection for cross-filtering
  const fromEntities = useMemo(() => {
    const map = new Map();
    baseFilteredTransactions.forEach(t => {
      if (!t.from_entity?.name) return;
      // If To entities are selected, only include senders on those recipients' transactions
      if (selectedToEntities.size > 0) {
        const toKey = t.to_entity?.key || t.to_entity?.name;
        if (!toKey || !selectedToEntities.has(toKey)) return;
      }
      const key = t.from_entity.key || t.from_entity.name;
      const existing = map.get(key) || { key, name: t.from_entity.name, count: 0, totalAmount: 0 };
      existing.count += 1;
      existing.totalAmount += Math.abs(parseFloat(t.amount) || 0);
      map.set(key, existing);
    });
    return [...map.values()].sort((a, b) => b.totalAmount - a.totalAmount);
  }, [baseFilteredTransactions, selectedToEntities]);

  // Compute To entities (recipients), constrained by From selection for cross-filtering
  const toEntities = useMemo(() => {
    const map = new Map();
    baseFilteredTransactions.forEach(t => {
      if (!t.to_entity?.name) return;
      // If From entities are selected, only include recipients on those senders' transactions
      if (selectedFromEntities.size > 0) {
        const fromKey = t.from_entity?.key || t.from_entity?.name;
        if (!fromKey || !selectedFromEntities.has(fromKey)) return;
      }
      const key = t.to_entity.key || t.to_entity.name;
      const existing = map.get(key) || { key, name: t.to_entity.name, count: 0, totalAmount: 0 };
      existing.count += 1;
      existing.totalAmount += Math.abs(parseFloat(t.amount) || 0);
      map.set(key, existing);
    });
    return [...map.values()].sort((a, b) => b.totalAmount - a.totalAmount);
  }, [baseFilteredTransactions, selectedFromEntities]);

  // Stage 2: Apply entity selection filtering on top of base
  const filteredTransactions = useMemo(() => {
    return baseFilteredTransactions.filter(t => {
      if (selectedFromEntities.size > 0) {
        const fromKey = t.from_entity?.key || t.from_entity?.name;
        if (!fromKey || !selectedFromEntities.has(fromKey)) return false;
      }
      if (selectedToEntities.size > 0) {
        const toKey = t.to_entity?.key || t.to_entity?.name;
        if (!toKey || !selectedToEntities.has(toKey)) return false;
      }
      return true;
    });
  }, [baseFilteredTransactions, selectedFromEntities, selectedToEntities]);

  // Compute summary from filtered transactions — context-aware based on entity selection
  const hasEntitySelection = selectedFromEntities.size > 0 || selectedToEntities.size > 0;
  const filteredSummary = useMemo(() => {
    const count = filteredTransactions.length;
    if (count === 0) {
      return hasEntitySelection
        ? { transaction_count: 0, total_inflows: 0, total_outflows: 0, net_flow: 0 }
        : { transaction_count: 0, total_volume: 0, unique_entities: 0, avg_amount: 0 };
    }

    if (hasEntitySelection) {
      // Entity mode: classify flows relative to selected entities
      let inflows = 0, outflows = 0;
      filteredTransactions.forEach(t => {
        const amt = Math.abs(parseFloat(t.amount) || 0);
        const toKey = t.to_entity?.key || t.to_entity?.name;
        const fromKey = t.from_entity?.key || t.from_entity?.name;
        // Use From selection as primary perspective; fall back to To
        if (selectedFromEntities.size > 0) {
          if (fromKey && selectedFromEntities.has(fromKey)) outflows += amt;
          if (toKey && selectedFromEntities.has(toKey)) inflows += amt;
        } else if (selectedToEntities.size > 0) {
          if (toKey && selectedToEntities.has(toKey)) inflows += amt;
          if (fromKey && selectedToEntities.has(fromKey)) outflows += amt;
        }
      });
      return {
        transaction_count: count,
        total_inflows: Math.round(inflows * 100) / 100,
        total_outflows: Math.round(outflows * 100) / 100,
        net_flow: Math.round((inflows - outflows) * 100) / 100,
      };
    } else {
      // Overview mode: aggregate metrics without directional flow
      let volume = 0;
      const entityKeys = new Set();
      filteredTransactions.forEach(t => {
        volume += Math.abs(parseFloat(t.amount) || 0);
        if (t.from_entity?.key) entityKeys.add(t.from_entity.key);
        else if (t.from_entity?.name) entityKeys.add(t.from_entity.name);
        if (t.to_entity?.key) entityKeys.add(t.to_entity.key);
        else if (t.to_entity?.name) entityKeys.add(t.to_entity.name);
      });
      return {
        transaction_count: count,
        total_volume: Math.round(volume * 100) / 100,
        unique_entities: entityKeys.size,
        avg_amount: Math.round((volume / count) * 100) / 100,
      };
    }
  }, [filteredTransactions, hasEntitySelection, selectedFromEntities, selectedToEntities]);

  // Compute volume data from filtered transactions so charts update with filters
  const filteredVolumeData = useMemo(() => {
    const groups = {};
    filteredTransactions.forEach(t => {
      if (!t.date) return;
      const cat = t.category || 'Uncategorized';
      const key = `${t.date}|${cat}`;
      if (!groups[key]) groups[key] = { date: t.date, category: cat, total_amount: 0, count: 0 };
      groups[key].total_amount += Math.abs(parseFloat(t.amount) || 0);
      groups[key].count += 1;
    });
    return Object.values(groups).sort((a, b) => a.date.localeCompare(b.date) || a.category.localeCompare(b.category));
  }, [filteredTransactions]);

  // Handle category change on a single transaction
  const handleCategoryChange = useCallback(async (nodeKey, category) => {
    try {
      await financialAPI.categorize(nodeKey, category, caseId);
      setTransactions(prev =>
        prev.map(t => t.key === nodeKey ? { ...t, category: category } : t)
      );
    } catch (err) {
      console.error('Failed to categorize:', err);
      alert('Failed to save category. Please try selecting the category again.\n\n' + err.message);
    }
  }, [caseId]);

  // Handle batch categorize
  const handleBatchCategorize = useCallback(async (nodeKeys, category) => {
    try {
      await financialAPI.batchCategorize(nodeKeys, category, caseId);
      setTransactions(prev =>
        prev.map(t => nodeKeys.includes(t.key) ? { ...t, category: category } : t)
      );
    } catch (err) {
      console.error('Failed to batch categorize:', err);
      alert('Failed to save category for ' + nodeKeys.length + ' transactions. Please try again.\n\n' + err.message);
    }
  }, [caseId]);

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
      setTransactions(prev =>
        prev.map(t => {
          if (t.key !== nodeKey) return t;
          if (side === 'from') {
            return { ...t, from_entity: entity, has_manual_from: true };
          }
          return { ...t, to_entity: entity, has_manual_to: true };
        })
      );
    } catch (err) {
      console.error('Failed to update from/to:', err);
      alert('Failed to save sender/beneficiary. Please click the edit icon and try again.\n\n' + err.message);
    }
  }, [caseId]);

  // Handle details change (purpose, counterparty_details, notes)
  const handleDetailsChange = useCallback(async (nodeKey, details) => {
    try {
      await financialAPI.updateDetails(nodeKey, {
        caseId,
        purpose: details.purpose,
        counterpartyDetails: details.counterpartyDetails,
        notes: details.notes,
      });
      setTransactions(prev =>
        prev.map(t => {
          if (t.key !== nodeKey) return t;
          const updated = { ...t };
          if (details.purpose !== undefined) updated.purpose = details.purpose;
          if (details.counterpartyDetails !== undefined) updated.counterparty_details = details.counterpartyDetails;
          if (details.notes !== undefined) updated.notes = details.notes;
          return updated;
        })
      );
    } catch (err) {
      console.error('Failed to update details:', err);
      alert('Failed to save transaction details. Please click into the field and try again.\n\n' + err.message);
    }
  }, [caseId]);

  const handleAmountChange = useCallback(async (nodeKey, newAmount, correctionReason) => {
    try {
      await financialAPI.updateAmount(nodeKey, {
        caseId: caseId,
        newAmount,
        correctionReason,
      });
      setTransactions(prev =>
        prev.map(t => t.key === nodeKey ? {
          ...t,
          amount: newAmount,
          amount_corrected: true,
          original_amount: t.original_amount ?? t.amount,
          correction_reason: correctionReason,
        } : t)
      );
    } catch (err) {
      console.error('Failed to update amount:', err);
      alert('Failed to save amount correction. Please click the amount and try again.\n\n' + err.message);
    }
  }, [caseId]);

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
      setTransactions(prev =>
        prev.map(t => {
          if (!nodeKeys.includes(t.key)) return t;
          if (side === 'from') {
            return { ...t, from_entity: entity, has_manual_from: true };
          }
          return { ...t, to_entity: entity, has_manual_to: true };
        })
      );
    } catch (err) {
      console.error('Failed to batch update from/to:', err);
      alert('Failed to save sender/beneficiary for ' + nodeKeys.length + ' transactions. Please try again.\n\n' + err.message);
    }
  }, [caseId]);

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
    params.append('case_name', caseId); // Case ID used as name if no name prop
    if (selectedCategories.size > 0 && selectedCategories.size < categoryNames.length) {
      params.append('categories', [...selectedCategories].join(','));
    }
    if (selectedTypes.size > 0 && selectedTypes.size < transactionTypes.length) {
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
    } else if (searchTerm.trim()) {
      params.append('search', searchTerm.trim());
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
      await loadData();
    } catch (err) {
      console.error('Auto-extract apply failed:', err);
      setAutoExtractError(err.message || 'Failed to apply extractions');
    }
    setAutoExtractApplying(false);
  }, [caseId, loadData]);

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
          <button onClick={loadData} className="mt-2 text-sm text-owl-blue-600 hover:underline flex items-center gap-1 mx-auto">
            <RefreshCw className="w-3.5 h-3.5" /> Retry
          </button>
        </div>
      </div>
    );
  }

  if (transactions.length === 0) {
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
            {filteredTransactions.length} of {transactions.length} transactions
          </span>
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
                onClick={() => setSearchTerm('')}
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
            onClick={loadData}
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
          onSearchChange={setSearchQuery}
        />
        <FinancialSummaryCards
          summary={filteredSummary}
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
            <FinancialCharts volumeData={filteredVolumeData} transactions={filteredTransactions} categoryColorMap={categoryColorMap} />
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
          transactions={filteredTransactions}
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
          onTransactionsRefresh={loadData}
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
        onComplete={loadData}
      />

      {/* Notes Upload Modal */}
      <NotesUploadModal
        isOpen={showNotesUploadModal}
        onClose={() => setShowNotesUploadModal(false)}
        caseId={caseId}
        transactions={transactions}
        onComplete={loadData}
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
