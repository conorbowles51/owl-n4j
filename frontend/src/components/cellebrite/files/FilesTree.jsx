import React, { useState } from 'react';
import { ChevronRight, ChevronDown, Folder, Loader2 } from 'lucide-react';
import { GROUP_BY_OPTIONS, CATEGORY_ICONS, categoryIcon, categoryColor } from './filesUtils';

/**
 * Left-pane tree with a group-by switcher. Each leaf click emits a filter
 * object that the parent uses to drive FilesList.
 *
 * Props:
 *   tree                 — server response from /cellebrite/files/tree
 *   groupBy              — current group-by mode
 *   onGroupByChange      — (mode) => void
 *   selectedKey          — currently-active leaf key
 *   onSelect             — (node) => void   // node has {key,label,filter}
 *   loading              — bool
 *   total                — total file count (root)
 */
export default function FilesTree({
  tree,
  groupBy,
  onGroupByChange,
  selectedKey,
  onSelect,
  loading = false,
  total = 0,
}) {
  return (
    <div className="w-60 flex-shrink-0 border-r border-light-200 bg-light-50 flex flex-col min-h-0">
      {/* Group-by selector */}
      <div className="p-2 border-b border-light-200 bg-white">
        <label className="text-[10px] text-light-500 font-medium">Group by</label>
        <select
          value={groupBy}
          onChange={(e) => onGroupByChange?.(e.target.value)}
          className="w-full mt-0.5 px-1.5 py-1 text-xs border border-light-300 rounded bg-white"
        >
          {GROUP_BY_OPTIONS.map((o) => (
            <option key={o.key} value={o.key}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* Root row (shows "All files") */}
        <button
          onClick={() => onSelect?.({ key: null, label: 'All files', filter: {} })}
          className={`w-full flex items-center gap-1.5 px-2 py-1.5 text-left text-xs border-b border-light-100 ${
            !selectedKey ? 'bg-owl-blue-50 font-semibold' : 'hover:bg-light-100'
          }`}
        >
          <Folder className="w-3.5 h-3.5 text-owl-blue-600" />
          <span className="flex-1">All files</span>
          <span className="text-[10px] text-light-500">{total.toLocaleString()}</span>
        </button>

        {loading ? (
          <div className="flex items-center justify-center py-4">
            <Loader2 className="w-4 h-4 animate-spin text-light-400" />
          </div>
        ) : !tree?.root?.children?.length ? (
          <div className="p-3 text-[11px] text-light-500 italic">No files to group.</div>
        ) : (
          <TreeNodes
            nodes={tree.root.children}
            depth={0}
            groupBy={groupBy}
            selectedKey={selectedKey}
            onSelect={onSelect}
          />
        )}
      </div>
    </div>
  );
}

function TreeNodes({ nodes, depth, groupBy, selectedKey, onSelect }) {
  return (
    <ul>
      {nodes.map((n) => (
        <TreeNode
          key={n.key || n.label}
          node={n}
          depth={depth}
          groupBy={groupBy}
          selectedKey={selectedKey}
          onSelect={onSelect}
        />
      ))}
    </ul>
  );
}

function TreeNode({ node, depth, groupBy, selectedKey, onSelect }) {
  const hasChildren = (node.children || []).length > 0;
  const [open, setOpen] = useState(depth === 0);
  const isSelected = selectedKey && selectedKey === node.key;

  // Icon/colour hint per mode
  let Icon = Folder;
  let iconColor = '#64748b';
  if (groupBy === 'category' && CATEGORY_ICONS[node.label]) {
    Icon = categoryIcon(node.label);
    iconColor = categoryColor(node.label);
  }

  return (
    <li>
      <div
        className={`flex items-center gap-1 px-2 py-1 cursor-pointer text-xs ${
          isSelected ? 'bg-owl-blue-50 font-medium' : 'hover:bg-light-100'
        }`}
        style={{ paddingLeft: 8 + depth * 10 }}
        onClick={() => onSelect?.(node)}
      >
        {hasChildren ? (
          <button
            onClick={(e) => {
              e.stopPropagation();
              setOpen(!open);
            }}
            className="p-0 flex-shrink-0 text-light-500"
          >
            {open ? (
              <ChevronDown className="w-3 h-3" />
            ) : (
              <ChevronRight className="w-3 h-3" />
            )}
          </button>
        ) : (
          <span className="w-3 flex-shrink-0" />
        )}
        <Icon className="w-3.5 h-3.5 flex-shrink-0" style={{ color: iconColor }} />
        <span className="flex-1 truncate text-light-900">{node.label}</span>
        <span className="text-[10px] text-light-500">{Number(node.count || 0).toLocaleString()}</span>
      </div>
      {open && hasChildren && (
        <TreeNodes
          nodes={node.children}
          depth={depth + 1}
          groupBy={groupBy}
          selectedKey={selectedKey}
          onSelect={onSelect}
        />
      )}
    </li>
  );
}
