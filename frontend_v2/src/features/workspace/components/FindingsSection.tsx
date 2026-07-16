import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { toast } from "sonner"
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  Database,
  ExternalLink,
  FileText,
  Link2,
  Orbit,
  Plus,
  Search,
  Trash2,
  X,
  type LucideIcon,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { evidenceAPI } from "@/features/evidence/api"
import { graphAPI } from "@/features/graph/api"
import type { EvidenceFile } from "@/types/evidence.types"
import type { GraphNode } from "@/types/graph.types"
import {
  useCreateFinding,
  useDeleteFinding,
  useFindings,
  useReorderFindings,
  useUpdateFinding,
} from "../hooks/use-workspace"
import type { Finding, LinkedEvidenceReference } from "../api"
import { formatWorkspaceDate } from "../lib/format-date"

interface FindingsSectionProps {
  caseId: string
  previewLimit?: number
}

const PRIORITY_STYLES: Record<string, string> = {
  HIGH: "bg-red-500/10 text-red-600 border-red-500/20",
  MEDIUM: "border-yellow-500/20 bg-yellow-500/10 text-yellow-700 dark:text-yellow-300",
  LOW: "bg-slate-500/10 text-slate-600 border-slate-500/20",
}

function countLinkedItems(finding: Finding) {
  return (
    (finding.linked_evidence_ids?.length ?? 0) +
    (finding.linked_document_ids?.length ?? 0) +
    (finding.linked_entity_keys?.length ?? 0)
  )
}

function evidenceUrl(item: Pick<LinkedEvidenceReference, "id" | "url">) {
  return item.url || `/api/evidence/${item.id}/file`
}

function openEvidence(item: Pick<LinkedEvidenceReference, "id" | "url">) {
  window.open(evidenceUrl(item), "_blank", "noopener,noreferrer")
}

function toggleValue(values: string[], value: string) {
  return values.includes(value)
    ? values.filter((item) => item !== value)
    : [...values, value]
}

function matchesFile(file: EvidenceFile, query: string) {
  const lower = query.trim().toLowerCase()
  if (!lower) return true
  return [file.original_filename, file.summary ?? "", file.id]
    .join(" ")
    .toLowerCase()
    .includes(lower)
}

function fileLabel(file: EvidenceFile | LinkedEvidenceReference) {
  return file.original_filename || file.id
}

function LinkedSummary({ finding }: { finding: Finding }) {
  const evidenceCount = finding.linked_evidence_ids?.length ?? 0
  const documentCount = finding.linked_document_ids?.length ?? 0
  const entityCount = finding.linked_entity_keys?.length ?? 0

  if (evidenceCount + documentCount + entityCount === 0) return null

  return (
    <>
      <span className="inline-flex items-center gap-1">
        <Link2 className="size-3" />
        {countLinkedItems(finding)} linked items
      </span>
      {evidenceCount > 0 && (
        <span className="inline-flex items-center gap-1">
          <Database className="size-3" />
          {evidenceCount} evidence
        </span>
      )}
      {documentCount > 0 && (
        <span className="inline-flex items-center gap-1">
          <FileText className="size-3" />
          {documentCount} documents
        </span>
      )}
      {entityCount > 0 && (
        <span className="inline-flex items-center gap-1">
          <Orbit className="size-3" />
          {entityCount} entities
        </span>
      )}
    </>
  )
}

function LinkedFileList({
  title,
  icon: Icon,
  files,
}: {
  title: string
  icon: LucideIcon
  files?: LinkedEvidenceReference[]
}) {
  if (!files?.length) return null

  return (
    <div className="mt-3 space-y-2">
      <div className="flex items-center gap-1.5 text-[11px] font-medium text-foreground">
        <Icon className="size-3.5 text-muted-foreground" />
        {title}
      </div>
      <div className="space-y-2">
        {files.map((file) => (
          <div key={file.id} className="rounded-md border border-border/70 bg-muted/20 p-2">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate text-xs font-medium">{fileLabel(file)}</p>
                <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-muted-foreground">
                  {file.summary || "No summary available"}
                </p>
              </div>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => openEvidence(file)}
                aria-label={`Open ${fileLabel(file)}`}
              >
                <ExternalLink className="size-3.5" />
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function SelectedChips({
  values,
  labels,
  onRemove,
}: {
  values: string[]
  labels: Record<string, string>
  onRemove: (value: string) => void
}) {
  if (!values.length) return null

  return (
    <div className="flex flex-wrap gap-1.5">
      {values.map((value) => (
        <Badge key={value} variant="slate" className="max-w-full gap-1">
          <span className="truncate">{labels[value] || value}</span>
          <button
            type="button"
            onClick={() => onRemove(value)}
            aria-label={`Remove ${labels[value] || value}`}
            className="rounded-sm hover:bg-muted-foreground/15"
          >
            <X className="size-3" />
          </button>
        </Badge>
      ))}
    </div>
  )
}

function FilePicker({
  title,
  icon: Icon,
  files,
  selectedIds,
  search,
  onSearchChange,
  onToggle,
}: {
  title: string
  icon: LucideIcon
  files: EvidenceFile[]
  selectedIds: string[]
  search: string
  onSearchChange: (value: string) => void
  onToggle: (id: string) => void
}) {
  const selected = useMemo(
    () => files.filter((file) => selectedIds.includes(file.id)),
    [files, selectedIds],
  )
  const visible = useMemo(() => {
    const selectedSet = new Set(selectedIds)
    const filtered = files.filter((file) => !selectedSet.has(file.id) && matchesFile(file, search))
    return [...selected, ...filtered].slice(0, 30)
  }, [files, search, selected, selectedIds])
  const labels = useMemo(
    () => Object.fromEntries(files.map((file) => [file.id, fileLabel(file)])),
    [files],
  )

  return (
    <div className="space-y-2 rounded-md border border-border p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          <Icon className="size-3.5 text-muted-foreground" />
          <p className="truncate text-xs font-medium">{title}</p>
        </div>
        <Badge variant="slate" className="h-5 px-1.5 text-[10px]">
          {selectedIds.length}
        </Badge>
      </div>
      <SelectedChips
        values={selectedIds}
        labels={labels}
        onRemove={onToggle}
      />
      <div className="relative">
        <Search className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder={`Search ${title.toLowerCase()}`}
          className="h-8 pl-7 text-xs"
        />
      </div>
      <div className="max-h-52 space-y-1 overflow-y-auto pr-1">
        {visible.length === 0 ? (
          <p className="py-4 text-center text-xs text-muted-foreground">No matches</p>
        ) : (
          visible.map((file) => {
            const checked = selectedIds.includes(file.id)
            return (
              <label
                key={file.id}
                className="flex cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 hover:bg-muted/40"
              >
                <Checkbox
                  checked={checked}
                  onCheckedChange={() => onToggle(file.id)}
                  aria-label={`${checked ? "Unlink" : "Link"} ${fileLabel(file)}`}
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-medium">{fileLabel(file)}</span>
                  <span className="mt-0.5 line-clamp-2 block text-[11px] leading-relaxed text-muted-foreground">
                    {file.summary || "No summary available"}
                  </span>
                </span>
              </label>
            )
          })
        )}
      </div>
    </div>
  )
}

function EntityPicker({
  entities,
  selectedKeys,
  search,
  isLoading,
  onSearchChange,
  onToggle,
}: {
  entities: GraphNode[]
  selectedKeys: string[]
  search: string
  isLoading: boolean
  onSearchChange: (value: string) => void
  onToggle: (key: string) => void
}) {
  const labels = useMemo(
    () =>
      Object.fromEntries(
        entities.map((node) => [node.key, node.label || node.key]),
      ),
    [entities],
  )

  return (
    <div className="space-y-2 rounded-md border border-border p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          <Orbit className="size-3.5 text-muted-foreground" />
          <p className="truncate text-xs font-medium">Entities</p>
        </div>
        <Badge variant="slate" className="h-5 px-1.5 text-[10px]">
          {selectedKeys.length}
        </Badge>
      </div>
      <SelectedChips
        values={selectedKeys}
        labels={labels}
        onRemove={onToggle}
      />
      <div className="relative">
        <Search className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="Search entities"
          className="h-8 pl-7 text-xs"
        />
      </div>
      <div className="max-h-52 space-y-1 overflow-y-auto pr-1">
        {search.trim().length === 0 ? (
          <p className="py-4 text-center text-xs text-muted-foreground">Search to link entities</p>
        ) : isLoading ? (
          <p className="py-4 text-center text-xs text-muted-foreground">Searching...</p>
        ) : entities.length === 0 ? (
          <p className="py-4 text-center text-xs text-muted-foreground">No matches</p>
        ) : (
          entities.slice(0, 30).map((entity) => {
            const checked = selectedKeys.includes(entity.key)
            return (
              <label
                key={entity.key}
                className="flex cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 hover:bg-muted/40"
              >
                <Checkbox
                  checked={checked}
                  onCheckedChange={() => onToggle(entity.key)}
                  aria-label={`${checked ? "Unlink" : "Link"} ${entity.label || entity.key}`}
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-medium">
                    {entity.label || entity.key}
                  </span>
                  <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
                    {entity.type || "entity"} - {entity.key}
                  </span>
                </span>
              </label>
            )
          })
        )}
      </div>
    </div>
  )
}

export function FindingsSection({ caseId, previewLimit }: FindingsSectionProps) {
  const { data: findings = [], isLoading } = useFindings(caseId)
  const createFinding = useCreateFinding(caseId)
  const updateFinding = useUpdateFinding(caseId)
  const deleteFinding = useDeleteFinding(caseId)
  const reorderFindings = useReorderFindings(caseId)

  const [editorOpen, setEditorOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Finding | null>(null)
  const [title, setTitle] = useState("")
  const [content, setContent] = useState("")
  const [priority, setPriority] = useState<Finding["priority"]>("MEDIUM")
  const [selectedEvidenceIds, setSelectedEvidenceIds] = useState<string[]>([])
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([])
  const [selectedEntityKeys, setSelectedEntityKeys] = useState<string[]>([])
  const [evidenceSearch, setEvidenceSearch] = useState("")
  const [documentSearch, setDocumentSearch] = useState("")
  const [entitySearch, setEntitySearch] = useState("")

  const evidenceQuery = useQuery({
    queryKey: ["evidence", caseId, "finding-link-picker"],
    queryFn: () => evidenceAPI.list(caseId),
    enabled: !previewLimit,
  })

  const entityQuery = useQuery({
    queryKey: ["workspace", caseId, "finding-entity-search", entitySearch.trim()],
    queryFn: () => graphAPI.search(entitySearch.trim(), caseId, 30),
    enabled: !previewLimit && entitySearch.trim().length > 0,
  })

  const evidenceFiles = evidenceQuery.data ?? []
  const entityResults = entityQuery.data?.nodes ?? []

  const visibleFindings = useMemo(
    () => (previewLimit ? findings.slice(0, previewLimit) : findings),
    [findings, previewLimit],
  )

  const resetEditor = () => {
    setEditorOpen(false)
    setEditingId(null)
    setTitle("")
    setContent("")
    setPriority("MEDIUM")
    setSelectedEvidenceIds([])
    setSelectedDocumentIds([])
    setSelectedEntityKeys([])
    setEvidenceSearch("")
    setDocumentSearch("")
    setEntitySearch("")
  }

  const openEditor = (finding?: Finding) => {
    if (finding) {
      setEditingId(finding.id)
      setTitle(finding.title)
      setContent(finding.content ?? "")
      setPriority(finding.priority ?? "MEDIUM")
      setSelectedEvidenceIds(finding.linked_evidence_ids ?? [])
      setSelectedDocumentIds(finding.linked_document_ids ?? [])
      setSelectedEntityKeys(finding.linked_entity_keys ?? [])
    } else {
      resetEditor()
      setEditorOpen(true)
      return
    }
    setEditorOpen(true)
  }

  const handleSave = () => {
    const payload = {
      title: title.trim(),
      content: content.trim() || undefined,
      priority,
      linked_evidence_ids: selectedEvidenceIds,
      linked_document_ids: selectedDocumentIds,
      linked_entity_keys: selectedEntityKeys,
    }
    if (!payload.title) return

    if (editingId) {
      updateFinding.mutate(
        { findingId: editingId, updates: payload },
        {
          onSuccess: resetEditor,
          onError: (error) =>
            toast.error(error instanceof Error ? error.message : "Could not update finding"),
        },
      )
      return
    }

    createFinding.mutate(payload, {
      onSuccess: resetEditor,
      onError: (error) =>
        toast.error(error instanceof Error ? error.message : "Could not create finding"),
    })
  }

  const moveFinding = (index: number, direction: -1 | 1) => {
    const targetIndex = index + direction
    if (targetIndex < 0 || targetIndex >= findings.length) return

    const ordered = findings.map((finding) => finding.id)
    const [moved] = ordered.splice(index, 1)
    ordered.splice(targetIndex, 0, moved)
    reorderFindings.mutate(ordered, {
      onError: (error) =>
        toast.error(error instanceof Error ? error.message : "Could not reorder findings"),
    })
  }

  const confirmRecycle = () => {
    if (!deleteTarget) return
    deleteFinding.mutate(deleteTarget.id, {
      onSuccess: () => {
        setDeleteTarget(null)
        toast.success("Finding moved to recycle bin")
      },
      onError: (error) =>
        toast.error(error instanceof Error ? error.message : "Could not recycle finding"),
    })
  }

  const isSaving = createFinding.isPending || updateFinding.isPending

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <AlertCircle className="size-4 text-rose-500" />
          <h2 className="text-sm font-semibold">Findings</h2>
          <Badge variant="slate" className="h-5 px-1.5 text-[10px]">
            {findings.length}
          </Badge>
        </div>
        {!previewLimit && (
          <Button variant="outline" size="sm" onClick={() => openEditor()}>
            <Plus className="mr-1 size-3" />
            New Finding
          </Button>
        )}
      </div>

      {editorOpen && !previewLimit && (
        <div className="space-y-3 rounded-lg border border-border p-4">
          <div className="grid gap-3 md:grid-cols-[1fr_160px]">
            <Input
              placeholder="Finding title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
            />
            <select
              value={priority}
              onChange={(event) => setPriority(event.target.value)}
              className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>
          </div>
          <Textarea
            rows={4}
            placeholder="What did you conclude, and why does it matter?"
            value={content}
            onChange={(event) => setContent(event.target.value)}
          />
          <div className="grid gap-3 lg:grid-cols-3">
            <FilePicker
              title="Evidence"
              icon={Database}
              files={evidenceFiles}
              selectedIds={selectedEvidenceIds}
              search={evidenceSearch}
              onSearchChange={setEvidenceSearch}
              onToggle={(id) => setSelectedEvidenceIds((current) => toggleValue(current, id))}
            />
            <FilePicker
              title="Documents"
              icon={FileText}
              files={evidenceFiles}
              selectedIds={selectedDocumentIds}
              search={documentSearch}
              onSearchChange={setDocumentSearch}
              onToggle={(id) => setSelectedDocumentIds((current) => toggleValue(current, id))}
            />
            <EntityPicker
              entities={entityResults}
              selectedKeys={selectedEntityKeys}
              search={entitySearch}
              isLoading={entityQuery.isFetching}
              onSearchChange={setEntitySearch}
              onToggle={(key) => setSelectedEntityKeys((current) => toggleValue(current, key))}
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={resetEditor} disabled={isSaving}>
              Cancel
            </Button>
            <Button size="sm" onClick={handleSave} disabled={!title.trim() || isSaving}>
              Save
            </Button>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="space-y-2">
          {[1, 2].map((index) => (
            <div key={index} className="h-20 animate-pulse rounded-lg bg-muted/30" />
          ))}
        </div>
      ) : visibleFindings.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border py-8 text-center text-xs text-muted-foreground">
          No findings yet.
        </div>
      ) : (
        <div className="space-y-3">
          {visibleFindings.map((finding, index) => {
            const priorityClass =
              PRIORITY_STYLES[(finding.priority ?? "MEDIUM").toUpperCase()] ??
              PRIORITY_STYLES.MEDIUM
            return (
              <div key={finding.id} className="rounded-lg border border-border p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-medium">{finding.title}</p>
                      <Badge variant="outline" className={`text-[10px] ${priorityClass}`}>
                        {finding.priority ?? "MEDIUM"}
                      </Badge>
                    </div>
                    {finding.content && (
                      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                        {finding.content}
                      </p>
                    )}
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
                      <LinkedSummary finding={finding} />
                      {finding.updated_at && <span>{formatWorkspaceDate(finding.updated_at)}</span>}
                    </div>
                    <LinkedFileList
                      title="Linked evidence"
                      icon={Database}
                      files={finding.linked_evidence}
                    />
                    <LinkedFileList
                      title="Linked documents"
                      icon={FileText}
                      files={finding.linked_documents}
                    />
                    {(finding.linked_entity_keys?.length ?? 0) > 0 && (
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {finding.linked_entity_keys?.map((key) => (
                          <Badge key={key} variant="outline" className="max-w-full">
                            <Orbit className="size-3" />
                            <span className="truncate">{key}</span>
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                  {!previewLimit && (
                    <div className="flex shrink-0 items-center gap-1">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => moveFinding(index, -1)}
                        disabled={index === 0 || reorderFindings.isPending}
                        aria-label={`Move ${finding.title} up`}
                      >
                        <ArrowUp className="size-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => moveFinding(index, 1)}
                        disabled={index === findings.length - 1 || reorderFindings.isPending}
                        aria-label={`Move ${finding.title} down`}
                      >
                        <ArrowDown className="size-3.5" />
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => openEditor(finding)}>
                        Edit
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => setDeleteTarget(finding)}
                        aria-label={`Recycle ${finding.title}`}
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      <Dialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Recycle finding?</DialogTitle>
            <DialogDescription>
              This removes the finding from the active workspace while preserving it in the case record.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteTarget(null)}
              disabled={deleteFinding.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={confirmRecycle}
              disabled={deleteFinding.isPending}
            >
              Recycle
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
