import React, { useState, useEffect } from 'react';
import { ChevronDown, ChevronRight, FileText, Focus } from 'lucide-react';
import { systemLogsAPI } from '../../services/api';

/**
 * Audit Log Section
 * 
 * Displays chain of custody tracking with timestamps, users, actions
 */
export default function AuditLogSection({
  caseId,
  isCollapsed,
  onToggle,
  onFocus,
  fullHeight = false, // When true, use full height for content panel
}) {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadLogs = async () => {
      if (!caseId) return;
      
      setLoading(true);
      try {
        // Get system logs filtered by case
        const logData = await systemLogsAPI.getLogs({
          case_id: caseId,
          limit: 50,
        });
        setLogs(logData.logs || []);
      } catch (err) {
        console.error('Failed to load audit log:', err);
      } finally {
        setLoading(false);
      }
    };

    loadLogs();
  }, [caseId]);

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return '';
    try {
      return new Date(timestamp).toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return timestamp;
    }
  };

  return (
    <div className={`border-b border-light-200 ${fullHeight ? 'h-full flex flex-col' : ''}`}>
      <div className={`${fullHeight ? 'flex-shrink-0' : ''} p-4 cursor-pointer hover:bg-light-50 transition-colors flex items-center justify-between`}
        onClick={(e) => onToggle && onToggle(e)}
      >
        <h3 className="text-sm font-semibold text-owl-blue-900 flex items-center gap-2">
          <FileText className="w-4 h-4" />
          Audit Log (Chain of Custody) ({logs.length})
        </h3>
        <div className="flex items-center gap-2">
          {onFocus && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onFocus(e);
              }}
              className="p-1 hover:bg-light-100 rounded"
              title="Focus on this section"
            >
              <Focus className="w-4 h-4 text-owl-blue-600" />
            </button>
          )}
          {isCollapsed ? (
            <ChevronRight className="w-4 h-4 text-light-600" />
          ) : (
            <ChevronDown className="w-4 h-4 text-light-600" />
          )}
        </div>
      </div>

      {!isCollapsed && (
        <div className={`px-4 pb-4 ${fullHeight ? 'flex flex-col flex-1 min-h-0' : ''}`}>
          {loading ? (
            <p className="text-xs text-light-500">Loading audit log...</p>
          ) : logs.length === 0 ? (
            <p className="text-sm text-light-500 text-center py-8">No audit log entries</p>
          ) : (
            <div className={`space-y-2 overflow-y-auto ${fullHeight ? 'flex-1 min-h-0' : 'max-h-96'}`}>
              {logs.map((log, idx) => (
                <div
                  key={idx}
                  className="p-3 bg-light-50 rounded-lg border border-light-200"
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex-1">
                      <p className="text-sm font-medium text-owl-blue-900">{log.action}</p>
                      {log.user && (
                        <p className="text-xs text-light-600">User: {log.user}</p>
                      )}
                    </div>
                    <span className="text-xs text-light-500">
                      {formatTimestamp(log.timestamp)}
                    </span>
                  </div>
                  {log.details && Object.keys(log.details).length > 0 && (
                    <div className="mt-2 text-xs text-light-600">
                      {Object.entries(log.details).map(([key, value]) => (
                        <p key={key}>
                          <span className="font-medium">{key}:</span> {String(value)}
                        </p>
                      ))}
                    </div>
                  )}
                  {log.success === false && (
                    <p className="text-xs text-red-600 mt-2">Failed: {log.error || 'Unknown error'}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
