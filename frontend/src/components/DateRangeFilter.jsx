import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Calendar, Clock, X, Filter } from 'lucide-react';

/**
 * DateRangeFilter Component
 * 
 * Allows users to filter the graph by date range with:
 * - Date and time inputs
 * - Visual timeline slider
 */
export default function DateRangeFilter({ 
  onDateRangeChange, 
  minDate, 
  maxDate,
  timelineEvents = [] 
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [startDate, setStartDate] = useState('');
  const [startTime, setStartTime] = useState('00:00');
  const [endDate, setEndDate] = useState('');
  const [endTime, setEndTime] = useState('23:59');
  const [timelineRange, setTimelineRange] = useState({ min: 0, max: 100 });

  // Use minDate/maxDate from props if available, otherwise calculate from timeline events
  // Memoize to prevent recalculation on every render
  const effectiveMinDate = useMemo(() => {
    if (minDate) return minDate;
    if (timelineEvents && timelineEvents.length > 0) {
      const dates = timelineEvents
        .map(e => e.date)
        .filter(d => d)
        .map(d => new Date(d));
      return dates.length > 0 
        ? new Date(Math.min(...dates)).toISOString().split('T')[0]
        : null;
    }
    return null;
  }, [minDate, timelineEvents]);
  
  const effectiveMaxDate = useMemo(() => {
    if (maxDate) return maxDate;
    if (timelineEvents && timelineEvents.length > 0) {
      const dates = timelineEvents
        .map(e => e.date)
        .filter(d => d)
        .map(d => new Date(d));
      return dates.length > 0
        ? new Date(Math.max(...dates)).toISOString().split('T')[0]
        : null;
    }
    return null;
  }, [maxDate, timelineEvents]);

  // Calculate timeline range percentage
  const calculateTimelinePosition = useCallback((dateStr) => {
    if (!effectiveMinDate || !effectiveMaxDate || !dateStr) return 0;
    const date = new Date(dateStr);
    const min = new Date(effectiveMinDate);
    const max = new Date(effectiveMaxDate);
    if (max.getTime() === min.getTime()) return 0;
    return ((date.getTime() - min.getTime()) / (max.getTime() - min.getTime())) * 100;
  }, [effectiveMinDate, effectiveMaxDate]);

  // Update timeline slider positions when dates change
  useEffect(() => {
    if (startDate && endDate && effectiveMinDate && effectiveMaxDate) {
      setTimelineRange({
        min: calculateTimelinePosition(startDate),
        max: calculateTimelinePosition(endDate),
      });
    }
  }, [startDate, endDate, effectiveMinDate, effectiveMaxDate, calculateTimelinePosition]);

  // Track applied date range (what's currently filtering)
  const [appliedStartDate, setAppliedStartDate] = useState('');
  const [appliedEndDate, setAppliedEndDate] = useState('');

  const handleApply = () => {
    // Apply the current date selections
    setAppliedStartDate(startDate);
    setAppliedEndDate(endDate);
    
    if (onDateRangeChange) {
      const start = startDate ? `${startDate}T${startTime}:00` : null;
      const end = endDate ? `${endDate}T${endTime}:59` : null;
      onDateRangeChange({
        start_date: startDate || null,
        end_date: endDate || null,
        start_datetime: start,
        end_datetime: end,
      });
    }
    
    // Close the filter panel
    setIsOpen(false);
  };

  const handleClear = () => {
    setStartDate('');
    setEndDate('');
    setStartTime('00:00');
    setEndTime('23:59');
    setAppliedStartDate('');
    setAppliedEndDate('');
    
    if (onDateRangeChange) {
      onDateRangeChange({
        start_date: null,
        end_date: null,
        start_datetime: null,
        end_datetime: null,
      });
    }
  };

  const handleTimelineSliderChange = (type, value) => {
    if (!effectiveMinDate || !effectiveMaxDate) return;
    
    const min = new Date(effectiveMinDate);
    const max = new Date(effectiveMaxDate);
    const range = max.getTime() - min.getTime();
    const newDate = new Date(min.getTime() + (range * value / 100));
    const dateStr = newDate.toISOString().split('T')[0];
    
    if (type === 'start') {
      setStartDate(dateStr);
      if (endDate && dateStr > endDate) {
        setEndDate(dateStr);
      }
    } else {
      setEndDate(dateStr);
      if (startDate && dateStr < startDate) {
        setStartDate(dateStr);
      }
    }
  };

  const hasActiveFilter = appliedStartDate || appliedEndDate;

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors ${
          hasActiveFilter
            ? 'bg-cyan-600 text-white hover:bg-cyan-500'
            : 'bg-dark-700 text-dark-300 hover:bg-dark-600'
        }`}
        title="Filter by date range"
      >
        <Filter className="w-4 h-4" />
        Date Range
        {hasActiveFilter && (
          <span className="ml-1 px-1.5 py-0.5 bg-white/20 rounded text-xs">
            Active
          </span>
        )}
      </button>

      {isOpen && (
        <div className="absolute top-full left-0 mt-2 bg-dark-800 rounded-lg p-4 w-96 border border-dark-700 shadow-xl z-50">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-dark-100 flex items-center gap-2">
              <Calendar className="w-4 h-4" />
              Date Range Filter
            </h3>
            <button
              onClick={() => setIsOpen(false)}
              className="p-1 hover:bg-dark-700 rounded transition-colors"
            >
              <X className="w-4 h-4 text-dark-400" />
            </button>
          </div>

          {/* Visual Timeline Slider */}
          {(effectiveMinDate && effectiveMaxDate) && (
            <div className="mb-4">
              <label className="block text-xs font-medium text-dark-400 mb-2">
                Timeline Range
              </label>
              <div className="relative h-8">
                {/* Background track */}
                <div className="absolute inset-0 bg-dark-700 rounded-full" />
                
                {/* Active range */}
                {startDate && endDate && (
                  <div
                    className="absolute h-full bg-cyan-600 rounded-full"
                    style={{
                      left: `${Math.min(timelineRange.min, timelineRange.max)}%`,
                      width: `${Math.abs(timelineRange.max - timelineRange.min)}%`,
                    }}
                  />
                )}
                
                {/* Start handle */}
                {startDate && (
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={timelineRange.min}
                    onChange={(e) => handleTimelineSliderChange('start', e.target.value)}
                    className="absolute top-0 w-full h-full opacity-0 cursor-pointer z-10"
                  />
                )}
                
                {/* End handle */}
                {endDate && (
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={timelineRange.max}
                    onChange={(e) => handleTimelineSliderChange('end', e.target.value)}
                    className="absolute top-0 w-full h-full opacity-0 cursor-pointer z-10"
                  />
                )}
                
                {/* Date labels */}
                <div className="absolute -bottom-5 left-0 right-0 flex justify-between text-xs text-dark-500">
                  <span>{effectiveMinDate}</span>
                  {startDate && endDate && (
                    <span className="text-cyan-400">
                      {startDate} to {endDate}
                    </span>
                  )}
                  <span>{effectiveMaxDate}</span>
                </div>
              </div>
            </div>
          )}

          {/* Date and Time Inputs */}
          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-dark-400 mb-1.5">
                Start Date & Time
              </label>
              <div className="flex gap-2">
                <div className="flex-1 flex items-center gap-2 bg-dark-900 rounded-lg px-3 py-2 border border-dark-700">
                  <Calendar className="w-4 h-4 text-dark-500" />
                  <input
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    className="flex-1 bg-transparent text-dark-100 text-sm focus:outline-none"
                    min={effectiveMinDate}
                    max={effectiveMaxDate || endDate}
                  />
                </div>
                <div className="flex items-center gap-2 bg-dark-900 rounded-lg px-3 py-2 border border-dark-700 w-24">
                  <Clock className="w-4 h-4 text-dark-500" />
                  <input
                    type="time"
                    value={startTime}
                    onChange={(e) => setStartTime(e.target.value)}
                    className="flex-1 bg-transparent text-dark-100 text-sm focus:outline-none"
                  />
                </div>
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-dark-400 mb-1.5">
                End Date & Time
              </label>
              <div className="flex gap-2">
                <div className="flex-1 flex items-center gap-2 bg-dark-900 rounded-lg px-3 py-2 border border-dark-700">
                  <Calendar className="w-4 h-4 text-dark-500" />
                  <input
                    type="date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    className="flex-1 bg-transparent text-dark-100 text-sm focus:outline-none"
                    min={startDate || effectiveMinDate}
                    max={effectiveMaxDate}
                  />
                </div>
                <div className="flex items-center gap-2 bg-dark-900 rounded-lg px-3 py-2 border border-dark-700 w-24">
                  <Clock className="w-4 h-4 text-dark-500" />
                  <input
                    type="time"
                    value={endTime}
                    onChange={(e) => setEndTime(e.target.value)}
                    className="flex-1 bg-transparent text-dark-100 text-sm focus:outline-none"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="mt-4 flex gap-2">
            <button
              onClick={handleClear}
              className="flex-1 px-3 py-2 bg-dark-700 hover:bg-dark-600 text-dark-300 rounded-lg text-sm transition-colors"
            >
              Clear Filter
            </button>
            <button
              onClick={handleApply}
              className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-sm transition-colors"
            >
              Apply
            </button>
          </div>

          {/* Info */}
          <div className="mt-3 text-xs text-dark-500 bg-dark-900/50 rounded p-2">
            <p>Shows nodes with dates in range or connected to nodes with dates in range.</p>
          </div>
        </div>
      )}
    </div>
  );
}

