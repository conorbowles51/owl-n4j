import React, { useState, useEffect, useCallback } from 'react';
import { 
  FileText, 
  X, 
  Filter, 
  RefreshCw, 
  Trash2,
  CheckCircle,
  XCircle,
  AlertCircle,
  Search,
  ChevronDown,
  ChevronUp,
  Clock,
  List,
  Calendar,
  DollarSign
} from 'lucide-react';
import { systemLogsAPI } from '../services/api';
import CostLedgerPanel from './CostLedgerPanel';

const LOG_TYPES = [
  { value: 'ai_assistant', label: 'AI Assistant' },
  { value: 'graph_operation', label: 'Graph Operation' },
  { value: 'case_management', label: 'Case Management' },
  { value: 'document_ingestion', label: 'Document Ingestion' },
  { value: 'user_action', label: 'User Action' },
  { value: 'system', label: 'System' },
  { value: 'error', label: 'Error' },
];

const LOG_ORIGINS = [
  { value: 'frontend', label: 'Frontend' },
  { value: 'backend', label: 'Backend' },
  { value: 'ingestion', label: 'Ingestion' },
  { value: 'system', label: 'System' },
];

export default function SystemLogsPanel({ isOpen, onClose }) {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [statistics, setStatistics] = useState(null);
  const [expandedLogs, setExpandedLogs] = useState(new Set());
  const [showCostLedger, setShowCostLedger] = useState(false);
  
  // Filters - using arrays for multi-select
  const [filters, setFilters] = useState({
    log_type: [], // Array of selected log types
    origin: [], // Array of selected origins
    user: '',
    success_only: null,
    search: '',
  });
  const [limit, setLimit] = useState(100);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [showFilters, setShowFilters] = useState(true);
  const [viewMode, setViewMode] = useState('list'); // 'list' or 'timeline'

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params = {
        ...filters,
        limit,
        offset,
      };
      
      // Remove empty filters and convert arrays to comma-separated strings for API
      const cleanedParams = {};
      Object.keys(params).forEach(key => {
        const value = params[key];
        if (value === '' || value === null || (Array.isArray(value) && value.length === 0)) {
          return; // Skip empty values
        }
        // Convert arrays to comma-separated strings for API
        if (Array.isArray(value)) {
          cleanedParams[key] = value.join(',');
        } else {
          cleanedParams[key] = value;
        }
      });
      const result = await systemLogsAPI.getLogs(cleanedParams);
      
      setLogs(result.logs || []);
      setTotal(result.total || 0);
    } catch (err) {
      console.error('Failed to load logs:', err);
    } finally {
      setLoading(false);
    }
  }, [filters, limit, offset]);

  const loadStatistics = useCallback(async () => {
    try {
      const stats = await systemLogsAPI.getStatistics();
      setStatistics(stats);
    } catch (err) {
      console.error('Failed to load statistics:', err);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      loadLogs();
      loadStatistics();
    }
  }, [isOpen, loadLogs, loadStatistics]);

  const handleFilterChange = (key, value) => {
    setFilters(prev => ({ ...prev, [key]: value }));
    setOffset(0); // Reset to first page when filter changes
  };

  const handleMultiSelectChange = (key, value) => {
    setFilters(prev => {
      const currentArray = prev[key] || [];
      const newArray = currentArray.includes(value)
        ? currentArray.filter(item => item !== value)
        : [...currentArray, value];
      return { ...prev, [key]: newArray };
    });
    setOffset(0);
  };

  const handleClearLogs = async () => {
    if (!confirm('Are you sure you want to clear all logs? This cannot be undone.')) {
      return;
    }
    
    try {
      await systemLogsAPI.clearLogs();
      await loadLogs();
      await loadStatistics();
    } catch (err) {
      console.error('Failed to clear logs:', err);
      alert('Failed to clear logs: ' + err.message);
    }
  };

  const toggleExpand = (index) => {
    setExpandedLogs(prev => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };

  const formatTimestamp = (timestamp) => {
    try {
      const date = new Date(timestamp);
      return date.toLocaleString();
    } catch {
      return timestamp;
    }
  };

  const getLogTypeColor = (type) => {
    const colors = {
      ai_assistant: 'bg-purple-100 text-purple-700',
      graph_operation: 'bg-blue-100 text-blue-700',
      case_management: 'bg-green-100 text-green-700',
      document_ingestion: 'bg-yellow-100 text-yellow-700',
      user_action: 'bg-indigo-100 text-indigo-700',
      system: 'bg-gray-100 text-gray-700',
      error: 'bg-red-100 text-red-700',
    };
    return colors[type] || 'bg-gray-100 text-gray-700';
  };

  const filteredLogs = logs.filter(log => {
    if (!filters.search) return true;
    const searchLower = filters.search.toLowerCase();
    return (
      log.action?.toLowerCase().includes(searchLower) ||
      log.user?.toLowerCase().includes(searchLower) ||
      JSON.stringify(log.details || {}).toLowerCase().includes(searchLower)
    );
  });

  // Group logs by time periods for timeline view
  const groupLogsByTime = (logs) => {
    const groups = {};
    logs.forEach(log => {
      try {
        const date = new Date(log.timestamp);
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);
        
        let timeGroup;
        if (diffMins < 1) {
          timeGroup = 'Just now';
        } else if (diffMins < 60) {
          timeGroup = `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`;
        } else if (diffHours < 24) {
          timeGroup = `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
        } else if (diffDays < 7) {
          timeGroup = `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
        } else {
          // Group by date for older logs
          const dateStr = date.toLocaleDateString('en-US', { 
            month: 'short', 
            day: 'numeric',
            year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined
          });
          timeGroup = dateStr;
        }
        
        if (!groups[timeGroup]) {
          groups[timeGroup] = [];
        }
        groups[timeGroup].push(log);
      } catch {
        // If timestamp parsing fails, put in "Unknown" group
        if (!groups['Unknown']) {
          groups['Unknown'] = [];
        }
        groups['Unknown'].push(log);
      }
    });
    
    // Sort groups by time (most recent first)
    const sortedGroups = Object.entries(groups).sort((a, b) => {
      // "Just now" and "X ago" come first, then dates
      if (a[0].includes('ago') || a[0] === 'Just now') return -1;
      if (b[0].includes('ago') || b[0] === 'Just now') return 1;
      return new Date(b[0]) - new Date(a[0]);
    });
    
    return sortedGroups;
  };

  const timelineGroups = viewMode === 'timeline' ? groupLogsByTime(filteredLogs) : [];

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-6xl h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-light-200">
          <div className="flex items-center gap-3">
            <FileText className="w-5 h-5 text-owl-purple-600" />
            <h2 className="text-xl font-semibold text-light-900">System Logs</h2>
            {statistics && (
              <span className="text-sm text-light-600">
                ({statistics.total_logs} total logs)
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {/* View Mode Toggle */}
            <div className="flex items-center gap-1 border border-light-300 rounded-lg p-1">
              <button
                onClick={() => setViewMode('list')}
                className={`p-1.5 rounded transition-colors ${
                  viewMode === 'list'
                    ? 'bg-owl-purple-500 text-white'
                    : 'text-light-600 hover:bg-light-100'
                }`}
                title="List View"
              >
                <List className="w-4 h-4" />
              </button>
              <button
                onClick={() => setViewMode('timeline')}
                className={`p-1.5 rounded transition-colors ${
                  viewMode === 'timeline'
                    ? 'bg-owl-purple-500 text-white'
                    : 'text-light-600 hover:bg-light-100'
                }`}
                title="Timeline View"
              >
                <Clock className="w-4 h-4" />
              </button>
            </div>
            <button
              onClick={() => setShowFilters(!showFilters)}
              className="p-2 hover:bg-light-100 rounded transition-colors"
              title="Toggle filters"
            >
              <Filter className="w-4 h-4" />
            </button>
            <button
              onClick={loadLogs}
              disabled={loading}
              className="p-2 hover:bg-light-100 rounded transition-colors disabled:opacity-50"
              title="Refresh logs"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={handleClearLogs}
              className="p-2 hover:bg-red-50 text-red-600 rounded transition-colors"
              title="Clear all logs"
            >
              <Trash2 className="w-4 h-4" />
            </button>
            <button
              onClick={() => setShowCostLedger(true)}
              className="flex items-center gap-2 px-3 py-2 text-sm bg-owl-blue-600 text-white rounded hover:bg-owl-blue-700 transition-colors"
              title="View Cost Ledger"
            >
              <DollarSign className="w-4 h-4" />
              Cost Ledger
            </button>
            <button
              onClick={onClose}
              className="p-2 hover:bg-light-100 rounded transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Filters */}
        {showFilters && (
          <div className="p-4 border-b border-light-200 bg-light-50">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <div>
                <label className="block text-xs font-medium text-light-700 mb-2">
                  Log Type {filters.log_type.length > 0 && `(${filters.log_type.length})`}
                </label>
                <div className="space-y-1 max-h-32 overflow-y-auto border border-light-300 rounded p-2 bg-white">
                  {LOG_TYPES.map(type => (
                    <label key={type.value} className="flex items-center gap-2 cursor-pointer hover:bg-light-50 p-1 rounded">
                      <input
                        type="checkbox"
                        checked={filters.log_type.includes(type.value)}
                        onChange={() => handleMultiSelectChange('log_type', type.value)}
                        className="w-4 h-4 text-owl-purple-600 border-light-300 rounded focus:ring-owl-purple-500"
                      />
                      <span className="text-xs text-light-700">{type.label}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-light-700 mb-2">
                  Origin {filters.origin.length > 0 && `(${filters.origin.length})`}
                </label>
                <div className="space-y-1 max-h-32 overflow-y-auto border border-light-300 rounded p-2 bg-white">
                  {LOG_ORIGINS.map(origin => (
                    <label key={origin.value} className="flex items-center gap-2 cursor-pointer hover:bg-light-50 p-1 rounded">
                      <input
                        type="checkbox"
                        checked={filters.origin.includes(origin.value)}
                        onChange={() => handleMultiSelectChange('origin', origin.value)}
                        className="w-4 h-4 text-owl-purple-600 border-light-300 rounded focus:ring-owl-purple-500"
                      />
                      <span className="text-xs text-light-700">{origin.label}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-light-700 mb-1">
                  Success Status
                </label>
                <select
                  value={filters.success_only === null ? '' : filters.success_only.toString()}
                  onChange={(e) => handleFilterChange('success_only', e.target.value === '' ? null : e.target.value === 'true')}
                  className="w-full px-2 py-1 text-sm border border-light-300 rounded focus:outline-none focus:border-owl-purple-500"
                >
                  <option value="">All</option>
                  <option value="true">Success Only</option>
                  <option value="false">Failed Only</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-light-700 mb-1">
                  Search
                </label>
                <div className="relative">
                  <Search className="absolute left-2 top-1/2 transform -translate-y-1/2 w-4 h-4 text-light-500" />
                  <input
                    type="text"
                    value={filters.search}
                    onChange={(e) => handleFilterChange('search', e.target.value)}
                    placeholder="Search logs..."
                    className="w-full pl-8 pr-2 py-1 text-sm border border-light-300 rounded focus:outline-none focus:border-owl-purple-500"
                  />
                </div>
              </div>
            </div>
            {statistics && (
              <div className="mt-3 flex gap-4 text-xs text-light-600">
                <span>Success Rate: {(statistics.success_rate * 100).toFixed(1)}%</span>
                <span>Successful: {statistics.successful}</span>
                <span>Failed: {statistics.failed}</span>
              </div>
            )}
          </div>
        )}

        {/* Logs List or Timeline */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading && logs.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <RefreshCw className="w-6 h-6 animate-spin text-owl-purple-500" />
            </div>
          ) : filteredLogs.length === 0 ? (
            <div className="flex items-center justify-center h-full text-light-600">
              No logs found
            </div>
          ) : viewMode === 'timeline' ? (
            /* Timeline View */
            <div className="relative">
              {/* Timeline Line */}
              <div className="absolute left-8 top-0 bottom-0 w-0.5 bg-owl-purple-200"></div>
              
              <div className="space-y-8">
                {timelineGroups.map(([timeGroup, groupLogs], groupIndex) => (
                  <div key={groupIndex} className="relative">
                    {/* Time Group Header */}
                    <div className="flex items-center gap-3 mb-4 sticky top-0 bg-white z-10 pb-2">
                      <div className="flex items-center justify-center min-w-[120px] px-3 py-1.5 bg-owl-purple-500 text-white rounded-full text-xs font-semibold shadow-sm">
                        <Calendar className="w-3 h-3 mr-1.5" />
                        {timeGroup}
                      </div>
                      <div className="flex-1 h-px bg-light-200"></div>
                      <span className="text-xs text-light-500 whitespace-nowrap">{groupLogs.length} event{groupLogs.length > 1 ? 's' : ''}</span>
                    </div>
                    
                    {/* Events in this time group */}
                    <div className="space-y-3 ml-8">
                      {groupLogs.map((log, logIndex) => {
                        const logIndexKey = `${groupIndex}-${logIndex}`;
                        return (
                          <div
                            key={logIndexKey}
                            className={`relative border-l-4 rounded-lg p-3 bg-white shadow-sm hover:shadow-md transition-shadow ${
                              !log.success 
                                ? 'border-red-500 bg-red-50' 
                                : log.type === 'ai_assistant'
                                ? 'border-purple-500'
                                : log.type === 'graph_operation'
                                ? 'border-blue-500'
                                : log.type === 'case_management'
                                ? 'border-green-500'
                                : log.type === 'error'
                                ? 'border-red-500'
                                : 'border-gray-400'
                            }`}
                          >
                            {/* Timeline Dot */}
                            <div className={`absolute -left-12 top-4 w-3 h-3 rounded-full border-2 border-white shadow-sm ${
                              !log.success 
                                ? 'bg-red-500' 
                                : log.type === 'ai_assistant'
                                ? 'bg-purple-500'
                                : log.type === 'graph_operation'
                                ? 'bg-blue-500'
                                : log.type === 'case_management'
                                ? 'bg-green-500'
                                : log.type === 'error'
                                ? 'bg-red-500'
                                : 'bg-gray-400'
                            }`}></div>
                            
                            <div className="flex items-start gap-3">
                              <div className="mt-0.5">
                                {log.success ? (
                                  <CheckCircle className="w-4 h-4 text-green-600" />
                                ) : (
                                  <XCircle className="w-4 h-4 text-red-600" />
                                )}
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 mb-1 flex-wrap">
                                  <span className={`px-2 py-0.5 text-xs rounded font-medium ${getLogTypeColor(log.type)}`}>
                                    {log.type.replace('_', ' ')}
                                  </span>
                                  <span className="text-xs text-light-600 bg-light-100 px-2 py-0.5 rounded">
                                    {log.origin}
                                  </span>
                                  {log.user && (
                                    <span className="text-xs text-light-600">
                                      by {log.user}
                                    </span>
                                  )}
                                  <span className="text-xs text-light-500 ml-auto">
                                    {formatTimestamp(log.timestamp)}
                                  </span>
                                </div>
                                <div className="text-sm text-light-900 font-medium mb-1">
                                  {log.action}
                                </div>
                                {log.error && (
                                  <div className="text-sm text-red-600 mb-2 flex items-center gap-1">
                                    <AlertCircle className="w-4 h-4" />
                                    {log.error}
                                  </div>
                                )}
                                {Object.keys(log.details || {}).length > 0 && (
                                  <button
                                    onClick={() => toggleExpand(logIndexKey)}
                                    className="text-xs text-owl-purple-600 hover:text-owl-purple-700 flex items-center gap-1"
                                  >
                                    {expandedLogs.has(logIndexKey) ? (
                                      <>
                                        <ChevronUp className="w-3 h-3" />
                                        Hide Details
                                      </>
                                    ) : (
                                      <>
                                        <ChevronDown className="w-3 h-3" />
                                        Show Details
                                      </>
                                    )}
                                  </button>
                                )}
                                {expandedLogs.has(logIndexKey) && log.details && (
                                  <pre className="mt-2 p-2 bg-light-100 rounded text-xs overflow-x-auto">
                                    {JSON.stringify(log.details, null, 2)}
                                  </pre>
                                )}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            /* List View */
            <div className="space-y-2">
              {filteredLogs.map((log, index) => (
                <div
                  key={index}
                  className={`border border-light-200 rounded-lg p-3 hover:bg-light-50 transition-colors ${
                    !log.success ? 'bg-red-50 border-red-200' : ''
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5">
                      {log.success ? (
                        <CheckCircle className="w-4 h-4 text-green-600" />
                      ) : (
                        <XCircle className="w-4 h-4 text-red-600" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`px-2 py-0.5 text-xs rounded ${getLogTypeColor(log.type)}`}>
                          {log.type.replace('_', ' ')}
                        </span>
                        <span className="text-xs text-light-600 bg-light-100 px-2 py-0.5 rounded">
                          {log.origin}
                        </span>
                        {log.user && (
                          <span className="text-xs text-light-600">
                            by {log.user}
                          </span>
                        )}
                        <span className="text-xs text-light-500 ml-auto">
                          {formatTimestamp(log.timestamp)}
                        </span>
                      </div>
                      <div className="text-sm text-light-900 font-medium mb-1">
                        {log.action}
                      </div>
                      {log.error && (
                        <div className="text-sm text-red-600 mb-2 flex items-center gap-1">
                          <AlertCircle className="w-4 h-4" />
                          {log.error}
                        </div>
                      )}
                      {Object.keys(log.details || {}).length > 0 && (
                        <button
                          onClick={() => toggleExpand(index)}
                          className="text-xs text-owl-purple-600 hover:text-owl-purple-700 flex items-center gap-1"
                        >
                          {expandedLogs.has(index) ? (
                            <>
                              <ChevronUp className="w-3 h-3" />
                              Hide Details
                            </>
                          ) : (
                            <>
                              <ChevronDown className="w-3 h-3" />
                              Show Details
                            </>
                          )}
                        </button>
                      )}
                      {expandedLogs.has(index) && log.details && (
                        <pre className="mt-2 p-2 bg-light-100 rounded text-xs overflow-x-auto">
                          {JSON.stringify(log.details, null, 2)}
                        </pre>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Pagination */}
        {total > limit && (
          <div className="flex items-center justify-between p-4 border-t border-light-200">
            <div className="text-sm text-light-600">
              Showing {offset + 1} - {Math.min(offset + limit, total)} of {total} logs
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setOffset(Math.max(0, offset - limit))}
                disabled={offset === 0}
                className="px-3 py-1 text-sm border border-light-300 rounded hover:bg-light-100 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Previous
              </button>
              <button
                onClick={() => setOffset(offset + limit)}
                disabled={offset + limit >= total}
                className="px-3 py-1 text-sm border border-light-300 rounded hover:bg-light-100 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
          </div>
        )}

      </div>
      
      {/* Cost Ledger Panel */}
      <CostLedgerPanel
        isOpen={showCostLedger}
        onClose={() => setShowCostLedger(false)}
      />
    </div>
  );
}

