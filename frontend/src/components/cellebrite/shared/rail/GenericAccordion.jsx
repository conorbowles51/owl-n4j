import React from 'react';

/**
 * Fallback renderer for selections whose type doesn't have a bespoke
 * renderer yet. Shows the payload as a key/value table so investigators
 * can still see what's there without us shipping a placeholder.
 *
 * This is the only renderer that should NEVER fail — every other
 * accordion can pass `payload` straight here and assume something
 * useful renders.
 */
export default function GenericAccordion({ selection }) {
  const payload = selection?.payload || {};
  const entries = Object.entries(payload).filter(
    ([, v]) => v != null && v !== '' && typeof v !== 'function',
  );
  if (entries.length === 0) {
    return (
      <div className="px-3 py-4 text-xs text-light-500 italic">
        No additional detail available for this {selection?.type || 'item'}.
      </div>
    );
  }
  return (
    <div className="px-3 py-2">
      <table className="w-full text-[11px]">
        <tbody>
          {entries.map(([k, v]) => (
            <tr key={k} className="border-b border-light-100 last:border-0">
              <td className="py-1 pr-2 align-top text-light-500 font-medium whitespace-nowrap">
                {humanise(k)}
              </td>
              <td className="py-1 align-top text-owl-blue-900 break-words">
                {render(v)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function humanise(key) {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function render(v) {
  if (v == null) return '';
  if (Array.isArray(v)) return v.length === 0 ? '—' : v.map(String).join(', ');
  if (typeof v === 'object') {
    try {
      return <code className="text-[10px]">{JSON.stringify(v)}</code>;
    } catch {
      return String(v);
    }
  }
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  return String(v);
}
