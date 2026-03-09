import { Checkbox } from "@/components/ui/checkbox"
import { StatusIndicator } from "@/components/ui/status-indicator"
import { Button } from "@/components/ui/button"
import { TableRow, TableCell } from "@/components/ui/table"
import { Eye, RotateCcw, Trash2 } from "lucide-react"
import type { EvidenceFile } from "@/types/evidence.types"

interface EvidenceRowProps {
  file: EvidenceFile
  selected: boolean
  onSelect: (id: string) => void
  onView?: (file: EvidenceFile) => void
  onReprocess?: (file: EvidenceFile) => void
  onDelete?: (file: EvidenceFile) => void
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function EvidenceRow({
  file,
  selected,
  onSelect,
  onView,
  onReprocess,
  onDelete,
}: EvidenceRowProps) {
  return (
    <TableRow className="group">
      <TableCell className="w-8">
        <Checkbox
          checked={selected}
          onCheckedChange={() => onSelect(file.id)}
        />
      </TableCell>
      <TableCell
        className="max-w-[300px] cursor-pointer truncate font-medium hover:text-amber-500"
        onClick={() => onView?.(file)}
      >
        {file.filename}
      </TableCell>
      <TableCell className="text-xs text-muted-foreground">
        {file.file_type}
      </TableCell>
      <TableCell className="font-mono text-xs">
        {formatSize(file.file_size)}
      </TableCell>
      <TableCell>
        <StatusIndicator status={file.status} />
      </TableCell>
      <TableCell className="font-mono text-xs">
        {file.entity_count ?? "—"}
      </TableCell>
      <TableCell className="text-xs text-muted-foreground">
        {new Date(file.uploaded_at).toLocaleDateString()}
      </TableCell>
      <TableCell>
        <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {onView && (
            <Button variant="ghost" size="icon-sm" onClick={() => onView(file)}>
              <Eye className="size-3.5" />
            </Button>
          )}
          {onReprocess && file.status !== "processing" && (
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => onReprocess(file)}
            >
              <RotateCcw className="size-3.5" />
            </Button>
          )}
          {onDelete && (
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => onDelete(file)}
            >
              <Trash2 className="size-3.5 text-red-400" />
            </Button>
          )}
        </div>
      </TableCell>
    </TableRow>
  )
}
