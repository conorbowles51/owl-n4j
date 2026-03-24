import {
  ChevronRight,
  Folder,
  FolderOpen,
  FolderPlus,
  Settings,
  Play,
  Pencil,
  Trash2,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import {
  ContextMenu,
  ContextMenuTrigger,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
} from "@/components/ui/context-menu"
import { cn } from "@/lib/cn"
import { useEvidenceStore } from "../evidence.store"
import { useRenameFolder } from "../hooks/use-folder-mutations"
import { useProcessFolder } from "../hooks/use-process-folder"
import { toast } from "sonner"
import type { FolderTreeNode as FolderTreeNodeType } from "@/types/evidence.types"

interface FolderTreeNodeProps {
  node: FolderTreeNodeType
  depth: number
  caseId: string
  onCreateFolder: (parentId: string | null) => void
  onDeleteFolder: (id: string, name: string, fileCount: number) => void
}

export function FolderTreeNode({
  node,
  depth,
  caseId,
  onCreateFolder,
  onDeleteFolder,
}: FolderTreeNodeProps) {
  const {
    currentFolderId,
    setCurrentFolder,
    expandedFolderIds,
    toggleFolderExpand,
    expandFolder,
  } = useEvidenceStore()

  const renameMutation = useRenameFolder(caseId)
  const processMutation = useProcessFolder(caseId)

  const isExpanded = expandedFolderIds.has(node.id)
  const isActive = currentFolderId === node.id
  const hasChildren = node.children.length > 0

  const handleClick = () => {
    setCurrentFolder(node.id)
    expandFolder(node.id)
  }

  const handleChevronClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    toggleFolderExpand(node.id)
  }

  const handleRename = () => {
    const newName = window.prompt("Rename folder", node.name)
    if (newName && newName.trim() && newName.trim() !== node.name) {
      renameMutation.mutate(
        { folderId: node.id, name: newName.trim() },
        {
          onSuccess: () => toast.success(`Renamed to "${newName.trim()}"`),
          onError: (err) => toast.error(err.message),
        }
      )
    }
  }

  const handleProcess = () => {
    processMutation.mutate(
      { folderId: node.id, recursive: true },
      {
        onSuccess: (data) => {
          toast.success(`Processing ${data.file_count} files from "${node.name}"`)
          useEvidenceStore.getState().openSidebarTo("processing")
        },
        onError: (err) => toast.error(err.message),
      }
    )
  }

  const paddingLeft = depth * 12 + 4

  return (
    <div>
      <ContextMenu>
        <ContextMenuTrigger asChild>
          <button
            onClick={handleClick}
            className={cn(
              "group flex w-full items-center gap-1 rounded-md py-1 pr-2 text-sm transition-colors",
              isActive
                ? "bg-amber-500/10 text-amber-500 font-medium"
                : "text-foreground/80 hover:bg-muted hover:text-foreground"
            )}
            style={{ paddingLeft: `${paddingLeft}px` }}
          >
            {/* Chevron */}
            <span
              onClick={handleChevronClick}
              className={cn(
                "flex size-4 shrink-0 items-center justify-center rounded transition-transform",
                hasChildren ? "visible" : "invisible"
              )}
            >
              <ChevronRight
                className={cn(
                  "size-3 text-muted-foreground transition-transform duration-200",
                  isExpanded && "rotate-90"
                )}
              />
            </span>

            {/* Folder icon */}
            {isExpanded ? (
              <FolderOpen
                className={cn(
                  "size-4 shrink-0",
                  node.has_profile ? "text-amber-500" : "text-slate-400"
                )}
              />
            ) : (
              <Folder
                className={cn(
                  "size-4 shrink-0",
                  node.has_profile ? "text-amber-500" : "text-slate-400"
                )}
              />
            )}

            {/* Name */}
            <span className="truncate text-xs">{node.name}</span>

            {/* File count badge */}
            {node.file_count > 0 && (
              <Badge
                variant="secondary"
                className="ml-auto shrink-0 text-[9px] px-1 py-0 h-4"
              >
                {node.file_count}
              </Badge>
            )}
          </button>
        </ContextMenuTrigger>

        <ContextMenuContent>
          <ContextMenuItem onClick={() => onCreateFolder(node.id)}>
            <FolderPlus className="size-4" />
            New Subfolder
          </ContextMenuItem>
          <ContextMenuItem onClick={() => {/* TODO: open profile dialog */}}>
            <Settings className="size-4" />
            Set Profile
          </ContextMenuItem>
          <ContextMenuItem onClick={handleProcess}>
            <Play className="size-4" />
            Process All
          </ContextMenuItem>
          <ContextMenuSeparator />
          <ContextMenuItem onClick={handleRename}>
            <Pencil className="size-4" />
            Rename
          </ContextMenuItem>
          <ContextMenuItem
            variant="destructive"
            onClick={() => onDeleteFolder(node.id, node.name, node.file_count)}
          >
            <Trash2 className="size-4" />
            Delete
          </ContextMenuItem>
        </ContextMenuContent>
      </ContextMenu>

      {/* Recursive children */}
      {isExpanded && hasChildren && (
        <div>
          {node.children.map((child) => (
            <FolderTreeNode
              key={child.id}
              node={child}
              depth={depth + 1}
              caseId={caseId}
              onCreateFolder={onCreateFolder}
              onDeleteFolder={onDeleteFolder}
            />
          ))}
        </div>
      )}
    </div>
  )
}
