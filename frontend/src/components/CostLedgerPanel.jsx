import React, { useState, useEffect, useCallback } from 'react';
import { X, DollarSign, TrendingUp, FileText, MessageSquare, Filter, Download } from 'lucide-react';
import { costLedgerAPI } from '../services/api';

export default function CostLedgerPanel({ isOpen, onClose }) {
  const [records, setRecords] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({
    job_type: '',
    model_id: '',
    case_id: '',
  });
  const [limit, setLimit] = useState(100);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [totalCost, setTotalCost] = useState(0);
  const [totalTokens, setTotalTokens] = useState(null);

  const loadRecords = useCallback(async () => {
    setLoading(true);
    try {
      const params = {
        ...filters,
        limit,
        offset,
      };
      
      // Remove empty filters
      const cleanedParams = {};
      Object.keys(params).forEach(key => {
        const value = params[key];
        if (value !== '' && value !== null && value !== undefined) {
          cleanedParams[key] = value;
        }
      });
      
      const result = await costLedgerAPI.getLedger(cleanedParams);
      
      setRecords(result.records || []);
      setTotal(result.total || 0);
      setTotalCost(result.total_cost || 0);
      setTotalTokens(result.total_tokens || null);
    } catch (err) {
      console.error('Failed to load cost records:', err);
    } finally {
      setLoading(false);
    }
  }, [filters, limit, offset]);

  const loadSummary = useCallback(async () => {
    try {
      const params = {};
      if (filters.case_id) {
        params.case_id = filters.case_id;
      }
      
      const result = await costLedgerAPI.getSummary(params);
      setSummary(result);
    } catch (err) {
      console.error('Failed to load cost summary:', err);
    }
  }, [filters.case_id]);

  useEffect(() => {
    if (isOpen) {
      loadRecords();
      loadSummary();
    }
  }, [isOpen, loadRecords, loadSummary]);

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 4,
      maximumFractionDigits: 6,
    }).format(amount);
  };

  const formatNumber = (num) => {
    if (num === null || num === undefined) return 'N/A';
    return new Intl.NumberFormat('en-US').format(num);
  };

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return '';
    try {
      return new Date(timestamp).toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
    } catch {
      return timestamp;
    }
  };

  const getJobTypeIcon = (jobType) => {
    switch (jobType) {
      case 'ingestion':
        return <FileText className="w-4 h-4" />;
      case 'ai_assistant':
        return <MessageSquare className="w-4 h-4" />;
      default:
        return null;
    }
  };

  const getJobTypeLabel = (jobType) => {
    switch (jobType) {
      case 'ingestion':
        return 'Ingestion';
      case 'ai_assistant':
        return 'AI Assistant';
      default:
        return jobType;
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-6xl h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-light-200">
          <div className="flex items-center gap-3">
            <DollarSign className="w-6 h-6 text-owl-blue-600" />
            <h2 className="text-xl font-semibold text-light-900">Cost Ledger</h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-light-100 rounded transition-colors"
            title="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Summary Section */}
        {summary && (
          <div className="p-6 bg-light-50 border-b border-light-200">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-white p-4 rounded-lg border border-light-200">
                <div className="text-sm text-light-600 mb-1">Total Cost</div>
                <div className="text-2xl font-bold text-owl-blue-600">
                  {formatCurrency(summary.total_cost)}
                </div>
                <div className="text-xs text-light-500 mt-1">
                  {formatNumber(summary.total_tokens)} tokens
                </div>
              </div>
              <div className="bg-white p-4 rounded-lg border border-light-200">
                <div className="text-sm text-light-600 mb-1">Ingestion</div>
                <div className="text-xl font-semibold text-green-600">
                  {formatCurrency(summary.ingestion_cost)}
                </div>
                <div className="text-xs text-light-500 mt-1">
                  {formatNumber(summary.ingestion_tokens)} tokens
                </div>
              </div>
              <div className="bg-white p-4 rounded-lg border border-light-200">
                <div className="text-sm text-light-600 mb-1">AI Assistant</div>
                <div className="text-xl font-semibold text-blue-600">
                  {formatCurrency(summary.ai_assistant_cost)}
                </div>
                <div className="text-xs text-light-500 mt-1">
                  {formatNumber(summary.ai_assistant_tokens)} tokens
                </div>
              </div>
              <div className="bg-white p-4 rounded-lg border border-light-200">
                <div className="text-sm text-light-600 mb-1">Models Used</div>
                <div className="text-xl font-semibold text-light-900">
                  {Object.keys(summary.by_model || {}).length}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Filters */}
        <div className="p-4 border-b border-light-200 bg-white">
          <div className="flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-2">
              <Filter className="w-4 h-4 text-light-600" />
              <span className="text-sm font-medium text-light-700">Filters:</span>
            </div>
            <select
              value={filters.job_type}
              onChange={(e) => setFilters(prev => ({ ...prev, job_type: e.target.value }))}
              className="px-3 py-1.5 border border-light-300 rounded text-sm focus:outline-none focus:border-owl-blue-500"
            >
              <option value="">All Job Types</option>
              <option value="ingestion">Ingestion</option>
              <option value="ai_assistant">AI Assistant</option>
            </select>
            <input
              type="text"
              value={filters.model_id}
              onChange={(e) => setFilters(prev => ({ ...prev, model_id: e.target.value }))}
              placeholder="Model ID"
              className="px-3 py-1.5 border border-light-300 rounded text-sm focus:outline-none focus:border-owl-blue-500"
            />
            <input
              type="text"
              value={filters.case_id}
              onChange={(e) => setFilters(prev => ({ ...prev, case_id: e.target.value }))}
              placeholder="Case ID"
              className="px-3 py-1.5 border border-light-300 rounded text-sm focus:outline-none focus:border-owl-blue-500"
            />
            <button
              onClick={() => {
                setFilters({ job_type: '', model_id: '', case_id: '' });
                setOffset(0);
              }}
              className="px-3 py-1.5 text-sm text-light-600 hover:text-light-900 hover:bg-light-100 rounded transition-colors"
            >
              Clear
            </button>
          </div>
        </div>

        {/* Records Table */}
        <div className="flex-1 overflow-auto p-6">
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-owl-blue-600"></div>
            </div>
          ) : records.length === 0 ? (
            <div className="text-center text-light-500 py-12">
              No cost records found
            </div>
          ) : (
            <div className="space-y-2">
              <div className="text-sm text-light-600 mb-4">
                Showing {offset + 1}-{Math.min(offset + limit, total)} of {total} records
                {totalCost > 0 && ` • Total: ${formatCurrency(totalCost)}`}
                {totalTokens && ` • ${formatNumber(totalTokens)} tokens`}
              </div>
              <table className="w-full text-sm">
                <thead className="bg-light-100 sticky top-0">
                  <tr>
                    <th className="px-4 py-2 text-left font-medium text-light-700">Time</th>
                    <th className="px-4 py-2 text-left font-medium text-light-700">Job Type</th>
                    <th className="px-4 py-2 text-left font-medium text-light-700">Model</th>
                    <th className="px-4 py-2 text-right font-medium text-light-700">Tokens</th>
                    <th className="px-4 py-2 text-right font-medium text-light-700">Cost</th>
                    <th className="px-4 py-2 text-left font-medium text-light-700">Description</th>
                  </tr>
                </thead>
                <tbody>
                  {records.map((record) => (
                    <tr key={record.id} className="border-b border-light-200 hover:bg-light-50">
                      <td className="px-4 py-2 text-light-600">
                        {formatTimestamp(record.created_at)}
                      </td>
                      <td className="px-4 py-2">
                        <div className="flex items-center gap-2">
                          {getJobTypeIcon(record.job_type)}
                          <span>{getJobTypeLabel(record.job_type)}</span>
                        </div>
                      </td>
                      <td className="px-4 py-2 text-light-900 font-mono text-xs">
                        {record.model_id}
                      </td>
                      <td className="px-4 py-2 text-right text-light-600">
                        {record.total_tokens ? formatNumber(record.total_tokens) : 'N/A'}
                        {record.prompt_tokens && record.completion_tokens && (
                          <div className="text-xs text-light-500">
                            ({formatNumber(record.prompt_tokens)} + {formatNumber(record.completion_tokens)})
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-2 text-right font-semibold text-owl-blue-600">
                        {formatCurrency(record.cost_usd)}
                      </td>
                      <td className="px-4 py-2 text-light-600 text-xs">
                        {record.description || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              
              {/* Pagination */}
              {total > limit && (
                <div className="flex items-center justify-between mt-4">
                  <button
                    onClick={() => setOffset(Math.max(0, offset - limit))}
                    disabled={offset === 0}
                    className="px-4 py-2 text-sm border border-light-300 rounded hover:bg-light-100 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Previous
                  </button>
                  <span className="text-sm text-light-600">
                    Page {Math.floor(offset / limit) + 1} of {Math.ceil(total / limit)}
                  </span>
                  <button
                    onClick={() => setOffset(offset + limit)}
                    disabled={offset + limit >= total}
                    className="px-4 py-2 text-sm border border-light-300 rounded hover:bg-light-100 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Next
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
