import { useState } from "react"
import { ChevronDown, ChevronRight, Folder, Loader2 } from "lucide-react"

import { cn } from "@/lib/cn"

import type { FileTreeNode, FileTreeResponse } from "../../types"
import { compactNumber } from "../shared/cellebrite-format"
import {
  GROUP_BY_OPTIONS,
  type FileTreeSelection,
  type FilesGroupBy,
  CATEGORY_ICONS,
  PARENT_ICONS,
  categoryColor,
  treeNodeKey,
  treeSelectionFromNode,
} from "./filesUtils"

export function FilesTree({
  tree,
  groupBy,
  selectedKey,
  loading,
  onGroupByChange,
  onSelect,
}: {
  tree?: FileTreeResponse
  groupBy: FilesGroupBy
  selectedKey: string | null
  loading: boolean
  onGroupByChange: (groupBy: FilesGroupBy) => void
  onSelect: (selection: FileTreeSelection) => void
}) {
  const rootCount = tree?.root?.count ?? 0

  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-border bg-muted/20">
      <div className="border-b border-border bg-card p-2">
        <label className="text-[10px] font-medium uppercase text-muted-foreground">Group by</label>
        <select
          value={groupBy}
          onChange={(event) => onGroupByChange(event.target.value as FilesGroupBy)}
          className="mt-1 h-8 w-full rounded-md border border-border bg-background px-2 text-xs"
        >
          {GROUP_BY_OPTIONS.map((option) => (
            <option key={option.key} value={option.key}>
              {option.label}
            </option>
          ))}
        </select>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <button
          type="button"
          onClick={() => onSelect({ key: null, label: "All files", filter: {} })}
          className={cn(
            "flex w-full items-center gap-1.5 border-b border-border px-2 py-2 text-left text-xs hover:bg-muted",
            !selectedKey && "bg-amber-500/10 font-semibold"
          )}
        >
          <Folder className="size-3.5 text-amber-500" />
          <span className="min-w-0 flex-1 truncate">All files</span>
          <span className="text-[10px] text-muted-foreground">{compactNumber(rootCount)}</span>
        </button>
        {loading ? (
          <div className="flex items-center justify-center py-5">
            <Loader2 className="size-4 animate-spin text-muted-foreground" />
          </div>
        ) : !tree?.root?.children?.length ? (
          <div className="p-3 text-[11px] text-muted-foreground">No files to group.</div>
        ) : (
          <TreeNodes nodes={tree.root.children} depth={0} groupBy={groupBy} selectedKey={selectedKey} onSelect={onSelect} />
        )}
      </div>
    </aside>
  )
}

function TreeNodes({
  nodes,
  depth,
  groupBy,
  selectedKey,
  onSelect,
}: {
  nodes: FileTreeNode[]
  depth: number
  groupBy: FilesGroupBy
  selectedKey: string | null
  onSelect: (selection: FileTreeSelection) => void
}) {
  return (
    <ul>
      {nodes.map((node) => (
        <TreeNode
          key={treeNodeKey(node)}
          node={node}
          depth={depth}
          groupBy={groupBy}
          selectedKey={selectedKey}
          onSelect={onSelect}
        />
      ))}
    </ul>
  )
}

function TreeNode({
  node,
  depth,
  groupBy,
  selectedKey,
  onSelect,
}: {
  node: FileTreeNode
  depth: number
  groupBy: FilesGroupBy
  selectedKey: string | null
  onSelect: (selection: FileTreeSelection) => void
}) {
  const children = node.children ?? []
  const hasChildren = children.length > 0
  const [open, setOpen] = useState(depth === 0)
  const key = treeNodeKey(node)
  const selected = selectedKey === key
  const Icon =
    groupBy === "category"
      ? (CATEGORY_ICONS[node.label as keyof typeof CATEGORY_ICONS] ?? CATEGORY_ICONS.Other)
      : groupBy === "parent"
        ? (PARENT_ICONS[node.label as keyof typeof PARENT_ICONS] ?? Folder)
        : Folder
  const color = groupBy === "category" ? categoryColor(node.label) : "#64748b"

  return (
    <li>
      <div
        className={cn("flex cursor-pointer items-center gap-1 px-2 py-1 text-xs hover:bg-muted", selected && "bg-amber-500/10 font-medium")}
        style={{ paddingLeft: 8 + depth * 10 }}
        onClick={() => onSelect(treeSelectionFromNode(node))}
      >
        {hasChildren ? (
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation()
              setOpen((current) => !current)
            }}
            className="shrink-0 text-muted-foreground"
            title={open ? "Collapse" : "Expand"}
          >
            {open ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}
          </button>
        ) : (
          <span className="w-3 shrink-0" />
        )}
        <Icon className="size-3.5 shrink-0" style={{ color }} />
        <span className="min-w-0 flex-1 truncate">{node.label}</span>
        <span className="text-[10px] text-muted-foreground">{compactNumber(node.count)}</span>
      </div>
      {open && hasChildren ? (
        <TreeNodes nodes={children} depth={depth + 1} groupBy={groupBy} selectedKey={selectedKey} onSelect={onSelect} />
      ) : null}
    </li>
  )
}
