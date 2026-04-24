import React, { useState } from 'react';
import { CheckCircle2, Pin, Tag, Users } from 'lucide-react';
import { evidenceUrl, videoFrameUrl, categoryIcon, categoryColor, formatSize } from './filesUtils';

/**
 * A selectable thumbnail for a single Cellebrite file. Supports grid or list
 * layout via the `layout` prop.
 */
export default function FileThumbnail({
  file,
  selected = false,
  onToggleSelect,
  onOpen,
  layout = 'grid',
}) {
  const [imgError, setImgError] = useState(false);
  const cat = file.cellebrite_category || 'Other';
  const Icon = categoryIcon(cat);
  const color = categoryColor(cat);

  const url = file.id ? evidenceUrl(file.id) : null;
  const thumbUrl =
    cat === 'Image' && url
      ? url
      : cat === 'Video' && file.id
      ? videoFrameUrl(file.id)
      : null;

  const hasTags = (file.tags || []).length > 0;
  const hasEntities = (file.linked_entity_ids || []).length > 0;

  if (layout === 'list') {
    return (
      <button
        onClick={onOpen}
        className={`w-full flex items-center gap-2 px-2 py-1.5 text-left border-b border-light-100 hover:bg-light-50 ${
          selected ? 'bg-owl-blue-50' : ''
        }`}
      >
        <input
          type="checkbox"
          checked={selected}
          onChange={(e) => {
            e.stopPropagation();
            onToggleSelect?.();
          }}
          onClick={(e) => e.stopPropagation()}
          className="flex-shrink-0"
        />
        <div className="w-10 h-10 bg-light-100 rounded overflow-hidden flex items-center justify-center flex-shrink-0">
          {thumbUrl && !imgError ? (
            <img
              src={thumbUrl}
              alt=""
              className="w-full h-full object-cover"
              loading="lazy"
              onError={() => setImgError(true)}
            />
          ) : (
            <Icon className="w-4 h-4" style={{ color }} />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-xs font-medium text-light-900 truncate">
            {file.original_filename || file.id}
          </div>
          <div className="text-[10px] text-light-500 flex items-center gap-2">
            <span>{cat}</span>
            <span>·</span>
            <span>{formatSize(file.size)}</span>
            {file.parent?.label && (
              <>
                <span>·</span>
                <span className="truncate">
                  {file.parent.label}
                  {file.parent.source_app ? ` · ${file.parent.source_app}` : ''}
                </span>
              </>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          {file.is_relevant && <CheckCircle2 className="w-3 h-3 text-emerald-600" title="Marked relevant" />}
          {hasTags && <Tag className="w-3 h-3 text-amber-600" title={(file.tags || []).join(', ')} />}
          {hasEntities && <Users className="w-3 h-3 text-owl-blue-600" title={`${file.linked_entity_ids.length} linked entities`} />}
        </div>
      </button>
    );
  }

  // Grid layout
  return (
    <button
      onClick={onOpen}
      className={`relative group aspect-square border rounded overflow-hidden bg-light-50 text-left ${
        selected ? 'border-owl-blue-500 ring-2 ring-owl-blue-300' : 'border-light-200 hover:border-owl-blue-300'
      }`}
      title={file.original_filename}
    >
      <div className="absolute inset-0 flex items-center justify-center bg-light-100">
        {thumbUrl && !imgError ? (
          <img
            src={thumbUrl}
            alt={file.original_filename}
            className="w-full h-full object-cover"
            loading="lazy"
            onError={() => setImgError(true)}
          />
        ) : (
          <Icon className="w-8 h-8" style={{ color }} />
        )}
      </div>

      {/* Overlay: filename + badges */}
      <div className="absolute left-0 right-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent text-white text-[10px] p-1.5">
        <div className="truncate font-medium">{file.original_filename || file.id}</div>
        <div className="text-[9px] opacity-80">{formatSize(file.size)}</div>
      </div>

      {/* Select checkbox */}
      <label
        onClick={(e) => e.stopPropagation()}
        className="absolute top-1 left-1 bg-white/90 rounded px-1 py-0.5 text-[10px]"
      >
        <input
          type="checkbox"
          checked={selected}
          onChange={() => onToggleSelect?.()}
          className="w-3 h-3"
        />
      </label>

      {/* Status badges */}
      <div className="absolute top-1 right-1 flex items-center gap-0.5">
        {file.is_relevant && (
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 drop-shadow" title="Marked relevant" />
        )}
        {hasTags && <Tag className="w-3.5 h-3.5 text-amber-300 drop-shadow" />}
        {hasEntities && <Users className="w-3.5 h-3.5 text-owl-blue-300 drop-shadow" />}
      </div>
    </button>
  );
}
