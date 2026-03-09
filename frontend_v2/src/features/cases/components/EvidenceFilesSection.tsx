import { useState, useMemo } from "react"
import {
  FileText,
  Search,
  RefreshCw,
  FileImage,
  FileSpreadsheet,
  File,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { EmptyState } from "@/components/ui/empty-state"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { useCaseEvidence } from "../hooks/use-case-evidence"
import { useQueryClient } from "@tanstack/react-query"
import type { EvidenceFile } from "@/types/evidence.types"

interface EvidenceFilesSectionProps {
  caseId: string
}

const FILE_TYPE_FILTERS = ["all", "pdf", "doc", "image", "csv", "other"] as const
type FileTypeFilter = (typeof FILE_TYPE_FILTERS)[number]

const PAGE_SIZE = 10

const statusVariant: Record<string, "success" | "warning" | "info" | "danger" | "slate"> = {
  processed: "success",
  processing: "warning",
  queued: "info",
  failed: "danger",
  unprocessed: "slate",
}

function getFileIcon(filename: string) {
  const ext = getExtension(filename)
  if (ext === "pdf" || ext === "doc" || ext === "docx" || ext === "txt") return FileText
  if (["png", "jpg", "jpeg", "gif", "bmp", "webp", "svg"].includes(ext)) return FileImage
  if (["csv", "xls", "xlsx", "tsv"].includes(ext)) return FileSpreadsheet
  return File
}

function getExtension(filename: string): string {
  const dot = filename.lastIndexOf(".")
  return dot >= 0 ? filename.slice(dot + 1).toLowerCase() : ""
}

function matchesTypeFilter(file: EvidenceFile, filter: FileTypeFilter): boolean {
  if (filter === "all") return true
  const ext = getExtension(file.original_filename)
  if (filter === "pdf") return ext === "pdf"
  if (filter === "doc") return ["doc", "docx", "txt", "rtf", "odt"].includes(ext)
  if (filter === "image") return ["png", "jpg", "jpeg", "gif", "bmp", "webp", "svg"].includes(ext)
  if (filter === "csv") return ["csv", "xls", "xlsx", "tsv"].includes(ext)
  return !["pdf", "doc", "docx", "txt", "rtf", "odt", "png", "jpg", "jpeg", "gif", "bmp", "webp", "svg", "csv", "xls", "xlsx", "tsv"].includes(ext)
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function EvidenceFilesSection({ caseId }: EvidenceFilesSectionProps) {
  const { data: files, isLoading } = useCaseEvidence(caseId)
  const queryClient = useQueryClient()
  const [search, setSearch] = useState("")
  const [typeFilter, setTypeFilter] = useState<FileTypeFilter>("all")
  const [page, setPage] = useState(0)

  const filtered = useMemo(
    () =>
      (files ?? [])
        .filter((f) => matchesTypeFilter(f, typeFilter))
        .filter(
          (f) =>
            !search ||
            f.original_filename.toLowerCase().includes(search.toLowerCase())
        )
        .sort(
          (a, b) =>
            new Date(b.created_at).getTime() -
            new Date(a.created_at).getTime()
        ),
    [files, typeFilter, search]
  )

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE)
  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  if (isLoading) {
    return (
      <div className="flex justify-center py-4">
        <LoadingSpinner size="sm" />
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {/* Search + refresh */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-2 top-1/2 size-3 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search files..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPage(0)
            }}
            className="h-7 pl-7 text-xs"
          />
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="h-7"
          onClick={() =>
            queryClient.invalidateQueries({ queryKey: ["evidence", caseId] })
          }
        >
          <RefreshCw className="size-3" />
        </Button>
      </div>

      {/* Type filter pills */}
      <div className="flex flex-wrap gap-1">
        {FILE_TYPE_FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => {
              setTypeFilter(f)
              setPage(0)
            }}
            className={`rounded-full px-2.5 py-0.5 text-[10px] font-medium capitalize transition-colors ${
              typeFilter === f
                ? "bg-amber-500/15 text-amber-600 dark:text-amber-400"
                : "bg-secondary text-muted-foreground hover:text-foreground"
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {paged.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="No evidence files"
          description={
            search || typeFilter !== "all"
              ? "No matches"
              : "Upload evidence from the workspace"
          }
          className="py-4"
        />
      ) : (
        <div className="space-y-1">
          {paged.map((file) => {
            const FileIcon = getFileIcon(file.original_filename)
            return (
              <div
                key={file.id}
                className="flex items-center gap-2 rounded-md border border-border px-3 py-2"
              >
                <FileIcon className="size-3.5 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium">
                    {file.original_filename}
                  </p>
                  <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                    <span>{formatBytes(file.size)}</span>
                    <span>
                      {new Date(file.created_at).toLocaleDateString()}
                    </span>
                    {file.entity_count !== undefined && file.entity_count > 0 && (
                      <span>{file.entity_count} entities</span>
                    )}
                  </div>
                </div>
                <Badge
                  variant={statusVariant[file.status] ?? "slate"}
                  className="text-[9px]"
                >
                  {file.status}
                </Badge>
              </div>
            )
          })}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-1 text-xs text-muted-foreground">
          <span>
            {filtered.length} file{filtered.length !== 1 ? "s" : ""}
          </span>
          <div className="flex gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-xs"
              disabled={page === 0}
              onClick={() => setPage(page - 1)}
            >
              Prev
            </Button>
            <span className="flex items-center px-1">
              {page + 1}/{totalPages}
            </span>
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-xs"
              disabled={page >= totalPages - 1}
              onClick={() => setPage(page + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
