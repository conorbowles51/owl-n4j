/**
 * Canonical phone identity utility.
 *
 * Single source of truth for the colour, short label, and styling
 * applied to a Cellebrite PhoneReport across the whole frontend.
 *
 * Every surface that displays Cellebrite-derived data (Comms Center,
 * Event Center, Timeline, Files, Cross-Phone Graph, main MapView,
 * graph nodes) must read from here so that one phone has one identity
 * everywhere.
 */

/**
 * Per-phone palette. Each slot pairs a hex colour (for SVG/canvas/inline
 * styles) with Tailwind class triples (for chips, stripes, badges).
 *
 * Slots are stable: a phone with display_index N gets PHONE_PALETTE[N % len].
 * Hex values are taken from the original DEVICE_PALETTE in eventUtils.js so
 * existing map markers and tracks render identically.
 */
export const PHONE_PALETTE = [
  {
    hex: '#2563eb',
    name: 'blue',
    ring: 'ring-blue-500',
    border: 'border-blue-500',
    bg: 'bg-blue-500',
    bgSoft: 'bg-blue-50',
    bgChip: 'bg-blue-100',
    text: 'text-blue-700',
    textOn: 'text-white',
  },
  {
    hex: '#dc2626',
    name: 'red',
    ring: 'ring-red-500',
    border: 'border-red-500',
    bg: 'bg-red-500',
    bgSoft: 'bg-red-50',
    bgChip: 'bg-red-100',
    text: 'text-red-700',
    textOn: 'text-white',
  },
  {
    hex: '#059669',
    name: 'emerald',
    ring: 'ring-emerald-500',
    border: 'border-emerald-500',
    bg: 'bg-emerald-500',
    bgSoft: 'bg-emerald-50',
    bgChip: 'bg-emerald-100',
    text: 'text-emerald-700',
    textOn: 'text-white',
  },
  {
    hex: '#d97706',
    name: 'amber',
    ring: 'ring-amber-500',
    border: 'border-amber-500',
    bg: 'bg-amber-500',
    bgSoft: 'bg-amber-50',
    bgChip: 'bg-amber-100',
    text: 'text-amber-700',
    textOn: 'text-white',
  },
  {
    hex: '#7c3aed',
    name: 'violet',
    ring: 'ring-violet-500',
    border: 'border-violet-500',
    bg: 'bg-violet-500',
    bgSoft: 'bg-violet-50',
    bgChip: 'bg-violet-100',
    text: 'text-violet-700',
    textOn: 'text-white',
  },
  {
    hex: '#0891b2',
    name: 'cyan',
    ring: 'ring-cyan-500',
    border: 'border-cyan-500',
    bg: 'bg-cyan-500',
    bgSoft: 'bg-cyan-50',
    bgChip: 'bg-cyan-100',
    text: 'text-cyan-700',
    textOn: 'text-white',
  },
  {
    hex: '#db2777',
    name: 'pink',
    ring: 'ring-pink-500',
    border: 'border-pink-500',
    bg: 'bg-pink-500',
    bgSoft: 'bg-pink-50',
    bgChip: 'bg-pink-100',
    text: 'text-pink-700',
    textOn: 'text-white',
  },
  {
    hex: '#65a30d',
    name: 'lime',
    ring: 'ring-lime-500',
    border: 'border-lime-500',
    bg: 'bg-lime-600',
    bgSoft: 'bg-lime-50',
    bgChip: 'bg-lime-100',
    text: 'text-lime-700',
    textOn: 'text-white',
  },
];

const PALETTE_LEN = PHONE_PALETTE.length;

/**
 * Hash a string to a stable non-negative integer (used as a fallback
 * when no display_index is available).
 */
function hashKey(key) {
  let h = 0;
  for (const ch of String(key || '')) {
    h = (h * 31 + ch.charCodeAt(0)) | 0;
  }
  return Math.abs(h);
}

/**
 * Resolve the palette slot for a given report.
 *
 * Preference order:
 *   1. report.display_index (provided by backend, stable per case)
 *   2. position of report_key in the supplied reports list
 *   3. hash of the report_key (last-resort fallback)
 */
export function paletteSlotForReport(report, reports = []) {
  if (report && Number.isInteger(report.display_index) && report.display_index >= 0) {
    return report.display_index % PALETTE_LEN;
  }
  if (report && Array.isArray(reports) && reports.length) {
    const idx = reports.findIndex((r) => r && r.report_key === report.report_key);
    if (idx >= 0) return idx % PALETTE_LEN;
  }
  if (report && report.report_key) {
    return hashKey(report.report_key) % PALETTE_LEN;
  }
  return 0;
}

/**
 * Resolve the palette slot from a bare report_key plus the reports list.
 * Used when only the key is in scope (e.g. inside a row component that
 * doesn't carry the full report object).
 */
export function paletteSlotForKey(reportKey, reports = []) {
  if (!reportKey) return 0;
  const found = (reports || []).find((r) => r && r.report_key === reportKey);
  if (found) return paletteSlotForReport(found, reports);
  return hashKey(reportKey) % PALETTE_LEN;
}

/**
 * Short label used in dense UI ("P1", "P2", …, "P9", "P10"+).
 * Beyond the palette length we keep counting (P9, P10, P11) so labels stay
 * unique even though colours start to repeat.
 */
export function phoneShortLabel(report, reports = []) {
  if (report && Number.isInteger(report.display_index) && report.display_index >= 0) {
    return `P${report.display_index + 1}`;
  }
  if (report && Array.isArray(reports) && reports.length) {
    const idx = reports.findIndex((r) => r && r.report_key === report.report_key);
    if (idx >= 0) return `P${idx + 1}`;
  }
  return 'P?';
}

export function phoneShortLabelByKey(reportKey, reports = []) {
  if (!reportKey) return 'P?';
  const found = (reports || []).find((r) => r && r.report_key === reportKey);
  return found ? phoneShortLabel(found, reports) : 'P?';
}

/**
 * Long descriptor used in tooltips and list headers.
 *   "P1 · iPhone 12 · John Smith"
 */
export function phoneLongLabel(report, reports = []) {
  if (!report) return '';
  const short = phoneShortLabel(report, reports);
  const model = report.device_model || 'Unknown device';
  const owner = report.phone_owner_name || '';
  return owner ? `${short} · ${model} · ${owner}` : `${short} · ${model}`;
}

/**
 * Single lookup returning everything UI components need to render a
 * phone identity. Stable across the app — every component should call
 * this rather than computing colour/label themselves.
 */
export function getPhoneIdentity(report, reports = []) {
  const slot = paletteSlotForReport(report, reports);
  const palette = PHONE_PALETTE[slot];
  return {
    slot,
    palette,
    hex: palette.hex,
    short: phoneShortLabel(report, reports),
    long: phoneLongLabel(report, reports),
    owner: report ? (report.phone_owner_name || '') : '',
    model: report ? (report.device_model || '') : '',
    reportKey: report ? report.report_key : '',
  };
}

/**
 * Convenience for components that only have a report_key.
 */
export function getPhoneIdentityByKey(reportKey, reports = []) {
  const report = (reports || []).find((r) => r && r.report_key === reportKey);
  if (report) return getPhoneIdentity(report, reports);
  // No report found — synthesise from hash so colours stay stable.
  const slot = hashKey(reportKey) % PALETTE_LEN;
  const palette = PHONE_PALETTE[slot];
  return {
    slot,
    palette,
    hex: palette.hex,
    short: 'P?',
    long: 'Unknown phone',
    owner: '',
    model: '',
    reportKey: reportKey || '',
  };
}

/**
 * Backwards-compatible hex-only accessor used by the existing
 * EventMapPanel / Timeline ring code. New code should prefer
 * getPhoneIdentityByKey().hex.
 */
export function phoneHexByKey(reportKey, reports = []) {
  return getPhoneIdentityByKey(reportKey, reports).hex;
}
