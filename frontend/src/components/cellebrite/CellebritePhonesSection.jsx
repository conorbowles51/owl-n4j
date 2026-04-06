import React, { useState, useEffect, useCallback } from 'react';
import { ChevronDown, ChevronRight, Smartphone, Focus } from 'lucide-react';
import { cellebriteAPI } from '../../services/api';

/**
 * Sidebar section listing ingested Cellebrite PhoneReport nodes.
 * Clicking a report opens the full Cellebrite view in the center panel.
 */
export default function CellebritePhonesSection({ caseId, isCollapsed, onToggle, onFocus }) {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadReports = useCallback(async () => {
    if (!caseId) return;
    setLoading(true);
    try {
      const data = await cellebriteAPI.getReports(caseId);
      setReports(data.reports || []);
    } catch (err) {
      console.error('Failed to load Cellebrite reports:', err);
      setReports([]);
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    loadReports();
  }, [loadReports]);

  return (
    <div className="border-b border-light-200">
      <div
        className="p-4 cursor-pointer hover:bg-light-50 transition-colors flex items-center justify-between"
        onClick={onToggle}
      >
        <h3 className="text-sm font-semibold text-owl-blue-900 flex items-center gap-2">
          <Smartphone className="w-4 h-4 text-emerald-600" />
          Phone Reports {reports.length > 0 ? `(${reports.length})` : ''}
        </h3>
        <div className="flex items-center gap-2">
          {onFocus && (
            <button
              onClick={(e) => { e.stopPropagation(); onFocus(e); }}
              className="p-1 hover:bg-light-100 rounded"
              title="Open Cellebrite view"
            >
              <Focus className="w-4 h-4 text-light-500" />
            </button>
          )}
          {isCollapsed ? (
            <ChevronRight className="w-4 h-4 text-light-500" />
          ) : (
            <ChevronDown className="w-4 h-4 text-light-500" />
          )}
        </div>
      </div>

      {!isCollapsed && (
        <div className="px-4 pb-4 space-y-2">
          {loading ? (
            <div className="text-xs text-light-500 italic">Loading...</div>
          ) : reports.length === 0 ? (
            <div className="text-xs text-light-500 italic">
              No phone reports ingested yet
            </div>
          ) : (
            reports.map((report) => (
              <div
                key={report.report_key}
                className="p-2 bg-light-50 rounded border border-light-200 hover:border-emerald-300 cursor-pointer transition-colors"
                onClick={(e) => { e.stopPropagation(); onFocus && onFocus(e); }}
              >
                <div className="flex items-center gap-2">
                  <Smartphone className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-medium text-owl-blue-900 truncate">
                      {report.device_model || 'Unknown Device'}
                    </div>
                    {report.phone_owner_name && (
                      <div className="text-xs text-light-600 truncate">
                        {report.phone_owner_name}
                      </div>
                    )}
                  </div>
                </div>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {report.stats.contacts > 0 && (
                    <span className="px-1.5 py-0.5 bg-owl-blue-50 text-owl-blue-700 text-[10px] rounded">
                      {report.stats.contacts} contacts
                    </span>
                  )}
                  {report.stats.calls > 0 && (
                    <span className="px-1.5 py-0.5 bg-owl-blue-50 text-owl-blue-700 text-[10px] rounded">
                      {report.stats.calls} calls
                    </span>
                  )}
                  {report.stats.messages > 0 && (
                    <span className="px-1.5 py-0.5 bg-owl-blue-50 text-owl-blue-700 text-[10px] rounded">
                      {report.stats.messages} msgs
                    </span>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
