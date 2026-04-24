import React from 'react';
import { Phone, MessageSquare, Mail } from 'lucide-react';

const TYPES = [
  { key: 'message', label: 'Messages', icon: MessageSquare, color: 'blue' },
  { key: 'call', label: 'Calls', icon: Phone, color: 'emerald' },
  { key: 'email', label: 'Emails', icon: Mail, color: 'amber' },
];

const COLORS = {
  blue: 'bg-owl-blue-100 border-owl-blue-400 text-owl-blue-800',
  emerald: 'bg-emerald-100 border-emerald-400 text-emerald-800',
  amber: 'bg-amber-100 border-amber-400 text-amber-800',
};

/**
 * Simple pill selector for comm types (messages/calls/emails).
 * Uses `active` Set<string> for multi-toggle state.
 */
export default function CommsTypeFilter({ active, onChange }) {
  const toggle = (k) => {
    const next = new Set(active);
    if (next.has(k)) next.delete(k);
    else next.add(k);
    onChange(next);
  };

  return (
    <div className="flex items-center gap-1.5">
      {TYPES.map(({ key, label, icon: Icon, color }) => {
        const on = active.has(key);
        return (
          <button
            key={key}
            onClick={() => toggle(key)}
            className={`flex items-center gap-1 px-2 py-1 rounded-full border text-xs font-medium transition-colors ${
              on
                ? COLORS[color]
                : 'bg-white border-light-300 text-light-500 hover:bg-light-50'
            }`}
          >
            <Icon className="w-3 h-3" />
            {label}
          </button>
        );
      })}
    </div>
  );
}
