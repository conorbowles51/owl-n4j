import React, { useMemo } from 'react';
import { 
  Calendar, 
  Clock, 
  FileText, 
  User, 
  Archive, 
  CheckCircle2, 
  AlertCircle,
  Target,
  BookOpen,
  Briefcase,
  Flag,
  Activity
} from 'lucide-react';

/**
 * Text Timeline View Component
 * 
 * Displays timeline events as a chronological list with color coding and event type labels
 */
export default function TextTimelineView({ events }) {
  // Get color for event type/thread
  const getEventColor = (event) => {
    const thread = event.thread || 'Other';
    const type = event.type || '';
    
    // Color mapping based on thread and type
    const colorMap = {
      'Theory': { bg: 'bg-purple-100', text: 'text-purple-800', border: 'border-purple-300' },
      'Evidence': { bg: 'bg-blue-100', text: 'text-blue-800', border: 'border-blue-300' },
      'Witnesses': { bg: 'bg-green-100', text: 'text-green-800', border: 'border-green-300' },
      'Notes': { bg: 'bg-yellow-100', text: 'text-yellow-800', border: 'border-yellow-300' },
      'Snapshots': { bg: 'bg-indigo-100', text: 'text-indigo-800', border: 'border-indigo-300' },
      'Documents': { bg: 'bg-cyan-100', text: 'text-cyan-800', border: 'border-cyan-300' },
      'Tasks': { bg: 'bg-orange-100', text: 'text-orange-800', border: 'border-orange-300' },
      'Deadlines': { bg: 'bg-red-100', text: 'text-red-800', border: 'border-red-300' },
      'Pinned Items': { bg: 'bg-pink-100', text: 'text-pink-800', border: 'border-pink-300' },
      'System Actions': { bg: 'bg-gray-100', text: 'text-gray-800', border: 'border-gray-300' },
      'Other': { bg: 'bg-slate-100', text: 'text-slate-800', border: 'border-slate-300' },
    };
    
    return colorMap[thread] || colorMap['Other'];
  };

  // Get icon for event type
  const getEventIcon = (event) => {
    const type = event.type || '';
    
    if (type.includes('theory')) return Target;
    if (type.includes('evidence') || type.includes('document')) return FileText;
    if (type.includes('witness') || type.includes('interview')) return User;
    if (type.includes('note')) return BookOpen;
    if (type.includes('snapshot')) return Archive;
    if (type.includes('task')) return Briefcase;
    if (type.includes('deadline') || type.includes('trial')) return Flag;
    if (type.includes('pinned')) return CheckCircle2;
    if (type.includes('system')) return Activity;
    
    return Calendar;
  };

  // Format event type label
  const getEventTypeLabel = (event) => {
    const type = event.type || '';
    
    // Convert snake_case or camelCase to readable label
    return type
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ')
      .replace(/([A-Z])/g, ' $1')
      .trim();
  };

  // Format date
  const formatDate = (dateString) => {
    if (!dateString) return 'Unknown date';
    try {
      const date = new Date(dateString);
      return date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateString;
    }
  };

  // Sort events chronologically
  const sortedEvents = useMemo(() => {
    return [...events].sort((a, b) => {
      const dateA = new Date(a.date || 0);
      const dateB = new Date(b.date || 0);
      return dateA - dateB;
    });
  }, [events]);

  if (sortedEvents.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm text-light-500">No timeline events available</p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="p-4 space-y-3">
        {sortedEvents.map((event, index) => {
          const colors = getEventColor(event);
          const Icon = getEventIcon(event);
          const typeLabel = getEventTypeLabel(event);
          const thread = event.thread || 'Other';
          
          return (
            <div
              key={event.id || index}
              className={`border-l-4 rounded-lg p-4 bg-white shadow-sm hover:shadow-md transition-shadow ${colors.border}`}
            >
              <div className="flex items-start gap-3">
                {/* Icon */}
                <div className={`flex-shrink-0 p-2 rounded-lg ${colors.bg}`}>
                  <Icon className={`w-5 h-5 ${colors.text}`} />
                </div>
                
                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    {/* Event Type Badge */}
                    <span className={`px-2 py-1 rounded text-xs font-semibold ${colors.bg} ${colors.text}`}>
                      {typeLabel}
                    </span>
                    
                    {/* Thread Badge */}
                    {thread && (
                      <span className="px-2 py-1 rounded text-xs font-medium bg-white/50 text-current">
                        {thread}
                      </span>
                    )}
                    
                    {/* Date */}
                    <div className="flex items-center gap-1 text-xs opacity-75 ml-auto">
                      <Clock className="w-3 h-3" />
                      <span>{formatDate(event.date)}</span>
                    </div>
                  </div>
                  
                  {/* Title */}
                  <h4 className="font-semibold text-sm mb-1">
                    {event.title || 'Untitled Event'}
                  </h4>
                  
                  {/* Description */}
                  {event.description && (
                    <p className="text-sm opacity-90 mb-2">
                      {event.description}
                    </p>
                  )}
                  
                  {/* Metadata */}
                  {event.metadata && Object.keys(event.metadata).length > 0 && (
                    <div className="flex flex-wrap gap-2 mt-2 text-xs">
                      {Object.entries(event.metadata).map(([key, value]) => {
                        if (value === null || value === undefined || value === '') return null;
                        return (
                          <span key={key} className="px-2 py-1 rounded bg-white/50">
                            <span className="font-medium">{key.replace(/_/g, ' ')}:</span>{' '}
                            <span>{String(value)}</span>
                          </span>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
