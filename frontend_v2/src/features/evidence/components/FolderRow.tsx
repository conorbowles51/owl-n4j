import { Folder, GripVertical } from "lucide-react"
import { TableRow, TableCell } from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import type { EvidenceFolder } from "@/types/evidence.types"

import {
  useEvidenceMoves,
  useEvidenceDropTarget,
} from "../hooks/use-evidence-moves"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu"
import { MoreHorizontal, FolderInput } from "lucide-react"
import type { MoveSource } from "../utils/move-targets"

interface FolderRowProps {
  folder: EvidenceFolder
  onNavigate: (folderId: string) => void
}

export function FolderRow({ folder, onNavigate }: FolderRowProps) {
  const moves = useEvidenceMoves()
  const drop = useEvidenceDropTarget(folder.id)
  const source: MoveSource = {
    kind: "folder",
    id: folder.id,
    name: folder.name,
    parent_id: folder.parent_id,
  }
  return (
    <TableRow
      className="group hover:bg-muted/50 transition-colors data-[drop-active=true]:bg-primary/15 data-[drop-active=true]:outline-2 data-[drop-active=true]:outline-primary"
      {...drop}
      draggable={Boolean(moves?.canMove)}
      onDragStart={(event) => moves?.startDrag(event, source)}
      onDragEnd={() => moves?.endDrag()}
    >
      <TableCell className="w-8">
        <div className="cursor-grab opacity-0 group-hover:opacity-100 transition-opacity">
          <GripVertical className="size-3.5 text-muted-foreground" />
        </div>
      </TableCell>
      <TableCell className="font-medium">
        <div className="flex items-center gap-2">
          <Folder className="size-4 shrink-0 text-amber-500" />
          <button
            onClick={() => onNavigate(folder.id)}
            title={folder.name}
            className="min-w-0 flex-1 truncate text-left hover:text-amber-500 transition-colors"
          >
            {folder.name}
          </button>
          {folder.has_profile ? (
            <Badge variant="secondary" className="text-[10px]">
              Profile
            </Badge>
          ) : null}
        </div>
      </TableCell>
      <TableCell className="text-xs text-muted-foreground">Folder</TableCell>
      <TableCell className="text-xs text-muted-foreground">—</TableCell>
      <TableCell className="text-xs text-muted-foreground">—</TableCell>
      <TableCell className="font-mono text-xs">
        <div className="flex flex-col items-start gap-1">
          {folder.file_count > 0 && (
            <Badge variant="secondary" className="text-[10px]">
              {folder.file_count} file{folder.file_count !== 1 ? "s" : ""}
            </Badge>
          )}
          {folder.subfolder_count > 0 && (
            <Badge variant="secondary" className="text-[10px]">
              {folder.subfolder_count} folder
              {folder.subfolder_count !== 1 ? "s" : ""}
            </Badge>
          )}
        </div>
      </TableCell>
      <TableCell className="text-xs text-muted-foreground">
        {folder.created_at
          ? new Date(folder.created_at).toLocaleDateString()
          : "—"}
      </TableCell>
      <TableCell className="text-right">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={`Actions for ${folder.name}`}
            >
              <MoreHorizontal className="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem
              disabled={!moves?.canMove}
              onClick={() => moves?.openMove(source)}
            >
              <FolderInput className="size-4" />
              Move to…
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </TableCell>
    </TableRow>
  )
}
