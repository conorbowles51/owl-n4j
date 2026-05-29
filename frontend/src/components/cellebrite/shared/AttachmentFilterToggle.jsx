import React from 'react';
import { Paperclip } from 'lucide-react';

/**
 * Compact "Has attachment" filter toggle, shared across every messaging
 * view. Controlled: pass `value` (bool) + `onChange(next)`.
 *
 * The views apply it by injecting `has: 'attachment'` into the parsed
 * cellebriteSearch query (so it composes with text search + other operators),
 * or — for thread-level lists — by filtering on the thread's has_attachments
 * flag. This component is purely the button.
 */
export default function AttachmentFilterToggle({ value, onChange, className = '', label = 'Has attachment' }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!value)}
      aria-pressed={value}
      title={value ? 'Showing only items with attachments — click to clear' : 'Show only items with attachments'}
      className={`inline-flex items-center gap-1 px-2 py-1 rounded border text-[11px] transition-colors ${
        value
          ? 'border-owl-blue-400 bg-owl-blue-50 text-owl-blue-800'
          : 'border-light-300 bg-white text-light-600 hover:bg-light-100'
      } ${className}`}
    >
      <Paperclip className="w-3 h-3" />
      <span>{label}</span>
    </button>
  );
}
