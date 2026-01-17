import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import {
  Play,
  Pause,
  SkipBack,
  SkipForward,
  ChevronLeft,
  ChevronRight,
  Clock,
  X,
  Calendar
} from 'lucide-react';

/**
 * TimeControl Component
 *
 * Provides time-based animation controls for the map view.
 * Allows scrubbing through time to see entities appear/disappear.
 */
export default function TimeControl({
  locations = [],
  onTimeChange,
  isActive = false,
  onClose,
}) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [currentTime, setCurrentTime] = useState(null);
  const animationRef = useRef(null);

  // Calculate date range from locations
  const dateRange = useMemo(() => {
    const dates = locations
      .filter(loc => loc.date)
      .map(loc => new Date(loc.date))
      .filter(d => !isNaN(d.getTime()))
      .sort((a, b) => a - b);

    if (dates.length === 0) {
      return { min: null, max: null, hasData: false };
    }

    return {
      min: dates[0],
      max: dates[dates.length - 1],
      hasData: true,
    };
  }, [locations]);

  // Initialize current time when date range changes
  useEffect(() => {
    if (dateRange.hasData && currentTime === null) {
      setCurrentTime(dateRange.min);
    }
  }, [dateRange, currentTime]);

  // Handle playback animation
  useEffect(() => {
    if (isPlaying && dateRange.hasData) {
      const DAY_MS = 24 * 60 * 60 * 1000;
      const interval = 100; // Animation frame interval in ms

      animationRef.current = setInterval(() => {
        setCurrentTime(prev => {
          if (!prev) return dateRange.min;
          const next = new Date(prev.getTime() + playbackSpeed * DAY_MS);
          if (next > dateRange.max) {
            setIsPlaying(false);
            return dateRange.max;
          }
          return next;
        });
      }, interval);
    }

    return () => {
      if (animationRef.current) {
        clearInterval(animationRef.current);
      }
    };
  }, [isPlaying, playbackSpeed, dateRange]);

  // Notify parent of time changes
  useEffect(() => {
    if (onTimeChange) {
      onTimeChange(currentTime);
    }
  }, [currentTime, onTimeChange]);

  // Reset when deactivated
  useEffect(() => {
    if (!isActive) {
      setIsPlaying(false);
      setCurrentTime(null);
      if (onTimeChange) {
        onTimeChange(null);
      }
    }
  }, [isActive, onTimeChange]);

  // Calculate slider position (0-100)
  const sliderPosition = useMemo(() => {
    if (!currentTime || !dateRange.hasData) return 0;
    const total = dateRange.max.getTime() - dateRange.min.getTime();
    if (total === 0) return 100;
    const current = currentTime.getTime() - dateRange.min.getTime();
    return (current / total) * 100;
  }, [currentTime, dateRange]);

  // Handle slider change
  const handleSliderChange = useCallback((e) => {
    if (!dateRange.hasData) return;
    const percent = parseFloat(e.target.value);
    const total = dateRange.max.getTime() - dateRange.min.getTime();
    const newTime = new Date(dateRange.min.getTime() + (percent / 100) * total);
    setCurrentTime(newTime);
  }, [dateRange]);

  // Step forward/backward by a day
  const stepTime = useCallback((days) => {
    if (!currentTime || !dateRange.hasData) return;
    const DAY_MS = 24 * 60 * 60 * 1000;
    const newTime = new Date(currentTime.getTime() + days * DAY_MS);
    if (newTime >= dateRange.min && newTime <= dateRange.max) {
      setCurrentTime(newTime);
    }
  }, [currentTime, dateRange]);

  // Jump to start/end
  const jumpToStart = useCallback(() => {
    if (dateRange.hasData) {
      setCurrentTime(dateRange.min);
    }
  }, [dateRange]);

  const jumpToEnd = useCallback(() => {
    if (dateRange.hasData) {
      setCurrentTime(dateRange.max);
    }
  }, [dateRange]);

  // Format date for display
  const formatDate = (date) => {
    if (!date) return '--';
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  // Count entities visible at current time
  const visibleCount = useMemo(() => {
    if (!currentTime) return locations.length;
    return locations.filter(loc => {
      if (!loc.date) return true;
      const locDate = new Date(loc.date);
      return !isNaN(locDate.getTime()) && locDate <= currentTime;
    }).length;
  }, [locations, currentTime]);

  if (!isActive) return null;

  return (
    <div className="absolute bottom-20 left-1/2 transform -translate-x-1/2 z-[1000] bg-white/95 backdrop-blur-sm rounded-lg shadow-lg border border-light-200 p-3 w-[480px] max-w-[calc(100vw-2rem)]">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 text-blue-500" />
          <span className="font-semibold text-sm text-light-800">Time Animation</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-light-500">
            {visibleCount} / {locations.length} entities
          </span>
          <button
            onClick={onClose}
            className="p-1 hover:bg-light-100 rounded"
          >
            <X className="w-4 h-4 text-light-500" />
          </button>
        </div>
      </div>

      {dateRange.hasData ? (
        <>
          {/* Current date display */}
          <div className="text-center mb-3">
            <div className="inline-flex items-center gap-2 bg-blue-50 rounded-lg px-3 py-1.5">
              <Calendar className="w-4 h-4 text-blue-500" />
              <span className="text-sm font-medium text-blue-700">
                {formatDate(currentTime)}
              </span>
            </div>
          </div>

          {/* Timeline slider */}
          <div className="mb-3">
            <div className="flex justify-between text-xs text-light-500 mb-1">
              <span>{formatDate(dateRange.min)}</span>
              <span>{formatDate(dateRange.max)}</span>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              step="0.1"
              value={sliderPosition}
              onChange={handleSliderChange}
              className="w-full h-2 bg-light-200 rounded-lg appearance-none cursor-pointer accent-blue-500"
            />
          </div>

          {/* Playback controls */}
          <div className="flex items-center justify-center gap-2">
            {/* Jump to start */}
            <button
              onClick={jumpToStart}
              className="p-2 hover:bg-light-100 rounded-lg transition-colors"
              title="Jump to start"
            >
              <SkipBack className="w-4 h-4 text-light-600" />
            </button>

            {/* Step backward */}
            <button
              onClick={() => stepTime(-1)}
              className="p-2 hover:bg-light-100 rounded-lg transition-colors"
              title="Previous day"
            >
              <ChevronLeft className="w-4 h-4 text-light-600" />
            </button>

            {/* Play/Pause */}
            <button
              onClick={() => setIsPlaying(!isPlaying)}
              className={`p-3 rounded-full transition-colors ${
                isPlaying
                  ? 'bg-blue-500 text-white hover:bg-blue-600'
                  : 'bg-blue-100 text-blue-600 hover:bg-blue-200'
              }`}
              title={isPlaying ? 'Pause' : 'Play'}
            >
              {isPlaying ? (
                <Pause className="w-5 h-5" />
              ) : (
                <Play className="w-5 h-5" />
              )}
            </button>

            {/* Step forward */}
            <button
              onClick={() => stepTime(1)}
              className="p-2 hover:bg-light-100 rounded-lg transition-colors"
              title="Next day"
            >
              <ChevronRight className="w-4 h-4 text-light-600" />
            </button>

            {/* Jump to end */}
            <button
              onClick={jumpToEnd}
              className="p-2 hover:bg-light-100 rounded-lg transition-colors"
              title="Jump to end"
            >
              <SkipForward className="w-4 h-4 text-light-600" />
            </button>

            {/* Speed selector */}
            <div className="ml-4 flex items-center gap-1">
              <span className="text-xs text-light-500">Speed:</span>
              {[1, 2, 5, 10].map(speed => (
                <button
                  key={speed}
                  onClick={() => setPlaybackSpeed(speed)}
                  className={`px-2 py-1 text-xs rounded transition-colors ${
                    playbackSpeed === speed
                      ? 'bg-blue-500 text-white'
                      : 'bg-light-100 text-light-600 hover:bg-light-200'
                  }`}
                >
                  {speed}x
                </button>
              ))}
            </div>
          </div>
        </>
      ) : (
        <div className="text-center py-4 text-light-500 text-sm">
          <Clock className="w-6 h-6 mx-auto mb-2 text-light-400" />
          No temporal data available
          <p className="text-xs mt-1">
            Entities need date information for time-based animation
          </p>
        </div>
      )}
    </div>
  );
}
