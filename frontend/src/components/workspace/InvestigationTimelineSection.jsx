import React, { useState, useEffect, useMemo } from 'react';
import { ChevronDown, ChevronRight, Focus, Calendar, Clock } from 'lucide-react';
import { workspaceAPI } from '../../services/api';

/**
 * Investigation Timeline Section
 * 
 * Displays a multi-threaded timeline of all significant case activities
 */
export default function InvestigationTimelineSection({
  caseId,
  isCollapsed,
  onToggle,
  onFocus,
  fullHeight = false,
}) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedThreads, setExpandedThreads] = useState(new Set());

  useEffect(() => {
    const loadTimeline = async () => {
      if (!caseId) return;
      
      setLoading(true);
      try {
        const data = await workspaceAPI.getInvestigationTimeline(caseId);
        setEvents(data.events || []);
      } catch (err) {
        console.error('Failed to load investigation timeline:', err);
      } finally {
        setLoading(false);
      }
    };

    loadTimeline();
  }, [caseId]);

  // Group events by thread
  const eventsByThread = useMemo(() => {
    const grouped = {};
    events.forEach(event => {
      const thread = event.thread || 'Other';
      if (!grouped[thread]) {
        grouped[thread] = [];
      }
      grouped[thread].push(event);
    });
    
    // Sort events within each thread by date
    Object.keys(grouped).forEach(thread => {
      grouped[thread].sort((a, b) => {
        const dateA = new Date(a.date || 0);
        const dateB = new Date(b.date || 0);
        return dateA - dateB;
      });
    });
    
    return grouped;
  }, [events]);

  // Get all unique threads
  const threads = useMemo(() => {
    return Object.keys(eventsByThread).sort();
  }, [eventsByThread]);

  const toggleThread = (thread) => {
    setExpandedThreads(prev => {
      const next = new Set(prev);
      if (next.has(thread)) {
        next.delete(thread);
      } else {
        next.add(thread);
      }
      return next;
    });
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'Unknown date';
    try {
      const date = new Date(dateString);
      return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateString;
    }
  };

  const getEventIcon = (type) => {
    switch (type) {
      case 'witness_created':
        return '👤';
      case 'task_created':
      case 'task_due':
      case 'task_status_change':
        return '✓';
      case 'theory_created':
        return '💡';
      case 'snapshot_created':
        return '📸';
      case 'evidence_uploaded':
      case 'evidence_processed':
        return '📄';
      case 'evidence_pinned':
        return '📌';
      case 'deadline':
      case 'trial_date':
        return '📅';
      case 'system_action':
        return '⚙️';
      default:
        return '•';
    }
  };

  const getEventColor = (type) => {
    switch (type) {
      case 'witness_created':
        return 'bg-blue-100 text-blue-700 border-blue-200';
      case 'task_created':
      case 'task_due':
      case 'task_status_change':
        return 'bg-green-100 text-green-700 border-green-200';
      case 'theory_created':
        return 'bg-yellow-100 text-yellow-700 border-yellow-200';
      case 'snapshot_created':
        return 'bg-purple-100 text-purple-700 border-purple-200';
      case 'evidence_uploaded':
      case 'evidence_processed':
        return 'bg-orange-100 text-orange-700 border-orange-200';
      case 'evidence_pinned':
        return 'bg-pink-100 text-pink-700 border-pink-200';
      case 'deadline':
      case 'trial_date':
        return 'bg-red-100 text-red-700 border-red-200';
      case 'system_action':
        return 'bg-gray-100 text-gray-700 border-gray-200';
      default:
        return 'bg-light-100 text-light-700 border-light-200';
    }
  };

  return (
    <div className="border-b border-light-200">
      <div
        className="p-4 cursor-pointer hover:bg-light-50 transition-colors flex items-center justify-between"
        onClick={(e) => onToggle && onToggle(e)}
      >
        <h3 className="text-sm font-semibold text-owl-blue-900 flex items-center gap-2">
          <Calendar className="w-4 h-4" />
          Investigation Timeline ({events.length})
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
        <div className={`px-4 pb-4 ${fullHeight ? 'flex flex-col h-full' : ''}`}>
          {loading ? (
            <p className="text-sm text-light-500 text-center py-8">Loading timeline...</p>
          ) : events.length === 0 ? (
            <p className="text-sm text-light-500 text-center py-8">No timeline events yet</p>
          ) : (
            <div className={`space-y-4 overflow-y-auto ${fullHeight ? 'flex-1 min-h-0' : 'max-h-96'}`}>
              {threads.map(thread => {
                const threadEvents = eventsByThread[thread];
                const isExpanded = expandedThreads.has(thread);
                
                return (
                  <div key={thread} className="border border-light-200 rounded-lg overflow-hidden">
                    <button
                      onClick={() => toggleThread(thread)}
                      className="w-full px-3 py-2 bg-light-50 hover:bg-light-100 transition-colors flex items-center justify-between text-left"
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-owl-blue-900">{thread}</span>
                        <span className="text-xs text-light-600">({threadEvents.length})</span>
                      </div>
                      {isExpanded ? (
                        <ChevronDown className="w-4 h-4 text-light-600" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-light-600" />
                      )}
                    </button>
                    
                    {isExpanded && (
                      <div className="p-3 space-y-2 bg-white">
                        {threadEvents.map(event => (
                          <div
                            key={event.id}
                            className={`p-2 rounded border ${getEventColor(event.type)} text-xs`}
                          >
                            <div className="flex items-start gap-2">
                              <span className="text-base flex-shrink-0">{getEventIcon(event.type)}</span>
                              <div className="flex-1 min-w-0">
                                <div className="font-medium mb-1">{event.title}</div>
                                {event.description && (
                                  <div className="text-xs opacity-80 mb-1 line-clamp-2">
                                    {event.description}
                                  </div>
                                )}
                                <div className="flex items-center gap-2 text-xs opacity-70">
                                  <Clock className="w-3 h-3" />
                                  <span>{formatDate(event.date)}</span>
                                </div>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
