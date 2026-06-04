import React, { useRef } from 'react';
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
 *   hasMore            — bool, more rows exist beyond the loaded slice
 *   loadingMore        — bool, the next page is being fetched
 *   onLoadMore         — () => void, fetch + append the next offset page
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
  hasMore = false,
  loadingMore = false,
  onLoadMore,
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

        {/* Load more — appends the next offset page. Only shown once the
            first page is rendered and more rows exist beyond it. */}
        {files.length > 0 && hasMore && (
          <div className="flex flex-col items-center gap-1 py-4 border-t border-light-200">
            <button
              type="button"
              onClick={onLoadMore}
              disabled={loadingMore}
              className="px-4 py-1.5 rounded bg-owl-blue-600 text-white text-xs font-medium hover:bg-owl-blue-700 disabled:opacity-60 disabled:cursor-default inline-flex items-center gap-1.5"
            >
              {loadingMore && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              {loadingMore ? 'Loading…' : 'Load more'}
            </button>
            <span className="text-[11px] text-light-500">
              Showing {files.length.toLocaleString()} of {total.toLocaleString()}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
