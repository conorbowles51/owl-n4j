
import { useMemo } from "react";
import { calculateVerticalPosition, formatDateForAxis, parseDate } from "../../utils/timeline";

/**
 * Vertical Date Axis Component
 */
export function VerticalDateAxis({ minDate, maxDate, timelineHeight, zoomLevel }) {
  const scaledHeight = timelineHeight * zoomLevel;
  
  const dateMarkers = useMemo(() => {
    if (!minDate || !maxDate) return [];
    
    const min = parseDate(minDate);
    const max = parseDate(maxDate);
    if (!min || !max) return [];
    
    const markers = [];
    const totalDays = Math.ceil((max.getTime() - min.getTime()) / (1000 * 60 * 60 * 24));
    
    // More markers when zoomed in
    let intervalDays = 1;
    const adjustedDays = totalDays / zoomLevel;
    if (adjustedDays > 365) intervalDays = 30;
    else if (adjustedDays > 180) intervalDays = 14;
    else if (adjustedDays > 90) intervalDays = 7;
    else if (adjustedDays > 30) intervalDays = 3;
    else if (adjustedDays > 14) intervalDays = 2;
    
    const current = new Date(min);
    while (current <= max) {
      const positionPercent = calculateVerticalPosition(
        current.toISOString().split('T')[0],
        null,
        minDate,
        maxDate
      );
      // Use pixel positioning to match dot positioning
      const positionPx = (positionPercent / 100) * scaledHeight;
      markers.push({
        date: new Date(current),
        positionPx
      });
      current.setDate(current.getDate() + intervalDays);
    }
    
    return markers;
  }, [minDate, maxDate, zoomLevel, scaledHeight]);
  
  return (
    <div 
      className="w-24 flex-shrink-0 border-r border-light-300 bg-white relative"
      style={{ height: `${scaledHeight}px` }}
    >
      {/* Timeline rail */}
      <div className="absolute right-0 top-0 bottom-0 w-1 bg-light-200" />
      
      {dateMarkers.map((marker, idx) => (
        <div
          key={idx}
          className="absolute left-0 right-0 flex items-center"
          style={{ top: `${marker.positionPx}px`, transform: 'translateY(-50%)' }}
        >
          <span className="text-xs text-light-600 px-1 py-0.5 bg-white rounded whitespace-nowrap font-medium">
            {formatDateForAxis(marker.date.toISOString().split('T')[0])}
          </span>
          <div className="flex-1 border-t border-dashed border-light-300" />
        </div>
      ))}
    </div>
  );
}