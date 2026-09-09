import { useEvidenceMoves } from "../hooks/use-evidence-moves"
import type { MoveSource } from "../utils/move-targets"
import { OpenFileLocationButton } from "./OpenFileLocationButton"
import {
  MoreHorizontal,
  Eye,
  Play,
  FolderInput,
  Trash2,
  ContactRound,
  Pin,
  PinOff,
} from "lucide-react"
import { Checkbox } from "@/components/ui/checkbox"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { TableRow, TableCell } from "@/components/ui/table"
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip"
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/cn"
import { useEvidenceStore } from "../evidence.store"
import { useGuardedProcess } from "../hooks/use-guarded-process"
import { getFileTypeCategory } from "../utils/file-types"
import { getDisplayStatus } from "../utils/display-status"
import { RouteBadge } from "./RouteBadge"
import { ProcessHoldDialog } from "./ProcessHoldDialog"
import { toast } from "sonner"
import type { FileRoute } from "../hooks/use-route-checks"
import type { EvidenceFileRecord, EvidenceFile } from "@/types/evidence.types"

interface FileRowProps {
  dragSource?: MoveSource
  file: EvidenceFileRecord
  caseId: string
  /**
   * This file's route, passed in rather than fetched here.
   *
   * The check is a batch call with a fifty-id limit, so it belongs to whatever
   * renders the list. A row that asked for itself would be one request per row.
   */
  route?: FileRoute
  onDelete?: (file: EvidenceFile) => void
  onAddToDossier?: (file: EvidenceFile) => void
  isPinned?: boolean
  onPin?: (fileId: string) => void
  onUnpin?: (pinId: string) => void
  pinId?: string
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024)
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
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
  processed:
    "bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/20",
  processing:
    "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
  unprocessed:
    "bg-slate-500/10 text-slate-600 dark:text-slate-400 border-slate-500/20",
  failed: "bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20",
}

export function FileRow({
  dragSource,
  route,
  file,
  caseId,
  onDelete,
  onAddToDossier,
  isPinned,
  onPin,
  onUnpin,
  pinId,
}: FileRowProps) {
  const {
    selectedFileIds,
    toggleFileSelection,
    openDetail,
    detailFileId,
    detailOpen,
  } = useEvidenceStore()
  const moves = useEvidenceMoves()
  const singleSource: MoveSource = { kind: "files", files: [file] }
  const gate = useGuardedProcess(caseId)
  const { start, isChecking, isProcessing } = gate

  const isSelected = selectedFileIds.has(file.id)
  const typeCategory = getFileTypeCategory(file.original_filename)
  const displayStatus = getDisplayStatus(file)
  const statusClass = STATUS_STYLES[displayStatus] ?? STATUS_STYLES.unprocessed

  // Only the success is announced here. A hold and a failure are both reported
  // by the gate, which knows what it held and why.
  const handleProcess = async () => {
    if ((await start({ fileIds: [file.id] })) === "started") {
      toast.success(`Processing ${file.original_filename}`)
    }
  }

  // Cast EvidenceFileRecord to EvidenceFile shape for compatibility with legacy handlers
  const asLegacyFile = file as unknown as EvidenceFile

  return (
    <TableRow
      className={cn(
        "group",
        isSelected && "bg-amber-500/5",
        detailOpen &&
          detailFileId === file.id &&
          "bg-primary/10 ring-1 ring-inset ring-primary/30"
      )}
      data-state={isSelected ? "selected" : undefined}
      data-evidence-file-id={file.id}
      tabIndex={-1}
      draggable={Boolean(moves?.canMove)}
      onDragStart={(event) =>
        moves?.startDrag(event, dragSource ?? singleSource)
      }
      onDragEnd={() => moves?.endDrag()}
    >
      {/* Checkbox */}
      <TableCell className="w-8">
        <Checkbox
          aria-label={`Select ${file.original_filename}`}
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
              className="block w-full min-w-0 truncate text-left text-sm font-medium hover:text-amber-500 transition-colors"
            >
              {file.original_filename}
            </button>
          </TooltipTrigger>
          <TooltipContent>{file.original_filename}</TooltipContent>
        </Tooltip>
        {file.folder_path && (
          <div className="mt-1 flex min-w-0 items-center gap-2 text-xs text-muted-foreground">
            <span
              className="min-w-0 flex-1 truncate"
              title={[
                "Evidence root",
                ...file.folder_path.map((folder) => folder.name),
              ].join(" / ")}
            >
              {[
                "Evidence root",
                ...file.folder_path.map((folder) => folder.name),
              ].join(" / ")}
            </span>
            <OpenFileLocationButton
              caseId={caseId}
              evidenceId={file.id}
              compact
            />
          </div>
        )}
      </TableCell>

      {/* Type badge, and the route badge when the file is not an ordinary document */}
      <TableCell>
        <div className="flex flex-wrap items-center gap-1">
          <Badge variant="secondary" className="text-[10px]">
            {typeCategory}
          </Badge>
          <RouteBadge route={route} />
        </div>
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
          {displayStatus}
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
        {/* Renders nothing until this row's own Process is held, and portals
            out of the table when it does, so the row markup stays a row. */}
        <ProcessHoldDialog gate={gate} />
        <div className="flex justify-end">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={`Actions for ${file.original_filename}`}
                className="opacity-100 sm:opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 data-[state=open]:opacity-100 transition-opacity"
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
                disabled={file.status === "processing" || isChecking || isProcessing}
              >
                <Play className="size-4" />
                Process
              </DropdownMenuItem>
              {isPinned && pinId && onUnpin ? (
                <DropdownMenuItem onClick={() => onUnpin(pinId)}>
                  <PinOff className="size-4" />
                  Unpin from workspace
                </DropdownMenuItem>
              ) : onPin ? (
                <DropdownMenuItem onClick={() => onPin(file.id)}>
                  <Pin className="size-4" />
                  Pin to workspace
                </DropdownMenuItem>
              ) : null}
              {onAddToDossier ? (
                <DropdownMenuItem onClick={() => onAddToDossier(asLegacyFile)}>
                  <ContactRound className="size-4" />
                  Add to Dossier
                </DropdownMenuItem>
              ) : null}
              <DropdownMenuItem
                disabled={!moves?.canMove}
                onClick={() => moves?.openMove(singleSource)}
              >
                <FolderInput className="size-4" />
                Move to…
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
