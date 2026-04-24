import React, { useRef, useEffect } from 'react';
import { Loader2, LayoutGrid, List as ListIcon } from 'lucide-react';
import FileThumbnail from './FileThumbnail';

/**
 * Middle pane: grid or list of files. Keeps it simple (no virtualisation yet —
 * server limit is 500). Supports click-to-open, click-checkbox-to-toggle-select,
 * shift+click range selection.
 *
 * Props:
 *   files
 *   total
 *   loading
 *   selectedIds        — Set<string>
 *   onToggleSelect     — (id) => void
 *   onRangeSelect      — (startIdx, endIdx) => void
 *   onOpen             — (file) => void
 *   layout, onLayoutChange
 */
export default function FilesList({
  files = [],
  total = 0,
  loading = false,
  selectedIds,
  onToggleSelect,
  onRangeSelect,
  onOpen,
  layout = 'grid',
  onLayoutChange,
}) {
  const lastSelectedIndex = useRef(null);

  const handleToggle = (file, idx, event) => {
    if (event?.shiftKey && lastSelectedIndex.current != null) {
      onRangeSelect?.(lastSelectedIndex.current, idx);
    } else {
      onToggleSelect?.(file.id);
    }
    lastSelectedIndex.current = idx;
  };

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-light-200 bg-light-50">
        <div className="text-xs text-light-600">
          {loading ? 'Loading…' : `${files.length.toLocaleString()} of ${total.toLocaleString()} files`}
          {selectedIds?.size > 0 && (
            <span className="ml-2 text-owl-blue-700 font-medium">
              · {selectedIds.size} selected
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => onLayoutChange?.('grid')}
            className={`p-1 rounded ${layout === 'grid' ? 'bg-owl-blue-100 text-owl-blue-700' : 'text-light-500 hover:bg-light-100'}`}
            title="Grid view"
          >
            <LayoutGrid className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => onLayoutChange?.('list')}
            className={`p-1 rounded ${layout === 'list' ? 'bg-owl-blue-100 text-owl-blue-700' : 'text-light-500 hover:bg-light-100'}`}
            title="List view"
          >
            <ListIcon className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading && files.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="w-5 h-5 animate-spin text-light-400" />
          </div>
        ) : files.length === 0 ? (
          <div className="flex items-center justify-center h-full text-sm text-light-500 italic">
            No files match the current filters.
          </div>
        ) : layout === 'grid' ? (
          <div
            className="p-3 grid gap-2"
            style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))' }}
          >
            {files.map((f, i) => (
              <FileThumbnail
                key={f.id}
                file={f}
                selected={selectedIds?.has(f.id)}
                onToggleSelect={() => handleToggle(f, i, { shiftKey: false })}
                onOpen={() => onOpen?.(f, i)}
                layout="grid"
              />
            ))}
          </div>
        ) : (
          <div>
            {files.map((f, i) => (
              <FileThumbnail
                key={f.id}
                file={f}
                selected={selectedIds?.has(f.id)}
                onToggleSelect={() => handleToggle(f, i, { shiftKey: false })}
                onOpen={() => onOpen?.(f, i)}
                layout="list"
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
