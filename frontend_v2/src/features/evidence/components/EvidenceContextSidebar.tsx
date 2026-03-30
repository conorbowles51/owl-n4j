import { useState, useMemo } from "react"
import {
  Info,
  Loader2,
  MessageSquare,
  PanelRightClose,
  FileText,
  Calendar,
  HardDrive,
  Hash,
  AlertCircle,
  Download,
  Eye,
  ChevronDown,
  ChevronRight,
  Music,
  FolderOpen,
  Play,
  RotateCcw,
  Network,
  ArrowRight,
  Users,
  Building,
  MapPin,
  Banknote,
  Tag,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { StatusIndicator, type ProcessingStatus } from "@/components/ui/status-indicator"
import { DocumentViewer } from "@/components/ui/document-viewer"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/cn"
import { useEvidenceStore } from "../evidence.store"
import { useUIStore } from "@/stores/ui.store"
import { useJobs } from "../hooks/use-jobs"
import { useFolderContents } from "../hooks/use-folder-contents"
import { JobsPanel } from "./JobsPanel"
import { FileSummaryPanel } from "./FileSummaryPanel"
import { ChatSidePanel } from "@/features/chat/components/ChatSidePanel"
import { evidenceAPI } from "../api"
import { useProcessBackground } from "../hooks/use-evidence-detail"
import { useFileEntities, useFileRelationships } from "../hooks/use-file-entities"
import type { FileEntity, FileRelationship } from "../hooks/use-file-entities"
import type { EvidenceFileRecord } from "@/types/evidence.types"

// --- Shared helpers ---

const IMAGE_EXTS = new Set(["jpg", "jpeg", "png", "gif", "bmp", "svg", "webp"])
const AUDIO_EXTS = new Set(["mp3", "wav", "ogg", "flac", "aac", "m4a"])
const VIDEO_EXTS = new Set(["mp4", "webm", "mov", "avi", "mkv", "flv", "wmv"])

function getExt(filename: string): string {
  return filename.split(".").pop()?.toLowerCase() ?? ""
}

function getMediaType(filename: string): "image" | "audio" | "video" | null {
  const ext = getExt(filename)
  if (IMAGE_EXTS.has(ext)) return "image"
  if (AUDIO_EXTS.has(ext)) return "audio"
  if (VIDEO_EXTS.has(ext)) return "video"
  return null
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function DetailRow({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ElementType
  label: string
  value: React.ReactNode
}) {
  return (
    <div className="flex items-center gap-3 rounded-md px-1 py-1.5 transition-colors hover:bg-muted/40">
      <Icon className="size-3.5 shrink-0 text-muted-foreground/60" />
      <span className="w-20 shrink-0 text-xs text-muted-foreground">{label}</span>
      <span className="min-w-0 flex-1 text-sm text-foreground">{value}</span>
    </div>
  )
}

function CollapsibleSection({
  title,
  defaultOpen = true,
  count,
  children,
}: {
  title: string
  defaultOpen?: boolean
  count?: number
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  const Chevron = open ? ChevronDown : ChevronRight

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground"
      >
        <Chevron className="size-3.5 text-muted-foreground/60" />
        {title}
        {count != null && count > 0 && (
          <Badge variant="secondary" className="ml-auto text-[10px] px-1.5 py-0">
            {count}
          </Badge>
        )}
      </button>
      {open && (
        <div className="border-t border-border px-3 pb-3 pt-1">
          {children}
        </div>
      )}
    </div>
  )
}

function SmartThumbnail({
  file,
  fileUrl,
  onOpenViewer,
}: {
  file: EvidenceFileRecord
  fileUrl: string
  onOpenViewer: () => void
}) {
  const mediaType = getMediaType(file.original_filename)
  if (!mediaType) return null

  return (
    <div className="overflow-hidden rounded-lg border border-border">
      {mediaType === "image" && (
        <button
          onClick={onOpenViewer}
          className="group relative w-full"
        >
          <img
            src={fileUrl}
            alt={file.original_filename}
            className="w-full max-h-[200px] object-contain bg-muted/30"
            loading="lazy"
          />
          <div className="absolute inset-0 flex items-center justify-center bg-black/0 group-hover:bg-black/30 transition-colors">
            <Eye className="size-6 text-white opacity-0 group-hover:opacity-100 transition-opacity" />
          </div>
        </button>
      )}

      {mediaType === "audio" && (
        <div className="flex flex-col items-center gap-3 bg-muted/30 p-4">
          <Music className="size-8 text-muted-foreground" />
          <audio
            controls
            src={fileUrl}
            className="w-full"
            preload="metadata"
          />
        </div>
      )}

      {mediaType === "video" && (
        <div className="bg-black">
          <video
            controls
            src={fileUrl}
            className="w-full max-h-[200px]"
            preload="metadata"
          />
        </div>
      )}
    </div>
  )
}

// --- Category icon mapping ---

const CATEGORY_ICONS: Record<string, React.ElementType> = {
  Person: Users,
  Organization: Building,
  Location: MapPin,
  Financial: Banknote,
  Money: Banknote,
}

function getCategoryIcon(category: string): React.ElementType {
  return CATEGORY_ICONS[category] || Tag
}

// --- Entity list grouped by category ---

function EntityList({ entities }: { entities: FileEntity[] }) {
  const grouped = useMemo(() => {
    const map = new Map<string, FileEntity[]>()
    for (const e of entities) {
      const existing = map.get(e.category) || []
      existing.push(e)
      map.set(e.category, existing)
    }
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]))
  }, [entities])

  if (entities.length === 0) {
    return (
      <p className="py-3 text-center text-xs text-muted-foreground">
        No entities extracted from this file.
      </p>
    )
  }

  return (
    <div className="space-y-2.5">
      {grouped.map(([category, items]) => {
        const Icon = getCategoryIcon(category)
        return (
          <div key={category}>
            <div className="mb-1 flex items-center gap-1.5">
              <Icon className="size-3 text-muted-foreground/60" />
              <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                {category}
              </span>
              <span className="text-[10px] text-muted-foreground/50">({items.length})</span>
            </div>
            <div className="space-y-0.5">
              {items.map((entity) => (
                <div
                  key={entity.id}
                  className="flex items-center justify-between gap-2 rounded px-1.5 py-0.5 text-xs hover:bg-muted/40"
                >
                  <span className="min-w-0 truncate text-foreground">
                    {entity.name}
                  </span>
                  {entity.confidence != null && (
                    <Badge
                      variant="outline"
                      className="shrink-0 px-1 py-0 text-[9px] font-normal text-muted-foreground"
                    >
                      {Math.round(entity.confidence * 100)}%
                    </Badge>
                  )}
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// --- Relationship list ---

function RelationshipList({ relationships }: { relationships: FileRelationship[] }) {
  if (relationships.length === 0) {
    return (
      <p className="py-3 text-center text-xs text-muted-foreground">
        No relationships extracted from this file.
      </p>
    )
  }

  return (
    <div className="space-y-1">
      {relationships.map((rel, i) => (
        <div
          key={i}
          className="flex items-center gap-1 rounded px-1.5 py-1 text-xs hover:bg-muted/40"
        >
          <span className="min-w-0 shrink truncate text-foreground" title={rel.source_entity_name}>
            {rel.source_entity_name}
          </span>
          <ArrowRight className="size-3 shrink-0 text-muted-foreground/50" />
          <Badge
            variant="outline"
            className="shrink-0 px-1 py-0 text-[9px] font-medium uppercase text-amber-500/80"
          >
            {rel.type}
          </Badge>
          <ArrowRight className="size-3 shrink-0 text-muted-foreground/50" />
          <span className="min-w-0 shrink truncate text-foreground" title={rel.target_entity_name}>
            {rel.target_entity_name}
          </span>
          {rel.confidence != null && (
            <Badge
              variant="outline"
              className="ml-auto shrink-0 px-1 py-0 text-[9px] font-normal text-muted-foreground"
            >
              {Math.round(rel.confidence * 100)}%
            </Badge>
          )}
        </div>
      ))}
    </div>
  )
}

// --- Details panel content (inline version of EvidenceDetailSheet) ---

function DetailsPanelContent({
  file,
  caseId,
}: {
  file: EvidenceFileRecord
  caseId: string
}) {
  const [viewerOpen, setViewerOpen] = useState(false)
  const fileUrl = evidenceAPI.getFileUrl(file.id)
  const ext = getExt(file.original_filename)

  const isProcessed = file.status === "processed"
  const isProcessing = file.status === "processing"
  const isFailed = file.status === "failed"
  const isUnprocessed = file.status === "unprocessed"

  const processMutation = useProcessBackground(caseId)

  // Only fetch entities/relationships for processed files
  const { data: entities, isLoading: entitiesLoading } = useFileEntities(
    isProcessed ? file.id : null
  )
  const { data: relationships, isLoading: relationshipsLoading } = useFileRelationships(
    isProcessed ? file.id : null
  )

  const handleProcess = () => {
    processMutation.mutate({ fileIds: [file.id] })
  }

  return (
    <>
      <ScrollArea className="h-full">
        <div className="space-y-4 p-4">
          {/* Header */}
          <div className="flex items-start gap-3">
            <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-amber-500/10">
              <FileText className="size-5 text-amber-500" />
            </div>
            <div className="min-w-0 flex-1">
              <h3 className="truncate text-sm font-semibold">
                {file.original_filename}
              </h3>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {ext.toUpperCase() || "File"} &middot; {formatSize(file.size)}
              </p>
            </div>
          </div>

          {/* Status row */}
          <div className="flex items-center gap-2">
            <StatusIndicator status={file.status as ProcessingStatus} />
            {file.is_duplicate && (
              <Badge variant="warning" className="text-[10px]">
                Duplicate
              </Badge>
            )}
          </div>

          {/* Action toolbar */}
          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              size="sm"
              onClick={() => setViewerOpen(true)}
            >
              <Eye className="size-3.5" />
              Open File
            </Button>
            <a href={fileUrl} download target="_blank" rel="noopener noreferrer">
              <Button variant="ghost" size="icon-sm" title="Download">
                <Download className="size-3.5" />
              </Button>
            </a>
          </div>

          {/* Smart thumbnail */}
          <SmartThumbnail
            file={file}
            fileUrl={fileUrl}
            onOpenViewer={() => setViewerOpen(true)}
          />

          {/* --- Unprocessed: prominent Process button --- */}
          {isUnprocessed && (
            <div className="overflow-hidden rounded-lg border border-amber-500/20 bg-amber-500/5">
              <div className="flex flex-col items-center gap-3 p-4">
                <p className="text-xs text-muted-foreground text-center">
                  This file has not been processed yet. Process it to extract entities, relationships, and generate a summary.
                </p>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleProcess}
                  disabled={processMutation.isPending}
                >
                  {processMutation.isPending ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <Play className="size-3.5" />
                  )}
                  Process this file
                </Button>
              </div>
            </div>
          )}

          {/* --- Processing: live progress indicator --- */}
          {isProcessing && (
            <div className="overflow-hidden rounded-lg border border-blue-500/20 bg-blue-500/5">
              <div className="flex items-center gap-3 p-4">
                <Loader2 className="size-5 shrink-0 animate-spin text-blue-500" />
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium text-blue-600 dark:text-blue-400">
                    Processing in progress
                  </p>
                  <p className="mt-0.5 text-[10px] text-muted-foreground">
                    Extracting entities and relationships...
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* --- Failed: error card + retry --- */}
          {isFailed && file.last_error && (
            <div className="overflow-hidden rounded-lg border border-red-200 bg-red-50 dark:border-red-500/20 dark:bg-red-500/5">
              <div className="flex items-start gap-3 p-3">
                <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-red-500/10">
                  <AlertCircle className="size-4 text-red-500" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-semibold text-red-600 dark:text-red-400">
                    Processing Error
                  </p>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                    {file.last_error}
                  </p>
                  <Button
                    variant="outline"
                    size="sm"
                    className="mt-2"
                    onClick={handleProcess}
                    disabled={processMutation.isPending}
                  >
                    {processMutation.isPending ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <RotateCcw className="size-3.5" />
                    )}
                    Retry
                  </Button>
                </div>
              </div>
            </div>
          )}

          {/* Details section (always shown) */}
          <CollapsibleSection title="Details">
            <DetailRow icon={HardDrive} label="File size" value={formatSize(file.size)} />
            <DetailRow
              icon={Calendar}
              label="Uploaded"
              value={file.created_at ? new Date(file.created_at).toLocaleString() : "---"}
            />
            {file.processed_at && (
              <DetailRow
                icon={Calendar}
                label="Processed"
                value={new Date(file.processed_at).toLocaleString()}
              />
            )}
            {file.folder_id && (
              <DetailRow
                icon={FolderOpen}
                label="Folder"
                value={file.folder_id}
              />
            )}
            <DetailRow
              icon={Hash}
              label="SHA-256"
              value={
                <span className="break-all font-mono text-[10px]">
                  {file.sha256}
                </span>
              }
            />
          </CollapsibleSection>

          {/* --- Processed: AI Summary, Entities, Relationships, Processing Info --- */}
          {isProcessed && (
            <>
              {/* AI Summary section */}
              <CollapsibleSection title="AI Summary">
                <FileSummaryPanel summary={file.summary} />
              </CollapsibleSection>

              {/* Extracted Entities section */}
              <CollapsibleSection
                title="Extracted Entities"
                count={entities?.length}
                defaultOpen={false}
              >
                {entitiesLoading ? (
                  <div className="flex items-center justify-center gap-2 py-4">
                    <Loader2 className="size-3.5 animate-spin text-muted-foreground" />
                    <span className="text-xs text-muted-foreground">Loading entities...</span>
                  </div>
                ) : (
                  <EntityList entities={entities || []} />
                )}
              </CollapsibleSection>

              {/* Relationships section */}
              <CollapsibleSection
                title="Key Relationships"
                count={relationships?.length}
                defaultOpen={false}
              >
                {relationshipsLoading ? (
                  <div className="flex items-center justify-center gap-2 py-4">
                    <Loader2 className="size-3.5 animate-spin text-muted-foreground" />
                    <span className="text-xs text-muted-foreground">Loading relationships...</span>
                  </div>
                ) : (
                  <RelationshipList relationships={relationships || []} />
                )}
              </CollapsibleSection>

              {/* Processing Info section */}
              {(file.entity_count != null || file.relationship_count != null || file.processed_at) && (
                <CollapsibleSection title="Processing Info" defaultOpen={false}>
                  {file.entity_count != null && (
                    <DetailRow
                      icon={Network}
                      label="Entities"
                      value={file.entity_count}
                    />
                  )}
                  {file.relationship_count != null && (
                    <DetailRow
                      icon={Network}
                      label="Relations"
                      value={file.relationship_count}
                    />
                  )}
                  {file.processed_at && (
                    <DetailRow
                      icon={Calendar}
                      label="Processed"
                      value={new Date(file.processed_at).toLocaleString()}
                    />
                  )}
                </CollapsibleSection>
              )}
            </>
          )}

          {/* Non-failed error display for edge cases */}
          {!isFailed && file.last_error && (
            <div className="overflow-hidden rounded-lg border border-red-200 bg-red-50 dark:border-red-500/20 dark:bg-red-500/5">
              <div className="flex items-start gap-3 p-3">
                <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-red-500/10">
                  <AlertCircle className="size-4 text-red-500" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-semibold text-red-600 dark:text-red-400">
                    Processing Error
                  </p>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                    {file.last_error}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Document Viewer modal */}
      <DocumentViewer
        open={viewerOpen}
        onOpenChange={setViewerOpen}
        documentUrl={fileUrl}
        documentName={file.original_filename}
      />
    </>
  )
}

// --- Main sidebar component ---

interface EvidenceContextSidebarProps {
  caseId: string
}

export function EvidenceContextSidebar({
  caseId,
}: EvidenceContextSidebarProps) {
  const { sidebarTab, setSidebarTab, detailFileId, currentFolderId } = useEvidenceStore()
  const setCollapsed = useUIStore((s) => s.setGraphPanelCollapsed)

  // Resolve detail file internally
  const { data: folderContents } = useFolderContents(caseId, currentFolderId)
  const detailFile = folderContents?.files.find((f) => f.id === detailFileId) ?? null
  const { data: jobs } = useJobs(caseId)
  const hasActiveJobs = useMemo(
    () =>
      jobs?.some((j) => !["completed", "failed"].includes(j.status)) ?? false,
    [jobs]
  )

  const tabs = [
    { id: "details" as const, label: "Details", icon: Info },
    { id: "processing" as const, label: "Processing", icon: Loader2 },
    { id: "chat" as const, label: "AI Chat", icon: MessageSquare },
  ]

  return (
    <div className="flex h-full flex-col border-l border-border bg-card">
      {/* Tab bar */}
      <div className="flex items-center border-b border-border bg-muted/30">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setSidebarTab(tab.id)}
            className={cn(
              "flex items-center gap-1.5 px-4 py-2 text-xs font-medium transition-colors border-b-2",
              sidebarTab === tab.id
                ? "border-amber-500 text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            <tab.icon className="size-3.5" />
            {tab.label}
            {tab.id === "processing" && hasActiveJobs && (
              <span className="size-1.5 rounded-full bg-amber-500 animate-pulse" />
            )}
          </button>
        ))}
        <div className="ml-auto pr-1">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => setCollapsed(true)}
              >
                <PanelRightClose className="size-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="left">Collapse panel</TooltipContent>
          </Tooltip>
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-hidden">
        {sidebarTab === "details" && (
          detailFile ? (
            <DetailsPanelContent file={detailFile} caseId={caseId} />
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
              <Info className="size-8 text-muted-foreground/40" />
              <p className="text-sm font-medium text-muted-foreground">
                Select a file to view details
              </p>
              <p className="text-xs text-muted-foreground/70">
                Click a filename in the file list
              </p>
            </div>
          )
        )}
        {sidebarTab === "processing" && (
          <JobsPanel caseId={caseId} />
        )}
        {sidebarTab === "chat" && (
          <ChatSidePanel caseId={caseId} />
        )}
      </div>
    </div>
  )
}
