import React from 'react';
import { appIconEmoji } from './commsUtils';

/**
 * Source-app filter chips. When `active` is empty → "All" is highlighted and
 * every app is included. Otherwise only the listed apps pass.
 *
 * Props:
 *  - apps: array of { source_app, thread_type, count }
 *  - active: Set<string> of selected source_app names
 *  - onChange: (Set<string>) => void
 */
export default function CommsAppFilter({ apps = [], active, onChange }) {
  // Aggregate counts by source_app across thread_types
  const byApp = new Map();
  for (const a of apps) {
    const key = a.source_app;
    if (!key) continue;
    const cur = byApp.get(key) || { source_app: key, count: 0 };
    cur.count += a.count || 0;
    byApp.set(key, cur);
  }
  const list = [...byApp.values()].sort((a, b) => b.count - a.count);

  if (list.length === 0) return null;

  const allSelected = active.size === 0;

  const toggle = (name) => {
    const next = new Set(active);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    onChange(next);
  };

  const selectAll = () => onChange(new Set());

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <button
        onClick={selectAll}
        className={`flex items-center gap-1 px-2 py-1 rounded-full border text-xs font-medium transition-colors ${
          allSelected
            ? 'bg-light-200 border-light-400 text-light-900'
            : 'bg-white border-light-300 text-light-500 hover:bg-light-50'
        }`}
      >
        All apps
      </button>
      {list.map(({ source_app, count }) => {
        const on = active.has(source_app);
        return (
          <button
            key={source_app}
            onClick={() => toggle(source_app)}
            className={`flex items-center gap-1 px-2 py-1 rounded-full border text-xs font-medium transition-colors ${
              on
                ? 'bg-purple-100 border-purple-400 text-purple-800'
                : 'bg-white border-light-300 text-light-600 hover:bg-light-50'
            }`}
            title={`${count.toLocaleString()} items`}
          >
            <span>{appIconEmoji(source_app)}</span>
            <span className="truncate max-w-[140px]">{source_app}</span>
            <span className="text-[10px] text-light-500">({count.toLocaleString()})</span>
          </button>
        );
      })}
    </div>
  );
}
