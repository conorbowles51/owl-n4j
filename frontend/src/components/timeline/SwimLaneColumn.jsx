import { EventDot, EventCardWithConnector } from './Events';
import { calculateVerticalPosition, parseDate, resolveOverlaps } from '../../utils/timeline';
import { useMemo } from 'react';
import { ChevronLeft } from 'lucide-react';

const CARD_HEIGHT = 80;

/**
 * Swim Lane Column Component - Collapsible column per event type
 */
export function SwimLaneColumn({ 
  type, 
  events, 
  onSelectEvent, 
  selectedEventKeys, 
  minDate, 
  maxDate, 
  color, 
  baseTimelineHeight,
  zoomLevel,
  isExpanded,
  onToggleExpand,
  onEventDotClick
}) {
  const laneEvents = events.filter(e => e.type === type);
  
  // Apply zoom to base height
  const scaledHeight = baseTimelineHeight * zoomLevel;
  
  // Sort events by date and time
  const sortedEvents = useMemo(() => {
    return [...laneEvents].sort((a, b) => {
      const dateA = parseDate(a.date);
      const dateB = parseDate(b.date);
      if (!dateA || !dateB) return 0;
      if (dateA.getTime() !== dateB.getTime()) {
        return dateA.getTime() - dateB.getTime();
      }
      return (a.time || '').localeCompare(b.time || '');
    });
  }, [laneEvents]);
  
  // Resolve overlapping events for expanded view
  const resolvedEvents = useMemo(() => {
    if (!isExpanded) return [];
    return resolveOverlaps(sortedEvents, minDate, maxDate, scaledHeight);
  }, [sortedEvents, minDate, maxDate, scaledHeight, isExpanded]);
  
  // Calculate required height based on resolved positions
  const requiredHeight = useMemo(() => {
    if (!isExpanded || resolvedEvents.length === 0) return scaledHeight;
    const lastEvent = resolvedEvents[resolvedEvents.length - 1];
    return Math.max(scaledHeight, lastEvent.displayPx + CARD_HEIGHT + 40);
  }, [resolvedEvents, scaledHeight, isExpanded]);
  
  const columnWidth = isExpanded ? 'min-w-[280px] w-[280px]' : 'min-w-[48px] w-[48px]';
  
  return (
    <div 
      className={`flex flex-col border-r border-light-200 last:border-r-0 transition-all duration-300 ${columnWidth}`}
    >
      {/* Column Header - fixed h-24 to match DATE header */}
      <div 
        className="h-24 border-b border-light-200 bg-white sticky top-0 z-30 cursor-pointer hover:bg-light-50 transition-colors flex items-center justify-center"
        style={{ borderTop: `4px solid ${color}` }}
        onClick={() => onToggleExpand(type)}
      >
        {isExpanded ? (
          <div className="flex items-center gap-1 px-2">
            <ChevronLeft className="w-4 h-4 text-light-400" />
            <div className="flex flex-col items-center flex-1">
              <span className="font-semibold text-sm truncate" style={{ color }}>
                {type}
              </span>
              <span className="text-xs text-light-500">
                {laneEvents.length}
              </span>
            </div>
            <ChevronLeft className="w-4 h-4 text-light-400" />
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full overflow-hidden py-1">
            <span 
              className="font-bold text-xs"
              style={{ 
                color,
                writingMode: 'vertical-rl',
                textOrientation: 'mixed',
                transform: 'rotate(180deg)',
                letterSpacing: '0.05em',
                maxHeight: '60px',
                overflow: 'hidden',
                textOverflow: 'ellipsis'
              }}
            >
              {type}
            </span>
            <span className="text-xs text-light-500 mt-1">
              {laneEvents.length}
            </span>
          </div>
        )}
      </div>
      
      {/* Column Content - matches VerticalDateAxis height exactly */}
      <div 
        className={`relative transition-all duration-300 overflow-visible ${
          isExpanded ? 'bg-gradient-to-b from-light-50/50 to-light-100/30' : 'bg-light-50/80'
        }`}
        style={{ height: `${scaledHeight}px` }}
      >
        {/* Vertical timeline rail */}
        <div 
          className="absolute top-0 bottom-0 w-1 rounded-full"
          style={{ 
            left: isExpanded ? '10px' : '50%', 
            transform: isExpanded ? 'none' : 'translateX(-50%)',
            backgroundColor: `${color}30`
          }}
        />
        
        {isExpanded ? (
          // Expanded: Show cards with connectors to actual dates
          resolvedEvents.map(event => (
            <EventCardWithConnector
              key={event.key}
              event={event}
              onSelect={onSelectEvent}
              isSelected={selectedEventKeys.includes(event.key)}
              actualPx={event.actualPx}
              displayPx={event.displayPx}
              color={color}
              timelineHeight={requiredHeight}
            />
          ))
        ) : (
          // Collapsed: Show dots only - use same pixel calculation as expanded view
          sortedEvents.map(event => {
            const topPercent = calculateVerticalPosition(event.date, event.time, minDate, maxDate);
            const topPx = (topPercent / 100) * scaledHeight;
            return (
              <EventDot
                key={event.key}
                event={event}
                topPx={topPx}
                color={color}
                onClick={() => onEventDotClick(type, event)}
                isSelected={selectedEventKeys.includes(event.key)}
              />
            );
          })
        )}
      </div>
    </div>
  );
}