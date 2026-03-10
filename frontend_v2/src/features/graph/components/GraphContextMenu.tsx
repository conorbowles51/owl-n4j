import { useEffect, useRef } from "react"
import {
  Expand,
  EyeOff,
  Pin,
  PinOff,
  Pencil,
  GitMerge,
  Copy,
  Trash2,
  Eye,
  Network,
  Sparkles,
} from "lucide-react"
import { useGraphStore } from "@/stores/graph.store"

interface GraphContextMenuProps {
  onExpand?: (key: string) => void
  onEdit?: (key: string) => void
  onDelete?: (key: string) => void
  onShowDetail?: (key: string) => void
  onAnalyzeRelationships?: (key: string) => void
  onMergeSelected?: () => void
}

export function GraphContextMenu({
  onExpand,
  onEdit,
  onDelete,
  onShowDetail,
  onAnalyzeRelationships,
  onMergeSelected,
}: GraphContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null)
  const {
    contextMenu,
    closeContextMenu,
    hideNode,
    togglePin,
    pinnedNodeKeys,
    selectedNodeKeys,
    addToSubgraph,
  } = useGraphStore()

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        closeContextMenu()
      }
    }
    if (contextMenu) {
      document.addEventListener("mousedown", handler)
      return () => document.removeEventListener("mousedown", handler)
    }
  }, [contextMenu, closeContextMenu])

  if (!contextMenu) return null

  const { x, y, nodeKey, nodeLabel } = contextMenu
  const isPinned = pinnedNodeKeys.has(nodeKey)
  const multiSelected = selectedNodeKeys.size > 1

  type MenuItem =
    | { separator: true }
    | { icon: typeof Eye; label: string; onClick: () => void; className?: string }

  const items: MenuItem[] = [
    {
      icon: Eye,
      label: "Show Details",
      onClick: () => { onShowDetail?.(nodeKey); closeContextMenu() },
    },
    {
      icon: Expand,
      label: "Expand Connections",
      onClick: () => { onExpand?.(nodeKey); closeContextMenu() },
    },
    {
      icon: Sparkles,
      label: "Relationship Analysis",
      onClick: () => { onAnalyzeRelationships?.(nodeKey); closeContextMenu() },
    },
    { separator: true },
    {
      icon: Network,
      label: "Add to Spotlight",
      onClick: () => { addToSubgraph([nodeKey]); closeContextMenu() },
    },
    {
      icon: isPinned ? PinOff : Pin,
      label: isPinned ? "Unpin Node" : "Pin Node",
      onClick: () => { togglePin(nodeKey); closeContextMenu() },
    },
    {
      icon: EyeOff,
      label: "Hide Node",
      onClick: () => { hideNode(nodeKey); closeContextMenu() },
    },
    { separator: true },
    {
      icon: Pencil,
      label: "Edit Node",
      onClick: () => { onEdit?.(nodeKey); closeContextMenu() },
    },
    {
      icon: Copy,
      label: "Copy Key",
      onClick: () => { navigator.clipboard.writeText(nodeKey); closeContextMenu() },
    },
    ...(multiSelected
      ? [
          {
            icon: GitMerge,
            label: "Merge Selected",
            onClick: () => { onMergeSelected?.(); closeContextMenu() },
          } as MenuItem,
        ]
      : []),
    { separator: true },
    {
      icon: Trash2,
      label: "Delete Node",
      className: "text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300",
      onClick: () => { onDelete?.(nodeKey); closeContextMenu() },
    },
  ]

  return (
    <div
      ref={menuRef}
      className="fixed z-50 min-w-[180px] rounded-lg border border-border bg-popover py-1 shadow-xl"
      style={{ left: x, top: y }}
    >
      <div className="px-3 py-1.5 text-xs font-medium text-muted-foreground truncate max-w-[200px]">
        {nodeLabel}
      </div>
      <div className="mx-1 border-t border-border" />
      {items.map((item, i) => {
        if ("separator" in item) {
          return <div key={i} className="mx-1 my-0.5 border-t border-border" />
        }
        const Icon = item.icon
        return (
          <button
            key={i}
            className={`flex w-full items-center gap-2 px-3 py-1.5 text-xs text-popover-foreground hover:bg-muted ${item.className ?? ""}`}
            onClick={item.onClick}
          >
            <Icon className="size-3.5" />
            {item.label}
          </button>
        )
      })}
    </div>
  )
}
