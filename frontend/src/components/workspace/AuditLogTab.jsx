import React, { useState, useEffect } from 'react';
import { systemLogsAPI } from '../../services/api';

/**
 * Audit Log Tab
 * 
 * Displays chain of custody tracking with timestamps, users, actions
 */
export default function AuditLogTab({ caseId }) {
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
          limit: 100,
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

  if (loading) {
    return (
      <div className="p-4 text-center text-light-600">
        Loading audit log...
      </div>
    );
  }

  return (
    <div className="p-4 space-y-3">
      {logs.length === 0 ? (
        <p className="text-sm text-light-500 text-center py-8">No audit log entries</p>
      ) : (
        logs.map((log, idx) => (
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
        ))
      )}
    </div>
  );
}
