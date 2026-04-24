/**
 * Shared helpers for the Cellebrite Files Explorer.
 */

import {
  Image as ImageIcon,
  Music,
  Film,
  FileText,
  File,
  Folder,
  MessageSquare,
  Phone,
  Mail,
  User,
  Globe,
} from 'lucide-react';

export const CATEGORY_ICONS = {
  Image: ImageIcon,
  Audio: Music,
  Video: Film,
  Text: FileText,
  Other: File,
};

export const CATEGORY_COLORS = {
  Image: '#06b6d4',
  Audio: '#10b981',
  Video: '#8b5cf6',
  Text: '#f59e0b',
  Other: '#64748b',
};

export const PARENT_LABEL_ICONS = {
  Person: User,
  Contact: User,
  Communication: MessageSquare,
  PhoneCall: Phone,
  Email: Mail,
  VisitedPage: Globe,
  Unlinked: Folder,
};

export const GROUP_BY_OPTIONS = [
  { key: 'category', label: 'Category (Image / Audio / Video / Text)' },
  { key: 'parent', label: 'Parent entity (Chat / Call / Email / …)' },
  { key: 'app', label: 'Source app (WhatsApp / Gmail / …)' },
  { key: 'path', label: 'Device path (DCIM / WhatsApp / …)' },
];

/**
 * Human-readable file size.
 */
export function formatSize(bytes) {
  if (bytes == null || isNaN(bytes)) return '';
  const n = Number(bytes);
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

/**
 * Build the evidence file URL.
 */
export function evidenceUrl(evidenceId) {
  return `/api/evidence/${encodeURIComponent(evidenceId)}/file`;
}

/**
 * Build the first video-frame thumbnail URL.
 */
export function videoFrameUrl(evidenceId) {
  return `/api/evidence/${encodeURIComponent(evidenceId)}/frames/frame_0001.jpg`;
}

export function categoryColor(category) {
  return CATEGORY_COLORS[category] || CATEGORY_COLORS.Other;
}

export function categoryIcon(category) {
  return CATEGORY_ICONS[category] || CATEGORY_ICONS.Other;
}
