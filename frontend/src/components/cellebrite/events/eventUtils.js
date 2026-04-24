/**
 * Shared helpers for the Cellebrite Location & Event Center.
 */

import {
  MapPin, Radio, Wifi, Phone, MessageSquare, Mail, Power,
  Unlock, Smartphone, Search, Globe, Users, Calendar,
} from 'lucide-react';

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
  meeting: 'Meeting',
};

// Per-device colour palette (matches backend hint but deterministic in case backend omits)
const DEVICE_PALETTE = [
  '#2563eb', '#dc2626', '#059669', '#d97706',
  '#7c3aed', '#0891b2', '#db2777', '#65a30d',
];

export function deviceColor(reportKey, reports = []) {
  const idx = reports.findIndex((r) => r.report_key === reportKey);
  if (idx < 0) {
    // Fallback: hash the key
    let h = 0;
    for (const ch of reportKey || '') h = (h * 31 + ch.charCodeAt(0)) | 0;
    return DEVICE_PALETTE[Math.abs(h) % DEVICE_PALETTE.length];
  }
  return DEVICE_PALETTE[idx % DEVICE_PALETTE.length];
}

export function eventColor(eventType) {
  return EVENT_COLORS[eventType] || '#64748b';
}

/**
 * Format ISO timestamp like "2022-11-14 14:30 UTC".
 */
export function formatTs(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
           `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  } catch {
    return iso;
  }
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
export function formatDuration(ms) {
  if (ms == null) return '';
  if (ms < 1000) return `${ms}ms`;
  const s = Math.round(ms / 1000);
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
