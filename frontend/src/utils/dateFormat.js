/**
 * Shared date formatting utilities.
 *
 * IMPORTANT: Date-only strings like "2023-10-01" are parsed by JS as UTC midnight.
 * When displayed with toLocaleDateString() in timezones west of UTC, this causes
 * an off-by-one-day error (e.g. Oct 1 UTC → Sep 30 EDT). We fix this by appending
 * T00:00:00 (no Z) so the date is treated as local time.
 */

function normalizeDate(dateString) {
  if (!dateString) return null;
  // If it already contains a time component, leave it alone
  if (dateString.includes('T') || dateString.includes(' ')) return new Date(dateString);
  // Date-only string: treat as local midnight, not UTC
  return new Date(dateString + 'T00:00:00');
}

/**
 * Format a date string as "Oct 1, 2023"
 */
export function formatDate(dateString) {
  if (!dateString) return '';
  try {
    const d = normalizeDate(dateString);
    return d.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return dateString;
  }
}

/**
 * Format a date string as "October 1, 2023" (long month)
 */
export function formatDateLong(dateString) {
  if (!dateString) return '';
  try {
    const d = normalizeDate(dateString);
    return d.toLocaleDateString('en-US', {
      month: 'long',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return dateString;
  }
}

/**
 * Format a date string as "Oct 1" (no year)
 */
export function formatShortDate(dateString) {
  if (!dateString) return '';
  try {
    const d = normalizeDate(dateString);
    return d.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return dateString;
  }
}

/**
 * Format a date string as "Oct 1, 2023, 02:30 PM" (with time)
 */
export function formatDateTime(dateString) {
  if (!dateString) return '';
  try {
    const d = normalizeDate(dateString);
    return d.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateString;
  }
}
