import { ContextMenu, ContextMenuContent, ContextMenuItem, ContextMenuSeparator, ContextMenuTrigger } from "@/components/ui/context-menu"
import { Expand, EyeOff, Pin, Pencil, GitMerge, Route, Copy, Trash2 } from "lucide-react"

interface GraphContextMenuProps {
  children: React.ReactNode
  nodeKey?: string
  nodeLabel?: string
  onExpand?: (key: string) => void
  onHide?: (key: string) => void
  onPin?: (key: string) => void
  onEdit?: (key: string) => void
  onMerge?: (key: string) => void
  onFindPaths?: (key: string) => void
  onCopyDetails?: (key: string) => void
  onDelete?: (key: string) => void
  canEdit?: boolean
}

export function GraphContextMenu({
  children,
  nodeKey,
  nodeLabel,
  onExpand,
  onHide,
  onPin,
  onEdit,
  onMerge,
  onFindPaths,
  onCopyDetails,
  onDelete,
  canEdit = true,
}: GraphContextMenuProps) {
  if (!nodeKey) return <>{children}</>

  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>{children}</ContextMenuTrigger>
      <ContextMenuContent className="w-48">
        <div className="px-2 py-1.5 text-xs font-medium text-muted-foreground truncate">
          {nodeLabel ?? nodeKey}
        </div>
        <ContextMenuSeparator />
        <ContextMenuItem onClick={() => onExpand?.(nodeKey)}>
          <Expand className="mr-2 size-3.5" />
          Expand Node
        </ContextMenuItem>
        <ContextMenuItem onClick={() => onHide?.(nodeKey)}>
          <EyeOff className="mr-2 size-3.5" />
          Hide Node
        </ContextMenuItem>
        <ContextMenuItem onClick={() => onPin?.(nodeKey)}>
          <Pin className="mr-2 size-3.5" />
          Pin Node
        </ContextMenuItem>
        <ContextMenuSeparator />
        {canEdit && (
          <>
            <ContextMenuItem onClick={() => onEdit?.(nodeKey)}>
              <Pencil className="mr-2 size-3.5" />
              Edit Entity
            </ContextMenuItem>
            <ContextMenuItem onClick={() => onMerge?.(nodeKey)}>
              <GitMerge className="mr-2 size-3.5" />
              Merge Entities
            </ContextMenuItem>
          </>
        )}
        <ContextMenuItem onClick={() => onFindPaths?.(nodeKey)}>
          <Route className="mr-2 size-3.5" />
          Find Paths
        </ContextMenuItem>
        <ContextMenuSeparator />
        <ContextMenuItem onClick={() => onCopyDetails?.(nodeKey)}>
          <Copy className="mr-2 size-3.5" />
          Copy Details
        </ContextMenuItem>
        {canEdit && (
          <ContextMenuItem
            className="text-red-400 focus:text-red-400"
            onClick={() => onDelete?.(nodeKey)}
          >
            <Trash2 className="mr-2 size-3.5" />
            Delete
          </ContextMenuItem>
        )}
      </ContextMenuContent>
    </ContextMenu>
  )
}
