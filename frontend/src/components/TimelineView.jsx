import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { 
  Calendar, 
  Clock, 
  DollarSign, 
  ChevronDown, 
  ChevronRight,
  Filter,
  Loader2,
  AlertCircle
} from 'lucide-react';
import { timelineAPI } from '../services/api';
import GraphSearchFilter from './GraphSearchFilter';
import { parseSearchQuery, matchesQuery } from '../utils/searchParser';

/**
 * Color palette for event types (matches GraphView)
 */
const TYPE_COLORS = {
  Transaction: '#06b6d4',  // cyan
  Transfer: '#14b8a6',     // teal
  Payment: '#84cc16',      // lime
  Communication: '#f97316', // orange
  Email: '#f97316',        // orange
  PhoneCall: '#a855f7',    // purple
  Meeting: '#eab308',      // yellow
  Other: '#6b7280',        // gray
};

/**
 * Format date for display
 */
function formatDate(dateStr) {
  if (!dateStr) return 'Unknown date';
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

/**
 * Format time for display
 */
function formatTime(timeStr) {
  if (!timeStr) return null;
  return timeStr;
}

/**
 * Group events by date
 */
function groupEventsByDate(events) {
  const groups = {};
  
  events.forEach(event => {
    const date = event.date || 'unknown';
    if (!groups[date]) {
      groups[date] = [];
    }
    groups[date].push(event);
  });
  
  // Sort dates (newest first or oldest first based on preference)
  const sortedDates = Object.keys(groups).sort((a, b) => {
    if (a === 'unknown') return 1;
    if (b === 'unknown') return -1;
    return a.localeCompare(b); // Oldest first
  });
  
  return sortedDates.map(date => ({
    date,
    events: groups[date],
  }));
}

/**
 * Single Event Card
 */
function EventCard({ event, onSelect, isSelected, modifierKeys }) {
  const color = TYPE_COLORS[event.type] || TYPE_COLORS.Other;
  
  const handleClick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    // Check modifier keys from the click event first (most reliable)
    // Fall back to tracked state if event doesn't have it
    const isMultiSelect = e.ctrlKey || e.metaKey || modifierKeys?.ctrl || modifierKeys?.meta;
    onSelect(event, isMultiSelect);
  };
  
  return (
    <button
      onClick={handleClick}
      className={`w-full text-left p-3 rounded-lg transition-all ${
        isSelected 
          ? 'bg-owl-blue-100 ring-2 ring-owl-blue-500' 
          : 'bg-white hover:bg-light-50 border border-light-200'
      }`}
    >
      <div className="flex items-start gap-3">
        {/* Type indicator */}
        <div 
          className="w-3 h-3 rounded-full mt-1.5 flex-shrink-0"
          style={{ backgroundColor: color }}
        />
        
        <div className="flex-1 min-w-0">
          {/* Header */}
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium text-owl-blue-900 truncate">
              {event.name}
            </span>
            <span 
              className="text-xs px-2 py-0.5 rounded flex-shrink-0"
              style={{ backgroundColor: `${color}20`, color }}
            >
              {event.type}
            </span>
          </div>
          
          {/* Time and Amount */}
          <div className="flex items-center gap-3 mt-1 text-xs text-light-600">
            {event.time && (
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {formatTime(event.time)}
              </span>
            )}
            {event.amount && (
              <span className="flex items-center gap-1">
                <DollarSign className="w-3 h-3" />
                {event.amount}
              </span>
            )}
          </div>
          
          {/* Connected entities */}
          {event.connections && event.connections.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {event.connections.slice(0, 3).map((conn, idx) => (
                <span 
                  key={idx}
                  className="text-xs bg-light-100 text-light-700 px-2 py-0.5 rounded"
                >
                  {conn.name}
                </span>
              ))}
              {event.connections.length > 3 && (
                <span className="text-xs text-light-600">
                  +{event.connections.length - 3} more
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </button>
  );
}

/**
 * Date Group Header
 */
function DateHeader({ date, eventCount, isExpanded, onToggle }) {
  return (
    <button
      onClick={onToggle}
      className="w-full flex items-center gap-3 py-2 text-left group"
    >
      <div className="flex items-center justify-center w-6 h-6 rounded bg-light-100 group-hover:bg-light-200 transition-colors">
        {isExpanded ? (
          <ChevronDown className="w-4 h-4 text-light-600" />
        ) : (
          <ChevronRight className="w-4 h-4 text-light-600" />
        )}
      </div>
      <div className="flex items-center gap-2">
        <Calendar className="w-4 h-4 text-light-600" />
        <span className="font-medium text-owl-blue-900">
          {formatDate(date)}
        </span>
        <span className="text-xs text-light-600 bg-light-100 px-2 py-0.5 rounded">
          {eventCount} event{eventCount !== 1 ? 's' : ''}
        </span>
      </div>
    </button>
  );
}

/**
 * Filter Panel
 */
function FilterPanel({ eventTypes, selectedTypes, onToggleType, onSelectAll, onClearAll }) {
  return (
    <div className="bg-light-50 rounded-lg p-3 mb-4 border border-light-200">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 text-sm text-light-700">
          <Filter className="w-4 h-4" />
          <span>Filter by type</span>
        </div>
        <div className="flex gap-2">
          <button 
            onClick={onSelectAll}
            className="text-xs text-light-600 hover:text-light-800"
          >
            All
          </button>
          <span className="text-light-400">|</span>
          <button 
            onClick={onClearAll}
            className="text-xs text-light-600 hover:text-light-800"
          >
            None
          </button>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {eventTypes.map(type => {
          const isSelected = selectedTypes.has(type);
          const color = TYPE_COLORS[type] || TYPE_COLORS.Other;
          return (
            <button
              key={type}
              onClick={() => onToggleType(type)}
              className={`text-xs px-2 py-1 rounded transition-all ${
                isSelected 
                  ? 'opacity-100' 
                  : 'opacity-40'
              }`}
              style={{ 
                backgroundColor: `${color}20`, 
                color,
                border: `1px solid ${isSelected ? color : 'transparent'}`
              }}
            >
              {type}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/**
 * TimelineView Component
 * 
 * Displays events in chronological order with swimlanes by type
 */
export default function TimelineView({ 
  onSelectEvent, 
  selectedEvent, 
  selectedNodeKeys = [], 
  timelineData = null,
  onSelectEvents,
  selectedEventKeys = [],
  onBackgroundClick
}) {
  const [events, setEvents] = useState([]);
  const [allEvents, setAllEvents] = useState([]); // Store unfiltered events
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedDates, setExpandedDates] = useState(new Set());
  const [selectedTypes, setSelectedTypes] = useState(new Set());
  const [modifierKeys, setModifierKeys] = useState({ ctrl: false, meta: false });
  const [searchTerm, setSearchTerm] = useState('');
  
  // Track modifier keys for multi-select (similar to GraphView)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Control') {
        setModifierKeys(prev => ({ ...prev, ctrl: true }));
      }
      if (e.key === 'Meta') {
        setModifierKeys(prev => ({ ...prev, meta: true }));
      }
    };
    
    const handleKeyUp = (e) => {
      // Reset when modifier key is released
      if (e.key === 'Control') {
        setModifierKeys(prev => ({ ...prev, ctrl: false }));
      }
      if (e.key === 'Meta') {
        setModifierKeys(prev => ({ ...prev, meta: false }));
      }
      // Also check if modifier is no longer pressed
      if (!e.ctrlKey) {
        setModifierKeys(prev => ({ ...prev, ctrl: false }));
      }
      if (!e.metaKey) {
        setModifierKeys(prev => ({ ...prev, meta: false }));
      }
    };
    
    // Also track mouse events to catch modifier state
    const handleMouseDown = (e) => {
      if (e.ctrlKey) setModifierKeys(prev => ({ ...prev, ctrl: true }));
      if (e.metaKey) setModifierKeys(prev => ({ ...prev, meta: true }));
    };

    const handleMouseUp = (e) => {
      if (!e.ctrlKey) setModifierKeys(prev => ({ ...prev, ctrl: false }));
      if (!e.metaKey) setModifierKeys(prev => ({ ...prev, meta: false }));
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    window.addEventListener('mousedown', handleMouseDown);
    window.addEventListener('mouseup', handleMouseUp);
    
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
      window.removeEventListener('mousedown', handleMouseDown);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);
  
  // Handle event selection
  const handleEventSelect = useCallback((event, isMultiSelect) => {
    if (onSelectEvents) {
      // Convert event to node-like structure for consistency
      const eventNode = {
        key: event.key,
        id: event.key,
        name: event.name,
        type: event.type,
      };
      
      onSelectEvents(eventNode, { ctrlKey: isMultiSelect, metaKey: isMultiSelect });
    } else if (onSelectEvent) {
      // Fallback to single event selection
      onSelectEvent(event);
    }
  }, [onSelectEvents, onSelectEvent]);
  
  // Available event types
  const eventTypes = useMemo(() => {
    const types = new Set();
    events.forEach(e => types.add(e.type));
    return Array.from(types).sort();
  }, [events]);

  // Initialize selected types when events load
  useEffect(() => {
    if (eventTypes.length > 0 && selectedTypes.size === 0) {
      setSelectedTypes(new Set(eventTypes));
    }
  }, [eventTypes]);

  // Use provided timelineData if available (already filtered by parent), otherwise load from API
  useEffect(() => {
    async function loadTimeline() {
      setIsLoading(true);
      setError(null);
      try {
        // If timelineData is provided as prop, use it (already filtered by parent App.jsx)
        if (timelineData !== null && Array.isArray(timelineData)) {
          console.log('📅 TimelineView using provided timelineData:', {
            count: timelineData.length,
            source: selectedNodeKeys.length > 0 ? 'subgraph' : 'main graph',
            selectedNodeKeys: selectedNodeKeys.length
          });
          setAllEvents(timelineData);
          setEvents(timelineData);
          // Expand all dates by default
          const dates = new Set(timelineData.map(e => e.date || 'unknown'));
          setExpandedDates(dates);
          setIsLoading(false);
          return;
        }
        
        // Otherwise, load from API (fallback - should not happen in normal flow)
        console.log('⚠️ TimelineView loading from API (no prop provided)');
        const data = await timelineAPI.getEvents();
        let allEvents = Array.isArray(data) ? data : (data?.events || []);
        
        // Filter by selected nodes if any are selected (subgraph timeline)
        // If no nodes selected, show all events from main graph
        if (selectedNodeKeys.length > 0) {
          const beforeCount = allEvents.length;
          const selectedKeysSet = new Set(selectedNodeKeys);
          
          allEvents = allEvents.filter(event => {
            // Check if the event itself is in the selected nodes
            if (selectedKeysSet.has(event.key)) {
              return true;
            }
            // Check if event is connected to any selected nodes via connections array
            if (event.connections && Array.isArray(event.connections)) {
              return event.connections.some(conn => 
                conn.key && selectedKeysSet.has(conn.key)
              );
            }
            return false;
          });
          console.log('TimelineView filtered for subgraph:', { 
            before: beforeCount,
            after: allEvents.length,
            selectedNodeKeys
          });
        } else {
          console.log('TimelineView showing all events from main graph:', { 
            totalCount: allEvents.length
          });
        }
        
        setAllEvents(allEvents);
        setEvents(allEvents);
        
        // Expand all dates by default
        const dates = new Set(allEvents.map(e => e.date || 'unknown'));
        setExpandedDates(dates);
      } catch (err) {
        console.error('Timeline load error:', err);
        setError(err.message);
      } finally {
        setIsLoading(false);
      }
    }
    
    loadTimeline();
  }, [selectedNodeKeys, timelineData]);

  // Filter events by search term (with boolean operators support)
  const searchFilteredEvents = useMemo(() => {
    if (!searchTerm) return events;
    
    // Parse the search query
    const queryAST = parseSearchQuery(searchTerm);
    
    // Filter events that match the query
    return events.filter(event => {
      return matchesQuery(queryAST, event);
    });
  }, [events, searchTerm]);

  // Filter events by selected types (applied after search filter)
  const filteredEvents = useMemo(() => {
    let filtered = searchFilteredEvents;
    if (selectedTypes.size > 0) {
      filtered = filtered.filter(e => selectedTypes.has(e.type));
    }
    return filtered;
  }, [searchFilteredEvents, selectedTypes]);

  // Group filtered events by date
  const groupedEvents = useMemo(() => {
    return groupEventsByDate(filteredEvents);
  }, [filteredEvents]);

  // Toggle date expansion
  const toggleDate = (date) => {
    setExpandedDates(prev => {
      const next = new Set(prev);
      if (next.has(date)) {
        next.delete(date);
      } else {
        next.add(date);
      }
      return next;
    });
  };

  // Toggle event type filter
  const toggleType = (type) => {
    setSelectedTypes(prev => {
      const next = new Set(prev);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  };

  // Select all types
  const selectAllTypes = () => {
    setSelectedTypes(new Set(eventTypes));
  };

  // Clear all types
  const clearAllTypes = () => {
    setSelectedTypes(new Set());
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center bg-light-50">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-8 h-8 text-owl-blue-600 animate-spin" />
          <span className="text-light-600">Loading timeline...</span>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="h-full flex items-center justify-center bg-light-50">
        <div className="flex flex-col items-center gap-3 text-center">
          <AlertCircle className="w-8 h-8 text-red-500" />
          <span className="text-light-800">Failed to load timeline</span>
          <span className="text-light-600 text-sm">{error}</span>
        </div>
      </div>
    );
  }

  // Empty state
  if (events.length === 0) {
    return (
      <div className="h-full flex items-center justify-center bg-light-50">
        <div className="flex flex-col items-center gap-3 text-center">
          <Calendar className="w-12 h-12 text-light-400" />
          <span className="text-light-800">No timeline events found</span>
          <span className="text-light-600 text-sm">
            Events need a date property to appear on the timeline
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full bg-light-50 overflow-hidden flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-light-200 bg-white">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Calendar className="w-5 h-5 text-owl-blue-700" />
            <h2 className="font-semibold text-owl-blue-900">Timeline</h2>
            <span className="text-xs text-light-600 bg-light-100 px-2 py-1 rounded">
              {filteredEvents.length} event{filteredEvents.length !== 1 ? 's' : ''}
            </span>
            {selectedEventKeys.length > 0 && (
              <span className="text-xs text-owl-orange-600 bg-owl-orange-100 px-2 py-1 rounded">
                {selectedEventKeys.length} selected
              </span>
            )}
          </div>
          {onSelectEvents && filteredEvents.length > 0 && (
            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  // Select all visible events by calling onSelectEvents for each with Ctrl pressed
                  // We need to simulate adding them one by one, but this will trigger multiple state updates
                  // For now, let's select them by finding nodes in bulk
                  filteredEvents.forEach((event) => {
                    const eventNode = {
                      key: event.key,
                      id: event.key,
                      name: event.name,
                      type: event.type,
                    };
                    // Call with Ctrl pressed to add to selection (not replace)
                    handleEventSelect(eventNode, true);
                  });
                }}
                className="text-xs px-3 py-1.5 bg-light-100 hover:bg-light-200 text-light-700 rounded transition-colors"
                title="Select all visible events (Ctrl/Cmd+click to add to selection)"
              >
                Select All
              </button>
              {selectedEventKeys.length > 0 && (
                <button
                  onClick={() => {
                    // Clear selection
                    if (onBackgroundClick) {
                      onBackgroundClick();
                    }
                  }}
                  className="text-xs px-3 py-1.5 bg-light-100 hover:bg-light-200 text-light-700 rounded transition-colors"
                  title="Clear selection"
                >
                  Clear
                </button>
              )}
            </div>
          )}
        </div>
        
        {/* Search Filter */}
        <div className="flex items-center gap-2">
          <GraphSearchFilter
            onFilterChange={setSearchTerm}
            placeholder="Filter timeline events..."
            disabled={isLoading}
          />
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {/* Filters */}
        {eventTypes.length > 1 && (
          <FilterPanel
            eventTypes={eventTypes}
            selectedTypes={selectedTypes}
            onToggleType={toggleType}
            onSelectAll={selectAllTypes}
            onClearAll={clearAllTypes}
          />
        )}

        {/* Timeline */}
        <div className="space-y-2">
          {groupedEvents.map(({ date, events: dateEvents }) => (
            <div key={date} className="border-l-2 border-light-300 pl-4">
              <DateHeader
                date={date}
                eventCount={dateEvents.length}
                isExpanded={expandedDates.has(date)}
                onToggle={() => toggleDate(date)}
              />
              
              {expandedDates.has(date) && (
                <div className="space-y-2 mt-2 mb-4">
                  {dateEvents.map(event => (
                    <EventCard
                      key={event.key}
                      event={event}
                      onSelect={handleEventSelect}
                      isSelected={selectedEventKeys.includes(event.key) || selectedEvent?.key === event.key}
                      modifierKeys={modifierKeys}
                    />
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}