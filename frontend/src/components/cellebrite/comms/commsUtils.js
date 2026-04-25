/**
 * Shared helpers for the Cellebrite Communication Center.
 */

export const IMAGE_EXT = /\.(jpg|jpeg|png|gif|bmp|webp|heic|heif|tif|tiff)$/i;
export const AUDIO_EXT = /\.(mp3|m4a|aac|ogg|opus|wav|amr|3gp|flac)$/i;
export const VIDEO_EXT = /\.(mp4|avi|mov|mkv|webm|3gp|wmv|flv)$/i;
export const DOC_EXT = /\.(pdf|txt|html?|xml|json|csv|rtf|docx?|md)$/i;

/**
 * Infer a UI-facing attachment kind. Prefers the backend-provided `category`
 * but falls back to filename extension inspection.
 */
export function attachmentKind(att) {
  if (!att) return 'other';
  const cat = (att.category || '').toLowerCase();
  if (cat === 'image') return 'image';
  if (cat === 'audio') return 'audio';
  if (cat === 'video') return 'video';
  if (cat === 'text') return 'doc';
  const name = att.original_filename || '';
  if (IMAGE_EXT.test(name)) return 'image';
  if (AUDIO_EXT.test(name)) return 'audio';
  if (VIDEO_EXT.test(name)) return 'video';
  if (DOC_EXT.test(name)) return 'doc';
  return 'other';
}

/**
 * Build the evidence file URL for an attachment.
 */
export function attachmentUrl(att) {
  if (!att || !att.evidence_id) return null;
  return `/api/evidence/${encodeURIComponent(att.evidence_id)}/file`;
}

/**
 * Build video frame thumbnail URL (first frame).
 */
export function videoThumbUrl(att) {
  if (!att || !att.evidence_id) return null;
  return `/api/evidence/${encodeURIComponent(att.evidence_id)}/frames/frame_0001.jpg`;
}

/**
 * Format an ISO timestamp as "HH:MM" (today) or "Mmm D, HH:MM" (other day).
 */
export function formatShortTime(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    const now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    if (sameDay) return time;
    const date = d.toLocaleDateString([], { month: 'short', day: 'numeric' });
    return `${date}, ${time}`;
  } catch {
    return iso;
  }
}

/**
 * Format a relative time like "2h ago", "3d ago", "Mar 14".
 */
export function formatRelative(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    const diffMs = Date.now() - d.getTime();
    const mins = Math.round(diffMs / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.round(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.round(hours / 24);
    if (days < 7) return `${days}d ago`;
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  } catch {
    return iso;
  }
}

/**
 * Format a duration string like "00:02:15" → "2:15".
 */
export function formatDuration(raw) {
  if (!raw) return '';
  // Expect "HH:MM:SS" or "MM:SS"
  const parts = String(raw).split(':').map(p => parseInt(p, 10) || 0);
  if (parts.length === 3) {
    const [h, m, s] = parts;
    if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    return `${m}:${String(s).padStart(2, '0')}`;
  }
  return raw;
}

/**
 * Short message body preview (first N chars, collapse whitespace).
 */
export function previewBody(body, n = 60) {
  if (!body) return '';
  const trimmed = String(body).replace(/\s+/g, ' ').trim();
  if (trimmed.length <= n) return trimmed;
  return trimmed.slice(0, n - 1) + '…';
}

/**
 * Icon hint / emoji for a given source app. Returns a short string.
 */
export function appIconEmoji(source) {
  const s = (source || '').toLowerCase();
  if (s.includes('whatsapp')) return '🟢';
  if (s.includes('facebook') || s.includes('messenger')) return '🔵';
  if (s.includes('gmail') || s.includes('mail')) return '✉️';
  if (s.includes('instagram')) return '🟣';
  if (s.includes('telegram')) return '✈️';
  if (s.includes('signal')) return '🔒';
  if (s.includes('sms') || s.includes('message')) return '💬';
  if (s.includes('call')) return '📞';
  return '💬';
}

/**
 * Deterministic per-sender colour palette so each participant in a thread
 * gets a distinct visual identity (bubble background + avatar). The phone
 * owner is always assigned the first slot (blue) so "you" is consistent.
 */
const SENDER_PALETTE = [
  // [bubbleBg, bubbleText, avatarBg, avatarText, label]
  { bubble: 'bg-owl-blue-100', text: 'text-owl-blue-950', avatar: 'bg-owl-blue-500', avatarText: 'text-white', name: 'blue' },
  { bubble: 'bg-emerald-100', text: 'text-emerald-950', avatar: 'bg-emerald-500', avatarText: 'text-white', name: 'emerald' },
  { bubble: 'bg-amber-100', text: 'text-amber-950', avatar: 'bg-amber-500', avatarText: 'text-white', name: 'amber' },
  { bubble: 'bg-purple-100', text: 'text-purple-950', avatar: 'bg-purple-500', avatarText: 'text-white', name: 'purple' },
  { bubble: 'bg-rose-100', text: 'text-rose-950', avatar: 'bg-rose-500', avatarText: 'text-white', name: 'rose' },
  { bubble: 'bg-cyan-100', text: 'text-cyan-950', avatar: 'bg-cyan-500', avatarText: 'text-white', name: 'cyan' },
  { bubble: 'bg-orange-100', text: 'text-orange-950', avatar: 'bg-orange-500', avatarText: 'text-white', name: 'orange' },
  { bubble: 'bg-teal-100', text: 'text-teal-950', avatar: 'bg-teal-500', avatarText: 'text-white', name: 'teal' },
];

/**
 * Hash a string to a stable non-negative integer for deterministic palette
 * indexing.
 */
function _hashKey(key) {
  let h = 0;
  const s = String(key || '');
  for (let i = 0; i < s.length; i += 1) {
    h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

/**
 * Build a `senderKey -> palette` map for a thread. The phone owner (if
 * present) gets palette slot 0 (blue), and remaining participants get
 * deterministic-but-distinct slots based on their key hash.
 *
 * Pass an array of participant objects with at least { key, is_owner }.
 */
export function buildSenderPalette(participants) {
  const map = new Map();
  if (!Array.isArray(participants) || participants.length === 0) return map;
  // Phone owner first
  const owner = participants.find((p) => p?.is_owner);
  const used = new Set();
  if (owner?.key) {
    map.set(owner.key, SENDER_PALETTE[0]);
    used.add(0);
  }
  // Other participants — try their hash slot, fall back to next free slot
  for (const p of participants) {
    if (!p?.key || map.has(p.key)) continue;
    let idx = _hashKey(p.key) % SENDER_PALETTE.length;
    // If slot 0 (owner colour) collides for a non-owner, bump
    if (idx === 0) idx = 1;
    let attempts = 0;
    while (used.has(idx) && attempts < SENDER_PALETTE.length) {
      idx = (idx + 1) % SENDER_PALETTE.length;
      if (idx === 0) idx = 1;
      attempts += 1;
    }
    map.set(p.key, SENDER_PALETTE[idx]);
    used.add(idx);
  }
  return map;
}

/**
 * Standalone helper to get a palette for a single sender key when the
 * caller doesn't have a participant list (e.g. cross-thread feeds).
 */
export function paletteForSenderKey(senderKey, isOwner = false) {
  if (isOwner) return SENDER_PALETTE[0];
  let idx = _hashKey(senderKey) % SENDER_PALETTE.length;
  if (idx === 0) idx = 1;
  return SENDER_PALETTE[idx];
}

/**
 * Two-letter initials for the avatar circle (e.g. "Sender Lemus" → "SL").
 */
export function senderInitials(name) {
  if (!name) return '?';
  const parts = String(name).trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
