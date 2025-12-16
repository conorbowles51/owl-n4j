// @ts-check

import { 
  Clock,
  DollarSign
} from "lucide-react";
import { formatTime } from "../../utils/timeline";

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
 * Event Dot - Small marker for collapsed view
 */
export function EventDot({ event, topPx, color, onClick, isSelected }) {
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        onClick(event);
      }}
      className={`absolute left-1/2 w-4 h-4 rounded-full transition-all hover:scale-150 z-10 ${
        isSelected ? 'ring-2 ring-owl-blue-500 ring-offset-2' : ''
      }`}
      style={{ 
        top: `${topPx}px`,
        transform: 'translate(-50%, -50%)',
        backgroundColor: color,
        boxShadow: '0 2px 4px rgba(0,0,0,0.2)'
      }}
      title={`${event.name} - ${formatDate(event.date)} ${event.time || ''}`}
    />
  );
}

/**
 * Event Card with Connector - Shows card with horizontal line to actual date position
 */
export function EventCardWithConnector({ event, onSelect, isSelected, actualPx, displayPx, color, timelineHeight }) {
  const handleClick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    const isMultiSelect = e.ctrlKey || e.metaKey;
    onSelect(event, isMultiSelect);
  };
  
  // Calculate if positions differ enough to show connector
  
  return (
    <>
      {/* Date marker dot on the timeline rail */}
      <div
        className="absolute w-3 h-3 rounded-full z-20"
        style={{
          left: '12px',
          top: `${actualPx}px`,
          transform: 'translate(-50%, -50%)',
          backgroundColor: color,
          boxShadow: '0 1px 3px rgba(0,0,0,0.4)',
          border: '2px solid white'
        }}
      />
      
      {/* Connector line from date marker to card */}
      <svg
        className="absolute pointer-events-none z-5"
        style={{
          left: '0',
          top: '0',
          width: '100%',
          height: `${timelineHeight}px`,
          overflow: 'visible'
        }}
      >
        <line
          x1="10"
          y1={actualPx}
          x2="57"
          y2={displayPx}
          stroke={color}
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
      
      {/* Event Card */}
      <button
        onClick={handleClick}
        className={`absolute left-14 right-2 px-3 py-2 rounded-lg transition-all text-left z-10 ${
          isSelected 
            ? 'bg-owl-blue-100 ring-2 ring-owl-blue-500 shadow-md' 
            : 'bg-white hover:bg-light-50 border border-light-200 hover:shadow-sm'
        }`}
        style={{ 
          top: `${displayPx}px`,
          transform: 'translateY(-50%)',
          borderLeft: `4px solid ${color}`,
        }}
        title={`${event.name} - ${formatDate(event.date)} ${event.time || ''}`}
      >
        <div className="flex flex-col gap-1">
          <span className="font-medium text-owl-blue-900 truncate text-sm">
            {event.name}
          </span>
          
          <div className="flex items-center gap-2 text-xs text-light-600">
            <span>{formatDate(event.date)}</span>
            {event.time && (
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {formatTime(event.time)}
              </span>
            )}
          </div>
          
          {event.amount && (
            <span className="flex items-center gap-1 text-xs text-light-700">
              <DollarSign className="w-3 h-3" />
              {event.amount}
            </span>
          )}
        </div>
      </button>
    </>
  );
}