import { Folder, GripVertical } from "lucide-react"
import { TableRow, TableCell } from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import type { EvidenceFolder } from "@/types/evidence.types"

interface FolderRowProps {
  folder: EvidenceFolder
  onNavigate: (folderId: string) => void
  onDropFile?: (folderId: string, evidenceId: string) => void
  onDropFolder?: (targetFolderId: string, draggedFolderId: string) => void
}

export function FolderRow({ folder, onNavigate, onDropFile, onDropFolder }: FolderRowProps) {
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.currentTarget.classList.add("bg-amber-500/10")
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.currentTarget.classList.remove("bg-amber-500/10")
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    e.currentTarget.classList.remove("bg-amber-500/10")
    const evidenceId = e.dataTransfer.getData("application/x-evidence-id")
    const draggedFolderId = e.dataTransfer.getData("application/x-folder-id")
    if (evidenceId) {
      onDropFile?.(folder.id, evidenceId)
    } else if (draggedFolderId && draggedFolderId !== folder.id) {
      onDropFolder?.(folder.id, draggedFolderId)
    }
  }

  const handleDragStart = (e: React.DragEvent) => {
    e.dataTransfer.setData("application/x-folder-id", folder.id)
    e.dataTransfer.effectAllowed = "move"
  }

  return (
    <TableRow
      className="group cursor-pointer hover:bg-muted/50 transition-colors"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <TableCell className="w-8">
        <div
          draggable
          onDragStart={handleDragStart}
          className="cursor-grab opacity-0 group-hover:opacity-100 transition-opacity"
        >
          <GripVertical className="size-3.5 text-muted-foreground" />
        </div>
      </TableCell>
      <TableCell
        className="font-medium"
        onClick={() => onNavigate(folder.id)}
      >
        <div className="flex items-center gap-2">
          <Folder className="size-4 text-amber-500" />
          <span className="hover:text-amber-500 transition-colors">{folder.name}</span>
        </div>
      </TableCell>
      <TableCell className="text-xs text-muted-foreground">Folder</TableCell>
      <TableCell className="text-xs text-muted-foreground">—</TableCell>
      <TableCell className="text-xs text-muted-foreground">—</TableCell>
      <TableCell className="font-mono text-xs">
        <div className="flex items-center gap-2">
          {folder.file_count > 0 && (
            <Badge variant="secondary" className="text-[10px]">
              {folder.file_count} file{folder.file_count !== 1 ? "s" : ""}
            </Badge>
          )}
          {folder.subfolder_count > 0 && (
            <Badge variant="secondary" className="text-[10px]">
              {folder.subfolder_count} folder{folder.subfolder_count !== 1 ? "s" : ""}
            </Badge>
          )}
        </div>
      </TableCell>
      <TableCell className="text-xs text-muted-foreground">
        {folder.created_at ? new Date(folder.created_at).toLocaleDateString() : "—"}
      </TableCell>
      <TableCell />
    </TableRow>
  )
}
