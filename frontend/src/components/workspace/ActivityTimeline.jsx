import React, { useState, useEffect } from 'react';
import { Clock, User } from 'lucide-react';

/**
 * Activity Timeline Component
 * 
 * Real-time collaboration feed showing recent activity
 */
export default function ActivityTimeline({ caseId }) {
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadActivities = async () => {
      if (!caseId) return;
      
      setLoading(true);
      try {
        // For now, use system logs as activity feed
        // In Phase 4, this will be WebSocket-based
        const logs = await fetch(`/api/system-logs?case_id=${caseId}&limit=20`, {
          credentials: 'include',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('authToken')}`,
          },
        }).then(r => r.json());
        
        setActivities((logs.logs || []).map(log => ({
          id: log.timestamp + log.action,
          user: log.user || 'System',
          action: log.action,
          timestamp: log.timestamp,
          details: log.details,
        })));
      } catch (err) {
        console.error('Failed to load activities:', err);
      } finally {
        setLoading(false);
      }
    };

    loadActivities();
    
    // Poll for updates (in Phase 4, this will be WebSocket)
    const interval = setInterval(loadActivities, 5000);
    return () => clearInterval(interval);
  }, [caseId]);

  const formatTime = (timestamp) => {
    if (!timestamp) return '';
    try {
      return new Date(timestamp).toLocaleTimeString('en-US', {
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
        Loading activity...
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      <h3 className="text-sm font-semibold text-owl-blue-900 mb-3">Activity Timeline</h3>
      {activities.length === 0 ? (
        <p className="text-sm text-light-500 text-center py-4">No recent activity</p>
      ) : (
        <div className="space-y-2">
          {activities.map((activity) => (
            <div
              key={activity.id}
              className="flex items-start gap-3 p-2 hover:bg-light-50 rounded-lg transition-colors"
            >
              <Clock className="w-4 h-4 text-light-600 mt-0.5 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <User className="w-3 h-3 text-light-600" />
                  <span className="text-xs font-medium text-owl-blue-900">{activity.user}</span>
                  <span className="text-xs text-light-500">{formatTime(activity.timestamp)}</span>
                </div>
                <p className="text-sm text-light-700 mt-1">{activity.action}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
