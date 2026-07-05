import { useCallback, useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useQueries, useQuery } from "@tanstack/react-query"
import { toast } from "sonner"
import {
  BookOpenText,
  Clock3,
  Edit3,
  FileText,
  Link2,
  Loader2,
  NotebookPen,
  Plus,
  Search,
  Sparkles,
  Trash2,
  X,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Textarea } from "@/components/ui/textarea"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/cn"
import { useEvidenceStore } from "@/features/evidence/evidence.store"
import { useEvidence } from "@/features/evidence/hooks/use-evidence"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { graphAPI } from "@/features/graph/api"
import { useGraphStore } from "@/stores/graph.store"
import { useUIStore } from "@/stores/ui.store"
import {
  useCreateNotebookNote,
  useDeleteNotebookNote,
  useNotebookNotes,
  useUpdateNotebookNote,
} from "../hooks/use-notebook"
import { useNotebookStore } from "../notebook.store"
import type { GraphNode, NodeDetail } from "@/types/graph.types"
import type {
  NotebookLink,
  NotebookLinkInput,
  NotebookNote,
  NotebookTargetType,
} from "../api"
import { notebookAuthorInitialsSource, notebookAuthorLabel } from "../lib/author-display"

interface NotebookPanelProps {
  caseId: string
}

interface DraftState {
  title: string
  body: string
  links: NotebookLinkInput[]
}

const EMPTY_DRAFT: DraftState = {
  title: "",
  body: "",
  links: [],
}

function formatDateTime(value?: string | null) {
  if (!value) return "Just now"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "Recently"
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

function initials(name?: string | null) {
  if (!name?.trim()) return "U"
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("")
}

function noteTitle(note: Pick<NotebookNote, "title" | "body">) {
  return note.title?.trim() || note.body.split(/\r?\n/).find(Boolean)?.slice(0, 80) || "Untitled note"
}

function linkKey(link: Pick<NotebookLinkInput, "target_type" | "target_id">) {
  return `${link.target_type}:${link.target_id}`
}

function linkLabel(link: Pick<NotebookLinkInput, "target_label" | "target_id">) {
  return link.target_label?.trim() || link.target_id
}

function linkIcon(type: NotebookTargetType) {
  if (type === "entity" || type === "timeline_event") {
    return <Link2 className="size-3 shrink-0" />
  }
  if (type === "agent_artifact") {
    return <Sparkles className="size-3 shrink-0" />
  }
  return <FileText className="size-3 shrink-0" />
}

function mergeLinks(existing: NotebookLinkInput[], incoming: NotebookLinkInput[]) {
  const merged = [...existing]
  const seen = new Set(existing.map(linkKey))
  for (const link of incoming) {
    if (!seen.has(linkKey(link))) {
      merged.push({ ...link, metadata: link.metadata ?? {} })
      seen.add(linkKey(link))
    }
  }
  return merged
}

function LinkChip({
  link,
  onOpen,
  onRemove,
  compact = false,
}: {
  link: NotebookLinkInput
  onOpen?: (link: NotebookLinkInput) => void
  onRemove?: (link: NotebookLinkInput) => void
  compact?: boolean
}) {
  const content = (
    <span
      className={cn(
        "inline-flex min-w-0 max-w-full items-center gap-1 rounded-full border border-border bg-muted/50 px-2 py-0.5 text-[10px] font-medium text-muted-foreground",
        onOpen && "cursor-pointer transition-colors hover:border-slate-400 hover:bg-muted hover:text-foreground",
        compact && "px-1.5"
      )}
      title={linkLabel(link)}
    >
      {linkIcon(link.target_type)}
      <span className="min-w-0 truncate">{linkLabel(link)}</span>
      {onRemove && (
        <button
          type="button"
          className="-mr-0.5 rounded-full p-0.5 text-muted-foreground hover:bg-background hover:text-foreground"
          onClick={(event) => {
            event.stopPropagation()
            onRemove(link)
          }}
          aria-label={`Remove ${linkLabel(link)}`}
        >
          <X className="size-2.5" />
        </button>
      )}
    </span>
  )

  if (!onOpen) return content

  return (
    <button type="button" className="min-w-0 max-w-full" onClick={() => onOpen(link)}>
      {content}
    </button>
  )
}

export function NotebookPanel({ caseId }: NotebookPanelProps) {
  const navigate = useNavigate()
  const selectedNodeSet = useGraphStore((s) => s.selectedNodeKeys)
  const selectNodes = useGraphStore((s) => s.selectNodes)
  const selectedFileSet = useEvidenceStore((s) => s.selectedFileIds)
  const detailFileId = useEvidenceStore((s) => s.detailFileId)
  const openEvidenceDetail = useEvidenceStore((s) => s.openDetail)
  const expandGraphPanelTo = useUIStore((s) => s.expandGraphPanelTo)
  const user = useAuthStore((s) => s.user)

  const activeNoteId = useNotebookStore((s) => s.activeNoteId)
  const clearActiveNote = useNotebookStore((s) => s.clearActiveNote)
  const draftIntentId = useNotebookStore((s) => s.draftIntentId)
  const draftLinks = useNotebookStore((s) => s.draftLinks)

  const [search, setSearch] = useState("")
  const [mineOnly, setMineOnly] = useState(false)
  const [composerOpen, setComposerOpen] = useState(false)
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null)
  const [draft, setDraft] = useState<DraftState>(EMPTY_DRAFT)
  const [entitySearch, setEntitySearch] = useState("")

  const selectedNodeKeys = useMemo(
    () => Array.from(selectedNodeSet).slice(0, 6),
    [selectedNodeSet]
  )
  const selectedFileIds = useMemo(() => {
    const ids = new Set(Array.from(selectedFileSet).slice(0, 6))
    if (detailFileId) ids.add(detailFileId)
    return Array.from(ids).slice(0, 6)
  }, [detailFileId, selectedFileSet])

  const noteParams = useMemo(
    () => ({ mine: mineOnly, q: search.trim() || undefined, limit: 100 }),
    [mineOnly, search]
  )
  const notesQuery = useNotebookNotes(caseId, noteParams)
  const notes = useMemo(() => notesQuery.data?.notes ?? [], [notesQuery.data?.notes])

  const createMutation = useCreateNotebookNote(caseId)
  const updateMutation = useUpdateNotebookNote(caseId)
  const deleteMutation = useDeleteNotebookNote(caseId)

  const selectedNodeQueries = useQueries({
    queries: selectedNodeKeys.map((key) => ({
      queryKey: ["graph", "node", key, caseId],
      queryFn: () => graphAPI.getNodeDetails(key, caseId),
      enabled: !!caseId && !!key,
      staleTime: 30_000,
    })),
  })

  const { data: evidenceFiles = [] } = useEvidence(caseId)
  const evidenceById = useMemo(
    () => new Map(evidenceFiles.map((file) => [file.id, file])),
    [evidenceFiles]
  )

  const contextLinks = useMemo(() => {
    const links: NotebookLinkInput[] = []
    selectedNodeKeys.forEach((key, index) => {
      const detail = selectedNodeQueries[index]?.data as NodeDetail | undefined
      links.push({
        target_type: "entity",
        target_id: key,
        target_label: detail?.label || key,
      })
    })
    selectedFileIds.forEach((id) => {
      const file = evidenceById.get(id)
      links.push({
        target_type: "evidence",
        target_id: id,
        target_label: file?.original_filename || id,
      })
    })
    return links
  }, [evidenceById, selectedFileIds, selectedNodeKeys, selectedNodeQueries])

  const entitySearchQuery = useQuery({
    queryKey: ["notebook", caseId, "entity-search", entitySearch],
    queryFn: () => graphAPI.search(entitySearch, caseId, 8),
    enabled: entitySearch.trim().length >= 2,
    staleTime: 15_000,
  })

  const openForEdit = useCallback((note: NotebookNote) => {
    setEditingNoteId(note.id)
    setDraft({
      title: note.title ?? "",
      body: note.body,
      links: note.links.map((link) => ({
        target_type: link.target_type,
        target_id: link.target_id,
        target_label: link.target_label,
        metadata: link.metadata ?? {},
      })),
    })
    setComposerOpen(true)
  }, [])

  const startNewNote = useCallback((links: NotebookLinkInput[] = []) => {
    clearActiveNote()
    setEditingNoteId(null)
    setDraft({ ...EMPTY_DRAFT, links })
    setComposerOpen(true)
  }, [clearActiveNote])

  useEffect(() => {
    if (draftIntentId > 0) {
      let cancelled = false
      queueMicrotask(() => {
        if (cancelled) return
        setEditingNoteId(null)
        setDraft({ ...EMPTY_DRAFT, links: draftLinks })
        setComposerOpen(true)
      })
      return () => {
        cancelled = true
      }
    }
  }, [draftIntentId, draftLinks])

  useEffect(() => {
    if (activeNoteId) {
      let cancelled = false
      queueMicrotask(() => {
        if (cancelled) return
        setMineOnly(false)
        setSearch("")
      })
      return () => {
        cancelled = true
      }
    }
  }, [activeNoteId])

  useEffect(() => {
    if (!activeNoteId) return
    const note = notes.find((item) => item.id === activeNoteId)
    if (note) {
      let cancelled = false
      queueMicrotask(() => {
        if (cancelled) return
        openForEdit(note)
      })
      return () => {
        cancelled = true
      }
    }
  }, [activeNoteId, notes, openForEdit])

  const addDraftLinks = (links: NotebookLinkInput[]) => {
    setDraft((current) => ({ ...current, links: mergeLinks(current.links, links) }))
  }

  const removeDraftLink = (link: NotebookLinkInput) => {
    setDraft((current) => ({
      ...current,
      links: current.links.filter((item) => linkKey(item) !== linkKey(link)),
    }))
  }

  const handleOpenLink = (link: NotebookLinkInput) => {
    if (link.target_type === "entity" || link.target_type === "timeline_event") {
      selectNodes([link.target_id])
      expandGraphPanelTo("detail")
      return
    }
    if (link.target_type === "evidence" || link.target_type === "document") {
      navigate(`/cases/${caseId}/evidence`)
      openEvidenceDetail(link.target_id)
    }
  }

  const handleSubmit = async () => {
    const body = draft.body.trim()
    if (!body) {
      toast.error("Add a note before saving")
      return
    }
    const payload = {
      title: draft.title.trim() || null,
      body,
      links: draft.links,
      tags: [],
    }

    try {
      if (editingNoteId) {
        await updateMutation.mutateAsync({ noteId: editingNoteId, input: payload })
        toast.success("Note updated")
      } else {
        await createMutation.mutateAsync(payload)
        toast.success("Note saved")
      }
      setComposerOpen(false)
      setEditingNoteId(null)
      setDraft(EMPTY_DRAFT)
      clearActiveNote()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not save note")
    }
  }

  const handleDelete = async (note: NotebookNote) => {
    if (!window.confirm(`Delete "${noteTitle(note)}"?`)) return
    try {
      await deleteMutation.mutateAsync(note.id)
      toast.success("Note deleted")
      if (editingNoteId === note.id) {
        setComposerOpen(false)
        setEditingNoteId(null)
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not delete note")
    }
  }

  const isSaving = createMutation.isPending || updateMutation.isPending

  return (
    <div className="flex h-full min-w-0 flex-col bg-card">
      <div className="border-b border-border px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <NotebookPen className="size-4 text-muted-foreground" />
              <h2 className="text-sm font-semibold text-foreground">Notebook</h2>
            </div>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Public case notes with linked evidence and entities.
            </p>
          </div>
          <Button size="sm" variant="secondary" onClick={() => startNewNote()}>
            <Plus className="size-3.5" />
            New
          </Button>
        </div>

        <div className="mt-3 flex items-center gap-2">
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search notes"
              className="h-8 pl-8 text-xs"
            />
          </div>
          <div className="flex shrink-0 rounded-md border border-border bg-muted/30 p-0.5">
            <button
              type="button"
              onClick={() => setMineOnly(false)}
              className={cn(
                "h-6 rounded px-2 text-[11px] font-medium transition-colors",
                !mineOnly ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
              )}
            >
              All
            </button>
            <button
              type="button"
              onClick={() => setMineOnly(true)}
              className={cn(
                "h-6 rounded px-2 text-[11px] font-medium transition-colors",
                mineOnly ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
              )}
            >
              Mine
            </button>
          </div>
        </div>
      </div>

      {composerOpen && (
        <div className="border-b border-border bg-muted/15 px-4 py-3">
          <div className="space-y-2.5">
            <Input
              value={draft.title}
              onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))}
              placeholder="Note title"
              className="h-8 bg-background text-sm font-medium"
            />
            <Textarea
              value={draft.body}
              onChange={(event) => setDraft((current) => ({ ...current, body: event.target.value }))}
              placeholder="Write the note..."
              className="min-h-28 resize-y bg-background text-sm leading-relaxed"
            />

            <div className="space-y-2 rounded-md border border-border bg-background p-2.5">
              <div className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                  <Link2 className="size-3.5" />
                  Linked items
                </span>
                {contextLinks.length > 0 && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-6 text-[11px]"
                    onClick={() => addDraftLinks(contextLinks)}
                  >
                    Attach selection
                    <Badge variant="slate" className="px-1 py-0 text-[9px]">
                      {contextLinks.length}
                    </Badge>
                  </Button>
                )}
              </div>

              {draft.links.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {draft.links.map((link) => (
                    <LinkChip
                      key={linkKey(link)}
                      link={link}
                      onOpen={handleOpenLink}
                      onRemove={removeDraftLink}
                    />
                  ))}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Link this note to the entities or files it explains.
                </p>
              )}

              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={entitySearch}
                  onChange={(event) => setEntitySearch(event.target.value)}
                  placeholder="Find an entity to link"
                  className="h-8 pl-8 text-xs"
                />
              </div>

              {entitySearch.trim().length >= 2 && (
                <div className="max-h-32 overflow-y-auto rounded-md border border-border bg-muted/20">
                  {entitySearchQuery.isLoading ? (
                    <div className="flex items-center gap-2 px-2 py-2 text-xs text-muted-foreground">
                      <Loader2 className="size-3.5 animate-spin" />
                      Searching
                    </div>
                  ) : entitySearchQuery.data?.nodes.length ? (
                    entitySearchQuery.data.nodes.map((node: GraphNode) => (
                      <button
                        key={node.key}
                        type="button"
                        className="flex w-full min-w-0 items-center justify-between gap-2 px-2 py-1.5 text-left text-xs hover:bg-background"
                        onClick={() => {
                          addDraftLinks([
                            {
                              target_type: "entity",
                              target_id: node.key,
                              target_label: node.label,
                            },
                          ])
                          setEntitySearch("")
                        }}
                      >
                        <span className="min-w-0 truncate font-medium">{node.label}</span>
                        <span className="shrink-0 text-[10px] text-muted-foreground">{node.type}</span>
                      </button>
                    ))
                  ) : (
                    <p className="px-2 py-2 text-xs text-muted-foreground">No matching entities</p>
                  )}
                </div>
              )}
            </div>

            <div className="flex items-center justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  setComposerOpen(false)
                  setEditingNoteId(null)
                  clearActiveNote()
                }}
              >
                Cancel
              </Button>
              <Button type="button" size="sm" onClick={handleSubmit} disabled={isSaving}>
                {isSaving && <Loader2 className="size-3.5 animate-spin" />}
                Save
              </Button>
            </div>
          </div>
        </div>
      )}

      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-2.5 p-3">
          {notesQuery.isLoading ? (
            <div className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Loading notes
            </div>
          ) : notes.length === 0 ? (
            <div className="flex min-h-64 flex-col items-center justify-center rounded-lg border border-dashed border-border px-6 text-center">
              <BookOpenText className="size-8 text-muted-foreground/50" />
              <p className="mt-3 text-sm font-medium text-foreground">
                No notes yet
              </p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                Capture leads, questions, interview updates, and links to the evidence behind them.
              </p>
              <Button className="mt-4" size="sm" variant="secondary" onClick={() => startNewNote(contextLinks)}>
                <Plus className="size-3.5" />
                Start a note
              </Button>
            </div>
          ) : (
            notes.map((note) => (
              <article
                key={note.id}
                className={cn(
                  "rounded-lg border border-border bg-background p-3 transition-colors hover:border-slate-300 dark:hover:border-slate-600",
                  editingNoteId === note.id && "border-slate-400 bg-muted/20 dark:border-slate-500"
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <button
                    type="button"
                    className="min-w-0 flex-1 text-left"
                    onClick={() => openForEdit(note)}
                  >
                    <h3 className="line-clamp-2 text-sm font-semibold leading-snug text-foreground">
                      {noteTitle(note)}
                    </h3>
                    <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                      {note.body}
                    </p>
                  </button>
                  <div className="flex shrink-0 items-center gap-0.5">
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-sm"
                          className="size-6"
                          onClick={() => openForEdit(note)}
                        >
                          <Edit3 className="size-3" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="left">Edit note</TooltipContent>
                    </Tooltip>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-sm"
                          className="size-6 text-muted-foreground hover:text-red-600"
                          onClick={() => handleDelete(note)}
                        >
                          <Trash2 className="size-3" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="left">Delete note</TooltipContent>
                    </Tooltip>
                  </div>
                </div>

                {note.links.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {note.links.slice(0, 6).map((link: NotebookLink) => (
                      <LinkChip
                        key={link.id}
                        link={link}
                        compact
                        onOpen={handleOpenLink}
                      />
                    ))}
                    {note.links.length > 6 && (
                      <Badge variant="slate" className="px-1.5 py-0 text-[10px]">
                        +{note.links.length - 6}
                      </Badge>
                    )}
                  </div>
                )}

                <div className="mt-2 flex min-w-0 items-center justify-between gap-2 text-[11px] text-muted-foreground">
                  <div className="flex min-w-0 items-center gap-1.5">
                    <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-muted text-[9px] font-semibold text-muted-foreground">
                      {initials(notebookAuthorInitialsSource(note, user))}
                    </span>
                    <span className="min-w-0 truncate">{notebookAuthorLabel(note, user)}</span>
                  </div>
                  <span className="flex shrink-0 items-center gap-1">
                    <Clock3 className="size-3" />
                    {formatDateTime(note.updated_at || note.created_at)}
                  </span>
                </div>
              </article>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  )
}
