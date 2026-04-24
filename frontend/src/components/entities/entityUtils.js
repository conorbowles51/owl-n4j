/**
 * Shared helpers for CaseEntity profile components.
 */

import {
  User, MapPin, Calendar, Smartphone, Building2, Car, Circle,
} from 'lucide-react';

export const ENTITY_TYPES = [
  { key: 'person', label: 'Person', icon: User, color: 'blue' },
  { key: 'address', label: 'Address', icon: MapPin, color: 'emerald' },
  { key: 'event', label: 'Event', icon: Calendar, color: 'amber' },
  { key: 'device', label: 'Device', icon: Smartphone, color: 'purple' },
  { key: 'organisation', label: 'Organisation', icon: Building2, color: 'slate' },
  { key: 'vehicle', label: 'Vehicle', icon: Car, color: 'rose' },
  { key: 'other', label: 'Other', icon: Circle, color: 'gray' },
];

const TYPE_BY_KEY = Object.fromEntries(ENTITY_TYPES.map((t) => [t.key, t]));

export function entityMeta(type) {
  return TYPE_BY_KEY[type] || TYPE_BY_KEY.other;
}

// Tailwind colour classes per entity type
export const COLOR_CLASSES = {
  blue: {
    bg: 'bg-blue-100',
    bgSoft: 'bg-blue-50',
    text: 'text-blue-800',
    border: 'border-blue-300',
    icon: 'text-blue-600',
    pill: 'bg-blue-100 text-blue-800 border-blue-300',
  },
  emerald: {
    bg: 'bg-emerald-100',
    bgSoft: 'bg-emerald-50',
    text: 'text-emerald-800',
    border: 'border-emerald-300',
    icon: 'text-emerald-600',
    pill: 'bg-emerald-100 text-emerald-800 border-emerald-300',
  },
  amber: {
    bg: 'bg-amber-100',
    bgSoft: 'bg-amber-50',
    text: 'text-amber-800',
    border: 'border-amber-300',
    icon: 'text-amber-600',
    pill: 'bg-amber-100 text-amber-800 border-amber-300',
  },
  purple: {
    bg: 'bg-purple-100',
    bgSoft: 'bg-purple-50',
    text: 'text-purple-800',
    border: 'border-purple-300',
    icon: 'text-purple-600',
    pill: 'bg-purple-100 text-purple-800 border-purple-300',
  },
  slate: {
    bg: 'bg-slate-100',
    bgSoft: 'bg-slate-50',
    text: 'text-slate-800',
    border: 'border-slate-300',
    icon: 'text-slate-600',
    pill: 'bg-slate-100 text-slate-800 border-slate-300',
  },
  rose: {
    bg: 'bg-rose-100',
    bgSoft: 'bg-rose-50',
    text: 'text-rose-800',
    border: 'border-rose-300',
    icon: 'text-rose-600',
    pill: 'bg-rose-100 text-rose-800 border-rose-300',
  },
  gray: {
    bg: 'bg-gray-100',
    bgSoft: 'bg-gray-50',
    text: 'text-gray-800',
    border: 'border-gray-300',
    icon: 'text-gray-600',
    pill: 'bg-gray-100 text-gray-800 border-gray-300',
  },
};

export function entityColorClasses(type) {
  return COLOR_CLASSES[entityMeta(type).color] || COLOR_CLASSES.gray;
}
