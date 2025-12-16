// Minimum spacing between cards in pixels
const MIN_CARD_SPACING = 90;

/**
 * Calculate vertical position of event on timeline (0-100% from top)
 * Top = earliest date, Bottom = latest date
 */
export function calculateVerticalPosition(eventDate, eventTime, minDate, maxDate) {
  if (!eventDate || !minDate || !maxDate) return 50;
  const event = parseDate(eventDate);
  const min = parseDate(minDate);
  const max = parseDate(maxDate);
  
  if (!event || !min || !max) return 50;
  
  // Parse time if available for more precise positioning
  let eventTimestamp = event.getTime();
  if (eventTime) {
    const [hours, minutes, seconds] = eventTime.split(':').map(Number);
    if (!isNaN(hours)) {
      event.setHours(hours, minutes || 0, seconds || 0);
      eventTimestamp = event.getTime();
    }
  }
  
  const minTimestamp = min.getTime();
  const maxTimestamp = max.getTime();
  const totalMs = maxTimestamp - minTimestamp;
  
  if (totalMs === 0) return 0;
  
  const eventMs = eventTimestamp - minTimestamp;
  const percentage = (eventMs / totalMs) * 100;
  return Math.max(0, Math.min(100, percentage));
}

/**
 * Format time for display
 */
export function formatTime(timeStr) {
  if (!timeStr) return null;
  return timeStr;
}

/**
 * Parse date string to Date object
 */
export function parseDate(dateStr) {
  if (!dateStr) return null;
  try {
    return new Date(dateStr);
  } catch {
    return null;
  }
}

/**
 * Resolve overlapping events by spreading them out
 * Returns array of events with actualPx and displayPx positions
 */
export function resolveOverlaps(events, minDate, maxDate, timelineHeight) {
  if (events.length === 0) return [];
  
  // Calculate actual positions first
  const eventsWithPositions = events.map(event => {
    const actualPercent = calculateVerticalPosition(event.date, event.time, minDate, maxDate);
    const actualPx = (actualPercent / 100) * timelineHeight;
    return {
      ...event,
      actualPercent,
      actualPx,
      displayPx: actualPx,
    };
  });
  
  // Sort by actual position
  eventsWithPositions.sort((a, b) => a.actualPx - b.actualPx);
  
  // Spread out overlapping events - ensure minimum spacing
  for (let i = 1; i < eventsWithPositions.length; i++) {
    const prev = eventsWithPositions[i - 1];
    const curr = eventsWithPositions[i];
    
    const minY = prev.displayPx + MIN_CARD_SPACING;
    if (curr.displayPx < minY) {
      curr.displayPx = minY;
    }
  }
  
  return eventsWithPositions;
}

/**
 * Calculate required height for a lane based on its events
 */
export function calculateRequiredHeight(events, minDate, maxDate, baseHeight) {
  if (events.length === 0) return baseHeight;
  
  const resolved = resolveOverlaps(events, minDate, maxDate, baseHeight);
  if (resolved.length === 0) return baseHeight;
  
  const lastEvent = resolved[resolved.length - 1];
  return Math.max(baseHeight, lastEvent.displayPx + CARD_HEIGHT + 40);
}

/**
 * Get date range from events with padding
 */
export function getDateRange(events) {
  const dates = events
    .map(e => e.date)
    .filter(d => d)
    .map(d => parseDate(d))
    .filter(d => d);
  
  if (dates.length === 0) return { min: null, max: null };
  
  const min = new Date(Math.min(...dates.map(d => d.getTime())));
  const max = new Date(Math.max(...dates.map(d => d.getTime())));
  
  const totalRange = max.getTime() - min.getTime();
  
  // Add more padding at the START to ensure events aren't hidden behind column headers
  // At minimum, add 30 days before the first event so it displays below the header
  const startPadding = Math.max(totalRange * 0.1, 30 * 24 * 60 * 60 * 1000); // 10% or 30 days minimum
  
  // Add smaller padding at the end
  const endPadding = Math.max(totalRange * 0.02, 7 * 24 * 60 * 60 * 1000); // 2% or 7 days minimum
  
  return { 
    min: new Date(min.getTime() - startPadding).toISOString().split('T')[0], 
    max: new Date(max.getTime() + endPadding).toISOString().split('T')[0] 
  };
}

/**
 * Format date for timeline axis
 */
export function formatDateForAxis(dateStr) {
  if (!dateStr) return '';
  const date = parseDate(dateStr);
  if (!date) return '';
  return date.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: date.getFullYear() !== new Date().getFullYear() ? 'numeric' : undefined,
  }).replace(/,/g, '');
}
