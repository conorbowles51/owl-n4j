import React, { useState, useEffect, useMemo, useRef } from 'react';
import { Calendar, Clock, ChevronLeft, ChevronRight, ZoomIn, ZoomOut, LayoutGrid, List } from 'lucide-react';
import { workspaceAPI } from '../../services/api';
import TextTimelineView from './TextTimelineView';

/**
 * Visual Investigation Timeline Component
 * 
 * Displays a multi-threaded visual timeline in the graph view area
 * 
 * @param {string} caseId - Case ID (required if events not provided)
 * @param {Array} events - Optional pre-loaded events (if provided, caseId is optional)
 * @param {number} externalWidth - Optional external width
 * @param {number} externalHeight - Optional external height
 */
export default function VisualInvestigationTimeline({
  caseId,
  events: externalEvents,
  width: externalWidth,
  height: externalHeight,
}) {
  const [events, setEvents] = useState(externalEvents || []);
  const [loading, setLoading] = useState(!externalEvents);
  const [zoomLevel, setZoomLevel] = useState(1);
  const [scrollPosition, setScrollPosition] = useState(0);
  const [viewMode, setViewMode] = useState('visual'); // 'visual' or 'text'
  const timelineRef = useRef(null);
  const containerRef = useRef(null);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });

  // Track container dimensions if not provided
  useEffect(() => {
    if (externalWidth && externalHeight) {
      setDimensions({ width: externalWidth, height: externalHeight });
      return;
    }

    const updateDimensions = () => {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        setDimensions({
          width: rect.width || containerRef.current.offsetWidth,
          height: rect.height || containerRef.current.offsetHeight,
        });
      }
    };

    updateDimensions();
    const resizeObserver = new ResizeObserver(updateDimensions);
    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }

    return () => resizeObserver.disconnect();
  }, [externalWidth, externalHeight]);

  useEffect(() => {
    // If external events are provided, use them and don't fetch
    if (externalEvents) {
      setEvents(externalEvents);
      setLoading(false);
      return;
    }

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
  }, [caseId, externalEvents]);

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

  // Get date range
  const dateRange = useMemo(() => {
    if (events.length === 0) return { min: null, max: null };
    
    const dates = events
      .map(e => new Date(e.date || 0))
      .filter(d => !isNaN(d.getTime()));
    
    if (dates.length === 0) return { min: null, max: null };
    
    return {
      min: new Date(Math.min(...dates)),
      max: new Date(Math.max(...dates)),
    };
  }, [events]);

  // Calculate timeline width based on date range and zoom
  const timelineWidth = useMemo(() => {
    if (!dateRange.min || !dateRange.max) return 2000;
    const daysDiff = (dateRange.max - dateRange.min) / (1000 * 60 * 60 * 24);
    return Math.max(2000, daysDiff * 50 * zoomLevel);
  }, [dateRange, zoomLevel]);

  // Calculate position for a date
  const getDatePosition = (dateString) => {
    if (!dateRange.min || !dateRange.max) return 0;
    const date = new Date(dateString);
    const totalDays = (dateRange.max - dateRange.min) / (1000 * 60 * 60 * 24);
    const daysFromStart = (date - dateRange.min) / (1000 * 60 * 60 * 24);
    return (daysFromStart / totalDays) * timelineWidth;
  };

  // Thread colors
  const threadColors = {
    'Witnesses': '#3b82f6',
    'Tasks': '#22c55e',
    'Theories': '#eab308',
    'Snapshots': '#a855f7',
    'Evidence': '#f97316',
    'Pinned Items': '#ec4899',
    'Deadlines': '#ef4444',
    'Notes': '#06b6d4',
    'Documents': '#14b8a6',
    'System Actions': '#6b7280',
    'Other': '#64748b',
  };

  const getThreadColor = (thread) => threadColors[thread] || threadColors['Other'];

  const formatDate = (dateString) => {
    if (!dateString) return 'Unknown date';
    try {
      const date = new Date(dateString);
      return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });
    } catch {
      return dateString;
    }
  };

  const formatDateTime = (dateString) => {
    if (!dateString) return 'Unknown date';
    try {
      const date = new Date(dateString);
      return date.toLocaleString('en-US', {
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
      case 'witness_interview':
        return '🎤';
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
      case 'document_uploaded':
        return '📋';
      case 'evidence_pinned':
        return '📌';
      case 'deadline':
      case 'trial_date':
        return '📅';
      case 'note_created':
      case 'note_updated':
        return '📝';
      case 'system_action':
        return '⚙️';
      default:
        return '•';
    }
  };

  const threads = Object.keys(eventsByThread).sort();
  const threadHeight = 100; // Increased for better readability
  const timelineHeight = threads.length * threadHeight + 120;

  const handleZoomIn = () => {
    setZoomLevel(prev => Math.min(prev + 0.2, 3));
  };

  const handleZoomOut = () => {
    setZoomLevel(prev => Math.max(prev - 0.2, 0.5));
  };

  const handleScroll = (direction) => {
    if (!timelineRef.current) return;
    
    const scrollAmount = 200;
    const currentScroll = timelineRef.current.scrollLeft;
    const maxScroll = Math.max(0, timelineWidth - (dimensions.width || 1000));
    
    if (direction === 'left') {
      timelineRef.current.scrollTo({
        left: Math.max(0, currentScroll - scrollAmount),
        behavior: 'smooth',
      });
    } else {
      timelineRef.current.scrollTo({
        left: Math.min(maxScroll, currentScroll + scrollAmount),
        behavior: 'smooth',
      });
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-owl-blue-600 mx-auto mb-4"></div>
          <p className="text-light-600">Loading timeline...</p>
        </div>
      </div>
    );
  }

  if (events.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <Calendar className="w-16 h-16 mx-auto mb-4 text-light-400" />
          <p className="text-light-600">No timeline events yet</p>
        </div>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="h-full w-full flex flex-col bg-white">
      {/* Controls */}
      <div className="flex items-center justify-between p-4 border-b border-light-200 bg-light-50">
        <div className="flex items-center gap-2">
          {/* View Mode Switcher */}
          <div className="flex items-center gap-1 bg-white rounded-lg border border-light-300 p-1">
            <button
              onClick={() => setViewMode('visual')}
              className={`px-3 py-1.5 rounded text-xs font-medium transition-colors flex items-center gap-1.5 ${
                viewMode === 'visual'
                  ? 'bg-owl-blue-600 text-white'
                  : 'text-light-600 hover:bg-light-100'
              }`}
              title="Visual Timeline"
            >
              <LayoutGrid className="w-3.5 h-3.5" />
              <span>Visual</span>
            </button>
            <button
              onClick={() => setViewMode('text')}
              className={`px-3 py-1.5 rounded text-xs font-medium transition-colors flex items-center gap-1.5 ${
                viewMode === 'text'
                  ? 'bg-owl-blue-600 text-white'
                  : 'text-light-600 hover:bg-light-100'
              }`}
              title="Text Timeline"
            >
              <List className="w-3.5 h-3.5" />
              <span>Text</span>
            </button>
          </div>
          
          {/* Visual mode controls */}
          {viewMode === 'visual' && (
            <>
              <div className="w-px h-6 bg-light-300 mx-2"></div>
              <button
                onClick={handleZoomOut}
                className="p-2 hover:bg-light-100 rounded transition-colors"
                title="Zoom out"
              >
                <ZoomOut className="w-4 h-4 text-light-600" />
              </button>
              <span className="text-sm text-light-600">{Math.round(zoomLevel * 100)}%</span>
              <button
                onClick={handleZoomIn}
                className="p-2 hover:bg-light-100 rounded transition-colors"
                title="Zoom in"
              >
                <ZoomIn className="w-4 h-4 text-light-600" />
              </button>
            </>
          )}
        </div>
        
        {/* Visual mode scroll controls and date range */}
        {viewMode === 'visual' && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => handleScroll('left')}
              className="p-2 hover:bg-light-100 rounded transition-colors"
              title="Scroll left"
            >
              <ChevronLeft className="w-4 h-4 text-light-600" />
            </button>
            <span className="text-xs text-light-600">
              {dateRange.min && dateRange.max && (
                <>
                  {formatDate(dateRange.min.toISOString())} - {formatDate(dateRange.max.toISOString())}
                </>
              )}
            </span>
            <button
              onClick={() => handleScroll('right')}
              className="p-2 hover:bg-light-100 rounded transition-colors"
              title="Scroll right"
            >
              <ChevronRight className="w-4 h-4 text-light-600" />
            </button>
          </div>
        )}
        
        {/* Text mode event count */}
        {viewMode === 'text' && (
          <div className="text-xs text-light-600">
            {events.length} event{events.length !== 1 ? 's' : ''}
          </div>
        )}
      </div>

      {/* Timeline Content */}
      {viewMode === 'text' ? (
        <TextTimelineView events={events} />
      ) : (
        <div 
          className="flex-1 overflow-auto relative" 
          ref={timelineRef}
          onScroll={(e) => {
            // Update scroll position for scroll buttons
            setScrollPosition(e.target.scrollLeft);
          }}
        >
        <div
          className="relative"
          style={{
            width: `${timelineWidth}px`,
            minHeight: `${timelineHeight}px`,
          }}
        >
          {/* Date axis - scrollable */}
          {dateRange.min && dateRange.max && (
            <div className="sticky top-0 z-20 bg-white border-b-2 border-light-300 shadow-sm" style={{ height: '80px' }}>
              <div className="relative h-full" style={{ paddingLeft: '180px' }}>
                {/* Date markers */}
                {(() => {
                  const markers = [];
                  const daysDiff = (dateRange.max - dateRange.min) / (1000 * 60 * 60 * 24);
                  const markerInterval = daysDiff > 365 ? 30 : daysDiff > 90 ? 7 : daysDiff > 30 ? 1 : 0.5;
                  
                  for (let i = 0; i <= daysDiff; i += markerInterval) {
                    const date = new Date(dateRange.min.getTime() + i * 24 * 60 * 60 * 1000);
                    const position = getDatePosition(date.toISOString());
                    markers.push(
                      <div
                        key={i}
                        className="absolute top-0 flex flex-col items-center"
                        style={{ left: `${position}px` }}
                      >
                        <div className="w-0.5 h-6 bg-owl-blue-400"></div>
                        <div className="text-xs font-medium text-owl-blue-900 mt-1 whitespace-nowrap bg-white px-1">
                          {formatDate(date.toISOString())}
                        </div>
                      </div>
                    );
                  }
                  return markers;
                })()}
              </div>
            </div>
          )}

          {/* Threads */}
          <div className="relative" style={{ marginTop: '80px' }}>
            {threads.map((thread, threadIndex) => {
              const threadEvents = eventsByThread[thread];
              const color = getThreadColor(thread);
              const yPosition = threadIndex * threadHeight;

              return (
                <div
                  key={thread}
                  className="relative border-b border-light-200 bg-white hover:bg-light-50 transition-colors"
                  style={{ height: `${threadHeight}px` }}
                >
                  {/* Thread label - sticky so it stays visible when scrolling */}
                  <div
                    className="sticky left-0 top-0 h-full flex items-center px-4 bg-white border-r-2 z-10 shadow-sm"
                    style={{ 
                      width: '180px', 
                      minWidth: '180px',
                      borderRightColor: color,
                      borderRightWidth: '4px',
                    }}
                  >
                    <div className="flex items-center gap-3 w-full">
                      <div
                        className="w-4 h-4 rounded-full flex-shrink-0 shadow-sm"
                        style={{ backgroundColor: color }}
                      ></div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-semibold text-owl-blue-900 truncate">{thread}</div>
                        <div className="text-xs text-light-600">{threadEvents.length} event{threadEvents.length !== 1 ? 's' : ''}</div>
                      </div>
                    </div>
                  </div>

                  {/* Thread strand/line - thicker and more visible */}
                  <div
                    className="absolute top-1/2 left-0 right-0 z-0"
                    style={{
                      backgroundColor: color,
                      opacity: 0.4,
                      left: '180px',
                      height: '3px',
                      transform: 'translateY(-50%)',
                      borderRadius: '2px',
                    }}
                  ></div>

                  {/* Events */}
                  <div className="absolute left-0 right-0 top-0 bottom-0" style={{ left: '180px' }}>
                    {threadEvents.map((event) => {
                      const position = getDatePosition(event.date);
                      
                      return (
                        <div
                          key={event.id}
                          className="absolute top-1/2 transform -translate-y-1/2 group"
                          style={{ left: `${position}px` }}
                        >
                          {/* Connection line from strand to event card */}
                          <div
                            className="absolute top-0 left-1/2 transform -translate-x-1/2 w-0.5 z-10"
                            style={{
                              height: '30px',
                              backgroundColor: color,
                              opacity: 0.5,
                            }}
                          ></div>

                          {/* Event marker on strand */}
                          <div
                            className="absolute top-0 left-1/2 transform -translate-x-1/2 w-6 h-6 rounded-full border-3 border-white shadow-lg cursor-pointer hover:scale-125 transition-transform z-20"
                            style={{ 
                              backgroundColor: color,
                              top: '-3px',
                            }}
                            title={`${event.title} - ${formatDateTime(event.date)}`}
                          >
                            <div className="w-full h-full flex items-center justify-center text-white text-[10px] font-bold">
                              {getEventIcon(event.type)}
                            </div>
                          </div>

                          {/* Event card - appears above the marker */}
                          <div
                            className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-4 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-30"
                            style={{ minWidth: '200px', maxWidth: '300px' }}
                          >
                            <div 
                              className="bg-white border-2 rounded-lg px-3 py-2 shadow-xl text-xs"
                              style={{ borderColor: color }}
                            >
                              <div className="font-semibold mb-1 text-owl-blue-900" style={{ color: color }}>
                                {event.title}
                              </div>
                              {event.description && (
                                <div className="text-xs text-light-700 mb-2 line-clamp-3">
                                  {event.description}
                                </div>
                              )}
                              <div className="flex items-center gap-1 text-xs text-light-600 border-t border-light-200 pt-2">
                                <Clock className="w-3 h-3" />
                                <span>{formatDateTime(event.date)}</span>
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        </div>
      )}
    </div>
  );
}
