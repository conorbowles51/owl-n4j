import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { 
  Calendar, 
  Loader2,
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  GitBranch,
} from 'lucide-react';
import { SwimLaneColumn } from './SwimLaneColumn';
import { getDateRange } from '../../utils/timeline';
import { RelationshipLines } from './RelationshipLines';
import { ZoomControls } from './ZoomControls';
import { FilterPanel } from './FilterPanel';
import { VerticalDateAxis } from './VerticalDateAxis';
import { timelineAPI } from '../../services/api';
import { EntityDock } from './EntityDock';
import GraphSearchFilter from '../GraphSearchFilter';
import { parseSearchQuery, matchesQuery } from '../../utils/searchParser';

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
 * TimelineView Component
 * 
 * Vertical swim lane timeline with collapsible columns and zoom:
 * - Date axis runs vertically (top = earliest, bottom = latest)
 * - Each event type has its own column
 * - Columns are narrow by default (dots), expand on click
 * - Zoom to spread out clustered events
 * - Connector lines show actual date positions
 */
export default function TimelineView({ 
  onSelectEvent, 
  selectedEvent, 
  timelineData = null,
  onSelectEvents,
  selectedEventKeys = [],
  onBackgroundClick,
  expandAllOnMount = false,
}) {
  const [events, setEvents] = useState([]);
  const [allEvents, setAllEvents] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedTypes, setSelectedTypes] = useState(new Set());
  const [searchTerm, setSearchTerm] = useState('');
  const [searchMode, setSearchMode] = useState('filter');
  const [pendingSearchTerm, setPendingSearchTerm] = useState('');
  const [expandedColumns, setExpandedColumns] = useState(new Set());
  const [zoomLevel, setZoomLevel] = useState(1);
  const [showRelationships, setShowRelationships] = useState(false);
  const [entityDockExpanded, setEntityDockExpanded] = useState(true);
  const timelineContainerRef = useRef(null);

  // Base timeline height
  const baseTimelineHeight = useMemo(() => {
    return Math.max(600, events.length * 40);
  }, [events.length]);

  const handleTimelineQueryChange = useCallback((value) => {
    setPendingSearchTerm(value);
    if (searchMode === 'filter') {
      setSearchTerm(value);
    }
  }, [searchMode]);

  const handleTimelineModeChange = useCallback((mode) => {
    setSearchMode(mode);
    if (mode === 'filter') {
      setSearchTerm(pendingSearchTerm);
    }
  }, [pendingSearchTerm]);

  const handleTimelineSearch = useCallback(() => {
    setSearchTerm(pendingSearchTerm);
  }, [pendingSearchTerm]);
  
  // Handle event selection - delegate to parent
  const handleEventSelect = useCallback((event, isMultiSelect) => {
    if (onSelectEvents) {
      const eventNode = {
        key: event.key,
        id: event.key,
        name: event.name,
        type: event.type,
      };
      onSelectEvents(eventNode, { ctrlKey: isMultiSelect, metaKey: isMultiSelect });
    } else if (onSelectEvent) {
      onSelectEvent(event);
    }
  }, [onSelectEvents, onSelectEvent]);

  // Handle clicking a dot in collapsed view
  const handleEventDotClick = useCallback((type, event) => {
    setExpandedColumns(prev => new Set([...prev, type]));
    handleEventSelect(event, false);
  }, [handleEventSelect]);

  // Toggle column expansion
  const toggleColumnExpand = useCallback((type) => {
    setExpandedColumns(prev => {
      const next = new Set(prev);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  }, []);
  
  // Available event types (only types that have events)
  const eventTypes = useMemo(() => {
    const types = new Set();
    events.forEach(e => types.add(e.type));
    return Array.from(types).sort();
  }, [events]);

  // Active event types (filtered by selectedTypes)
  const activeEventTypes = useMemo(() => {
    if (selectedTypes.size === 0) return eventTypes;
    return eventTypes.filter(t => selectedTypes.has(t));
  }, [eventTypes, selectedTypes]);

  // Initialize selected types when events load
  useEffect(() => {
    if (eventTypes.length > 0 && selectedTypes.size === 0) {
      setSelectedTypes(new Set(eventTypes));
    }
  }, [eventTypes]);

  // Expand all columns on mount when requested (e.g. for export capture)
  useEffect(() => {
    if (expandAllOnMount && eventTypes.length > 0) {
      setExpandedColumns(new Set(eventTypes));
    }
  }, [expandAllOnMount, eventTypes]);

  // Use provided timelineData - the parent (App.jsx) handles filtering
  useEffect(() => {
    async function loadTimeline() {
      setIsLoading(true);
      setError(null);
      try {
        if (timelineData !== null && Array.isArray(timelineData)) {
          // Use pre-filtered timelineData from parent
          setAllEvents(timelineData);
          setEvents(timelineData);
          setIsLoading(false);
          return;
        }
        
        // Fallback: load from API if no timelineData provided
        const data = await timelineAPI.getEvents();
        const allEvents = Array.isArray(data) ? data : (data?.events || []);
        setAllEvents(allEvents);
        setEvents(allEvents);
      } catch (err) {
        console.error('Timeline load error:', err);
        setError(err.message);
      } finally {
        setIsLoading(false);
      }
    }
    
    loadTimeline();
  }, [timelineData]);

  // Filter events by search term
  const searchFilteredEvents = useMemo(() => {
    if (!searchTerm) return events;
    const queryAST = parseSearchQuery(searchTerm);
    return events.filter(event => matchesQuery(queryAST, event));
  }, [events, searchTerm]);

  // Filter events by selected types
  const filteredEvents = useMemo(() => {
    let filtered = searchFilteredEvents;
    if (selectedTypes.size > 0) {
      filtered = filtered.filter(e => selectedTypes.has(e.type));
    }
    return filtered;
  }, [searchFilteredEvents, selectedTypes]);

  // Get date range for positioning
  const dateRange = useMemo(() => {
    return getDateRange(filteredEvents);
  }, [filteredEvents]);

  // Get selected events (full event objects) for the entity dock
  const selectedEvents = useMemo(() => {
    if (selectedEventKeys.length === 0) return [];
    const keySet = new Set(selectedEventKeys);
    return filteredEvents.filter(event => keySet.has(event.key));
  }, [filteredEvents, selectedEventKeys]);

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

  // Expand all columns
  const expandAllColumns = useCallback(() => {
    setExpandedColumns(new Set(activeEventTypes));
  }, [activeEventTypes]);

  // Collapse all columns
  const collapseAllColumns = useCallback(() => {
    setExpandedColumns(new Set());
  }, []);

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
    <div className="h-full bg-light-50 overflow-hidden flex">
      {/* Main Content Area */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        {/* Header - stays fixed width, doesn't expand with timeline content */}
        <div className="p-4 border-b border-light-200 bg-white flex-shrink-0">
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
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
            <div className="flex items-center gap-2 flex-wrap">
              <ZoomControls zoomLevel={zoomLevel} onZoomChange={setZoomLevel} />
              <button
                onClick={() => setShowRelationships(!showRelationships)}
                className={`text-xs px-3 py-1.5 rounded transition-colors flex items-center gap-1 ${
                  showRelationships 
                    ? 'bg-owl-blue-100 text-owl-blue-700' 
                    : 'bg-light-100 hover:bg-light-200 text-light-700'
                }`}
                title="Show relationship lines between events"
              >
                <GitBranch className="w-4 h-4" />
                Relations
              </button>
              <button
                onClick={expandAllColumns}
                className="text-xs px-3 py-1.5 bg-light-100 hover:bg-light-200 text-light-700 rounded transition-colors"
                title="Expand all columns"
              >
                <ChevronRight className="w-4 h-4 inline mr-1" />
                Expand
              </button>
              <button
                onClick={collapseAllColumns}
                className="text-xs px-3 py-1.5 bg-light-100 hover:bg-light-200 text-light-700 rounded transition-colors"
                title="Collapse all columns"
              >
                <ChevronLeft className="w-4 h-4 inline mr-1" />
                Collapse
              </button>
            </div>
          </div>
          
          {/* Search Filter */}
          <div className="flex items-center gap-2 mb-3">
            <GraphSearchFilter
              mode={searchMode}
              onModeChange={handleTimelineModeChange}
              onFilterChange={setSearchTerm}
              onQueryChange={handleTimelineQueryChange}
              onSearch={handleTimelineSearch}
              placeholder="Filter timeline events..."
              disabled={isLoading}
            />
          </div>

          {/* Type Filters */}
          {eventTypes.length > 1 && (
            <FilterPanel
              eventTypes={eventTypes}
              selectedTypes={selectedTypes}
              onToggleType={toggleType}
              onSelectAll={selectAllTypes}
              onClearAll={clearAllTypes}
            />
          )}
        </div>

        {/* Timeline Grid */}
        <div className="flex-1 overflow-auto" ref={timelineContainerRef}>
          <div className="relative" style={{ display: 'inline-flex', minWidth: '100%', minHeight: '100%' }}>
            {/* Vertical Date Axis */}
            {dateRange.min && dateRange.max && (
              <div className="sticky left-0 z-20 bg-white shadow-sm">
                {/* Empty header cell for alignment - h-24 to match column headers */}
                <div className="h-24 border-b border-light-300 bg-white sticky top-0 z-30 flex items-center justify-center">
                  <span className="text-xs font-medium text-light-500">DATE</span>
                </div>
                <VerticalDateAxis
                  minDate={dateRange.min}
                  maxDate={dateRange.max}
                  timelineHeight={baseTimelineHeight}
                  zoomLevel={zoomLevel}
                />
              </div>
            )}
            
            {/* Swim Lane Columns */}
            <div className="flex flex-1">
              {activeEventTypes.map(type => {
                const color = TYPE_COLORS[type] || TYPE_COLORS.Other;
                return (
                  <SwimLaneColumn
                    key={type}
                    type={type}
                    events={filteredEvents}
                    onSelectEvent={handleEventSelect}
                    selectedEventKeys={selectedEventKeys}
                    minDate={dateRange.min}
                    maxDate={dateRange.max}
                    color={color}
                    baseTimelineHeight={baseTimelineHeight}
                    zoomLevel={zoomLevel}
                    isExpanded={expandedColumns.has(type)}
                    onToggleExpand={toggleColumnExpand}
                    onEventDotClick={handleEventDotClick}
                  />
                );
              })}
            </div>
            
            {/* Relationship Lines Overlay - positioned over everything */}
            {showRelationships && dateRange.min && dateRange.max && (
              <RelationshipLines
                events={filteredEvents}
                activeEventTypes={activeEventTypes}
                expandedColumns={expandedColumns}
                minDate={dateRange.min}
                maxDate={dateRange.max}
                scaledHeight={baseTimelineHeight * zoomLevel}
              />
            )}
          </div>
        </div>
        
        {/* Entity Dock - shows connected entities for selected events */}
        <EntityDock
          selectedEvents={selectedEvents}
          onEntityClick={(entity) => {
            // Delegate entity click to parent for showing details
            if (onSelectEvents) {
              onSelectEvents(entity, { ctrlKey: false, metaKey: false });
            }
          }}
          isExpanded={entityDockExpanded}
          onToggleExpand={() => setEntityDockExpanded(prev => !prev)}
        />
      </div>

    </div>
  );
}
