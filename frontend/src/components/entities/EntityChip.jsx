import React from 'react';
import { X } from 'lucide-react';
import { entityMeta, entityColorClasses } from './entityUtils';

/**
 * Compact entity chip: icon + name + optional remove button.
 */
export default function EntityChip({
  entity,
  onClick,
  onRemove,
  size = 'sm',
}) {
  if (!entity) return null;
  const meta = entityMeta(entity.entity_type);
  const Icon = meta.icon;
  const cls = entityColorClasses(entity.entity_type);

  const sizeCls =
    size === 'xs'
      ? 'text-[10px] px-1.5 py-0.5 gap-1'
      : size === 'sm'
      ? 'text-xs px-2 py-0.5 gap-1'
      : 'text-sm px-2.5 py-1 gap-1.5';

  return (
    <span
      className={`inline-flex items-center rounded-full border ${cls.pill} ${sizeCls} max-w-[200px] ${
        onClick ? 'cursor-pointer hover:shadow-sm' : ''
      }`}
      onClick={onClick ? (e) => { e.stopPropagation(); onClick(entity); } : undefined}
      title={`${meta.label}: ${entity.name}`}
    >
      <Icon className="w-3 h-3 flex-shrink-0" />
      <span className="truncate">{entity.name}</span>
      {onRemove && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onRemove(entity);
          }}
          className="flex-shrink-0 hover:opacity-70"
        >
          <X className="w-3 h-3" />
        </button>
      )}
    </span>
  );
}
