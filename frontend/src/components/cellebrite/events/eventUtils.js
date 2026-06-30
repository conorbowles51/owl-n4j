/**
 * Shared helpers for the Cellebrite Location & Event Center.
 */

import {
  MapPin, Radio, Wifi, Phone, MessageSquare, Mail, Power,
  Unlock, Smartphone, Search, Globe, Users, Calendar,
  File as FileIcon, Image as ImageIcon, Video as VideoIcon,
  FileAudio, FileText, Keyboard,
} from 'lucide-react';
import { fmtDateTime, getTzId } from '../shared/cellebriteTime';

// Event type colour palette
export const EVENT_COLORS = {
  location: '#06b6d4',      // cyan
  cell_tower: '#8b5cf6',    // violet
  wifi: '#10b981',          // emerald
  call: '#2563eb',          // blue
  message: '#f59e0b',       // amber
  email: '#ef4444',         // red
  power: '#6b7280',         // gray
  device_event: '#64748b',  // slate
  app_session: '#14b8a6',   // teal
  search: '#db2777',        // pink
  visit: '#9333ea',         // purple
  meeting: '#f97316',       // orange
  file: '#0ea5e9',          // sky — media files (images/videos/audio/docs)
  autofill: '#7c3aed',      // violet — saved form/search input
};

export const EVENT_ICONS = {
  location: MapPin,
  cell_tower: Radio,
  wifi: Wifi,
  call: Phone,
  message: MessageSquare,
  email: Mail,
  power: Power,
  device_event: Unlock,
  app_session: Smartphone,
  search: Search,
  visit: Globe,
  meeting: Users,
  file: FileIcon,
  autofill: Keyboard,
};

// Per-category icon/label for "file" timeline events (images/videos/audio/docs),
// so a media row reads as what it is even before its thumbnail/player loads.
export const FILE_CATEGORY_ICONS = {
  image: ImageIcon,
  video: VideoIcon,
  audio: FileAudio,
  text: FileText,
  document: FileText,
};
export const FILE_CATEGORY_LABELS = {
  image: 'Image',
  video: 'Video',
  audio: 'Audio',
  text: 'Document',
  document: 'Document',
};

export const EVENT_LABELS = {
  location: 'Location',
  cell_tower: 'Cell tower',
  wifi: 'WiFi',
  call: 'Call',
  message: 'Message',
  email: 'Email',
  power: 'Power',
  device_event: 'Device event',
  app_session: 'App',
  search: 'Search',
  visit: 'Visit',
  meeting: 'Calendar',
  file: 'File',
  autofill: 'Autofill',
};

// Per-device colour palette is now owned by utils/phoneIdentity.js so the
// same colour applies to every Cellebrite surface (Comms, Events, Map,
// graph). This helper delegates to keep historical call sites working.
import { phoneHexByKey } from '../../../utils/phoneIdentity';

export function deviceColor(reportKey, reports = []) {
  return phoneHexByKey(reportKey, reports);
}

export function eventColor(eventType) {
  return EVENT_COLORS[eventType] || '#64748b';
}

/**
 * Format ISO timestamp as "YYYY-MM-DD HH:MM:SS" in the Cellebrite view's
 * selected timezone (see shared/cellebriteTime). Previously used the browser's
 * local getters with a hardcoded "UTC" label — the source of the timeline /
 * detail-drawer timezone mismatch. Now consistent with every other surface.
 */
export function formatTs(iso) {
  return fmtDateTime(iso, getTzId());
}

/**
 * Parse timestamp string to Date, return null on failure.
 */
export function parseTs(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  return isNaN(d.getTime()) ? null : d;
}

/**
 * Filter events whose timestamp falls within [playhead - windowMs, playhead].
 */
export function eventsWithinTrail(events, playheadTime, trailWindowMs) {
  if (!playheadTime) return events;
  const pEnd = playheadTime.getTime();
  const pStart = pEnd - trailWindowMs;
  return events.filter((e) => {
    const t = parseTs(e.timestamp);
    if (!t) return false;
    const ms = t.getTime();
    return ms >= pStart && ms <= pEnd;
  });
}

/**
 * Compute min/max timestamp from an events array.
 */
export function dateRangeFromEvents(events) {
  let min = null;
  let max = null;
  for (const e of events) {
    const d = parseTs(e.timestamp);
    if (!d) continue;
    if (min === null || d < min) min = d;
    if (max === null || d > max) max = d;
  }
  return { min, max };
}

/**
 * Haversine distance (metres) between two lat/lon points.
 */
export function haversineM(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

/**
 * Format a duration in ms as "1h 23m" / "45s".
 */
export function formatDuration(value) {
  if (value == null || value === '') return '';
  // Strings: Cellebrite stores call durations as "HH:MM:SS" (or "MM:SS"
  // for short calls), the events feed sometimes sends "1h 23m" already
  // pre-formatted, and a few legacy paths emit ISO-8601 like "PT1M30S".
  // Anything that isn't a finite number gets normalised through here.
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) return '';
    // Already pre-formatted (contains a unit suffix) — return as-is.
    if (/[a-zA-Z]/.test(trimmed) && !/^P/i.test(trimmed)) return trimmed;
    // HH:MM:SS / MM:SS / SS
    if (/^\d{1,2}(:\d{1,2}){0,2}$/.test(trimmed)) {
      const parts = trimmed.split(':').map((p) => parseInt(p, 10) || 0);
      let secs = 0;
      if (parts.length === 3) secs = parts[0] * 3600 + parts[1] * 60 + parts[2];
      else if (parts.length === 2) secs = parts[0] * 60 + parts[1];
      else secs = parts[0];
      return formatSeconds(secs);
    }
    // ISO-8601 PT?H?M?S — minimal subset, no fractional support.
    const iso = /^P(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$/i.exec(trimmed);
    if (iso) {
      const h = parseInt(iso[1] || '0', 10);
      const m = parseInt(iso[2] || '0', 10);
      const s = parseInt(iso[3] || '0', 10);
      return formatSeconds(h * 3600 + m * 60 + s);
    }
    // Numeric string — fall through to the number branch.
    const asNum = Number(trimmed);
    if (Number.isFinite(asNum)) return formatNumeric(asNum);
    return '';
  }
  return formatNumeric(value);
}

function formatNumeric(ms) {
  if (!Number.isFinite(ms)) return '';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return formatSeconds(Math.round(ms / 1000));
}

function formatSeconds(s) {
  if (!Number.isFinite(s) || s < 0) return '';
  if (s === 0) return '0s';
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

/**
 * Playback speed multipliers (real-world seconds per wall-clock second).
 */
export const PLAYBACK_SPEEDS = [1, 2, 5, 10, 30, 60, 300, 1800];
