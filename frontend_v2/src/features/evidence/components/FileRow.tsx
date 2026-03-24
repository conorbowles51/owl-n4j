import { MoreHorizontal, Eye, Play, FolderInput, Trash2 } from "lucide-react"
import { Checkbox } from "@/components/ui/checkbox"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { TableRow, TableCell } from "@/components/ui/table"
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip"
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/cn"
import { useEvidenceStore } from "../evidence.store"
import { useProcessBackground } from "../hooks/use-evidence-detail"
import { getFileTypeCategory } from "../utils/file-types"
import { toast } from "sonner"
import type { EvidenceFileRecord, EvidenceFile } from "@/types/evidence.types"

interface FileRowProps {
  file: EvidenceFileRecord
  caseId: string
  onDelete?: (file: EvidenceFile) => void
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
}

function formatRelativeTime(dateStr: string | null): string {
  if (!dateStr) return "--"
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMinutes = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMinutes < 1) return "Just now"
  if (diffMinutes < 60) return `${diffMinutes}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`
  return date.toLocaleDateString()
}

const STATUS_STYLES: Record<string, string> = {
  processed: "bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/20",
  processing: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
  unprocessed: "bg-slate-500/10 text-slate-600 dark:text-slate-400 border-slate-500/20",
  failed: "bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20",
}

export function FileRow({ file, caseId, onDelete }: FileRowProps) {
  const { selectedFileIds, toggleFileSelection, openDetail } = useEvidenceStore()
  const processMutation = useProcessBackground(caseId)

  const isSelected = selectedFileIds.has(file.id)
  const typeCategory = getFileTypeCategory(file.original_filename)
  const statusClass = STATUS_STYLES[file.status] ?? STATUS_STYLES.unprocessed

  const handleProcess = () => {
    processMutation.mutate(
      { fileIds: [file.id] },
      {
        onSuccess: () => toast.success(`Processing ${file.original_filename}`),
        onError: (err) => toast.error(err.message),
      }
    )
  }

  // Cast EvidenceFileRecord to EvidenceFile shape for compatibility with legacy handlers
  const asLegacyFile = file as unknown as EvidenceFile

  return (
    <TableRow
      className={cn("group", isSelected && "bg-amber-500/5")}
      data-state={isSelected ? "selected" : undefined}
    >
      {/* Checkbox */}
      <TableCell className="w-8">
        <Checkbox
          checked={isSelected}
          onCheckedChange={() => toggleFileSelection(file.id)}
        />
      </TableCell>

      {/* Filename */}
      <TableCell>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              onClick={() => openDetail(file.id)}
              className="max-w-[300px] truncate text-left text-sm font-medium hover:text-amber-500 transition-colors"
            >
              {file.original_filename}
            </button>
          </TooltipTrigger>
          <TooltipContent>{file.original_filename}</TooltipContent>
        </Tooltip>
      </TableCell>

      {/* Type badge */}
      <TableCell>
        <Badge variant="secondary" className="text-[10px]">
          {typeCategory}
        </Badge>
      </TableCell>

      {/* Size */}
      <TableCell className="font-mono text-xs text-muted-foreground">
        {formatSize(file.size)}
      </TableCell>

      {/* Status */}
      <TableCell>
        <span
          className={cn(
            "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium capitalize",
            statusClass
          )}
        >
          {file.status}
        </span>
      </TableCell>

      {/* Entity count */}
      <TableCell className="font-mono text-xs text-muted-foreground">
        {file.status === "processed"
          ? `${file.entity_count ?? 0} / ${file.relationship_count ?? 0}`
          : "--"}
      </TableCell>

      {/* Date */}
      <TableCell className="text-xs text-muted-foreground">
        {formatRelativeTime(file.created_at)}
      </TableCell>

      {/* Actions */}
      <TableCell>
        <div className="flex justify-end">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                className="opacity-0 group-hover:opacity-100 transition-opacity"
              >
                <MoreHorizontal className="size-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => openDetail(file.id)}>
                <Eye className="size-4" />
                Open
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={handleProcess}
                disabled={file.status === "processing"}
              >
                <Play className="size-4" />
                Process
              </DropdownMenuItem>
              <DropdownMenuItem disabled>
                <FolderInput className="size-4" />
                Move To...
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                variant="destructive"
                onClick={() => onDelete?.(asLegacyFile)}
              >
                <Trash2 className="size-4" />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </TableCell>
    </TableRow>
  )
}
